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


_REPORTLAB_WRAPPED_IMAGE_JPEG_BYTES = _jpeg_bytes()


def _build_reportlab_wrapped_image_pdf(path: Path) -> None:
    """reportlab의 ``canvas.drawImage()``로 JPEG 1개를 삽입한 PDF.

    reportlab은 이미지 XObject를 ``/Filter [/ASCII85Decode /DCTDecode]``
    형태(전송 필터 + 완결코덱 필터 연쇄)로 감싸는 것이 관측된 기본 동작이다
    (이 파일 작성 중 직접 실측 확인 — 결코 인위적으로 지어낸 저수준 조작이
    아니라, 널리 쓰이는 PDF 생성 라이브러리의 기본 산출물임).

    원본 JPEG 바이트를 모듈 상수(``_REPORTLAB_WRAPPED_IMAGE_JPEG_BYTES``)로
    고정해, 07 재실행(2026-09-28) 시 DEF-INT-001 해소를 "열리기만 하면 됨"이
    아니라 "최종 BinData 바이트가 원본과 바이트 단위로 완전히 동일한가"까지
    검증할 수 있게 한다(unit-2-test.md TC-601과 동일한 엄격도).
    """
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 750, "Image test page")
    c.drawImage(
        ImageReader(io.BytesIO(_REPORTLAB_WRAPPED_IMAGE_JPEG_BYTES)),
        72,
        600,
        width=40,
        height=30,
    )
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


def test_reportlab_generated_jpeg_no_longer_corrupted_in_final_hwpx_DEF_INT_001_resolved(
    reportlab_wrapped_image_pdf: Path,
) -> None:
    """DEF-INT-001(High) — 07 재실행(2026-09-28), unit-2 3차 재작업 이후 Closed 확인.

    이력: 이전 07 실행(이 테스트의 이전 이름
    ``test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001``,
    git 이력 참고)이 unit-0~8을 monkeypatch 없이 실제 구현으로 엮어 돌린 결과,
    ``reportlab``(널리 쓰이는 PDF 생성 라이브러리)이 기본으로 만드는
    ``/Filter [/ASCII85Decode /DCTDecode]``(전송 필터 + 완결코덱 필터 연쇄)
    이미지가 unit-2(``image_extractor.py``)에서 마지막 필터만 보고 완결
    코덱으로 잘못 라벨링되어, ASCII85로 인코딩된 텍스트가 그대로 "jpeg"
    바이트인 것처럼 unit-7 -> unit-4를 거쳐 최종 ``.hwpx``의
    ``BinData/binN.jpg``에 손상된 채 임베딩되는 결함을 발견했다(DEF-INT-001,
    High). 규칙 F에 따라 05단계(unit-2)로 반려했다.

    수정: 05단계 3차 재작업(``docs/harness/units/unit-2-note.md`` §12)이
    ``_raw_bytes_and_format``를 필터 배열 **전체**를 해석하도록 고쳐, 완결
    코덱 앞에 선행 전송/압축 필터(ASCII85Decode 등, pypdf 표준 디코더로
    안전하게 해석 가능한 것에 한정)가 있으면 실제로 디코드해 원본 코덱
    바이트를 복원하고, 안전하게 해석할 수 없으면 ``image_format="unknown"``
    (기존 미지원 포맷 경로, unit-7이 이미 제외+경고로 처리)으로 명시적으로
    빠지도록 했다. 06단계가 신규 pytest 케이스(TC-601~607)와 뮤테이션
    검증(TC-610, 선행 필터 디코드 로직을 되돌리면 즉시 5건 FAIL로 잡힘)으로
    이 수정을 독립 재검증해 PASS 판정했다(``docs/harness/units/unit-2-test.md``
    §12).

    이 07 재실행은 그 수정이 monkeypatch 없는 실제 orchestrator ->
    unit-2 -> unit-7 -> unit-4 전체 파이프라인 경로에서도 실제로 유효한
    이미지를 만들어내는지, 이 테스트 자신의 assert를 뒤집어 직접 재확인한다
    (호출 프롬프트 지시대로 회귀가드 반전 작업 — 07이 코드를 직접 고치는
    것이 아니라 결함이 해소되었다는 사실을 증거로 고정하는 것).
    """
    out = FIXTURE_DIR / "reportlab_wrapped_image.hwpx"
    result = convert(
        reportlab_wrapped_image_pdf, out, ConversionOptions(overwrite_existing=True)
    )

    assert result.success is True
    assert result.errors == []
    # 수정 후에도 이 조합(다중 필터 연쇄, 완결 코덱으로 정상 복원됨) 자체는
    # 경고 대상이 아니다 — 원본이 손상 없이 그대로 보존되었으므로
    # ConversionWarning을 낼 이유가 없다(REQ-003 정상 충족).
    assert result.warnings == []
    assert result.stats.images_embedded == 1

    with zipfile.ZipFile(out) as zf:
        bin_entries = [n for n in zf.namelist() if n.startswith("BinData/")]
        assert len(bin_entries) == 1
        raw = zf.read(bin_entries[0])

    # 수정된(정상) 동작을 직접 명시적으로 확인한다: BinData에 들어간 바이트가
    # 이제 유효한 JPEG로 정상적으로 열린다(ASCII85 전송 필터가 실제로 벗겨져
    # 원본 JPEG 바이트가 그대로 보존됨). 이 assert가 다시 실패하면 DEF-INT-001
    # 유형의 회귀가 재발했다는 뜻이므로 즉시 05단계로 재반려해야 한다.
    is_valid_image = True
    try:
        Image.open(io.BytesIO(raw)).load()
    except Exception:
        is_valid_image = False

    assert is_valid_image is True, (
        "DEF-INT-001이 재발한 것으로 보입니다 — BinData의 이미지가 다시 "
        "유효하지 않습니다. 규칙 F에 따라 05단계(unit-2)로 재반려하고, "
        "이 assert를 다시 'is_valid_image is False'로 되돌리며 이 테스트/"
        "함수명/docstring을 '결함 재현' 방향으로 갱신해야 합니다."
    )

    # 07 재실행(2026-09-28) 강화 검증: "열리기만 하면 됨"보다 엄격하게,
    # 최종 BinData 바이트가 ASCII85 전송 필터를 실제로 벗겨낸 원본 JPEG와
    # 바이트 단위로 완전히 동일한지까지 확인한다(unit-2-test.md TC-601과
    # 동일한 엄격도를 통합 경로 — orchestrator->unit-2->unit-7->unit-4 —
    # 에서도 실측 재현).
    assert raw == _REPORTLAB_WRAPPED_IMAGE_JPEG_BYTES, (
        "BinData 바이트가 열리기는 하지만 원본 JPEG와 바이트 단위로 "
        "동일하지 않습니다 — 재인코딩 등 다른 경로로 REQ-003(원본 보존)이 "
        "훼손되었을 수 있습니다."
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
