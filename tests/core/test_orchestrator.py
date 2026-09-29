"""단위테스트 — ``pdf_to_hwpx.core.orchestrator``(unit-8, REQ-005/REQ-009/REQ-010).

`docs/harness/units/unit-8-note.md` §8의 인수 조건(AC-1~AC-8, 26개 항목)을
1:1로 커버한다. 대응표는 `docs/harness/units/unit-8-test.md` 4절 참고.

테스트 전략(설계 근거):
    - AC-1(정상 변환)과 "real E2E"(4절 TC-810x)는 reportlab으로 실제 PDF를
      만들어 unit-0~7의 진짜 구현을 그대로 통과시킨다(모킹 없음) — 통합
      지점으로서 orchestrator가 실제로 부품들을 올바르게 엮는지 증명한다.
    - AC-2(dedup)/AC-3 일부/AC-5(경고)/AC-6(통계)는 `extract_text_blocks`/
      `extract_table_blocks`/`extract_image_blocks`를 monkeypatch로 대체해
      값을 직접 통제한다 — 이 값들은 이미 unit-1/2/3의 06 세션이 검증했으므로
      (traceability.md REQ-002/003/004 PASS) 여기서 다시 증명할 필요가 없고,
      orchestrator 자신의 배선(오류 매핑/dedup/통계 집계/벌크헤드)만 정밀하게
      격리해 검증하는 것이 이 unit의 책임 범위에 맞다. monkeypatch 대상은
      `pdf_to_hwpx.core.orchestrator` 모듈 네임스페이스에 바인딩된 이름이다
      (orchestrator.py가 `from ... import name` 형태로 가져왔으므로).
    - `_bbox_overlap_ratio`/`_exclude_text_overlapping_tables`/`_fragment_top_y`/
      `_order_page_fragments`는 private 헬퍼이지만 orchestrator.py 모듈에서
      직접 import 가능하며, 이 모듈의 핵심 판단 로직(2-1/2-2절)이므로 값
      경계(0.5 임계값 등)를 직접 검증한다.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Iterator

import pypdf
import pytest
from lxml import etree
from PIL import Image as PILImage
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from pdf_to_hwpx.common.exceptions import OutputPathError
from pdf_to_hwpx.common.logging_setup import LOGGER_NAME
from pdf_to_hwpx.core import orchestrator as orch
from pdf_to_hwpx.core.orchestrator import (
    ConversionOptions,
    ProgressEvent,
    _bbox_overlap_ratio,
    _exclude_text_overlapping_tables,
    _fragment_top_y,
    _order_page_fragments,
    convert,
)
from pdf_to_hwpx.hwpx_kernel import schema as hwpx_schema
from pdf_to_hwpx.pdf_reader.ir import (
    ImageBlockIR,
    TableBlockIR,
    TableCellIR,
    TextBlockIR,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / ".harness-tmp" / "pdf_fixtures_06_unit8"
NS = {
    "hs": hwpx_schema.NAMESPACES["hs"],
    "hp": hwpx_schema.NAMESPACES["hp"],
}


# ---------------------------------------------------------------------------
# PDF 생성 헬퍼 (reportlab/pypdf, .harness-tmp 전용 격리 디렉터리)
# ---------------------------------------------------------------------------


def _tiny_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (4, 4), color=(255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_blank_pages_pdf(path: Path, page_count: int) -> None:
    """monkeypatch 기반 테스트용 — 페이지 수만 맞으면 내용은 중요하지 않다."""
    c = rl_canvas.Canvas(str(path), pagesize=letter)
    for i in range(page_count):
        c.drawString(72, 750, f"page {i}")
        c.showPage()
    c.save()


def _make_text_pdf(path: Path, texts_per_page: list[list[str]]) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=letter)
    for page_texts in texts_per_page:
        y = 700
        for text in page_texts:
            c.drawString(72, y, text)
            y -= 30
        c.showPage()
    c.save()


def _make_table_text_image_pdf(path: Path) -> bytes:
    """1페이지(자유텍스트+표2x2+이미지) + 2페이지(순수텍스트) PDF.

    표 grid: x=[72,300], y=[400,500](reportlab 좌표, y 위로 증가),
    세로 분할선 x=186, 가로 분할선 y=450 -> pdfplumber 좌표계(top 아래로
    증가)에서 reportlab y=[450,500] 구간이 표의 "위쪽 행"(pdfplumber row0)이다.
    """
    jpeg_bytes = _tiny_jpeg_bytes()
    image_reader = ImageReader(io.BytesIO(jpeg_bytes))

    c = rl_canvas.Canvas(str(path), pagesize=letter)

    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "Hello World")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, 660, "Bold Text")
    c.setFont("Helvetica", 10)

    c.rect(72, 400, 228, 100)
    c.line(186, 400, 186, 500)
    c.line(72, 450, 300, 450)
    c.drawString(90, 470, "R0C0")
    c.drawString(200, 470, "R0C1")
    c.drawString(90, 420, "R1C0")
    c.drawString(200, 420, "R1C1")

    c.drawImage(image_reader, 400, 600, width=40, height=30)
    c.showPage()

    c.drawString(72, 700, "Second page plain text")
    c.showPage()
    c.save()
    return jpeg_bytes


def _make_encrypted_pdf(path: Path) -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="unit8-test-secret", owner_password="unit8-test-owner")
    with path.open("wb") as f:
        writer.write(f)


def _make_empty_pdf(path: Path) -> None:
    writer = pypdf.PdfWriter()
    with path.open("wb") as f:
        writer.write(f)


def _make_corrupted_pdf(path: Path) -> None:
    path.write_bytes(b"this is not a pdf file at all - unit-8 fixture" * 5)


@pytest.fixture(scope="session")
def fixtures() -> Iterator[dict[str, Path | bytes]]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    blank_1page = FIXTURE_DIR / "blank_1page.pdf"
    _make_blank_pages_pdf(blank_1page, 1)

    blank_2page = FIXTURE_DIR / "blank_2page.pdf"
    _make_blank_pages_pdf(blank_2page, 2)

    blank_3page = FIXTURE_DIR / "blank_3page.pdf"
    _make_blank_pages_pdf(blank_3page, 3)

    text_1page = FIXTURE_DIR / "text_1page.pdf"
    _make_text_pdf(text_1page, [["Hello unit-8"]])

    text_2page = FIXTURE_DIR / "text_2page.pdf"
    _make_text_pdf(text_2page, [["Page one text"], ["Page two text"]])

    combo = FIXTURE_DIR / "combo_table_text_image.pdf"
    jpeg_bytes = _make_table_text_image_pdf(combo)

    encrypted = FIXTURE_DIR / "encrypted.pdf"
    _make_encrypted_pdf(encrypted)

    empty0 = FIXTURE_DIR / "empty_0page.pdf"
    _make_empty_pdf(empty0)

    corrupted = FIXTURE_DIR / "corrupted.pdf"
    _make_corrupted_pdf(corrupted)

    paths: dict[str, Path | bytes] = {
        "blank_1page": blank_1page,
        "blank_2page": blank_2page,
        "blank_3page": blank_3page,
        "text_1page": text_1page,
        "text_2page": text_2page,
        "combo": combo,
        "combo_jpeg_bytes": jpeg_bytes,
        "encrypted": encrypted,
        "empty0": empty0,
        "corrupted": corrupted,
    }
    yield paths

    for value in paths.values():
        if isinstance(value, Path) and value.exists():
            value.unlink()
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        pass


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path


def _read_section_xml(hwpx_path: Path) -> bytes:
    with zipfile.ZipFile(hwpx_path) as zf:
        return zf.read("Contents/section0.xml")


def _all_free_text(root) -> list[str]:
    """``<hp:tc>`` 바깥(자유 문단)에 있는 ``<hp:t>`` 텍스트만 모은다."""
    texts = []
    for t in root.findall(f".//{{{NS['hp']}}}t"):
        # 조상 중에 hp:tc가 있으면 표 셀 내부 텍스트 -> 제외
        ancestor = t.getparent()
        in_table = False
        while ancestor is not None:
            if ancestor.tag == f"{{{NS['hp']}}}tc":
                in_table = True
                break
            ancestor = ancestor.getparent()
        if not in_table:
            texts.append(t.text or "")
    return texts


def _all_table_cell_text(root) -> list[str]:
    texts = []
    for tc in root.findall(f".//{{{NS['hp']}}}tc"):
        for t in tc.findall(f".//{{{NS['hp']}}}t"):
            texts.append(t.text or "")
    return texts


# ===========================================================================
# 1. Private 헬퍼 단위 테스트 — _bbox_overlap_ratio
# ===========================================================================


class TestBboxOverlapRatio:
    def test_identical_boxes_ratio_is_one(self):
        box = (0.0, 0.0, 10.0, 10.0)
        assert _bbox_overlap_ratio(box, box) == 1.0

    def test_no_overlap_ratio_is_zero(self):
        a = (0.0, 0.0, 10.0, 10.0)
        b = (20.0, 20.0, 30.0, 30.0)
        assert _bbox_overlap_ratio(a, b) == 0.0

    def test_touching_edges_ratio_is_zero(self):
        """경계값: 맞닿기만 하고 겹치지 않으면(면적 0) 0.0."""
        a = (0.0, 0.0, 10.0, 10.0)
        b = (10.0, 0.0, 20.0, 10.0)
        assert _bbox_overlap_ratio(a, b) == 0.0

    def test_smaller_box_fully_inside_larger_ratio_is_one(self):
        """작은 박스가 큰 박스 안에 완전히 포함되면, 분모가 작은 쪽 면적이라
        비율이 1.0이 된다(REQ-005 dedup가 의존하는 핵심 성질)."""
        big = (0.0, 0.0, 100.0, 100.0)
        small = (10.0, 10.0, 20.0, 20.0)
        assert _bbox_overlap_ratio(big, small) == 1.0
        assert _bbox_overlap_ratio(small, big) == 1.0

    def test_partial_overlap_known_ratio(self):
        a = (0.0, 0.0, 10.0, 10.0)  # area 100
        b = (5.0, 0.0, 15.0, 10.0)  # area 100, intersection x[5,10] y[0,10] = 5*10=50
        assert _bbox_overlap_ratio(a, b) == pytest.approx(0.5)

    def test_zero_area_box_ratio_is_zero(self):
        a = (0.0, 0.0, 10.0, 10.0)
        degenerate = (5.0, 5.0, 5.0, 8.0)  # width 0
        assert _bbox_overlap_ratio(a, degenerate) == 0.0


# ===========================================================================
# 2. Private 헬퍼 단위 테스트 — _exclude_text_overlapping_tables (AC-2 근거)
# ===========================================================================


def _text_block(bbox, text="t") -> TextBlockIR:
    return TextBlockIR(
        bbox=bbox, text=text, font_name="Helvetica", font_size=10.0,
        bold=False, italic=False, to_unicode_missing=False,
    )


def _table_block(bbox, rows=1, cols=1, has_merged=False) -> TableBlockIR:
    cells = [TableCellIR(row_span=1, col_span=1, text="c") for _ in range(rows * cols)]
    return TableBlockIR(bbox=bbox, rows=rows, cols=cols, cells=cells, has_merged_cells=has_merged)


class TestExcludeTextOverlappingTables:
    def test_no_tables_returns_all_text_unchanged(self):
        blocks = [_text_block((0, 0, 5, 5)), _text_block((10, 10, 15, 15))]
        result = _exclude_text_overlapping_tables(blocks, [])
        assert result == blocks

    def test_empty_text_blocks_returns_empty(self):
        assert _exclude_text_overlapping_tables([], [_table_block((0, 0, 10, 10))]) == []

    def test_text_at_exactly_threshold_is_excluded(self):
        """겹침비가 정확히 0.5(임계값)이면 제외되어야 한다(>= 0.5).

        두 박스를 같은 면적(10x10=100)으로 맞춰 분모(더 작은 쪽 면적)가
        항상 100이 되게 하고, 겹치는 폭만 조절해 교집합을 정확히 절반(50)로
        맞춘다 — 교집합/분모 = 50/100 = 0.5 정확히.
        """
        table = _table_block((0.0, 0.0, 10.0, 10.0))
        text = _text_block((5.0, 0.0, 15.0, 10.0))  # 교집합 x[5,10]*y[0,10]=50
        kept = _exclude_text_overlapping_tables([text], [table])
        assert kept == []

    def test_text_just_below_threshold_is_kept(self):
        """같은 면적(100) 박스를 임계값보다 살짝 덜 겹치게(교집합 49,
        ratio=0.49<0.5) 배치하면 제외되지 않아야 한다."""
        table = _table_block((0.0, 0.0, 10.0, 10.0))
        text = _text_block((5.1, 0.0, 15.1, 10.0))  # 교집합 x[5.1,10]*y[0,10]=4.9*10=49
        kept = _exclude_text_overlapping_tables([text], [table])
        assert kept == [text]

    def test_text_fully_overlapping_table_is_excluded(self):
        table = _table_block((0.0, 0.0, 100.0, 100.0))
        text = _text_block((10.0, 10.0, 20.0, 20.0))
        assert _exclude_text_overlapping_tables([text], [table]) == []

    def test_text_not_overlapping_any_table_is_kept(self):
        table = _table_block((0.0, 0.0, 10.0, 10.0))
        text = _text_block((100.0, 100.0, 110.0, 110.0))
        assert _exclude_text_overlapping_tables([text], [table]) == [text]

    def test_mixed_blocks_only_overlapping_ones_excluded(self):
        table = _table_block((0.0, 0.0, 10.0, 10.0))
        overlapping = _text_block((1.0, 1.0, 2.0, 2.0), text="in-table")
        outside = _text_block((100.0, 100.0, 200.0, 200.0), text="outside")
        kept = _exclude_text_overlapping_tables([overlapping, outside], [table])
        assert kept == [outside]

    def test_overlap_with_any_one_of_multiple_tables_excludes(self):
        table_a = _table_block((0.0, 0.0, 10.0, 10.0))
        table_b = _table_block((100.0, 100.0, 110.0, 110.0))
        text = _text_block((101.0, 101.0, 102.0, 102.0))
        assert _exclude_text_overlapping_tables([text], [table_a, table_b]) == []

    def test_does_not_mutate_input_list(self):
        blocks = [_text_block((0, 0, 5, 5))]
        original_len = len(blocks)
        _exclude_text_overlapping_tables(blocks, [_table_block((0, 0, 100, 100))])
        assert len(blocks) == original_len


# ===========================================================================
# 3. Private 헬퍼 단위 테스트 — _fragment_top_y / _order_page_fragments (2-2절)
# ===========================================================================


def _fragment_with_bbox(bbox_str: str | None):
    el = etree.Element("dummy")
    if bbox_str is not None:
        el.set("bboxPt", bbox_str)
    return el


class TestFragmentOrdering:
    def test_fragment_top_y_parses_y0(self):
        assert _fragment_top_y(_fragment_with_bbox("10.00,25.50,20.00,30.00")) == 25.5

    def test_fragment_top_y_missing_attribute_defaults_zero(self):
        assert _fragment_top_y(_fragment_with_bbox(None)) == 0.0

    def test_fragment_top_y_malformed_value_defaults_zero(self):
        assert _fragment_top_y(_fragment_with_bbox("not-a-number,also-bad")) == 0.0

    def test_fragment_top_y_too_few_parts_defaults_zero(self):
        assert _fragment_top_y(_fragment_with_bbox("10.00")) == 0.0

    def test_order_page_fragments_sorts_by_y0_images_appended_last(self):
        p1 = _fragment_with_bbox("0,50,10,60")
        p2 = _fragment_with_bbox("0,10,10,20")
        t1 = _fragment_with_bbox("0,30,10,40")
        img1 = _fragment_with_bbox("0,5,10,15")  # 낮은 y0라도 이미지는 항상 맨 뒤
        ordered = _order_page_fragments([p1], [t1], [img1, p2])
        # image_fragments 인자로 넘긴 것들만 이미지로 취급되어 맨 뒤에 붙는다.
        # p2는 image_fragments 목록에 넣었으므로(테스트 의도: 순서결정 검증) 그대로 뒤에 남는다.
        assert ordered == [t1, p1, img1, p2]

    def test_order_page_fragments_paragraph_and_table_interleaved_by_y0(self):
        para_top = _fragment_with_bbox("0,0,10,10")
        table_mid = _fragment_with_bbox("0,50,10,60")
        para_bottom = _fragment_with_bbox("0,100,10,110")
        ordered = _order_page_fragments([para_top, para_bottom], [table_mid], [])
        assert ordered == [para_top, table_mid, para_bottom]

    def test_order_page_fragments_empty_inputs_returns_empty(self):
        assert _order_page_fragments([], [], []) == []


# ===========================================================================
# 4. ConversionOptions / 상수 기본값
# ===========================================================================


class TestOptionsAndConstants:
    def test_default_options_values(self):
        opts = ConversionOptions()
        assert opts.enable_ocr is False
        assert opts.ocr_lang == "kor"
        assert opts.overwrite_existing is False
        assert opts.progress_callback is None
        assert opts.target_hwpx_min_version == orch.HWPX_MIN_SUPPORTED_VERSION

    def test_hwpx_min_supported_version_matches_schema_version(self):
        assert orch.HWPX_MIN_SUPPORTED_VERSION == hwpx_schema.SCHEMA_VERSION

    def test_convert_with_none_options_uses_defaults(self, fixtures, out_dir):
        result = convert(fixtures["text_1page"], out_dir / "none_opts.hwpx", options=None)
        assert result.success is True


# ===========================================================================
# 5. AC-1 정상 변환 (unit-8-note.md §8, 1~4번)
# ===========================================================================


class TestAC1NormalConversion:
    def test_basic_success_result_shape(self, fixtures, out_dir):
        output = out_dir / "basic.hwpx"
        result = convert(fixtures["text_1page"], output)
        assert result.success is True
        assert result.output_path == output
        assert result.errors == []

    def test_output_file_is_valid_zip_with_expected_entries(self, fixtures, out_dir):
        output = out_dir / "zipcheck.hwpx"
        convert(fixtures["text_1page"], output)
        assert output.exists()
        with zipfile.ZipFile(output) as zf:
            names = set(zf.namelist())
            assert "mimetype" in names
            assert "Contents/section0.xml" in names

    def test_section_xml_is_well_formed_and_contains_input_text(self, fixtures, out_dir):
        output = out_dir / "wellformed.hwpx"
        convert(fixtures["text_1page"], output)
        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)  # 파싱 실패 시 예외 -> 테스트 실패
        all_text = " ".join(t.text or "" for t in root.findall(f".//{{{NS['hp']}}}t"))
        assert "Hello unit-8" in all_text

    @pytest.mark.parametrize("fixture_key", ["blank_1page", "blank_2page", "blank_3page"])
    def test_total_pages_matches_actual_page_count(self, fixtures, out_dir, fixture_key):
        page_count = {"blank_1page": 1, "blank_2page": 2, "blank_3page": 3}[fixture_key]
        output = out_dir / f"{fixture_key}.hwpx"
        result = convert(fixtures[fixture_key], output)
        assert result.success is True
        assert result.stats.total_pages == page_count


# ===========================================================================
# 6. AC-2 REQ-005 dedup — 실제 파이프라인 (unit-8-note.md §8, 5~7번)
# ===========================================================================


class TestAC2RealPipelineDedup:
    """monkeypatch 없이 실제 표/텍스트/이미지가 섞인 PDF로 end-to-end 검증."""

    def test_table_cell_text_appears_exactly_once_inside_table(self, fixtures, out_dir):
        output = out_dir / "combo.hwpx"
        result = convert(fixtures["combo"], output)
        assert result.success is True, result.errors
        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)

        cell_texts = _all_table_cell_text(root)
        free_texts = _all_free_text(root)

        assert "R0C0" in " ".join(cell_texts)
        # 자유 문단(표 밖)에는 R0C0이 등장하지 않아야 한다(dedup으로 제외됨).
        assert "R0C0" not in " ".join(free_texts)
        assert "R0C1" not in " ".join(free_texts)
        assert "R1C0" not in " ".join(free_texts)
        assert "R1C1" not in " ".join(free_texts)

    def test_non_overlapping_text_is_preserved_as_free_paragraph(self, fixtures, out_dir):
        output = out_dir / "combo2.hwpx"
        convert(fixtures["combo"], output)
        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)
        free_texts = " ".join(_all_free_text(root))
        assert "Hello World" in free_texts
        assert "Bold Text" in free_texts
        assert "Second page plain text" in free_texts

    def test_image_included_even_though_table_present_on_page(self, fixtures, out_dir):
        output = out_dir / "combo3.hwpx"
        result = convert(fixtures["combo"], output)
        assert result.success is True
        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)
        pics = root.findall(f".//{{{NS['hp']}}}pic")
        assert len(pics) == 1
        assert result.stats.images_embedded == 1
        with zipfile.ZipFile(output) as zf:
            bin_entries = [n for n in zf.namelist() if n.startswith("BinData/")]
            assert len(bin_entries) == 1


# ===========================================================================
# 6-b. AC-2 monkeypatch 기반 정밀 dedup 배선 검증(경계값 직접 통제)
# ===========================================================================


class TestAC2MonkeypatchedDedupWiring:
    def test_dedup_wiring_excludes_only_overlapping_text(self, fixtures, out_dir, monkeypatch):
        table = _table_block((0.0, 0.0, 100.0, 20.0), rows=1, cols=1)
        overlapping_text = _text_block((10.0, 5.0, 20.0, 15.0), text="OVERLAP")
        free_text = _text_block((0.0, 200.0, 50.0, 210.0), text="FREE")

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [overlapping_text, free_text])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [table])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "wired_dedup.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.success is True, result.errors

        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)
        free_texts = " ".join(_all_free_text(root))
        assert "FREE" in free_texts
        assert "OVERLAP" not in free_texts


# ===========================================================================
# 7. AC-3 예외 계층 -> ConversionResult.errors 매핑 (unit-8-note.md §8, 8~12번)
# ===========================================================================


class TestAC3ExceptionMapping:
    def test_encrypted_pdf_maps_to_encrypted_error(self, fixtures, out_dir):
        output = out_dir / "encrypted_out.hwpx"
        result = convert(fixtures["encrypted"], output)
        assert result.success is False
        assert result.output_path is None
        assert len(result.errors) == 1
        assert result.errors[0].code == "EncryptedPdfError"
        assert "비밀번호로 보호된 PDF는 지원하지 않습니다." in result.errors[0].message
        assert not output.exists()

    def test_corrupted_pdf_maps_to_corrupted_error(self, fixtures, out_dir):
        output = out_dir / "corrupted_out.hwpx"
        result = convert(fixtures["corrupted"], output)
        assert result.success is False
        assert result.errors[0].code == "CorruptedPdfError"
        assert not output.exists()

    def test_empty_pdf_maps_to_empty_error(self, fixtures, out_dir):
        output = out_dir / "empty_out.hwpx"
        result = convert(fixtures["empty0"], output)
        assert result.success is False
        assert result.errors[0].code == "EmptyPdfError"
        assert not output.exists()

    def test_nonexistent_input_path_maps_to_corrupted_error(self, fixtures, out_dir):
        """위험 케이스(AC 범위 밖이지만 명백히 위험한 입력) — 존재하지 않는
        입력 파일은 ``load_pdf``의 ``OSError`` 분기를 거쳐 CorruptedPdfError로
        매핑되어야 하며 예외를 던지면 안 된다(REQ-009 계약)."""
        output = out_dir / "nonexistent_out.hwpx"
        result = convert(FIXTURE_DIR / "does_not_exist_unit8.pdf", output)
        assert result.success is False
        assert result.errors[0].code == "CorruptedPdfError"

    def test_internal_error_hides_stack_trace_but_logs_full_traceback(
        self, fixtures, out_dir, monkeypatch, caplog
    ):
        def _boom(fragments):
            raise ValueError("secret internal detail C:/should/not/leak")

        monkeypatch.setattr(hwpx_schema, "build_reference_section_body", _boom)

        output = out_dir / "internal_error.hwpx"
        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            result = convert(fixtures["blank_1page"], output)

        assert result.success is False
        assert result.errors[0].code == "INTERNAL_ERROR"
        assert "secret internal detail" not in result.errors[0].message
        assert "예상치 못한 오류가 발생했습니다" in result.errors[0].message
        # 컨테이너는 생성됐다가(container_built=True) 실패로 정리(삭제)되어야 한다.
        assert not output.exists()
        # 로그에는 전체 traceback이 남아야 한다(exc_info 첨부 확인).
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any(r.exc_info is not None for r in error_records)
        # traceback 텍스트 자체는 로그에 남아야 한다(사용자 메시지에만 없으면 됨).
        assert "secret internal detail" in caplog.text

    def test_page_processing_failure_isolates_page_and_continues(
        self, fixtures, out_dir, monkeypatch
    ):
        """AC-3 12번 — 페이지1만 실패해도 페이지0은 계속 처리되고(통계에 반영),
        최종 success는 False(부분 성공 상태 없음, DEC-038)."""
        call_count = {"n": 0}

        def _fail_on_second_call(page):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated page-1 failure")
            return []

        page0_text = _text_block((0.0, 0.0, 10.0, 10.0), text="page0-text-12chars")

        def _text_blocks(page):
            return [page0_text] if call_count["n"] == 0 else []

        monkeypatch.setattr(orch, "extract_text_blocks", _text_blocks)
        monkeypatch.setattr(orch, "extract_table_blocks", _fail_on_second_call)
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "bulkhead.hwpx"
        result = convert(fixtures["blank_2page"], output)

        assert result.success is False
        assert result.output_path is None
        assert not output.exists()
        assert len(result.errors) == 1
        assert result.errors[0].code == "PAGE_PROCESSING_FAILED"
        assert result.errors[0].page_index == 1

        # 페이지0은 예외 이전에 완전히 처리되어 통계에 반영되어야 한다(격리 증거).
        assert result.stats.chars_extracted == len("page0-text-12chars")

    def test_all_pages_fail_records_issue_per_page_independently(
        self, fixtures, out_dir, monkeypatch
    ):
        def _always_fail(page):
            raise RuntimeError("boom")

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", _always_fail)
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "bulkhead_all.hwpx"
        result = convert(fixtures["blank_2page"], output)

        assert result.success is False
        page_indices = sorted(e.page_index for e in result.errors)
        assert page_indices == [0, 1]
        assert all(e.code == "PAGE_PROCESSING_FAILED" for e in result.errors)


# ===========================================================================
# 8. AC-4 OutputPathError 사전 검증 (unit-8-note.md §8, 13~15번)
# ===========================================================================


class TestAC4OutputPathValidation:
    def test_existing_output_without_overwrite_fails_before_loading_pdf(
        self, fixtures, out_dir, monkeypatch
    ):
        output = out_dir / "existing.hwpx"
        output.write_bytes(b"pre-existing content")

        call_count = {"n": 0}
        real_load_pdf = orch.load_pdf

        def _spy_load_pdf(path):
            call_count["n"] += 1
            return real_load_pdf(path)

        monkeypatch.setattr(orch, "load_pdf", _spy_load_pdf)

        result = convert(fixtures["text_1page"], output, ConversionOptions(overwrite_existing=False))
        assert result.success is False
        assert result.errors[0].code == "OutputPathError"
        # load_pdf가 실제로 호출되지 않았어야 한다(PDF 자체가 손상돼도 이
        # 경로에서는 그 결함이 보고되면 안 된다는 순서 보장 검증).
        assert call_count["n"] == 0
        # 기존 파일은 이번 실행이 만든 것이 아니므로 건드리면 안 된다.
        assert output.read_bytes() == b"pre-existing content"

    def test_existing_output_with_overwrite_true_succeeds_and_replaces_file(
        self, fixtures, out_dir
    ):
        output = out_dir / "overwrite.hwpx"
        output.write_bytes(b"stale content")

        result = convert(fixtures["text_1page"], output, ConversionOptions(overwrite_existing=True))
        assert result.success is True
        assert output.read_bytes() != b"stale content"
        with zipfile.ZipFile(output) as zf:
            assert "mimetype" in zf.namelist()

    def test_missing_parent_directory_is_created_when_ancestor_writable(
        self, fixtures, out_dir
    ):
        output = out_dir / "nested" / "sub" / "auto_created.hwpx"
        assert not output.parent.exists()
        result = convert(fixtures["text_1page"], output)
        assert result.success is True
        assert output.exists()

    def test_corrupted_pdf_does_not_report_output_path_error_when_overwrite_flag_set(
        self, fixtures, out_dir
    ):
        """13번의 순서 보장이 반대 방향에서도 성립하는지: 출력 경로 문제가
        없으면(overwrite=True 또는 파일 미존재) 이후 단계(PDF 로드)의 실패가
        정상적으로 보고되어야 한다(OutputPathError로 가려지면 안 됨)."""
        output = out_dir / "corrupted_with_overwrite.hwpx"
        result = convert(fixtures["corrupted"], output, ConversionOptions(overwrite_existing=True))
        assert result.errors[0].code == "CorruptedPdfError"


# ===========================================================================
# 9. AC-5 ConversionWarning 매핑 (unit-8-note.md §8, 16~17번)
# ===========================================================================


class TestAC5ImageWarnings:
    def test_ccitt_image_produces_incomplete_bitstream_warning_and_not_counted(
        self, fixtures, out_dir, monkeypatch
    ):
        ccitt_image = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=b"fake-ccitt", image_format="ccitt")
        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [ccitt_image])

        output = out_dir / "ccitt_warn.hwpx"
        result = convert(fixtures["blank_1page"], output)

        assert result.success is True
        assert len(result.warnings) == 1
        warning = result.warnings[0]
        assert warning.code == "IMAGE_FORMAT_INCOMPLETE_BITSTREAM"
        assert warning.page_index == 0
        assert "ccitt" in warning.detail
        assert result.stats.images_embedded == 0

    def test_unsupported_format_produces_unsupported_warning(self, fixtures, out_dir, monkeypatch):
        weird_image = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=b"???", image_format="gif")
        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [weird_image])

        output = out_dir / "unsupported_warn.hwpx"
        result = convert(fixtures["blank_1page"], output)

        assert result.success is True
        assert result.warnings[0].code == "IMAGE_FORMAT_UNSUPPORTED"
        assert result.stats.images_embedded == 0

    def test_warning_detail_matches_original_embedder_message(self, fixtures, out_dir, monkeypatch):
        from pdf_to_hwpx.hwpx_writer.image_embedder import embed_image_blocks

        jbig2_image = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=b"x", image_format="jbig2")
        _, original_warnings, _ = embed_image_blocks([jbig2_image])
        expected_message = original_warnings[0].message

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [jbig2_image])

        output = out_dir / "jbig2_warn.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.warnings[0].detail == expected_message

    def test_supported_and_unsupported_images_mixed_only_supported_counted(
        self, fixtures, out_dir, monkeypatch
    ):
        good = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=_tiny_jpeg_bytes(), image_format="jpeg")
        bad = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=b"x", image_format="unknown")
        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [good, bad])

        output = out_dir / "mixed_images.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.success is True
        assert result.stats.images_embedded == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "IMAGE_FORMAT_UNSUPPORTED"


# ===========================================================================
# 10. AC-6 ConversionStats 정확성 (unit-8-note.md §8, 18~23번)
# ===========================================================================


class TestAC6Stats:
    def test_tables_detected_and_preserved_fully_split_by_merged_flag(
        self, fixtures, out_dir, monkeypatch
    ):
        """의도적으로 비대칭 구성(병합 2개, 비병합 1개)을 쓴다 — 병합/비병합이
        1:1이면 ``has_merged_cells`` 조건이 실수로 반전돼도(뮤테이션 M3로
        실측 확인됨, unit-8-test.md 5절) 우연히 같은 개수가 나와 결함을
        놓칠 수 있기 때문이다."""

        def _merged_table(y_offset: float) -> TableBlockIR:
            merged_cells = [
                TableCellIR(row_span=1, col_span=2, text="A"),
                TableCellIR(row_span=1, col_span=1, text="B"),
                TableCellIR(row_span=1, col_span=1, text="C"),
            ]
            return TableBlockIR(
                bbox=(0.0, y_offset, 100.0, y_offset + 100.0),
                rows=2, cols=2, cells=merged_cells, has_merged_cells=True,
            )

        merged_table_1 = _merged_table(0.0)
        merged_table_2 = _merged_table(500.0)
        simple_table = _table_block((0.0, 200.0, 50.0, 250.0), rows=1, cols=1, has_merged=False)

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(
            orch, "extract_table_blocks",
            lambda page: [merged_table_1, simple_table, merged_table_2],
        )
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "stats_tables.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.success is True, result.errors
        assert result.stats.tables_detected == 3
        assert result.stats.tables_preserved_fully == 1

    def test_images_embedded_counts_only_actually_embedded(self, fixtures, out_dir, monkeypatch):
        good1 = ImageBlockIR(bbox=(0, 0, 5, 5), raw_bytes=_tiny_jpeg_bytes(), image_format="jpeg")
        good2 = ImageBlockIR(bbox=(0, 0, 5, 5), raw_bytes=_tiny_jpeg_bytes(), image_format="png")
        warned = ImageBlockIR(bbox=(0, 0, 5, 5), raw_bytes=b"x", image_format="ccitt")
        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [good1, good2, warned])

        output = out_dir / "stats_images.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.stats.images_embedded == 2

    def test_chars_extracted_includes_deduped_text(self, fixtures, out_dir, monkeypatch):
        """chars_extracted는 dedup '이전' 값(표와 겹쳐 제외된 텍스트도 포함)."""
        table = _table_block((0.0, 0.0, 100.0, 100.0))
        overlapping = _text_block((10.0, 10.0, 20.0, 20.0), text="EXCLUDED")  # 8글자
        free = _text_block((0.0, 200.0, 50.0, 210.0), text="KEPT12345")  # 9글자

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [overlapping, free])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [table])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "stats_chars.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.success is True, result.errors
        assert result.stats.chars_extracted == len("EXCLUDED") + len("KEPT12345")

    def test_chars_replaced_with_placeholder_sums_only_flagged_blocks(
        self, fixtures, out_dir, monkeypatch
    ):
        flagged = TextBlockIR(
            bbox=(0.0, 300.0, 10.0, 310.0), text="\u25a1\u25a1\u25a1", font_name=None,
            font_size=None, bold=False, italic=False, to_unicode_missing=True,
        )
        normal = _text_block((0.0, 400.0, 10.0, 410.0), text="normal-text")

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [flagged, normal])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        output = out_dir / "stats_placeholder.hwpx"
        result = convert(fixtures["blank_1page"], output)
        assert result.success is True, result.errors
        assert result.stats.chars_replaced_with_placeholder == 3
        assert result.stats.chars_extracted == 3 + len("normal-text")

    def test_elapsed_seconds_positive_on_success(self, fixtures, out_dir):
        result = convert(fixtures["text_1page"], out_dir / "elapsed_ok.hwpx")
        assert result.stats.elapsed_seconds > 0

    def test_elapsed_seconds_positive_on_failure(self, fixtures, out_dir):
        result = convert(fixtures["encrypted"], out_dir / "elapsed_fail.hwpx")
        assert result.stats.elapsed_seconds > 0


# ===========================================================================
# 11. AC-7 progress_callback 호출 순서 (unit-8-note.md §8, 24~25번)
# ===========================================================================


class TestAC7ProgressCallback:
    def test_stage_sequence_on_success(self, fixtures, out_dir):
        events: list[ProgressEvent] = []
        options = ConversionOptions(progress_callback=events.append)
        output = out_dir / "progress_ok.hwpx"
        result = convert(fixtures["blank_2page"], output, options)

        assert result.success is True
        stages = [e.stage for e in events]
        assert stages[0] == "loading"
        assert stages[-1] == "done"
        assert stages[-2] == "saving"

        for page_num in (1, 2):
            assert any(e.stage == "extracting" and e.current_page == page_num for e in events)
            assert any(e.stage == "building" and e.current_page == page_num for e in events)

        # total_pages는 매 이벤트에서 실제 페이지 수(2)와 일치해야 한다
        # (loading 단계는 아직 페이지 수를 모르므로 0이 허용됨).
        for e in events:
            if e.stage != "loading":
                assert e.total_pages == 2

    def test_no_progress_callback_does_not_raise(self, fixtures, out_dir):
        result = convert(fixtures["text_1page"], out_dir / "no_callback.hwpx", ConversionOptions())
        assert result.success is True

    def test_done_stage_not_emitted_on_failure(self, fixtures, out_dir):
        events: list[ProgressEvent] = []
        options = ConversionOptions(progress_callback=events.append)
        result = convert(fixtures["encrypted"], out_dir / "progress_fail.hwpx", options)

        assert result.success is False
        stages = [e.stage for e in events]
        assert "done" not in stages

    def test_done_stage_not_emitted_on_page_bulkhead_failure(
        self, fixtures, out_dir, monkeypatch
    ):
        def _always_fail(page):
            raise RuntimeError("boom")

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", _always_fail)
        monkeypatch.setattr(orch, "extract_image_blocks", lambda page: [])

        events: list[ProgressEvent] = []
        options = ConversionOptions(progress_callback=events.append)
        result = convert(fixtures["blank_1page"], out_dir / "progress_bulkhead.hwpx", options)

        assert result.success is False
        assert "done" not in [e.stage for e in events]
        assert "saving" not in [e.stage for e in events]


# ===========================================================================
# 12. AC-8 알려진 리스크 확인(결함 아님, unit-8-note.md §8, 26번)
# ===========================================================================


class TestAC8KnownImageCoordinateRisk:
    def test_multi_page_images_collide_at_same_absolute_position_documented_risk(
        self, fixtures, out_dir, monkeypatch
    ):
        """이 테스트는 '결함 탐지'가 아니라 unit-8-note.md §2-3/AC-8이 명시한
        알려진 한계가 실제로 재현됨을 문서화한다 — 다른 값이 나오면 오히려
        08단계 이관 전제가 깨진 것이므로 그 자체를 재확인 대상으로 삼는다."""
        img_a = ImageBlockIR(bbox=(0.0, 0.0, 50.0, 50.0), raw_bytes=_tiny_jpeg_bytes(), image_format="jpeg")
        img_b = ImageBlockIR(bbox=(0.0, 0.0, 50.0, 50.0), raw_bytes=_tiny_jpeg_bytes(), image_format="jpeg")

        monkeypatch.setattr(orch, "extract_text_blocks", lambda page: [])
        monkeypatch.setattr(orch, "extract_table_blocks", lambda page: [])
        calls = {"n": 0}

        def _images(page):
            calls["n"] += 1
            return [img_a] if calls["n"] == 1 else [img_b]

        monkeypatch.setattr(orch, "extract_image_blocks", _images)

        output = out_dir / "coord_risk.hwpx"
        result = convert(fixtures["blank_2page"], output)
        assert result.success is True

        section_bytes = _read_section_xml(output)
        root = etree.fromstring(section_bytes)
        positions = [
            (pos.get("xHwpunit"), pos.get("yHwpunit"))
            for pos in root.findall(f".//{{{NS['hp']}}}pos")
        ]
        sizes = [
            (sz.get("widthHwpunit"), sz.get("heightHwpunit"))
            for sz in root.findall(f".//{{{NS['hp']}}}sz")
        ]
        assert len(positions) == 2
        # 알려진 한계: 서로 다른 페이지의 이미지인데도 좌표/크기가 동일하게 충돌한다.
        assert positions[0] == positions[1]
        assert sizes[0] == sizes[1]


# ===========================================================================
# 13. 추가 위험 케이스(AC 범위 밖이지만 명백히 위험해 직접 확인)
# ===========================================================================


class TestExtraRiskCases:
    def test_enable_ocr_true_does_not_change_behavior_yet(self, fixtures, out_dir):
        """REQ-014 미구현 — enable_ocr=True를 넘겨도 크래시하지 않고 False와
        동일하게 동작해야 한다(unit-8-note.md §3 명시)."""
        opts_true = ConversionOptions(enable_ocr=True, ocr_lang="eng")
        opts_false = ConversionOptions(enable_ocr=False)
        r_true = convert(fixtures["text_1page"], out_dir / "ocr_true.hwpx", opts_true)
        r_false = convert(fixtures["text_1page"], out_dir / "ocr_false.hwpx", opts_false)
        assert r_true.success is True
        assert r_false.success is True
        assert r_true.stats.total_pages == r_false.stats.total_pages
        assert r_true.stats.chars_extracted == r_false.stats.chars_extracted

    def test_all_blank_pages_no_text_table_image_succeeds_with_zero_stats(
        self, fixtures, out_dir
    ):
        result = convert(fixtures["blank_2page"], out_dir / "all_blank.hwpx")
        assert result.success is True
        assert result.stats.tables_detected == 0
        assert result.stats.images_embedded == 0

    def test_progress_callback_that_raises_is_caught_as_internal_error(
        self, fixtures, out_dir
    ):
        """위험 케이스(AC 범위 밖, 명백히 위험한 입력이라 직접 확인) — 호출자가
        넘긴 ``progress_callback`` 이 예외를 던지면, convert()의 최상위
        ``except Exception:`` 캐치올이 이를 그대로 삼켜 INTERNAL_ERROR로
        변환한다(실제 동작 실측 — REQ-009 "예외를 던지지 않는다" 계약은
        지켜지지만, 호출자 자신의 콜백 버그가 일반 내부 오류 메시지 뒤에
        가려진다는 부수효과가 있다. 결함으로 단정하지 않고 8절 리스크로
        기록한다)."""

        def _boom(event):
            raise RuntimeError("callback exploded")

        options = ConversionOptions(progress_callback=_boom)
        output = out_dir / "callback_boom.hwpx"
        result = convert(fixtures["text_1page"], output, options)

        assert result.success is False
        assert result.errors[0].code == "INTERNAL_ERROR"
        assert not output.exists()


# ===========================================================================
# 14. 커버리지 보강 — 방어적/저확률 분기 직접 테스트
# ===========================================================================


class TestCoverageGapClosure:
    def test_container_build_error_after_container_built_triggers_cleanup(
        self, fixtures, out_dir, monkeypatch
    ):
        from pdf_to_hwpx.common.exceptions import ContainerBuildError

        def _raise_container_error(container_path, xml_bytes, section_name="section0.xml"):
            raise ContainerBuildError("simulated disk failure")

        monkeypatch.setattr(orch.hwpx_container, "add_section_xml", _raise_container_error)

        output = out_dir / "container_build_error.hwpx"
        result = convert(fixtures["blank_1page"], output)

        assert result.success is False
        assert result.errors[0].code == "ContainerBuildError"
        assert "HWPX 파일을 생성할 수 없습니다" in result.errors[0].message
        assert not output.exists()

    def test_validate_output_path_breaks_when_no_existing_ancestor_found(self, monkeypatch):
        class _RootLikeFakePath:
            def exists(self) -> bool:
                return False

            @property
            def parent(self) -> "_RootLikeFakePath":
                return self

        monkeypatch.setattr(orch.os, "access", lambda path, mode: True)
        orch._validate_output_path(_RootLikeFakePath(), overwrite_existing=False)

    def test_validate_output_path_raises_when_no_write_permission(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch.os, "access", lambda path, mode: False)
        output = tmp_path / "no_permission.hwpx"
        with pytest.raises(OutputPathError, match="쓰기 권한이 없습니다"):
            orch._validate_output_path(output, overwrite_existing=False)

    def test_cleanup_partial_output_swallows_oserror_but_logs_warning(self, caplog):
        class _UnlinkFailsFakePath:
            def unlink(self, missing_ok: bool = False) -> None:
                raise OSError("simulated file lock")

            def __str__(self) -> str:
                return "<fake-locked-path>"

        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            orch._cleanup_partial_output(_UnlinkFailsFakePath())

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        assert any(r.exc_info is not None for r in warning_records)

    def test_bbox_overlap_ratio_stays_within_unit_range_for_edge_shapes(self):
        cases = [
            ((0.0, 0.0, 1e-6, 1e-6), (0.0, 0.0, 1e-6, 1e-6)),
            ((0.0, 0.0, 1000.0, 1000.0), (999.999999, 999.999999, 1000.0, 1000.0)),
        ]
        for a, b in cases:
            ratio = _bbox_overlap_ratio(a, b)
            assert 0.0 <= ratio <= 1.0
