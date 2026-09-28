"""``ImageBlockIR`` 목록 -> BinData id 할당 + HWPX 배치 프래그먼트 생성 (unit-7, REQ-003).

(선행 계약: `pdf_to_hwpx.pdf_reader.image_extractor.extract_image_blocks`(unit-2,
`docs/harness/units/unit-2-note.md` §9 "2차 재작업(DEC-028)" — 특히 ``image_format``이
낼 수 있는 값의 최신 정의), `pdf_to_hwpx.hwpx_kernel.schema.image_block_to_picture_fragment`
(unit-4, `docs/harness/units/unit-4-note.md` §2-2 — 이 함수는 "배치 프래그먼트만" 만들고
BinData 파트 저장은 unit-7 책임이라고 명시함).)

**이 모듈이 실제로 하는 일 (2가지, 지시문 그대로)**:
    1. 페이지(또는 문서) 안의 ``ImageBlockIR`` 각각에 BinData 파트용 고유 id를
       부여한다(``bin0``, ``bin1``, ... — 호출자가 여러 페이지에 걸쳐 유일성을
       유지하려면 ``start_index``를 이어서 넘겨야 한다, 아래 함수 docstring 참고).
    2. 그 id를 ``schema.image_block_to_picture_fragment(block, bin_data_id=id)``에
       넘겨 배치(위치/크기) 프래그먼트를 만든다.

**이 모듈이 하지 않는 일 (의도적, 공유 자원 이슈로 이관)**:
    ``block.raw_bytes``를 실제 HWPX zip의 BinData 파트에 써 넣고
    ``META-INF/manifest.xml``/``Contents/content.hpf``에 등록하는 것은
    ``hwpx_kernel/container.py``(unit-4 확정 파일 범위)의 기능이 필요한데,
    이 호출 시점까지 ``container.py``에는 그런 함수가 없다(직접 확인 완료 —
    ``add_section_xml``/``build_empty_container`` 두 개뿐). 05-unit-developer
    "병렬 호출 시 추가 규칙"에 따라 이 unit은 ``container.py``를 직접 확장하지
    않고, 대신 이 함수가 반환하는 ``EmbeddedImage.bin_data_id``/``raw_bytes``/
    ``image_format`` 3종을 오케스트레이터(unit-8) 또는 ``container.py`` 후속
    확장 담당자가 그대로 소비할 수 있는 형태로 넘긴다(제안 시그니처는
    ``docs/harness/units/unit-7-note.md`` "BinData 저장 공유 자원 이슈" 절 참고).

**CCITT/JBIG2 처리 방침(지시문이 요청한 판단, 근거 명시)**:
    unit-2-note.md §7-4-2가 경고한 대로, ``image_format in {"ccitt", "jbig2"}``인
    ``raw_bytes``는 그 자체로 완결된 "파일"이 아니라 너비/행수 등 PDF XObject
    딕셔너리 쪽 메타데이터 없이는 범용 뷰어/이미지 라이브러리가 독립적으로 열 수
    없는 원본 비트스트림이다(TIFF/PNG 헤더가 없음). 이 값을 그대로 HWPX BinData에
    넣으면 한글이 손상된 이미지로 표시하거나 아예 열지 못할 위험이 매우 크다.
    이번 unit은 이 두 포맷을 **지원 범위 밖으로 명시**하고, 해당 이미지를
    결과에서 제외한 뒤 ``ImageEmbedWarning``으로 그 사실을 알린다(조용히
    누락시키지 않음 — REQ-005 "미보존 요소 고지" 정신과 부합, 과설계 방지 차원의
    합리적 축소). 실제로 CCITT/JBIG2를 열 수 있는 표준 컨테이너(TIFF 등)로
    감싸려면 XObject의 ``/Columns``/``/Rows``/``/K`` 등 추가 메타데이터를
    ``ImageBlockIR``에 실어야 하는데, 이는 공유 계약(``ir.py``) 확장이 필요한
    별도 결정이라 이 unit이 임의로 지어내지 않는다(필요하면 unit-2/unit-8 재논의
    대상).

    같은 이유로, ``"jpeg"``/``"jp2"``/``"png"``/``"tiff"`` 4종(그 자체로 완결된
    표준 이미지 파일임이 보장됨 — jpeg/jp2/png는 unit-2가 원본 스트림 그대로 또는
    왕복검증을 거쳐 보장, tiff는 인라인 이미지 경로에서 pypdf/Pillow가 만든 완성된
    TIFF 파일)만 "임베딩 가능"으로 취급한다. 그 외 값(``"unknown"`` 포함, 향후
    unit-2가 새로운 미인식 필터를 만나 반환할 수 있는 값)도 완결된 파일임을
    보장할 수 없으므로 같은 방식(제외 + 경고)으로 처리한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from pdf_to_hwpx.hwpx_kernel.schema import image_block_to_picture_fragment
from pdf_to_hwpx.pdf_reader.ir import ImageBlockIR

# 그 자체로 완결된 표준 이미지 파일임이 보장되는 image_format만 BinData에
# 그대로 써 넣을 수 있다(모듈 docstring "CCITT/JBIG2 처리 방침" 참고).
SUPPORTED_IMAGE_FORMATS = frozenset({"jpeg", "jp2", "png", "tiff"})

# 완결된 파일이 아님이 명확히 알려진 포맷(원인을 구체적으로 알림).
_INCOMPLETE_BITSTREAM_FORMATS = frozenset({"ccitt", "jbig2"})

_BIN_DATA_ID_PREFIX = "bin"


@dataclass(frozen=True)
class EmbeddedImage:
    """BinData id가 부여되고 배치 프래그먼트까지 만들어진 이미지 1개.

    ``raw_bytes``/``image_format``은 실제 BinData 파트 저장(이 unit의 책임 밖,
    모듈 docstring 참고)을 담당할 후속 처리가 그대로 쓸 수 있도록 원본 그대로
    다시 실어 보낸다(``ImageBlockIR``을 다시 들추지 않아도 되게 하기 위함).
    """

    bin_data_id: str
    image_format: str
    raw_bytes: bytes
    fragment: etree._Element


@dataclass(frozen=True)
class ImageEmbedWarning:
    """REQ-005 "미보존 요소 고지" 정신에 따라, 조용히 제외된 이미지 1개를 알린다.

    ``code``는 unit-8/14가 정의할 ``ConversionWarning.code``(아직 코드로
    존재하지 않음 — 03 §4-1, unit-8/14 Not Started)에 그대로 매핑할 수 있도록
    문자열 상수로 뒀다. 이 데이터클래스 자체는 그 정식 타입이 아니라, 이
    unit이 파일 범위 밖(``core/``, unit-8)의 정식 타입에 의존하지 않고 자체
    계약만으로 완결되게 하기 위한 임시 표현이다(unit-8 통합 시 매핑 필요 —
    unit-7-note.md "공유 문서 갱신 요청" 참고).
    """

    code: str
    message: str
    image_index: int


def _bin_data_id(index: int) -> str:
    return f"{_BIN_DATA_ID_PREFIX}{index}"


def embed_image_blocks(
    blocks: list[ImageBlockIR],
    *,
    start_index: int = 0,
) -> tuple[list[EmbeddedImage], list[ImageEmbedWarning], int]:
    """``ImageBlockIR`` 목록에 BinData id를 부여하고 배치 프래그먼트를 만든다.

    Args:
        blocks: 한 페이지(또는 호출자가 정한 단위)의 이미지 목록. 순서대로
            처리하며, 이 함수는 ``blocks``를 읽기 전용으로만 사용한다.
        start_index: BinData id 번호 시작값. 여러 페이지를 순회하며 이
            함수를 반복 호출하는 오케스트레이터(unit-8)는 문서 전체에서
            id가 겹치지 않도록, 매 호출 후 반환되는 3번째 값(다음
            ``start_index``)을 다음 호출에 그대로 넘겨야 한다.

    Returns:
        ``(embedded, warnings, next_start_index)`` 튜플.
        - ``embedded``: 임베딩 가능한 이미지들의 ``EmbeddedImage`` 목록
          (``SUPPORTED_IMAGE_FORMATS``에 속하는 것만, 입력 순서 유지).
        - ``warnings``: 지원 범위 밖이라 제외된 이미지들의 ``ImageEmbedWarning``
          목록(``blocks`` 안에서의 원래 인덱스를 ``image_index``에 담음).
        - ``next_start_index``: 다음 호출에 넘길 시작 인덱스
          (``start_index + len(embedded)`` — 실제로 id가 소비된 개수만큼만
          증가, 건너뛴 이미지는 id를 소비하지 않는다).
    """
    embedded: list[EmbeddedImage] = []
    warnings: list[ImageEmbedWarning] = []
    counter = start_index

    for index, block in enumerate(blocks):
        if block.image_format not in SUPPORTED_IMAGE_FORMATS:
            warnings.append(_build_warning(block, index))
            continue

        bin_data_id = _bin_data_id(counter)
        counter += 1
        fragment = image_block_to_picture_fragment(block, bin_data_id=bin_data_id)
        embedded.append(
            EmbeddedImage(
                bin_data_id=bin_data_id,
                image_format=block.image_format,
                raw_bytes=block.raw_bytes,
                fragment=fragment,
            )
        )

    return embedded, warnings, counter


def _build_warning(block: ImageBlockIR, index: int) -> ImageEmbedWarning:
    if block.image_format in _INCOMPLETE_BITSTREAM_FORMATS:
        return ImageEmbedWarning(
            code="IMAGE_FORMAT_INCOMPLETE_BITSTREAM",
            message=(
                f"{block.image_format} 형식 이미지는 너비/행수 등 PDF 내부 메타데이터 "
                "없이는 독립적으로 열 수 있는 파일이 아니어서 이번 버전에서는 HWPX에 "
                "삽입하지 않고 건너뛰었습니다."
            ),
            image_index=index,
        )
    return ImageEmbedWarning(
        code="IMAGE_FORMAT_UNSUPPORTED",
        message=(
            f"인식할 수 없거나 지원하지 않는 이미지 형식({block.image_format!r})이라 "
            "HWPX에 삽입하지 않고 건너뛰었습니다."
        ),
        image_index=index,
    )
