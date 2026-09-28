"""unit-7 AC-1~AC-4 — `pdf_to_hwpx/hwpx_writer/image_embedder.py` 검증.

근거: docs/harness/units/unit-7-note.md §5 AC-1(1~4번)/AC-2(5~7번)/AC-3(8~9번)/
AC-4(10~11번).

**범위 제외(반드시 읽을 것, AC-5)**: 이 unit이 반환하는 `EmbeddedImage.raw_bytes`가
실제 `.hwpx` zip의 BinData 파트에 저장되는지(즉 한글에서 이미지가 실제로 보이는지)는
이 파일의 테스트 대상이 아니다. `hwpx_kernel/container.py`에 BinData 삽입 함수가
아직 없다(unit-4 확정 파일 범위, unit-7-note.md §6-1 "container.py 확장 필요" 참고
— 다른 트랙에서 별도로 진행 중). 그 확장이 완료되고 오케스트레이터(unit-8)가 통합한
이후에만 종단 간(end-to-end) 검증이 가능하다. 여기서는 "BinData id 할당 로직 +
배치 프래그먼트 생성 로직 + CCITT/JBIG2/미지원 포맷 제외 로직 + 체이닝"만 증명한다.
"""

from __future__ import annotations

import copy

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.hwpx_kernel.schema import (
    fragment_to_bytes,
    image_block_to_picture_fragment,
)
from pdf_to_hwpx.hwpx_writer.image_embedder import (
    SUPPORTED_IMAGE_FORMATS,
    EmbeddedImage,
    ImageEmbedWarning,
    embed_image_blocks,
)
from pdf_to_hwpx.pdf_reader.ir import ImageBlockIR


def qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def _make_block(image_format: str, raw_bytes: bytes = b"\x89PNG\r\n\x1a\nfake", bbox=(0.0, 0.0, 100.0, 200.0)) -> ImageBlockIR:
    return ImageBlockIR(bbox=bbox, raw_bytes=raw_bytes, image_format=image_format)


# ---------------------------------------------------------------------------
# 모듈 상수
# ---------------------------------------------------------------------------


def test_supported_image_formats_constant_matches_ac_scope():
    """AC-1/AC-2 근거: 지원 포맷은 정확히 이 4개이며, 그 외(ccitt/jbig2/unknown 등)는
    전부 제외 대상이어야 한다(unit-7-note.md §1-3)."""
    assert SUPPORTED_IMAGE_FORMATS == frozenset({"jpeg", "jp2", "png", "tiff"})


# ---------------------------------------------------------------------------
# AC-1: 기본 임베딩 (지원 포맷 4종 각각 + 혼합 목록)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("image_format", sorted(SUPPORTED_IMAGE_FORMATS))
def test_embed_single_supported_format_produces_embedded_image(image_format):
    """AC-1-1~4: jpeg/jp2/png/tiff 각각이 embedded에 포함되고, bin_data_id/
    raw_bytes/fragment가 계약대로 나온다."""
    raw = f"raw-bytes-for-{image_format}".encode()
    block = _make_block(image_format, raw_bytes=raw, bbox=(1.0, 2.0, 3.0, 4.0))

    embedded, warnings, next_start_index = embed_image_blocks([block])

    assert warnings == []
    assert len(embedded) == 1
    img = embedded[0]
    assert isinstance(img, EmbeddedImage)

    # AC-1-3: start_index(기본 0)부터 "bin{N}" 형태
    assert img.bin_data_id == "bin0"
    # AC-1-9: 실제로 id를 소비한 개수만큼만 next_start_index 증가
    assert next_start_index == 1

    # AC-1-2: raw_bytes는 바이트 단위로 완전히 동일(재인코딩 없음)
    assert img.raw_bytes == raw
    assert img.raw_bytes is block.raw_bytes or img.raw_bytes == block.raw_bytes

    assert img.image_format == image_format

    # AC-1-4: fragment는 schema.image_block_to_picture_fragment(block, bin_data_id=그 id)가
    # 반환한 것과 정확히 동일한 구조를 가진다.
    expected_fragment = image_block_to_picture_fragment(block, bin_data_id="bin0")
    assert etree.QName(img.fragment).localname == "pic"
    assert img.fragment.tag == expected_fragment.tag
    assert img.fragment.get("binDataIDRef") == "bin0"
    assert img.fragment.get("format") == image_format
    assert fragment_to_bytes(img.fragment) == fragment_to_bytes(expected_fragment)


def test_embed_multiple_supported_images_preserves_input_order_and_sequential_ids():
    """AC-1-1, AC-1-3: 여러 이미지가 입력 순서대로 embedded에 포함되고,
    bin_data_id가 순차적으로 부여된다."""
    blocks = [
        _make_block("jpeg", raw_bytes=b"AAA"),
        _make_block("png", raw_bytes=b"BBB"),
        _make_block("tiff", raw_bytes=b"CCC"),
        _make_block("jp2", raw_bytes=b"DDD"),
    ]
    embedded, warnings, next_start_index = embed_image_blocks(blocks)

    assert warnings == []
    assert [img.image_format for img in embedded] == ["jpeg", "png", "tiff", "jp2"]
    assert [img.raw_bytes for img in embedded] == [b"AAA", b"BBB", b"CCC", b"DDD"]
    assert [img.bin_data_id for img in embedded] == ["bin0", "bin1", "bin2", "bin3"]
    assert next_start_index == 4


def test_embed_respects_custom_start_index():
    block = _make_block("png")
    embedded, warnings, next_start_index = embed_image_blocks([block], start_index=5)
    assert embedded[0].bin_data_id == "bin5"
    assert next_start_index == 6


# ---------------------------------------------------------------------------
# AC-2: CCITT/JBIG2/미지원 포맷 제외 + 경고
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("image_format", ["ccitt", "jbig2"])
def test_incomplete_bitstream_formats_excluded_with_correct_warning_code(image_format):
    """AC-2-5: ccitt/jbig2는 embedded에서 제외되고
    IMAGE_FORMAT_INCOMPLETE_BITSTREAM 경고로 원래 인덱스와 함께 보고된다."""
    block = _make_block(image_format)
    embedded, warnings, next_start_index = embed_image_blocks([block])

    assert embedded == []
    assert len(warnings) == 1
    warning = warnings[0]
    assert isinstance(warning, ImageEmbedWarning)
    assert warning.code == "IMAGE_FORMAT_INCOMPLETE_BITSTREAM"
    assert warning.image_index == 0
    assert image_format in warning.message

    # AC-1-9(경고는 id를 소비하지 않음)의 대응
    assert next_start_index == 0


@pytest.mark.parametrize("image_format", ["unknown", "gif", "bmp", "", "CCITT", "PNG"])
def test_unsupported_or_unrecognized_formats_use_unsupported_code(image_format):
    """AC-2-6: unknown이거나 SUPPORTED_IMAGE_FORMATS에 없는 임의의 다른 문자열
    (대소문자가 다른 값 포함 — 화이트리스트는 대소문자 구분)은 IMAGE_FORMAT_UNSUPPORTED로
    분류되고, 5번(INCOMPLETE_BITSTREAM)과 코드가 구분된다."""
    block = _make_block(image_format)
    embedded, warnings, next_start_index = embed_image_blocks([block])

    assert embedded == []
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.code == "IMAGE_FORMAT_UNSUPPORTED"
    assert warning.image_index == 0
    assert next_start_index == 0


def test_warning_image_index_reflects_original_position_in_blocks_list():
    """AC-2-5/6: image_index는 embedded로 소비된 개수가 아니라 blocks 리스트
    안에서의 원래 인덱스여야 한다 — 경고 대상이 목록 중간에 섞여 있는 경우를 확인."""
    blocks = [
        _make_block("png"),  # index 0 -> embedded, bin0
        _make_block("ccitt"),  # index 1 -> warning
        _make_block("jbig2"),  # index 2 -> warning
        _make_block("jpeg"),  # index 3 -> embedded, bin1
        _make_block("unknown"),  # index 4 -> warning
    ]
    embedded, warnings, next_start_index = embed_image_blocks(blocks)

    assert [img.bin_data_id for img in embedded] == ["bin0", "bin1"]
    assert [img.image_format for img in embedded] == ["png", "jpeg"]
    # 경고 대상은 bin_data_id를 소비하지 않았으므로 next_start_index는 2(embedded 개수)
    assert next_start_index == 2

    assert [(w.code, w.image_index) for w in warnings] == [
        ("IMAGE_FORMAT_INCOMPLETE_BITSTREAM", 1),
        ("IMAGE_FORMAT_INCOMPLETE_BITSTREAM", 2),
        ("IMAGE_FORMAT_UNSUPPORTED", 4),
    ]


def test_ccitt_and_jbig2_warning_codes_are_distinguishable_from_unsupported():
    """AC-2-6 원문: "5번과 코드 구분 필수" — 두 코드 문자열이 실제로 다름을 명시적으로 확인."""
    ccitt_block = _make_block("ccitt")
    unknown_block = _make_block("unknown")
    _, warnings, _ = embed_image_blocks([ccitt_block, unknown_block])
    codes = [w.code for w in warnings]
    assert codes[0] != codes[1]
    assert set(codes) == {"IMAGE_FORMAT_INCOMPLETE_BITSTREAM", "IMAGE_FORMAT_UNSUPPORTED"}


def test_excluded_formats_do_not_raise_exceptions():
    """AC-2-7 (예외를 던지지 않음): ccitt/jbig2/unknown 모두 예외 없이 정상적으로
    목록에서 제외되고 경고만 남긴다."""
    blocks = [_make_block("ccitt"), _make_block("jbig2"), _make_block("unknown")]
    embedded, warnings, next_start_index = embed_image_blocks(blocks)  # 예외 없이 반환되어야 함
    assert embedded == []
    assert len(warnings) == 3
    assert next_start_index == 0


def test_exception_from_schema_layer_propagates_and_is_not_swallowed():
    """AC-2-7 후반부: 이 함수 자체가 예외를 던지는 유일한 경로는
    schema.image_block_to_picture_fragment 내부에서 예외가 발생하는 경우(예: bbox
    형식 이상)이며, 그 예외는 삼켜지지 않고 그대로 전파되어야 한다.

    bbox를 4-튜플이 아닌 3-튜플로 만들어 `x0, y0, x1, y1 = block.bbox` 언패킹이
    schema.py 내부에서 ValueError를 던지도록 강제한다(위험 케이스, 6단계 원칙상
    이 unit이 삼키지 않는다는 계약을 실제로 증명하기 위해 AC 범위를 넘어 확인).
    """
    malformed_block = ImageBlockIR(bbox=(0.0, 0.0, 10.0), raw_bytes=b"x", image_format="png")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        embed_image_blocks([malformed_block])


# ---------------------------------------------------------------------------
# AC-3: 다중 페이지 체이닝
# ---------------------------------------------------------------------------


def test_chaining_across_two_pages_does_not_collide_ids():
    """AC-3-8: 1차 호출의 next_start_index를 2차 호출의 start_index로 그대로
    넘기면, 두 페이지에서 임베딩된 bin_data_id가 서로 겹치지 않는다."""
    page1_blocks = [_make_block("png"), _make_block("jpeg")]
    page2_blocks = [_make_block("tiff"), _make_block("jp2")]

    embedded1, warnings1, next_index = embed_image_blocks(page1_blocks, start_index=0)
    assert warnings1 == []
    assert [img.bin_data_id for img in embedded1] == ["bin0", "bin1"]
    assert next_index == 2

    embedded2, warnings2, next_index2 = embed_image_blocks(page2_blocks, start_index=next_index)
    assert warnings2 == []
    assert [img.bin_data_id for img in embedded2] == ["bin2", "bin3"]
    assert next_index2 == 4

    all_ids = [img.bin_data_id for img in embedded1] + [img.bin_data_id for img in embedded2]
    assert len(all_ids) == len(set(all_ids))  # 겹치는 id 없음


def test_chaining_next_start_index_ignores_warned_images():
    """AC-3-9: next_start_index == start_index + len(embedded) — 경고 처리된
    이미지 수와 무관하게 오직 실제로 id를 소비한 개수만 반영한다."""
    blocks = [_make_block("png"), _make_block("ccitt"), _make_block("jbig2"), _make_block("unknown")]
    embedded, warnings, next_start_index = embed_image_blocks(blocks, start_index=10)
    assert len(embedded) == 1
    assert len(warnings) == 3
    assert next_start_index == 10 + len(embedded) == 11


def test_three_page_chaining_end_to_end():
    """AC-3 확장: 3페이지 연속 체이닝에서도 전체 문서 범위에서 id 유일성이 유지된다."""
    idx = 0
    all_ids: list[str] = []
    for page_blocks in (
        [_make_block("png"), _make_block("ccitt")],
        [_make_block("jpeg")],
        [_make_block("tiff"), _make_block("jp2"), _make_block("unknown")],
    ):
        embedded, _warnings, idx = embed_image_blocks(page_blocks, start_index=idx)
        all_ids.extend(img.bin_data_id for img in embedded)

    assert all_ids == ["bin0", "bin1", "bin2", "bin3"]
    assert idx == 4


# ---------------------------------------------------------------------------
# AC-4: 빈 입력 / 안정성(읽기 전용, 상태 비변경)
# ---------------------------------------------------------------------------


def test_empty_blocks_list_returns_empty_tuple_without_exception():
    """AC-4-10: 빈 목록은 예외 없이 ([], [], N)을 반환한다."""
    result = embed_image_blocks([], start_index=5)
    assert result == ([], [], 5)


def test_empty_blocks_list_default_start_index():
    """AC-4-10 경계: start_index 기본값(0)에서도 동일하게 동작한다."""
    assert embed_image_blocks([]) == ([], [], 0)


def test_function_does_not_mutate_input_blocks():
    """AC-4-11: 입력 blocks(및 그 안의 각 ImageBlockIR)를 읽기 전용으로만
    사용하며 어떤 상태도 변경하지 않는다."""
    block = _make_block("png", raw_bytes=b"original")
    blocks = [block]
    snapshot = copy.deepcopy(blocks)

    embed_image_blocks(blocks)

    assert blocks == snapshot
    assert blocks[0].raw_bytes == b"original"
    assert blocks[0].image_format == "png"


def test_repeated_calls_with_same_input_and_start_index_produce_equal_results():
    """AC-4-11: 같은 입력으로 여러 번 호출해도 각 호출의 embedded/warnings
    내용이 동일하다(bin_data_id 번호는 start_index에 의해서만 달라짐 — 이번
    케이스는 start_index가 같으므로 완전히 동일해야 한다)."""
    blocks = [_make_block("jpeg", raw_bytes=b"same"), _make_block("ccitt")]

    result1 = embed_image_blocks(blocks, start_index=3)
    result2 = embed_image_blocks(blocks, start_index=3)

    embedded1, warnings1, next1 = result1
    embedded2, warnings2, next2 = result2

    assert next1 == next2
    assert warnings1 == warnings2
    assert len(embedded1) == len(embedded2) == 1
    assert embedded1[0].bin_data_id == embedded2[0].bin_data_id
    assert embedded1[0].raw_bytes == embedded2[0].raw_bytes
    assert embedded1[0].image_format == embedded2[0].image_format
    assert fragment_to_bytes(embedded1[0].fragment) == fragment_to_bytes(embedded2[0].fragment)


def test_repeated_calls_with_different_start_index_only_bin_data_id_differs():
    """AC-4-11 원문: "bin_data_id 번호만 start_index에 의해 달라짐"을 명시적으로 검증."""
    block = _make_block("tiff", raw_bytes=b"stable")

    embedded_a, _, _ = embed_image_blocks([block], start_index=0)
    embedded_b, _, _ = embed_image_blocks([block], start_index=100)

    assert embedded_a[0].bin_data_id == "bin0"
    assert embedded_b[0].bin_data_id == "bin100"
    assert embedded_a[0].raw_bytes == embedded_b[0].raw_bytes == b"stable"
    assert embedded_a[0].image_format == embedded_b[0].image_format == "tiff"
