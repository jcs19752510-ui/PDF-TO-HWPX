"""unit-2 AC-1(2차 개정)~AC-6 -- `pdf_to_hwpx/pdf_reader/image_extractor.py` 검증.

근거:
  - docs/harness/units/unit-2-note.md §9-8 (AC-1 2차 개정, DEC-028 반영)
    §7-8 (AC-2~AC-6, 1차 재작업에서 변경 없음 확정)
  - docs/harness/decisions.md DEC-028 (FlateDecode류 원시 픽셀 샘플 ->
    무손실 PNG 합성 + 왕복검증)
  - 03-system-design.md §1-3(unit-2 행)/§2-1(pypdf 선정)/§3-1(ImageBlockIR)

이 파일은 06단계 2차 재검증(규칙 F) 호출의 산출물이다. 1차 재검증(FAIL,
DEF-001/DEF-002)과 05단계의 1차/2차 재작업을 거쳐, 이번에는 DEC-028이
확정한 "무손실 PNG 합성 + 왕복검증" 설계가 실제로 pytest로 증명되는지
독립적으로 재현한다(note의 자체 확인은 참고용이며 대체하지 않음).

PDF 픽스처는 unit-0/unit-1 테스트의 공유 파일을 건드리지 않기 위해 이 파일
전용의 별도 디렉터리(`.harness-tmp/pdf_fixtures_06_unit2_recheck2/`)를 이
파일 안에서 자체적으로 만든다.

reportlab은 이 프로젝트의 런타임/개발 의존성에 없어 설치하지 않았다. 대신
pypdf의 저수준 객체 API(`PdfWriter`+`pypdf.generic`)로 이미지 XObject/
콘텐츠 스트림을 직접 구성해 PDF를 즉석 생성한다(mock 없음, 실제 PDF 파싱
경로를 전부 통과시켜 검증).

**의도적으로 다루지 않은 것(과설계 방지, 근거 명시)**:
  - `/LZWDecode`: `_synthesize_lossless_png`는 FlateDecode와 동일한
    `xobj.get_data()` 경로(압축 해제는 전적으로 pypdf 표준 디코더 책임)를
    타므로, "압축 해제 이후" 로직(메타데이터 해석/PNG 합성/왕복검증)은
    필터 종류와 무관하게 동일한 코드 경로다. LZW 인코더를 직접 구현하는
    비용 대비, FlateDecode/무필터/RunLengthDecode 3종으로 이미 "압축 해제
    이후 공통 로직"이 충분히 검증된다고 판단해 LZW 전용 케이스는 추가하지
    않았다(pypdf 자신의 LZW 디코더 정확성은 pypdf의 책임 범위).
"""

from __future__ import annotations

import io
import tomllib
import zlib
from pathlib import Path
from typing import Iterator

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NullObject,
    NumberObject,
    StreamObject,
)

import pdf_to_hwpx.pdf_reader.image_extractor as image_extractor_module
from pdf_to_hwpx.pdf_reader.ir import ImageBlockIR
from pdf_to_hwpx.pdf_reader.loader import load_pdf
from pdf_to_hwpx.pdf_reader.image_extractor import (
    _detect_image_format,
    _PngRoundTripVerificationError,
    _UnsupportedRawImageEncodingError,
    extract_image_blocks,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / ".harness-tmp" / "pdf_fixtures_06_unit2_recheck2"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --------------------------------------------------------------------------
# 저수준 PDF 빌더 (mock 없음, pypdf.generic 객체를 직접 조립)
# --------------------------------------------------------------------------


def _make_jpeg_bytes(
    width: int, height: int, gradient: bool = False, color: tuple[int, int, int] = (0, 0, 0)
) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    if gradient:
        pixels = img.load()
        for x in range(width):
            for y in range(height):
                pixels[x, y] = (x * 4 % 256, y * 5 % 256, (x + y) % 256)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _runlength_encode(data: bytes) -> bytes:
    """PDF ``/RunLengthDecode`` 인코더(테스트 전용, 전부 리터럴 런으로만
    인코딩 -- 반복 압축은 쓰지 않음). ``pypdf.filters.RunLengthDecode.decode``
    로 원본과 완전히 왕복됨을 별도로 확인했다(이 파일 작성 시 직접 검증)."""
    out = bytearray()
    i = 0
    while i < len(data):
        chunk = data[i : i + 128]
        out.append(len(chunk) - 1)
        out.extend(chunk)
        i += len(chunk)
    out.append(128)  # EOD
    return bytes(out)


def _add_image_xobject(
    writer: PdfWriter,
    resources: DictionaryObject,
    name: str,
    data: bytes,
    width: int,
    height: int,
    pdf_filter: str | None,
    color_space=NameObject("/DeviceRGB"),
    bits_per_component: int = 8,
    decode: list[float] | None = None,
) -> None:
    """이미지 XObject를 만들어 리소스에 등록한다.

    ``pdf_filter=None``이면 ``/Filter`` 키 자체를 만들지 않는다(=PDF의
    "필터 없음" 원시 픽셀 케이스). ``color_space``는 ``NameObject``(내장
    이름) 또는 ``ArrayObject``(``/Indexed``/``/ICCBased`` 등)를 그대로
    받는다.
    """
    image_stream = StreamObject()
    image_stream.set_data(data)
    image_stream[NameObject("/Type")] = NameObject("/XObject")
    image_stream[NameObject("/Subtype")] = NameObject("/Image")
    image_stream[NameObject("/Width")] = NumberObject(width)
    image_stream[NameObject("/Height")] = NumberObject(height)
    image_stream[NameObject("/ColorSpace")] = color_space
    image_stream[NameObject("/BitsPerComponent")] = NumberObject(bits_per_component)
    if pdf_filter is not None:
        image_stream[NameObject("/Filter")] = NameObject(pdf_filter)
    if decode is not None:
        image_stream[NameObject("/Decode")] = ArrayObject([FloatObject(v) for v in decode])
    img_ref = writer._add_object(image_stream)
    if "/XObject" not in resources:
        resources[NameObject("/XObject")] = DictionaryObject()
    resources["/XObject"][NameObject(name)] = img_ref


def _set_content(writer: PdfWriter, page, content: str) -> None:
    content_stream = StreamObject()
    content_stream.set_data(content.encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content_stream)


def _ensure_resources(page) -> DictionaryObject:
    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()
    return page["/Resources"]


def _make_single_image_pdf(
    path: Path,
    data: bytes,
    width: int,
    height: int,
    pdf_filter: str | None,
    page_size: int = 200,
    color_space=NameObject("/DeviceRGB"),
    bits_per_component: int = 8,
    decode: list[float] | None = None,
    resources_extra: DictionaryObject | None = None,
) -> None:
    """단일 이미지가 페이지 전체에 그려지는 PDF를 만드는 공용 빌더."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=page_size, height=page_size)
    resources = _ensure_resources(page)
    if resources_extra is not None:
        for key, value in resources_extra.items():
            resources[NameObject(key)] = value
    _add_image_xobject(
        writer,
        resources,
        "/Im0",
        data,
        width,
        height,
        pdf_filter,
        color_space=color_space,
        bits_per_component=bits_per_component,
        decode=decode,
    )
    _set_content(writer, page, f"q {page_size} 0 0 {page_size} 0 0 cm /Im0 Do Q")
    with path.open("wb") as f:
        writer.write(f)


def _make_small_placement_jpeg_pdf(path: Path, jpeg_bytes: bytes, width: int, height: int) -> None:
    """페이지(300x150, 비정방형) 중 일부 작은 영역에만 이미지가 배치되는 PDF
    (AC-2: bbox가 배치 영역이 아니라 항상 페이지 전체 크기여야 함을 검증하기
    위해, 배치 영역과 페이지 크기를 의도적으로 다르게 만듦)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=150)
    resources = _ensure_resources(page)
    _add_image_xobject(writer, resources, "/Im0", jpeg_bytes, width, height, "/DCTDecode")
    _set_content(writer, page, "q 20 0 0 20 5 5 cm /Im0 Do Q")
    with path.open("wb") as f:
        writer.write(f)


def _make_undisplayed_image_pdf(path: Path, jpeg_bytes: bytes, width: int, height: int) -> None:
    """이미지가 Resources/XObject에는 선언되어 있지만 콘텐츠 스트림에서
    `/Im0 Do`로 그려지지 않는 PDF (AC-3)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    resources = _ensure_resources(page)
    _add_image_xobject(writer, resources, "/Im0", jpeg_bytes, width, height, "/DCTDecode")
    _set_content(writer, page, "q Q")  # /Im0 Do 없음 -- 그려지지 않음
    with path.open("wb") as f:
        writer.write(f)


def _make_two_images_pdf(path: Path, jpeg_a: bytes, jpeg_c: bytes) -> None:
    """서로 다른 두 이미지가 모두 그려지는 PDF (다중 이미지 카운트 검증)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    resources = _ensure_resources(page)
    _add_image_xobject(writer, resources, "/Im0", jpeg_a, 10, 10, "/DCTDecode")
    _add_image_xobject(writer, resources, "/Im1", jpeg_c, 15, 15, "/DCTDecode")
    _set_content(writer, page, "q 50 0 0 50 0 0 cm /Im0 Do Q q 50 0 0 50 100 100 cm /Im1 Do Q")
    with path.open("wb") as f:
        writer.write(f)


def _make_blank_page_pdf(path: Path) -> None:
    """이미지가 전혀 없는 빈 페이지 PDF (AC-4)."""
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as f:
        writer.write(f)


def _make_inline_image_pdf(path: Path) -> None:
    """BI/ID/EI 연산자로 그려지는 인라인 이미지 PDF (is_inline=True 경로)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    content = "q 10 0 0 10 0 0 cm BI /W 2 /H 2 /CS /G /BPC 8 /F /AHx ID FF00FF00> EI Q"
    _set_content(writer, page, content)
    with path.open("wb") as f:
        writer.write(f)


def _make_corrupted_dct_pdf(path: Path) -> None:
    """DCTDecode로 선언됐으나 실제로는 유효하지 않은 바이트 스트림 (위험
    입력 케이스, TC-021 갱신판)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    resources = _ensure_resources(page)
    garbage = b"not a real jpeg stream at all 1234567890"
    _add_image_xobject(writer, resources, "/Im0", garbage, 10, 10, "/DCTDecode")
    _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
    with path.open("wb") as f:
        writer.write(f)


@pytest.fixture(scope="module")
def pdf_fixtures() -> Iterator[dict]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    jpeg_small = _make_jpeg_bytes(40, 30)
    jpeg_gradient = _make_jpeg_bytes(64, 48, gradient=True)
    jpeg_a = _make_jpeg_bytes(10, 10, color=(0, 0, 0))
    jpeg_c = _make_jpeg_bytes(15, 15, color=(255, 255, 255))
    # 1차 재검증(unit-2-test.md v1)에서 DEF-002를 재현했던 정확히 동일한
    # 픽스처. 05단계 재작업(DCT/JPX/CCITT/JBIG2 경로를 Pillow 완전 우회)
    # 이후 이 픽스처가 실제로 해소되는지 재확인하는 회귀 케이스로 재사용한다.
    jpeg_def002 = _make_jpeg_bytes(10, 10, gradient=True, color=(0, 0, 0))

    paths: dict[str, Path] = {}

    p = FIXTURE_DIR / "single_jpeg.pdf"
    _make_single_image_pdf(p, jpeg_small, 40, 30, "/DCTDecode")
    paths["single_jpeg"] = p

    p = FIXTURE_DIR / "single_jpeg_gradient.pdf"
    _make_single_image_pdf(p, jpeg_gradient, 64, 48, "/DCTDecode")
    paths["single_jpeg_gradient"] = p

    p = FIXTURE_DIR / "small_placement_jpeg.pdf"
    _make_small_placement_jpeg_pdf(p, jpeg_small, 40, 30)
    paths["small_placement_jpeg"] = p

    p = FIXTURE_DIR / "undisplayed.pdf"
    _make_undisplayed_image_pdf(p, jpeg_small, 40, 30)
    paths["undisplayed"] = p

    p = FIXTURE_DIR / "two_images.pdf"
    _make_two_images_pdf(p, jpeg_a, jpeg_c)
    paths["two_images"] = p

    p = FIXTURE_DIR / "blank_page.pdf"
    _make_blank_page_pdf(p)
    paths["blank_page"] = p

    p = FIXTURE_DIR / "inline_image.pdf"
    _make_inline_image_pdf(p)
    paths["inline_image"] = p

    p = FIXTURE_DIR / "def002_jpeg.pdf"
    _make_single_image_pdf(p, jpeg_def002, 10, 10, "/DCTDecode")
    paths["def002_jpeg"] = p

    p = FIXTURE_DIR / "corrupted_image_stream.pdf"
    _make_corrupted_dct_pdf(p)
    paths["corrupted_image_stream"] = p

    extra = {
        "jpeg_small_bytes": jpeg_small,
        "jpeg_gradient_bytes": jpeg_gradient,
        "jpeg_a_bytes": jpeg_a,
        "jpeg_c_bytes": jpeg_c,
        "jpeg_def002_bytes": jpeg_def002,
    }

    yield {**paths, **extra}  # type: ignore[dict-item]

    for key, value in paths.items():
        if isinstance(value, Path) and value.exists():
            value.unlink()
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        pass


def _extract_single_block(pdf_path: Path) -> ImageBlockIR:
    doc = load_pdf(pdf_path)
    try:
        blocks = extract_image_blocks(doc.pypdf_reader.pages[0])
    finally:
        doc.close()
    assert len(blocks) == 1
    return blocks[0]


def _extract_blocks(pdf_path: Path) -> list[ImageBlockIR]:
    doc = load_pdf(pdf_path)
    try:
        return extract_image_blocks(doc.pypdf_reader.pages[0])
    finally:
        doc.close()


def _extract_single_block_expect_raise(pdf_path: Path, exc_type):
    doc = load_pdf(pdf_path)
    try:
        with pytest.raises(exc_type):
            extract_image_blocks(doc.pypdf_reader.pages[0])
    finally:
        doc.close()


# ==========================================================================
# AC-1-1/2 (REQ-003, 완결된 이미지 코덱): DCTDecode/JPXDecode/CCITTFaxDecode/
# JBIG2Decode는 raw_bytes가 원본 스트림과 "항상, 예외 없이" 바이트 동일
# ==========================================================================


def test_extract_image_blocks_returns_one_block_for_displayed_image(pdf_fixtures):
    doc = load_pdf(pdf_fixtures["single_jpeg"])
    try:
        blocks = extract_image_blocks(doc.pypdf_reader.pages[0])
    finally:
        doc.close()
    assert isinstance(blocks, list)
    assert len(blocks) == 1
    assert isinstance(blocks[0], ImageBlockIR)


def test_extract_image_blocks_raw_bytes_are_byte_identical_to_source_jpeg(pdf_fixtures):
    block = _extract_single_block(pdf_fixtures["single_jpeg"])
    assert block.raw_bytes == pdf_fixtures["jpeg_small_bytes"]
    assert block.image_format == "jpeg"


def test_extract_image_blocks_raw_bytes_byte_identical_for_complex_gradient_jpeg(pdf_fixtures):
    block = _extract_single_block(pdf_fixtures["single_jpeg_gradient"])
    assert block.raw_bytes == pdf_fixtures["jpeg_gradient_bytes"]


def test_dctdecode_jpeg_raw_bytes_no_longer_diverges_DEF002_resolved(pdf_fixtures):
    """[DEF-002 재검증] 1차 재검증(unit-2-test.md v1)에서 원본과 조용히
    달라졌던 바로 그 10x10 그라디언트 JPEG 픽스처가, 05단계 재작업(DCT
    경로를 Pillow/필터디코더 완전 우회 -- `xobj._data` 그대로 반환) 이후
    실제로 바이트 단위 완전 동일해지는지 재현 확인한다."""
    block = _extract_single_block(pdf_fixtures["def002_jpeg"])
    original = pdf_fixtures["jpeg_def002_bytes"]
    assert block.raw_bytes == original, "DEF-002가 재발함 -- 05단계 재작업이 해소하지 못함"
    assert len(block.raw_bytes) == len(original)


def test_extract_image_blocks_multiple_displayed_images_all_counted(pdf_fixtures):
    blocks = _extract_blocks(pdf_fixtures["two_images"])
    assert len(blocks) == 2
    assert all(b.image_format == "jpeg" for b in blocks)
    raw_sets = {b.raw_bytes for b in blocks}
    assert pdf_fixtures["jpeg_a_bytes"] in raw_sets
    assert pdf_fixtures["jpeg_c_bytes"] in raw_sets


@pytest.mark.parametrize(
    "pdf_filter, expected_format",
    [
        ("/DCTDecode", "jpeg"),
        ("/JPXDecode", "jp2"),
        ("/CCITTFaxDecode", "ccitt"),
        ("/JBIG2Decode", "jbig2"),
    ],
)
def test_self_contained_codec_filters_pass_through_bytes_unconditionally(pdf_filter, expected_format):
    """AC-1-2: DCT/JPX/CCITT/JBIG2 4종 전부, 실제로 유효한 코덱 데이터인지와
    "무관하게"(=이 함수가 필터를 전혀 해석/디코드하지 않으므로) raw_bytes가
    선언된 원본 스트림과 항상 바이트 단위로 동일해야 한다. 1차 06단계 결과서는
    JPX/CCITT/JBIG2를 개별 재현하지 않았다고 명시적으로 밝힌 리스크였는데
    (unit-2-test.md §8), 이번 2차 재검증에서 4종 모두를 파라미터화해 보강한다.

    임의(비유효) 바이트를 사용하는 이유: 이 경로는 코덱 유효성을 검증하지
    않고 그대로 반환하는 것이 REQ-003의 핵심 취지이므로, 오히려 "유효하지
    않은 바이트도 그대로 통과한다"는 것 자체가 검증 대상이다."""
    arbitrary_bytes = f"not a real {expected_format} codec stream, arbitrary bytes 0123456789".encode()
    path = FIXTURE_DIR / f"self_contained_{expected_format}.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, arbitrary_bytes, 5, 5, pdf_filter)
        block = _extract_single_block(path)
        assert block.raw_bytes == arbitrary_bytes
        assert block.image_format == expected_format
    finally:
        if path.exists():
            path.unlink()


def test_unrecognized_filter_falls_back_to_unknown_format_and_raw_bytes():
    """`_SELF_CONTAINED_CODEC_FILTER_TO_FORMAT`/`_RAW_SAMPLE_FILTER_TO_FORMAT`
    어디에도 없는 필터 이름을 만나면, 추측하지 않고 원본 바이트를 그대로
    반환하며 `image_format="unknown"`으로 표기해야 한다(안전한 기본값)."""
    arbitrary_bytes = b"arbitrary bytes for unrecognized filter"
    path = FIXTURE_DIR / "unrecognized_filter.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, arbitrary_bytes, 5, 5, "/SomeMadeUpFilter")
        block = _extract_single_block(path)
        assert block.raw_bytes == arbitrary_bytes
        assert block.image_format == "unknown"
    finally:
        if path.exists():
            path.unlink()


def test_filter_array_last_entry_determines_format_dctdecode_case():
    """`/Filter`가 배열([/ASCII85Decode /DCTDecode] 같은 드문 연쇄 필터)일
    때, 배열의 **마지막** 항목만으로 image_format을 결정하는 분기(내부
    `_raw_bytes_and_format`의 ArrayObject 처리)를 화이트박스로 커버한다.
    raw_bytes는 여전히 가공 없는 원본 스트림 그대로(전송용 필터가 벗겨지지
    않은 상태일 수 있음, 모듈 docstring "알려진 한계" 참고 -- 이 테스트는
    "완전한 이미지 파일"을 만드는 것이 아니라 필터 배열 처리 분기 자체를
    검증하는 것이 목적이다)."""
    arbitrary_bytes = b"stream bytes, still ASCII85-wrapped in this rare case"
    path = FIXTURE_DIR / "filter_array_ascii85_dct.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)
        image_stream = StreamObject()
        image_stream.set_data(arbitrary_bytes)
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        image_stream[NameObject("/Width")] = NumberObject(5)
        image_stream[NameObject("/Height")] = NumberObject(5)
        image_stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = ArrayObject(
            [NameObject("/ASCII85Decode"), NameObject("/DCTDecode")]
        )
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        block = _extract_single_block(path)
        assert block.image_format == "jpeg"
        assert block.raw_bytes == arbitrary_bytes
    finally:
        if path.exists():
            path.unlink()


def test_null_filter_object_propagates_pypdf_internal_error_known_limitation():
    """[발견한 잔여 리스크, 낮은 심각도, AC 범위 밖 -- 5단계 반려 대상 아님]
    `/Filter` 값이 실제 PDF `null` 키워드(`NullObject`)로 명시된 경우 --
    `/Filter` 키가 아예 없는 경우(9-2절 "필터 없음")와는 구조적으로 다르다 --
    를 06단계가 처음 가정한 것과 달리 재확인했다.

    `_raw_bytes_and_format`은 이 경우를 "필터 없음"과 동일하게 분류해
    `_synthesize_lossless_png` 경로로 보내지만, 그 안에서 호출하는
    `xobj.get_data()`(pypdf 자신의 표준 디코더)는 `/Filter`가 `NullObject`인
    경우를 "필터 없음"으로 취급하지 않고 `NotImplementedError("Unsupported
    filter NullObject")`를 던진다(pypdf 6.19.0 `filters.py::decode_stream_data`
    직접 확인). 즉 우리 코드의 필터 분류 로직과 pypdf 표준 디코더의 실제 동작
    사이에 이 극히 희귀한 입력(`/Filter null` 명시)에 한해 불일치가 있다.

    이 테스트가 FAIL(=5단계 반려 결함)로 취급되지 않는 이유:
      1. AC-1(2차 개정)/9-2절 지원 범위 표 어디에도 "`/Filter`가 명시적
         `null`인 경우"는 다루지 않는다(9-2절은 "필터 없음"=키 부재만 명시).
      2. 모듈 docstring "Raises" 절은 "pypdf 내부에서 던지는 예외를 그대로
         전파한다"고만 약속하며, 이 경우 실제로 예외가 삼켜지지 않고 그대로
         전파된다(NotImplementedError) -- 계약 위반이 아니다.
      3. 실무에서 PDF 생성기가 `/Filter`에 명시적 `null`을 쓰는 사례는
         사실상 없다(필터가 없으면 키 자체를 생략하는 것이 표준적 관행).
    다만 unit-8(오케스트레이터) 착수 전 참고할 수 있도록 8절 "리스크 및 잔존
    이슈"에 낮은 심각도(Low)로 기록한다."""
    width, height = 2, 1
    raw_pixels = bytes([1, 2, 3, 4, 5, 6])

    path = FIXTURE_DIR / "null_filter.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)
        image_stream = StreamObject()
        image_stream.set_data(raw_pixels)
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        image_stream[NameObject("/Width")] = NumberObject(width)
        image_stream[NameObject("/Height")] = NumberObject(height)
        image_stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = NullObject()
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        # 예외가 삼켜지지 않고 그대로 전파되는지만 확인한다(구체적 예외
        # 타입까지는 이 unit이 보장하지 않음 -- 위 docstring 근거).
        _extract_single_block_expect_raise(path, Exception)
    finally:
        if path.exists():
            path.unlink()


def test_unrecognized_filter_with_missing_data_raises_pdfreaderror():
    """인식하지 못하는 필터 분기(그 외 필터)에서도 `_data`가 없는 비정상
    구조를 만나면 조용히 넘어가지 않고 `PdfReadError`를 던져야 한다(내부
    `_raw_bytes_and_format` 마지막 분기 커버)."""
    from pypdf.errors import PdfReadError

    from pdf_to_hwpx.pdf_reader.image_extractor import _raw_bytes_and_format

    fake_xobj = {"/Filter": "/SomeMadeUpFilter"}
    with pytest.raises(PdfReadError):
        _raw_bytes_and_format(fake_xobj, resources=None)


def test_non_image_subtype_xobject_is_skipped_form_xobject_ignored():
    """`/Resources/XObject`에 이미지가 아닌 Form XObject가 섞여 있어도
    무시되고(예외 없이), 실제 이미지만 추출되는지 확인(`_extract_resource_
    xobject_images`의 `/Subtype != /Image` 분기 커버)."""
    path = FIXTURE_DIR / "form_and_image_xobject.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)

        form_stream = StreamObject()
        form_stream.set_data(b"q Q")
        form_stream[NameObject("/Type")] = NameObject("/XObject")
        form_stream[NameObject("/Subtype")] = NameObject("/Form")
        form_ref = writer._add_object(form_stream)

        jpeg_bytes = _make_jpeg_bytes(5, 5)
        _add_image_xobject(writer, resources, "/Im0", jpeg_bytes, 5, 5, "/DCTDecode")
        resources["/XObject"][NameObject("/Fm0")] = form_ref

        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q /Fm0 Do")
        with path.open("wb") as f:
            writer.write(f)

        blocks = _extract_blocks(path)
        assert len(blocks) == 1
        assert blocks[0].raw_bytes == jpeg_bytes
    finally:
        if path.exists():
            path.unlink()


def test_page_without_resources_key_returns_empty_list():
    """`/Resources` 키 자체가 없는 페이지(구조적으로 드문 경우)에서도
    예외 없이 빈 목록을 반환해야 한다(`_extract_resource_xobject_images`의
    `resources is None` 분기 커버)."""
    path = FIXTURE_DIR / "no_resources_key.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        del page[NameObject("/Resources")]
        with path.open("wb") as f:
            writer.write(f)

        blocks = _extract_blocks(path)
        assert blocks == []
    finally:
        if path.exists():
            path.unlink()


# ==========================================================================
# AC-1-3 (원시 픽셀 샘플, DEC-028): FlateDecode/LZWDecode/RunLengthDecode/
# 필터 없음 -> 무손실 PNG 합성. 압축스트림/원시픽셀과의 직접 == 비교가 아니라
# "PNG 디코드 후 픽셀이 올바르게 해석됐는지"로 검증해야 한다(9-8-2 근거).
# ==========================================================================


def test_flate_raster_image_synthesizes_lossless_png_matching_original_pixels(pdf_fixtures):
    """DEF-001 재검증(갱신판): FlateDecode 원시 픽셀(DeviceRGB, 8bpc) ->
    `image_format=="png"`, PNG 시그니처로 시작, 그리고 PNG를 디코드한 픽셀이
    원본 원시 픽셀 샘플과 완전히 동일해야 한다. (원본 압축 스트림 또는
    압축 해제 픽셀과 raw_bytes를 직접 `==` 비교하는 것은 이제 AC 위반이
    아니라 애초에 논리적으로 성립할 수 없는 요구라 더 이상 그렇게 검증하지
    않는다 -- unit-2-note.md §9-8-2/§9-8-7 근거.)"""
    width, height = 4, 3
    raw_pixels = bytes([i % 256 for i in range(width * height * 3)])
    compressed = zlib.compress(raw_pixels)

    path = FIXTURE_DIR / "flate_rgb8.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, compressed, width, height, "/FlateDecode")
        block = _extract_single_block(path)

        assert block.image_format == "png"
        assert block.raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        # 압축 스트림/압축해제 픽셀과 raw_bytes를 직접 비교하지 않는다(위 docstring 근거).
        assert block.raw_bytes != compressed
        assert block.raw_bytes != raw_pixels

        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "RGB"
        assert decoded.size == (width, height)
        assert decoded.tobytes() == raw_pixels, (
            "PNG로 합성된 픽셀이 원본 원시 픽셀 샘플과 다름 -- DEC-028 무손실 요건 위반"
        )
    finally:
        if path.exists():
            path.unlink()


def test_no_filter_raster_image_synthesizes_lossless_png(pdf_fixtures):
    """필터가 전혀 없는(원시 그대로) 이미지도 동일하게 PNG로 합성되고
    픽셀이 보존되는지 확인."""
    width, height = 3, 2
    raw_pixels = bytes([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180])
    assert len(raw_pixels) == width * height * 3

    path = FIXTURE_DIR / "no_filter_rgb8.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, raw_pixels, width, height, None)
        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.tobytes() == raw_pixels
    finally:
        if path.exists():
            path.unlink()


def test_runlength_encoded_raster_image_synthesizes_lossless_png():
    """RunLengthDecode로 인코딩된 원시 픽셀도 동일한 합성 경로를 타는지
    확인(필터 종류에 무관하게 압축 해제 이후 로직은 공통, 모듈 docstring
    "의도적으로 다루지 않은 것" 근거 참고)."""
    width, height = 2, 2
    raw_pixels = bytes([0, 0, 0, 255, 255, 255, 128, 128, 128, 64, 64, 64])
    encoded = _runlength_encode(raw_pixels)

    path = FIXTURE_DIR / "runlength_rgb8.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, encoded, width, height, "/RunLengthDecode")
        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.tobytes() == raw_pixels
    finally:
        if path.exists():
            path.unlink()


def test_flate_gray_1bpc_with_inverted_decode_array_applies_inversion_correctly():
    """FlateDecode, DeviceGray, 1bpc, `/Decode [1 0]`(전체반전) -- 픽셀
    단위(getpixel)로 반전이 실제로 반영됐는지 확인(9-7-1/9-2절 근거)."""
    width, height = 2, 1
    # 원본 비트: 픽셀0=0(검정), 픽셀1=1(흰색) -- MSB부터, 나머지는 패딩 0
    raw_bits = bytes([0b01000000])
    compressed = zlib.compress(raw_bits)

    path = FIXTURE_DIR / "flate_gray1_inverted.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceGray"),
            bits_per_component=1,
            decode=[1, 0],
        )
        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        # Decode [1 0] 반전 없이 그대로였다면 (0, 255)였을 것 -- 반전되어 (255, 0)이어야 한다.
        assert decoded.getpixel((0, 0)) == 255
        assert decoded.getpixel((1, 0)) == 0
    finally:
        if path.exists():
            path.unlink()


def test_flate_gray_8bpc_with_explicit_identity_decode_array_is_accepted():
    """`/Decode [0 1]`(항등, 기본값과 동일한 값을 명시적으로 선언한 경우)도
    정상 처리되는지 확인(내부 `_maybe_apply_inverted_decode`의 "명시적
    항등" 분기 커버 -- `decode=None`과는 다른 코드 경로)."""
    width, height = 2, 1
    raw_pixels = bytes([10, 200])
    compressed = zlib.compress(raw_pixels)

    path = FIXTURE_DIR / "flate_gray8_explicit_identity_decode.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceGray"),
            bits_per_component=8,
            decode=[0, 1],
        )
        block = _extract_single_block(path)
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.tobytes() == raw_pixels
    finally:
        if path.exists():
            path.unlink()


def test_flate_indexed_4bpc_palette_preserved_after_png_synthesis():
    """FlateDecode, `/Indexed [/DeviceRGB hival lookup]`, 4bpc -- 인덱스 값과
    팔레트(RGB)가 왕복 후에도 완전히 보존되는지 확인(9-3절 근거)."""
    palette_rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])  # 3개 팔레트 엔트리(hival=2)
    width, height = 2, 1
    # 픽셀0=index0, 픽셀1=index2 -- 4bpc 팩킹: 상위니블=0, 하위니블=2
    raw_indices = bytes([0x02])
    compressed = zlib.compress(raw_indices)

    color_space = ArrayObject(
        [
            NameObject("/Indexed"),
            NameObject("/DeviceRGB"),
            NumberObject(2),
            ByteStringObject(palette_rgb),
        ]
    )

    path = FIXTURE_DIR / "flate_indexed4.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=color_space,
            bits_per_component=4,
        )
        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "P"
        assert decoded.getpixel((0, 0)) == 0
        assert decoded.getpixel((1, 0)) == 2
        palette = decoded.getpalette()
        assert tuple(palette[0:3]) == (255, 0, 0)
        assert tuple(palette[6:9]) == (0, 0, 255)
    finally:
        if path.exists():
            path.unlink()


def test_flate_indexed_with_explicit_default_decode_array_is_accepted():
    """인덱스 컬러 이미지에 `/Decode [0 2^BitsPerComponent-1]`(=기본값과
    동일한 값을 명시적으로 선언)이 붙어도 정상 처리되어야 한다(내부
    `_maybe_apply_inverted_decode`의 "인덱스 컬러 + 명시적 기본값" 분기
    커버)."""
    palette_rgb = bytes([255, 0, 0, 0, 255, 0])  # hival=1
    width, height = 1, 1
    raw_indices = bytes([0x01])
    compressed = zlib.compress(raw_indices)
    color_space = ArrayObject(
        [NameObject("/Indexed"), NameObject("/DeviceRGB"), NumberObject(1), ByteStringObject(palette_rgb)]
    )

    path = FIXTURE_DIR / "flate_indexed_explicit_default_decode.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=color_space,
            bits_per_component=8,
            # 인덱스 컬러의 기본 /Decode는 [0, 2^BitsPerComponent-1]이다(PDF
            # 스펙 그대로 -- /Hival이 아니라 BitsPerComponent 기준, 내부
            # `_maybe_apply_inverted_decode`의 `default_indexed` 계산과 일치).
            # 8bpc이므로 [0, 255]가 명시적 기본값이다.
            decode=[0, 255],
        )
        block = _extract_single_block(path)
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.getpixel((0, 0)) == 1
    finally:
        if path.exists():
            path.unlink()


def test_indexed_lookup_as_compressed_stream_object_is_resolved():
    """`/Indexed`의 lookup 테이블이 (문자열 리터럴이 아니라) 자체 필터를
    가진 별도 스트림 객체로 저장된 경우(9-3절 "팔레트가 스트림일 수도")도
    `get_data()`로 올바르게 해석되는지 확인(내부 `_resolve_indexed_layout`의
    "lookup이 스트림" 분기 커버)."""
    palette_rgb = bytes([10, 20, 30, 40, 50, 60])  # hival=1
    palette_compressed = zlib.compress(palette_rgb)

    width, height = 1, 1
    raw_indices = bytes([0x01])
    compressed = zlib.compress(raw_indices)

    path = FIXTURE_DIR / "indexed_lookup_stream.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)

        lookup_stream = StreamObject()
        lookup_stream.set_data(palette_compressed)
        lookup_stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        lookup_ref = writer._add_object(lookup_stream)

        color_space = ArrayObject(
            [NameObject("/Indexed"), NameObject("/DeviceRGB"), NumberObject(1), lookup_ref]
        )

        image_stream = StreamObject()
        image_stream.set_data(compressed)
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        image_stream[NameObject("/Width")] = NumberObject(width)
        image_stream[NameObject("/Height")] = NumberObject(height)
        image_stream[NameObject("/ColorSpace")] = color_space
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        block = _extract_single_block(path)
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        palette = decoded.getpalette()
        assert tuple(palette[3:6]) == (40, 50, 60)
    finally:
        if path.exists():
            path.unlink()


def test_named_colorspace_resource_indirect_reference_is_resolved():
    """`/ColorSpace /CS0`처럼 리소스 이름으로 간접 참조된 ColorSpace가
    `resources["/ColorSpace"]["/CS0"]`에서 올바르게 해석되는지 확인(9-2절
    "리소스 이름 간접참조" 근거)."""
    width, height = 2, 2
    raw_pixels = bytes([0, 64, 128, 255])  # DeviceGray 8bpc, 2x2
    compressed = zlib.compress(raw_pixels)

    colorspace_resource = DictionaryObject({NameObject("/CS0"): NameObject("/DeviceGray")})

    path = FIXTURE_DIR / "named_colorspace.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/CS0"),
            bits_per_component=8,
            resources_extra=DictionaryObject({NameObject("/ColorSpace"): colorspace_resource}),
        )
        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "L"
        assert decoded.tobytes() == raw_pixels
    finally:
        if path.exists():
            path.unlink()


def test_iccbased_colorspace_with_n3_is_treated_as_rgb():
    """`/ICCBased`(`/N`=3)가 DeviceRGB와 동등하게 취급되는지 확인(9-2절 근거)."""
    width, height = 2, 1
    raw_pixels = bytes([10, 20, 30, 40, 50, 60])
    compressed = zlib.compress(raw_pixels)

    path = FIXTURE_DIR / "iccbased_n3.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)

        icc_stream = StreamObject()
        icc_stream.set_data(b"")
        icc_stream[NameObject("/N")] = NumberObject(3)
        icc_ref = writer._add_object(icc_stream)
        colorspace_array = ArrayObject([NameObject("/ICCBased"), icc_ref])

        image_stream = StreamObject()
        image_stream.set_data(compressed)
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        image_stream[NameObject("/Width")] = NumberObject(width)
        image_stream[NameObject("/Height")] = NumberObject(height)
        image_stream[NameObject("/ColorSpace")] = colorspace_array
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        block = _extract_single_block(path)
        assert block.image_format == "png"
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "RGB"
        assert decoded.tobytes() == raw_pixels
    finally:
        if path.exists():
            path.unlink()


# ==========================================================================
# AC-1-3 계속: 지원 범위 밖 조합 -> _UnsupportedRawImageEncodingError
# (조용히 누락되지 않고 명시적으로 실패해야 함)
# ==========================================================================


def test_indexed_with_devicegray_base_palette_expanded_to_rgb():
    """`/Indexed`의 base가 `/DeviceGray`인 경우(9-2절 지원 범위), 팔레트의
    각 회색조 값(1바이트)이 RGB 삼중항(gray, gray, gray)으로 올바르게
    확장되는지 확인(`_convert_gray_or_rgb_palette_to_rgb`의 base_components
    == 1 분기 커버)."""
    gray_palette = bytes([0, 128, 255])  # hival=2, 그레이 팔레트 3개 엔트리
    width, height = 1, 1
    raw_indices = bytes([0x01])
    compressed = zlib.compress(raw_indices)
    color_space = ArrayObject(
        [NameObject("/Indexed"), NameObject("/DeviceGray"), NumberObject(2), ByteStringObject(gray_palette)]
    )

    path = FIXTURE_DIR / "indexed_devicegray_base.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path, compressed, width, height, "/FlateDecode", color_space=color_space, bits_per_component=8
        )
        block = _extract_single_block(path)
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "P"
        assert decoded.getpixel((0, 0)) == 1
        palette = decoded.getpalette()
        assert tuple(palette[3:6]) == (128, 128, 128)
    finally:
        if path.exists():
            path.unlink()


def test_devicecmyk_raw_raster_image_raises_unsupported_error():
    """DeviceCMYK 원시 픽셀(FlateDecode)은 PNG가 CMYK을 표현할 수 없어
    명시적으로 실패해야 한다(9-2절 근거, 조용히 RGB로 근사 변환하지 않음)."""
    width, height = 2, 1
    raw_pixels = bytes([0, 0, 0, 255] * (width * height))
    compressed = zlib.compress(raw_pixels)

    path = FIXTURE_DIR / "devicecmyk_raw.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceCMYK"),
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_with_devicecmyk_base_raises_unsupported_error():
    """`/Indexed`의 base가 DeviceCMYK인 경우도 동일하게 명시적으로 실패해야
    한다(9-2절 "DeviceCMYK은 직접이든 Indexed의 base든 미지원")."""
    palette_cmyk = bytes([0, 0, 0, 255, 0, 0, 0, 0])  # 2개 엔트리, 4채널
    width, height = 1, 1
    raw_indices = bytes([0x00])
    compressed = zlib.compress(raw_indices)
    color_space = ArrayObject(
        [
            NameObject("/Indexed"),
            NameObject("/DeviceCMYK"),
            NumberObject(1),
            ByteStringObject(palette_cmyk),
        ]
    )

    path = FIXTURE_DIR / "indexed_cmyk_base.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path, compressed, width, height, "/FlateDecode", color_space=color_space, bits_per_component=8
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_unsupported_bits_per_component_for_rgb_raises_unsupported_error():
    """RGB에서 8bpc 외(예: 16bpc)는 지원 범위 밖이라 명시적으로 실패해야
    한다(9-2절 근거)."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0, 0, 0, 0, 0, 0]))

    path = FIXTURE_DIR / "unsupported_bpc_rgb16.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceRGB"),
            bits_per_component=16,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_arbitrary_decode_array_raises_unsupported_error():
    """항등([0 1])도, 전체반전([1 0])도 아닌 임의의 `/Decode` 배열(예:
    `[0.2 0.8]`)은 지원 범위 밖이라 명시적으로 실패해야 한다(9-2절 근거)."""
    width, height = 2, 1
    raw_pixels = bytes([100, 200])
    compressed = zlib.compress(raw_pixels)

    path = FIXTURE_DIR / "arbitrary_decode.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceGray"),
            bits_per_component=8,
            decode=[0.2, 0.8],
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_with_custom_decode_raises_unsupported_error():
    """인덱스 컬러 이미지에 사용자정의 `/Decode`가 붙으면(기본값과 다르면)
    명시적으로 실패해야 한다(9-2절 근거, "인덱스 컬러의 사용자정의 Decode
    포함" 항목)."""
    palette_rgb = bytes([255, 0, 0, 0, 255, 0])
    width, height = 1, 1
    raw_indices = bytes([0x01])
    compressed = zlib.compress(raw_indices)
    color_space = ArrayObject(
        [NameObject("/Indexed"), NameObject("/DeviceRGB"), NumberObject(1), ByteStringObject(palette_rgb)]
    )

    path = FIXTURE_DIR / "indexed_custom_decode.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=color_space,
            bits_per_component=8,
            decode=[1, 0],  # 인덱스 컬러에서는 [0, maxval]만 기본값 -- [1,0]은 사용자정의로 취급됨
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_missing_colorspace_raises_unsupported_error():
    """`/ColorSpace` 자체가 없는 원시 픽셀 이미지는 추측 없이 명시적으로
    실패해야 한다."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0, 0, 0]))

    path = FIXTURE_DIR / "missing_colorspace.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)
        image_stream = StreamObject()
        image_stream.set_data(compressed)
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        image_stream[NameObject("/Width")] = NumberObject(width)
        image_stream[NameObject("/Height")] = NumberObject(height)
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_unresolvable_named_colorspace_raises_unsupported_error():
    """리소스 이름으로 참조된 ColorSpace가 `/Resources/ColorSpace`에도 없고
    내장 이름도 아니면 명시적으로 실패해야 한다(`_resolve_named_colorspace`
    최종 실패 분기 커버)."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0, 0, 0]))

    path = FIXTURE_DIR / "unresolvable_named_colorspace.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/CSNotDeclaredAnywhere"),
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_empty_array_colorspace_raises_unsupported_error():
    """`/ColorSpace`가 빈 배열(`[]`, 구조적으로 비정상)인 경우도 추측하지
    않고 명시적으로 실패해야 한다(`_base_colorspace_name`의 빈 배열 분기
    커버)."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0, 0, 0]))

    path = FIXTURE_DIR / "empty_array_colorspace.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=ArrayObject([]),
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_unsupported_colorspace_family_raises_unsupported_error():
    """`/Separation` 같이 DEC-028 지원 표(9-2절)에 아예 없는 ColorSpace
    계열은 추측하지 않고 명시적으로 실패해야 한다(`_base_colorspace_name`의
    "알 수 없는 head" 분기 커버)."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0]))
    color_space = ArrayObject(
        [NameObject("/Separation"), NameObject("/Spot1"), NameObject("/DeviceGray")]
    )

    path = FIXTURE_DIR / "unsupported_colorspace_family.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path, compressed, width, height, "/FlateDecode", color_space=color_space, bits_per_component=8
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_array_with_wrong_length_raises_unsupported_error():
    """`/Indexed` 배열이 표준 4개 항목([/Indexed base hival lookup])이 아닌
    경우(구조적으로 비정상) 명시적으로 실패해야 한다(`_resolve_indexed_
    layout`의 길이 검증 분기 커버)."""
    width, height = 1, 1
    compressed = zlib.compress(bytes([0]))
    malformed_color_space = ArrayObject([NameObject("/Indexed"), NameObject("/DeviceRGB")])  # 2개뿐

    path = FIXTURE_DIR / "indexed_wrong_length.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=malformed_color_space,
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_unsupported_bits_per_component_raises_unsupported_error():
    """인덱스 컬러에서 지원 범위(1/2/4/8bpc) 밖의 BitsPerComponent(예: 16)는
    명시적으로 실패해야 한다(`_resolve_indexed_layout`의 BPC 검증 분기
    커버)."""
    palette_rgb = bytes([255, 0, 0, 0, 255, 0])
    width, height = 1, 1
    compressed = zlib.compress(bytes([0, 0]))
    color_space = ArrayObject(
        [NameObject("/Indexed"), NameObject("/DeviceRGB"), NumberObject(1), ByteStringObject(palette_rgb)]
    )

    path = FIXTURE_DIR / "indexed_unsupported_bpc.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=color_space,
            bits_per_component=16,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_palette_lookup_shorter_than_hival_raises_unsupported_error():
    """`/Indexed` 팔레트 lookup 테이블 길이가 `/Hival`이 요구하는 최소
    길이보다 짧으면(구조적으로 비정상) 명시적으로 실패해야 한다
    (`_resolve_indexed_layout`의 lookup 길이 검증 분기 커버)."""
    too_short_palette = bytes([255, 0, 0])  # hival=2 -> 3개 엔트리(9바이트) 필요하지만 3바이트뿐
    width, height = 1, 1
    compressed = zlib.compress(bytes([0]))
    color_space = ArrayObject(
        [
            NameObject("/Indexed"),
            NameObject("/DeviceRGB"),
            NumberObject(2),
            ByteStringObject(too_short_palette),
        ]
    )

    path = FIXTURE_DIR / "indexed_palette_too_short.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=color_space,
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_indexed_base_colorspace_given_as_array_form_calrgb_is_recognized():
    """Indexed의 base ColorSpace가 배열 형태(`[/CalRGB <<...>>]`, PDF 스펙상
    유효한 표현)로 주어져도 head 이름만으로 인식되는지 확인(`_base_colorspace_
    name`의 "배열 head가 지원 목록에 있음" 분기 커버 -- `/ICCBased`가 아닌
    다른 배열형 ColorSpace 경로)."""
    palette_rgb = bytes([10, 20, 30, 40, 50, 60])  # hival=1
    width, height = 1, 1
    raw_indices = bytes([0x01])
    compressed = zlib.compress(raw_indices)
    base_as_array = ArrayObject([NameObject("/CalRGB"), DictionaryObject()])
    color_space = ArrayObject(
        [NameObject("/Indexed"), base_as_array, NumberObject(1), ByteStringObject(palette_rgb)]
    )

    path = FIXTURE_DIR / "indexed_calrgb_array_base.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path, compressed, width, height, "/FlateDecode", color_space=color_space, bits_per_component=8
        )
        block = _extract_single_block(path)
        decoded = Image.open(io.BytesIO(block.raw_bytes))
        decoded.load()
        assert decoded.mode == "P"
        palette = decoded.getpalette()
        assert tuple(palette[3:6]) == (40, 50, 60)
    finally:
        if path.exists():
            path.unlink()


def test_convert_palette_defensive_branch_rejects_unexpected_component_count():
    """`_convert_gray_or_rgb_palette_to_rgb`는 base_components가 1(Gray) 또는
    3(RGB)이 아니면 명시적으로 실패한다 -- 이 분기는 호출 경로
    (`_resolve_indexed_layout`)가 이미 CMYK(4)/None을 앞에서 걸러내므로 현재
    공개 API로는 도달할 수 없는 방어적 코드(dead code)다. 화이트박스로 직접
    호출해 이 방어 로직 자체가 실제로 존재하고 동작하는지만 확인한다(코드
    커버리지 갭이 아니라 "방어적 이중 검증"임을 증명)."""
    from pdf_to_hwpx.pdf_reader.image_extractor import _convert_gray_or_rgb_palette_to_rgb

    with pytest.raises(_UnsupportedRawImageEncodingError):
        _convert_gray_or_rgb_palette_to_rgb(bytes([0, 0]), base_components=2)


def test_missing_width_or_height_raises_unsupported_error():
    """`/Width` 또는 `/Height`가 없는 원시 픽셀 이미지는 추측 없이 명시적
    으로 실패해야 한다(`_synthesize_lossless_png` 진입 시점의 첫 검증
    분기 커버)."""
    path = FIXTURE_DIR / "missing_width_height.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        resources = _ensure_resources(page)
        image_stream = StreamObject()
        image_stream.set_data(zlib.compress(bytes([0, 0, 0])))
        image_stream[NameObject("/Type")] = NameObject("/XObject")
        image_stream[NameObject("/Subtype")] = NameObject("/Image")
        # /Width 의도적으로 생략
        image_stream[NameObject("/Height")] = NumberObject(1)
        image_stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
        image_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        image_stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        img_ref = writer._add_object(image_stream)
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): img_ref})
        _set_content(writer, page, "q 200 0 0 200 0 0 cm /Im0 Do Q")
        with path.open("wb") as f:
            writer.write(f)

        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


def test_pixel_data_length_mismatch_raises_unsupported_error():
    """압축 해제된 원시 픽셀 바이트 길이가 `/Width`x`/Height`x채널수와 맞지
    않으면(`Image.frombytes`가 `ValueError`를 던지는 상황) 원인 체인을
    보존한 채 `_UnsupportedRawImageEncodingError`로 변환돼야 한다(9-6절
    "ValueError를 잡아 더 명확한 메시지로 재변환" 분기 커버)."""
    width, height = 4, 4  # 4x4 RGB는 48바이트가 필요하지만 1바이트만 준다
    too_short = bytes([1])
    compressed = zlib.compress(too_short)

    path = FIXTURE_DIR / "pixel_length_mismatch.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(
            path,
            compressed,
            width,
            height,
            "/FlateDecode",
            color_space=NameObject("/DeviceRGB"),
            bits_per_component=8,
        )
        _extract_single_block_expect_raise(path, _UnsupportedRawImageEncodingError)
    finally:
        if path.exists():
            path.unlink()


# ==========================================================================
# AC-1-4 (DEC-028 필수 요건): 왕복검증이 실패하면 조용히 반환하지 않고
# _PngRoundTripVerificationError를 던져야 한다 (화이트박스, 강제 재현)
# ==========================================================================


def test_png_round_trip_failure_propagates_as_explicit_exception(monkeypatch, pdf_fixtures):
    """`_verify_png_round_trip_or_raise`를 몽키패치해 "왕복 검증에 실패한
    것처럼" 강제로 불일치를 재현한다 -- 정상 흐름에서는 발생하지 않는
    경로이므로 화이트박스로 직접 재현하는 것이 유일한 방법이다(9-7-2절과
    동일한 접근, 06단계가 독립적으로 재구성).

    이 테스트는 05단계 note의 "몽키패치로 확인했다"는 자체 보고를 06단계가
    그대로 신뢰하지 않고, 별도로 새로 작성한 몽키패치로 독립 재현한 것이다
    (지시문 3번 요구사항)."""

    def _always_fail(png_bytes, source_image):
        raise _PngRoundTripVerificationError("06단계 재검증용 강제 재현 -- 실제 불일치 아님")

    monkeypatch.setattr(image_extractor_module, "_verify_png_round_trip_or_raise", _always_fail)

    width, height = 2, 1
    raw_pixels = bytes([10, 20, 30, 40, 50, 60])
    compressed = zlib.compress(raw_pixels)
    path = FIXTURE_DIR / "roundtrip_forced_failure.pdf"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _make_single_image_pdf(path, compressed, width, height, "/FlateDecode")
        _extract_single_block_expect_raise(path, _PngRoundTripVerificationError)
    finally:
        if path.exists():
            path.unlink()


def test_png_round_trip_verification_actually_detects_pixel_mismatch():
    """위 테스트가 "몽키패치가 예외를 그대로 전파하는지"만 보여준다면, 이
    테스트는 "왕복검증 함수 자체가 실제로 픽셀 불일치를 탐지하는 로직을
    갖고 있는지"를 화이트박스로 직접 확인한다(더 강한 보증 -- 함수를 완전히
    대체하지 않고, PNG 합성 직후 픽셀을 실제로 훼손시켜 real 함수를 그대로
    호출한다)."""
    from pdf_to_hwpx.pdf_reader.image_extractor import _verify_png_round_trip_or_raise

    width, height = 2, 1
    raw_pixels = bytes([10, 20, 30, 40, 50, 60])
    source_image = Image.frombytes("RGB", (width, height), raw_pixels)

    tampered_image = Image.frombytes("RGB", (width, height), bytes([99, 99, 99, 40, 50, 60]))
    buf = io.BytesIO()
    tampered_image.save(buf, format="PNG")

    with pytest.raises(_PngRoundTripVerificationError):
        _verify_png_round_trip_or_raise(buf.getvalue(), source_image)

    # 반대로 동일한 픽셀이면 예외 없이 통과해야 한다(오탐 아님을 함께 확인).
    buf2 = io.BytesIO()
    source_image.save(buf2, format="PNG")
    _verify_png_round_trip_or_raise(buf2.getvalue(), source_image)  # 예외 없어야 함


def test_png_round_trip_verification_detects_size_mismatch():
    """왕복검증의 크기/모드 불일치 분기(픽셀 비교 이전 단계)를 직접
    재현한다."""
    from pdf_to_hwpx.pdf_reader.image_extractor import _verify_png_round_trip_or_raise

    source_image = Image.frombytes("RGB", (2, 1), bytes([1, 2, 3, 4, 5, 6]))
    differently_sized = Image.new("RGB", (3, 1), color=(0, 0, 0))
    buf = io.BytesIO()
    differently_sized.save(buf, format="PNG")

    with pytest.raises(_PngRoundTripVerificationError):
        _verify_png_round_trip_or_raise(buf.getvalue(), source_image)


def test_png_round_trip_verification_detects_palette_mismatch():
    """왕복검증의 인덱스 팔레트 불일치 분기를 직접 재현한다(9-4절, mode
    "P" 전용 검증 경로)."""
    from pdf_to_hwpx.pdf_reader.image_extractor import _verify_png_round_trip_or_raise

    source_image = Image.frombytes("P", (1, 1), bytes([0]))
    source_image.putpalette(bytes([255, 0, 0] + [0, 0, 0] * 255))

    tampered = Image.frombytes("P", (1, 1), bytes([0]))
    tampered.putpalette(bytes([0, 255, 0] + [0, 0, 0] * 255))  # 팔레트 색이 다름
    buf = io.BytesIO()
    tampered.save(buf, format="PNG")

    with pytest.raises(_PngRoundTripVerificationError):
        _verify_png_round_trip_or_raise(buf.getvalue(), source_image)


# ==========================================================================
# AC-1-5/6: image_format 값 집합, 인라인 이미지 경로(변경 없음)
# ==========================================================================


def test_inline_image_is_included_is_inline_branch(pdf_fixtures):
    """AC-1/AC-3의 포함 조건이 `is_inline or is_displayed`이므로, 인라인
    이미지(is_inline=True) 경로도 실제로 결과에 포함되는지 확인한다. 인라인
    경로는 변경 없이 여전히 pypdf/Pillow 경유(알려진 한계, 결함 아님)이므로
    바이트 동일성은 요구하지 않는다(9-8-6절)."""
    block = _extract_single_block(pdf_fixtures["inline_image"])
    assert block.bbox == (0.0, 0.0, 200.0, 200.0)


# ==========================================================================
# AC-2: bbox (알려진 근사치 -- 결함 아님, note §1-3/AC-2 근거, 변경 없음)
# ==========================================================================


def test_bbox_is_always_full_mediabox_regardless_of_actual_placement(pdf_fixtures):
    block = _extract_single_block(pdf_fixtures["small_placement_jpeg"])
    assert block.bbox == (0.0, 0.0, 300.0, 150.0)


def test_bbox_matches_non_square_mediabox_width_height_order(pdf_fixtures):
    block = _extract_single_block(pdf_fixtures["small_placement_jpeg"])
    x0, y0, x1, y1 = block.bbox
    assert (x0, y0) == (0.0, 0.0)
    assert x1 == pytest.approx(300.0)
    assert y1 == pytest.approx(150.0)


# ==========================================================================
# AC-3: 미표시 리소스 제외 (변경 없음)
# ==========================================================================


def test_undisplayed_resource_only_image_is_excluded(pdf_fixtures):
    blocks = _extract_blocks(pdf_fixtures["undisplayed"])
    assert blocks == []


# ==========================================================================
# AC-4: 빈 페이지 (변경 없음)
# ==========================================================================


def test_blank_page_with_no_images_returns_empty_list_without_exception(pdf_fixtures):
    blocks = _extract_blocks(pdf_fixtures["blank_page"])
    assert blocks == []


# ==========================================================================
# AC-5: 의존성 전제 조건 (Pillow, 변경 없음)
# ==========================================================================


def test_pillow_is_declared_in_pyproject_dependencies():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    assert any(dep.strip().lower().startswith("pillow") for dep in deps), (
        "pyproject.toml dependencies에 Pillow가 없음 -- AC-5 위반"
    )


def test_pillow_import_succeeds_in_test_environment():
    import PIL  # noqa: F401


# ==========================================================================
# AC-6: 안정성 / 범위 준수 (변경 없음)
# ==========================================================================


def test_extract_image_blocks_idempotent_multiple_calls(pdf_fixtures):
    doc = load_pdf(pdf_fixtures["two_images"])
    try:
        page = doc.pypdf_reader.pages[0]
        first = extract_image_blocks(page)
        second = extract_image_blocks(page)
    finally:
        doc.close()
    assert first == second
    assert first is not second


def test_image_extractor_only_imports_ir_and_does_not_redefine_shared_contracts():
    source = Path(image_extractor_module.__file__).read_text(encoding="utf-8")
    assert "from pdf_to_hwpx.pdf_reader.ir import ImageBlockIR" in source
    assert "class ImageBlockIR" not in source
    assert "class PdfDocument" not in source
    assert "class PageIR" not in source


def test_extract_image_blocks_signature_only_accepts_pypdf_page_param():
    import inspect

    sig = inspect.signature(extract_image_blocks)
    assert list(sig.parameters.keys()) == ["pypdf_page"]


# ==========================================================================
# 내부 헬퍼(_detect_image_format) 화이트박스 검증 -- 정상/경계/예외 확장자
# (인라인 이미지 경로 전용, 변경 없음)
# ==========================================================================


@pytest.mark.parametrize(
    "image_name, expected_format",
    [
        ("Im0.jpg", "jpeg"),
        ("Im0.jpeg", "jpeg"),
        ("Im0.JPG", "jpeg"),
        ("Im0.png", "png"),
        ("Im0.tif", "tiff"),
        ("Im0.tiff", "tiff"),
        ("Im0.jp2", "jp2"),
        ("Im0.bmp", "bmp"),
        ("Im0", "unknown"),
        ("", "unknown"),
    ],
)
def test_detect_image_format_normalizes_known_and_unknown_extensions(image_name, expected_format):
    assert _detect_image_format(image_name) == expected_format


# ==========================================================================
# 회귀(regression): 손상된 스트림 -- 기대치가 바뀐 항목 (TC-021 갱신판)
# ==========================================================================


def test_extract_image_blocks_no_longer_raises_for_corrupted_self_contained_stream(pdf_fixtures):
    """[기대치 갱신, 회귀 아님] 1차 재검증(unit-2-test.md v1) 시점에는 이
    케이스가 예외를 던지는 것이 기대치였다(당시 구현이 Pillow로 디코드를
    시도하다 우연히 실패했기 때문). 05단계 재작업 이후 DCT/JPX/CCITT/JBIG2
    경로는 필터를 전혀 해석하지 않고 원본 바이트를 그대로 반환하므로,
    "손상된" 스트림이라도 예외 없이 그대로 통과해야 하는 것이 REQ-003(재인코딩
    없이 그대로 추출) 취지와 정확히 일치하는 의도된 동작이다(unit-2-note.md
    §7-3 "행동 변화", §9-8-9 근거). 이 테스트를 "예외가 안 나서 결함"으로
    보고하지 않는다."""
    block = _extract_single_block(pdf_fixtures["corrupted_image_stream"])
    assert block.image_format == "jpeg"
    assert block.raw_bytes == b"not a real jpeg stream at all 1234567890"


# ==========================================================================
# 명시적 AC 범위는 아니지만 위험하다고 판단해 유지하는 케이스
# ==========================================================================


def test_extract_image_blocks_raises_for_structurally_broken_xobject_missing_data():
    """`_data` 속성 자체가 없는 비정상 스트림 구조를 만나면(예: XObject
    딕셔너리가 손상되어 pypdf가 완전한 StreamObject를 만들지 못한 경우와
    동등한 상황) `PdfReadError`가 발생해야 한다(9-6절, "삼키는 except가
    없다"는 주장의 화이트박스 검증). 실제 PDF로 이런 상태를 안전하게
    재현하기 어려워, `_raw_bytes_and_format`을 직접 호출하는 화이트박스
    방식으로 검증한다."""
    from pypdf.errors import PdfReadError

    from pdf_to_hwpx.pdf_reader.image_extractor import _raw_bytes_and_format

    fake_xobj = {"/Filter": "/DCTDecode"}
    # `_data` 속성이 없는 일반 dict를 넘겨 getattr(xobj, "_data", None)이
    # None이 되는 상황을 재현한다.
    with pytest.raises(PdfReadError):
        _raw_bytes_and_format(fake_xobj, resources=None)
