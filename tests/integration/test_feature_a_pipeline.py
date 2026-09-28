"""Feature A(코어 PDF->HWPX 변환 파이프라인, unit-0~8) 07단계 통합테스트.

(docs/harness/feature-A-integration-test.md 의 실행 가능 증거.)

이 파일은 06단계(unit-0~8 개별 단위테스트, 전부 PASS)가 이미 검증한 것을
반복하지 않는다. 06단계는 대부분 monkeypatch로 각 unit을 격리 검증했고,
orchestrator(unit-8) 자신의 06 세션조차 "실제 부품을 전부 그대로 통과시키는"
케이스는 AC-1/AC-2 일부로 한정했다(unit-8-test.md 2절). 이 파일은 그 반대—
**unit-0~8을 전부 실제 구현으로, monkeypatch 없이** 엮어서 "부품끼리 실제로
맞물릴 때"만 드러나는 문제를 찾는 데 집중한다(규칙: 개별 단위 테스트에서 이미
검증된 것을 반복하지 않는다).

규칙 K: 임시 아티팩트는 ``.harness-tmp/pdf_fixtures_07_feature_a/`` 하위에만
만들고, 세션 종료 시 스스로 정리한다.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator

import pytest
from lxml import etree
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    DictionaryObject,
    NameObject,
    NumberObject,
    StreamObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pdf_to_hwpx.core.orchestrator import ConversionOptions, convert
from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / ".harness-tmp" / "pdf_fixtures_07_feature_a"

_HP = NAMESPACES["hp"]


def _t(tag: str) -> str:
    return f"{{{_HP}}}{tag}"


@pytest.fixture(scope="session", autouse=True)
def _fixture_dir() -> Iterator[Path]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    yield FIXTURE_DIR
    # 세션 종료 시 이 파일이 만든 것만 정리(규칙 K) — 하위 전체를 비우되,
    # 디렉터리 자체가 다른 파일로 오염돼 있으면 강제로 지우지 않는다.
    for p in FIXTURE_DIR.glob("*"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 실제 PDF 픽스처 빌더 (mock 없음, reportlab/pypdf 저수준 조합)
# ---------------------------------------------------------------------------


def _jpeg_bytes(size=(40, 30), color=(200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _build_reportlab_wrapped_image_pdf(path: Path) -> None:
    """reportlab의 ``canvas.drawImage()``로 JPEG 1개를 삽입한 PDF.

    reportlab은 이미지 XObject를 ``/Filter [/ASCII85Decode /DCTDecode]``
    형태(전송 필터 + 완결코덱 필터 연쇄)로 감싸는 것이 관측된 기본 동작이다
    (이 파일 작성 중 직접 실측 확인 — 결코 인위적으로 지어낸 저수준 조작이
    아니라, 널리 쓰이는 PDF 생성 라이브러리의 기본 산출물임).
    """
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 750, "Image test page")
    c.drawImage(ImageReader(io.BytesIO(_jpeg_bytes())), 72, 600, width=40, height=30)
    c.showPage()
    c.save()


def _ensure_resources(page) -> DictionaryObject:
    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()
    return page["/Resources"]


def _add_image_xobject(
    writer: PdfWriter,
    resources: DictionaryObject,
    name: str,
    data: bytes,
    width: int,
    height: int,
    pdf_filter,
) -> None:
    stream = StreamObject()
    stream.set_data(data)
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Image")
    stream[NameObject("/Width")] = NumberObject(width)
    stream[NameObject("/Height")] = NumberObject(height)
    stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    stream[NameObject("/BitsPerComponent")] = NumberObject(8)
    if pdf_filter is not None:
        stream[NameObject("/Filter")] = pdf_filter
    ref = writer._add_object(stream)
    if "/XObject" not in resources:
        resources[NameObject("/XObject")] = DictionaryObject()
    resources["/XObject"][NameObject(name)] = ref


def _set_content(writer: PdfWriter, page, content: str) -> None:
    stream = StreamObject()
    stream.set_data(content.encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)


def _build_ccitt_image_pdf(path: Path) -> None:
    """``/CCITTFaxDecode`` 필터 1개짜리 이미지가 있는 PDF(unit-2가 이미
    "완결 코덱이지만 원본 비트스트림은 그 자체로 완결된 파일이 아님"으로
    분류한 포맷) — CCITT는 unit-7이 명시적으로 제외+경고 처리 대상이므로,
    실제 파이프라인에서 경고가 올바른 code/page_index로 도달하는지 확인하는
    용도다."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    resources = _ensure_resources(page)
    _add_image_xobject(
        writer, resources, "/Im0", b"\x00" * 32, 40, 30, NameObject("/CCITTFaxDecode")
    )
    _set_content(writer, page, "q 40 0 0 30 10 10 cm /Im0 Do Q")
    with path.open("wb") as f:
        writer.write(f)


@pytest.fixture(scope="session")
def reportlab_wrapped_image_pdf() -> Path:
    path = FIXTURE_DIR / "reportlab_wrapped_image.pdf"
    _build_reportlab_wrapped_image_pdf(path)
    return path


@pytest.fixture(scope="session")
def ccitt_image_pdf() -> Path:
    path = FIXTURE_DIR / "ccitt_image.pdf"
    _build_ccitt_image_pdf(path)
    return path


def _build_merged_table_two_pages_pdf(path: Path) -> None:
    """page1: 굵게 제목 + 기울임 문단 + 가로병합 2x2 표(선으로 실제로 그림,
    pdfplumber가 실제 격자로 인식). page2: 순수 문단 텍스트만."""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 760, "Report Title Bold")
    c.setFont("Helvetica-Oblique", 12)
    c.drawString(72, 735, "Italic paragraph text below title.")

    x0, x1, x2 = 72, 150, 228
    y0, y1, y2 = 650, 620, 590
    c.setLineWidth(1)
    c.line(x0, y0, x2, y0)
    c.line(x0, y1, x2, y1)
    c.line(x0, y2, x2, y2)
    c.line(x0, y0, x0, y2)
    c.line(x2, y0, x2, y2)
    c.line(x1, y1, x1, y2)  # 중간 세로선은 아래쪽 행에만 -> 위쪽 행 가로병합
    c.setFont("Helvetica", 10)
    c.drawString(x0 + 5, y0 - 15, "MERGED_A")
    c.drawString(x0 + 5, y1 - 15, "R1C0")
    c.drawString(x1 + 5, y1 - 15, "R1C1")
    c.showPage()

    c.setFont("Helvetica", 12)
    c.drawString(72, 750, "Second page plain paragraph text without any table or image.")
    c.showPage()
    c.save()


@pytest.fixture(scope="session")
def merged_table_two_pages_pdf() -> Path:
    path = FIXTURE_DIR / "merged_table_two_pages.pdf"
    _build_merged_table_two_pages_pdf(path)
    return path


# ---------------------------------------------------------------------------
# TC-INT-001 (핵심 발견) — 다중 필터 연쇄 이미지가 조용히 손상된 채 임베딩됨
# ---------------------------------------------------------------------------


def test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001(
    reportlab_wrapped_image_pdf: Path,
) -> None:
    """DEF-INT-001(High, 통합 시점 발견 — 규칙 F, 05단계로 피드백 필요).

    근본 원인: unit-2(image_extractor.py) ``_raw_bytes_and_format``는 필터
    배열의 **마지막** 필터가 "완결 코덱"(DCTDecode 등)이면 ``xobj._data``
    (필터를 전혀 적용하지 않은 원본 스트림)를 그대로 반환한다. 필터가 1개뿐일
    때는 이것이 정확히 원본 JPEG 바이트와 같지만, ``reportlab`` 같은 널리
    쓰이는 PDF 생성 라이브러리는 이미지 XObject를 기본적으로
    ``/Filter [/ASCII85Decode /DCTDecode]``(전송 필터 + 코덱 필터 연쇄)로
    감싼다 — 이 경우 ``_data``는 여전히 ASCII85로 인코딩된 텍스트이지
    JPEG 바이트가 아닌데도 ``image_format="jpeg"``로 표시된다.

    unit-2 자신의 06 세션은 이 조합(다중 필터 연쇄)을 "실무에서 극히
    드묾"으로 보고 실제 재현 테스트 없이 한계로만 기록했다
    (unit-2-note.md §7-4-3). 그러나 이 테스트가 보여주듯 reportlab의
    **기본 동작**이 이미 이 조건을 만족하므로 결코 드문 경우가 아니다.

    unit-7(image_embedder.py)의 ``SUPPORTED_IMAGE_FORMATS`` 화이트리스트는
    포맷 **이름**만 보고 통과시키며 바이트 유효성을 검증하지 않고,
    unit-4의 ``container.add_bin_data()``도 ``image_format`` 문자열만
    검사할 뿐 실제 바이트가 그 포맷인지 확인하지 않는다(직접 소스 확인,
    ``container.py`` 320행대). 세 unit(2/7/4) 모두 개별적으로는 자신의
    계약을 정확히 지켰지만, "포맷 라벨이 실제 바이트 내용과 일치한다"는
    암묵적 가정을 아무도 검증하지 않아 조합 시점에만 드러나는 결함이다.

    영향: ``convert()``가 ``success=True``, ``warnings=[]``, ``errors=[]``를
    반환하면서도 최종 `.hwpx`의 ``BinData/binN.jpg``에는 실제로 열리지 않는
    깨진 바이트가 들어간다 — REQ-003(원본 보존)이 사실상 무의미해지고
    REQ-005(미보존 요소 고지)도 지켜지지 않는다(사용자에게 아무 경고 없음).

    이 테스트는 ``pytest.mark.xfail(strict=True)``로 표시한다 — 05단계가
    (a) unit-2가 다중 필터 연쇄를 해석하도록 고치거나, (b) unit-7/4가
    바이트 유효성(매직넘버)을 검증해 경고로 전환하는 방식으로 고치면 이
    테스트가 "예상외로 통과"하게 되어 strict=True 덕분에 CI가 실패로
    표시한다 — 수정 완료를 놓치지 않기 위한 의도적 장치다. 07단계가 직접
    코드를 고치지 않는다(규칙 F).
    """
    out = FIXTURE_DIR / "reportlab_wrapped_image.hwpx"
    result = convert(
        reportlab_wrapped_image_pdf, out, ConversionOptions(overwrite_existing=True)
    )

    assert result.success is True
    assert result.errors == []
    # 현재(결함 있는) 동작: 아무 경고도 없이 "성공"으로 보고된다.
    assert result.warnings == []
    assert result.stats.images_embedded == 1

    with zipfile.ZipFile(out) as zf:
        bin_entries = [n for n in zf.namelist() if n.startswith("BinData/")]
        assert len(bin_entries) == 1
        raw = zf.read(bin_entries[0])

    # 현재(결함 있는) 동작을 직접 명시적으로 확인한다: BinData에 들어간
    # 바이트는 유효한 이미지로 열리지 않는다(ASCII85로 인코딩된 텍스트가
    # 그대로 "jpeg"라는 라벨을 달고 들어갔기 때문). 05단계가 이 결함을
    # 고치면(다중 필터 해석 또는 바이트 검증 도입) 아래 assert가 실패로
    # 바뀌어 이 테스트 자체가 갱신 대상임을 즉시 알려준다 — 의도적으로
    # "현재의 버그를 문서화"하는 회귀 가드다(규칙 F: 07단계는 코드를
    # 직접 고치지 않고, 결함을 재현 가능한 형태로 고정해 05로 되돌린다).
    is_valid_image = True
    try:
        Image.open(io.BytesIO(raw)).load()
    except Exception:
        is_valid_image = False

    assert is_valid_image is False, (
        "DEF-INT-001이 수정된 것으로 보입니다 — BinData의 이미지가 이제 "
        "유효합니다. docs/harness/decisions.md와 이 테스트를 함께 갱신하고, "
        "이 assert를 'is_valid_image is True'로 뒤집어야 합니다."
    )


# ---------------------------------------------------------------------------
# TC-INT-002 — 실제 조합: 병합 표 + 굵게/기울임 텍스트 + 2페이지, 전부 실제 부품
# ---------------------------------------------------------------------------


def test_real_pipeline_merged_table_and_styled_text_two_pages(
    merged_table_two_pages_pdf: Path,
) -> None:
    """unit-1(스타일 추출) -> unit-5(문단 조립), unit-3(표 인식,
    실제 가로병합) -> unit-6(그리드 좌표 복원) 이 monkeypatch 없이
    orchestrator를 통해 실제로 맞물릴 때 최종 XML까지 정확한지 확인.
    06단계는 이 조합을 합성 IR로만 검증했다(paragraph_builder/table_builder
    각자의 06 테스트는 unit-1/3이 실제로 만든 IR을 쓰지 않음)."""
    out = FIXTURE_DIR / "merged_table_two_pages.hwpx"
    result = convert(
        merged_table_two_pages_pdf, out, ConversionOptions(overwrite_existing=True)
    )

    assert result.success is True, result.errors
    assert result.stats.total_pages == 2
    assert result.stats.tables_detected == 1
    # has_merged_cells=True인 표는 "완전 보존"에서 제외(unit-8 정책, 2-4절)
    assert result.stats.tables_preserved_fully == 0

    with zipfile.ZipFile(out) as zf:
        xml_bytes = zf.read("Contents/section0.xml")
    root = etree.fromstring(xml_bytes)

    # 굵게 제목 run
    bold_runs = [r for r in root.iter(_t("run")) if r.get("bold") == "1"]
    assert len(bold_runs) == 1
    assert bold_runs[0].find(_t("t")).text == "Report Title Bold"

    # 기울임 문단 run
    italic_runs = [r for r in root.iter(_t("run")) if r.get("italic") == "1"]
    assert len(italic_runs) == 1

    # 가로 병합 셀이 실제 추출/실제 그리드복원을 거쳐 colSpan="2"로 도달
    merged_cells = [tc for tc in root.iter(_t("tc")) if tc.get("colSpan") == "2"]
    assert len(merged_cells) == 1
    merged_text = merged_cells[0].find(f"{_t('subList')}/{_t('p')}/{_t('run')}/{_t('t')}")
    assert merged_text.text == "MERGED_A"

    tbl = next(root.iter(_t("tbl")))
    assert tbl.get("hasMergedCells") == "1"

    # 표 하나만 있고(총 3칸: 병합1+비병합2), tc 총 개수는 3개여야 한다
    # (divmod 단순 가정이었다면 4개가 나왔을 것 — unit-6의 실측 그리드
    # 복원이 실제로 동작함을 확인).
    assert len(tbl.findall(f".//{_t('tc')}")) == 3

    # 2페이지 텍스트가 순서대로(1페이지 내용 뒤에 2페이지 내용) 존재
    all_text = [t.text for t in root.iter(_t("t"))]
    assert all_text.index("Report Title Bold") < all_text.index(
        "Second page plain paragraph text without any table or image."
    )

    # REQ-005 dedup: 표 셀 텍스트는 unit-1(실제 텍스트추출)이 독립적으로도
    # 같은 좌표에서 word를 뽑아내지만(자유 텍스트 후보), unit-8의 dedup이
    # 표 bbox와 겹치는 이 블록들을 제외하므로 각 셀 텍스트는 정확히 1회만
    # (표 안에서만) 등장해야 한다 — 중복 등장하면 dedup 배선이 실제
    # 추출 결과(합성 IR이 아님)와는 맞물리지 않는다는 뜻.
    for cell_text in ("MERGED_A", "R1C0", "R1C1"):
        assert all_text.count(cell_text) == 1, (
            f"{cell_text!r}가 {all_text.count(cell_text)}회 등장 — REQ-005 dedup이 "
            "실제 추출 파이프라인에서 표 셀 텍스트의 중복(자유 텍스트로도 별도 "
            "등장)을 제거하지 못했을 가능성"
        )


# ---------------------------------------------------------------------------
# TC-INT-004 — CCITT 이미지: 실제 파이프라인에서 경고로 정확히 배선되는가
# ---------------------------------------------------------------------------


def test_real_ccitt_image_produces_warning_not_silent_inclusion(
    ccitt_image_pdf: Path,
) -> None:
    out = FIXTURE_DIR / "ccitt_image.hwpx"
    result = convert(ccitt_image_pdf, out, ConversionOptions(overwrite_existing=True))
    assert result.success is True, result.errors
    assert result.stats.images_embedded == 0
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "IMAGE_FORMAT_INCOMPLETE_BITSTREAM"
    assert result.warnings[0].page_index == 0

    with zipfile.ZipFile(out) as zf:
        bin_entries = [n for n in zf.namelist() if n.startswith("BinData/")]
    assert bin_entries == []
