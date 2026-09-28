"""unit-3 AC-1~AC-5 -- `pdf_to_hwpx/pdf_reader/table_recognizer.py` 검증.

근거: docs/harness/units/unit-3-note.md §6(AC-1~AC-5), §1-2(병합 셀 휴리스틱)/
§1-4(rows/cols 정의), 03-system-design.md §1-3(unit-3 행)/§3-1(TableBlockIR).

PDF 픽스처는 unit-0/unit-1 테스트(각각 전용 `.harness-tmp/pdf_fixtures_06_unit0`,
`..._unit1`)를 건드리지 않기 위해 이 파일 전용의 별도 디렉터리
(`.harness-tmp/pdf_fixtures_06_unit3/`)를 자체적으로 만든다(병렬 웨이브 규칙 --
다른 단위의 공유 파일을 수정하지 않음, unit-1 테스트와 동일한 패턴).

병합 셀 픽스처는 reportlab의 고수준 Table/TableStyle이 아니라 캔버스에 선분을
직접 그려(``canvas.line``) 격자선 일부를 의도적으로 생략하는 방식으로 만든다
(unit-3-note.md §5가 자체 검증에 쓴 것과 동일한 방식). 이렇게 해야 "어느 선이
빠졌는지"를 정확히 통제할 수 있고, pdfplumber가 실제로 해당 위치를 병합으로
인식 가능한 형태(``Table.rows[i].cells``의 ``None``)로 만드는지 사전에
확인할 수 있다(아래 각 빌더 함수 docstring에 어떤 선을 생략했는지 명시).

AC-4의 "표 2개 이상" 경계, AC-5의 "알려진 미탐 한계"는 각각 실제 PDF와
화이트박스 스텁(``_build_table_block`` 직접 호출, unit-1의 `_sanitize_text`
직접 검증과 동일한 관례)을 섞어서 검증한다. 특히 AC-5는 pdfplumber의 실제
선-검출 알고리즘에 의존하지 않고 알고리즘의 문서화된 동작을 결정론적으로
재현하기 위해 화이트박스로 검증한다(근거는 해당 테스트 docstring 참고).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pdfplumber
import pytest
from reportlab.pdfgen import canvas

from pdf_to_hwpx.pdf_reader.ir import TableBlockIR
from pdf_to_hwpx.pdf_reader.loader import load_pdf
from pdf_to_hwpx.pdf_reader.table_recognizer import (
    _build_table_block,
    extract_table_blocks,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / ".harness-tmp" / "pdf_fixtures_06_unit3"

# 3x3 격자 좌표(reportlab 캔버스 좌표계, y는 아래에서 위로 증가).
_X = [100, 200, 300, 400]
_Y = [700, 650, 600, 550]  # 위에서 아래로(페이지 상단이 첫 행)


def _draw_grid(c: canvas.Canvas, skip_v=None, skip_h=None) -> None:
    """3x3 격자선을 그리되, ``skip_v``/``skip_h``에 지정된 선분만 생략한다.

    skip_v: {(열 인덱스, 행 인덱스)} -- ``_X[열 인덱스]``의 세로선 중 그 행
        범위(``_Y[행]``~``_Y[행+1]``)에 해당하는 구간만 생략.
    skip_h: {(행 인덱스, 열 인덱스)} -- ``_Y[행 인덱스]``의 가로선 중 그 열
        범위(``_X[열]``~``_X[열+1]``)에 해당하는 구간만 생략.
    """
    skip_v = skip_v or set()
    skip_h = skip_h or set()
    for ci, x in enumerate(_X):
        for ri in range(3):
            if (ci, ri) in skip_v:
                continue
            c.line(x, _Y[ri], x, _Y[ri + 1])
    for ri, y in enumerate(_Y):
        for ci in range(3):
            if (ri, ci) in skip_h:
                continue
            c.line(_X[ci], y, _X[ci + 1], y)


def _cell_center(ri: int, ci: int) -> tuple[float, float]:
    x = (_X[ci] + _X[ci + 1]) / 2
    y = (_Y[ri] + _Y[ri + 1]) / 2 - 4
    return x, y


def _make_plain_table_pdf(path: Path) -> None:
    """병합 없는 3x3 표 -- 격자선 전부 존재, 9칸 전부 텍스트 A~I."""
    c = canvas.Canvas(str(path))
    _draw_grid(c)
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    idx = 0
    for ri in range(3):
        for ci in range(3):
            x, y = _cell_center(ri, ci)
            c.drawCentredString(x, y, labels[idx])
            idx += 1
    c.showPage()
    c.save()


def _make_plain_table_with_blank_cell_pdf(path: Path) -> None:
    """병합 없는 3x3 표이되, 마지막 칸(행2/열2)에는 텍스트를 그리지 않는다
    (AC-1-3: 실제 사각형은 있지만 내용이 없는 셀 -> text가 ``""``이어야 함,
    dataclass 필드 타입이 ``str``이므로 ``None``이면 안 됨)."""
    c = canvas.Canvas(str(path))
    _draw_grid(c)
    labels = {
        (0, 0): "A", (0, 1): "B", (0, 2): "C",
        (1, 0): "D", (1, 1): "E", (1, 2): "F",
        (2, 0): "G", (2, 1): "H",  # (2, 2)는 의도적으로 비움
    }
    for (ri, ci), t in labels.items():
        x, y = _cell_center(ri, ci)
        c.drawCentredString(x, y, t)
    c.showPage()
    c.save()


def _make_hmerge_table_pdf(path: Path) -> None:
    """가로 병합 -- 0행의 0/1열 사이 세로선(``_X[1]``, 행 인덱스 0 구간)만 생략.

    병합된 칸(0행 0~1열)에는 텍스트 "A"만 쓴다("A"가 병합된 큰 사각형 안에
    들어가므로 pdfplumber가 그 병합 셀의 텍스트로 추출해야 한다).
    """
    c = canvas.Canvas(str(path))
    _draw_grid(c, skip_v={(1, 0)})
    labels = {
        (0, 0): "A", (0, 2): "C",
        (1, 0): "D", (1, 1): "E", (1, 2): "F",
        (2, 0): "G", (2, 1): "H", (2, 2): "I",
    }
    for (ri, ci), t in labels.items():
        x, y = _cell_center(ri, ci)
        c.drawCentredString(x, y, t)
    c.showPage()
    c.save()


def _make_vmerge_table_pdf(path: Path) -> None:
    """세로 병합 -- 1열의 0/1행 사이 가로선(``_Y[1]``, 열 인덱스 1 구간)만 생략."""
    c = canvas.Canvas(str(path))
    _draw_grid(c, skip_h={(1, 1)})
    labels = {
        (0, 0): "A", (0, 1): "B", (0, 2): "C",
        (1, 0): "D", (1, 2): "F",
        (2, 0): "G", (2, 1): "H", (2, 2): "I",
    }
    for (ri, ci), t in labels.items():
        x, y = _cell_center(ri, ci)
        c.drawCentredString(x, y, t)
    c.showPage()
    c.save()


def _make_two_tables_pdf(path: Path) -> None:
    """한 페이지에 병합 없는 표 2개(위/아래, bbox가 서로 겹치지 않음)."""
    c = canvas.Canvas(str(path))
    _draw_grid(c)
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    idx = 0
    for ri in range(3):
        for ci in range(3):
            x, y = _cell_center(ri, ci)
            c.drawCentredString(x, y, labels[idx])
            idx += 1
    x2 = [100, 150, 200]
    y2 = [400, 370, 340]
    for x in x2:
        c.line(x, y2[0], x, y2[-1])
    for y in y2:
        c.line(x2[0], y, x2[-1], y)
    c.drawCentredString(125, 383, "1")
    c.drawCentredString(175, 383, "2")
    c.drawCentredString(125, 353, "3")
    c.drawCentredString(175, 353, "4")
    c.showPage()
    c.save()


def _make_no_table_pdf(path: Path) -> None:
    """표는 없고 일반 텍스트만 있는 페이지."""
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, "just some text, no table here")
    c.showPage()
    c.save()


def _make_empty_page_pdf(path: Path) -> None:
    """텍스트도 도형도 전혀 없는 완전히 빈 페이지(no_table과는 별개의 경계값)."""
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()


@pytest.fixture(scope="module")
def pdf_fixtures() -> Iterator[dict[str, Path]]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    builders = {
        "plain": _make_plain_table_pdf,
        "plain_blank_cell": _make_plain_table_with_blank_cell_pdf,
        "hmerge": _make_hmerge_table_pdf,
        "vmerge": _make_vmerge_table_pdf,
        "two_tables": _make_two_tables_pdf,
        "no_table": _make_no_table_pdf,
        "empty_page": _make_empty_page_pdf,
    }
    paths: dict[str, Path] = {}
    for key, builder in builders.items():
        p = FIXTURE_DIR / f"{key}.pdf"
        builder(p)
        paths[key] = p

    yield paths

    for p in paths.values():
        if p.exists():
            p.unlink()
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        pass  # 다른 테스트가 같은 세션에서 추가 생성했다면 강제로 지우지 않음


# --------------------------------------------------------------------------
# 계약을 흉내내는 최소 스텁 (unittest.mock 미사용, 순수 duck-typing 객체,
# unit-1 `_FakePage` 관례와 동일)
# --------------------------------------------------------------------------


class _FakeRow:
    def __init__(self, bbox, cells):
        self.bbox = bbox
        self.cells = cells


class _FakeTable:
    def __init__(self, bbox, rows, extract_result):
        self.bbox = bbox
        self.rows = rows
        self._extract_result = extract_result

    def extract(self):
        return self._extract_result


class _FakeTablePage:
    """``extract_table_blocks``가 실제로 필요로 하는 유일한 계약
    (``find_tables(**kwargs) -> list[Table-like]``)만 구현한 스텁."""

    def __init__(self, tables: list[_FakeTable]) -> None:
        self._tables = tables
        self.calls: list[dict] = []

    def find_tables(self, **kwargs):
        self.calls.append(kwargs)
        return self._tables


# ==========================================================================
# AC-1: 기본 동작
# ==========================================================================


def test_plain_table_returns_one_block_with_correct_grid_and_spans(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["plain"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, TableBlockIR)
    assert block.rows == 3
    assert block.cols == 3
    assert len(block.cells) == block.rows * block.cols == 9
    assert all(cell.row_span == 1 and cell.col_span == 1 for cell in block.cells)


def test_plain_table_has_merged_cells_is_false(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["plain"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert blocks[0].has_merged_cells is False


def test_plain_table_cell_text_matches_actual_content(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["plain"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    texts = sorted(cell.text for cell in blocks[0].cells)
    assert texts == sorted(["A", "B", "C", "D", "E", "F", "G", "H", "I"])


def test_plain_table_blank_cell_text_is_empty_string_not_none(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["plain_blank_cell"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert len(blocks) == 1
    block = blocks[0]
    assert len(block.cells) == 9
    empty_cells = [cell for cell in block.cells if cell.text == ""]
    assert len(empty_cells) == 1
    assert empty_cells[0].row_span == 1 and empty_cells[0].col_span == 1
    # dataclass 필드 타입이 str이므로 None이 섞이면 안 됨(AC-1-3).
    assert all(isinstance(cell.text, str) for cell in block.cells)
    assert all(cell.text is not None for cell in block.cells)


def test_extract_table_blocks_via_loader_pdfdocument_input_contract(pdf_fixtures):
    """모듈 docstring이 명시한 실제 입력 계약(PdfDocument.plumber_pdf.pages[i])
    그대로 unit-0의 load_pdf를 통해 얻은 페이지로도 동작하는지 확인."""
    doc = load_pdf(pdf_fixtures["plain"])
    try:
        blocks = extract_table_blocks(doc.plumber_pdf.pages[0])
    finally:
        doc.close()
    assert len(blocks) == 1
    assert blocks[0].rows == 3 and blocks[0].cols == 3


# ==========================================================================
# AC-2: 가로 병합
# ==========================================================================


def test_hmerge_table_merged_cell_has_col_span_2_row_span_1(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["hmerge"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert len(blocks) == 1
    block = blocks[0]
    merged = [cell for cell in block.cells if cell.col_span >= 2]
    assert len(merged) == 1
    assert merged[0].col_span == 2
    assert merged[0].row_span == 1
    assert merged[0].text == "A"


def test_hmerge_table_has_merged_cells_is_true(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["hmerge"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert blocks[0].has_merged_cells is True


def test_hmerge_table_cell_count_is_less_than_rows_times_cols(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["hmerge"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    block = blocks[0]
    assert block.rows == 3 and block.cols == 3
    assert len(block.cells) == 8 < block.rows * block.cols


# ==========================================================================
# AC-3: 세로 병합
# ==========================================================================


def test_vmerge_table_merged_cell_has_row_span_2_col_span_1(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["vmerge"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert len(blocks) == 1
    block = blocks[0]
    merged = [cell for cell in block.cells if cell.row_span >= 2]
    assert len(merged) == 1
    assert merged[0].row_span == 2
    assert merged[0].col_span == 1
    assert merged[0].text == "B"


def test_vmerge_table_has_merged_cells_is_true(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["vmerge"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert blocks[0].has_merged_cells is True


# ==========================================================================
# AC-4: 경계/예외 상황
# ==========================================================================


def test_no_table_page_returns_empty_list(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["no_table"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert blocks == []


def test_completely_empty_page_returns_empty_list_without_exception(pdf_fixtures):
    """AC-4-1의 변형 -- 표가 없을 뿐 아니라 페이지에 아무 콘텐츠도 없는
    극단적 경계값(위험 케이스로 판단해 범위 밖이라도 포함, 06-unit-tester 원칙)."""
    with pdfplumber.open(str(pdf_fixtures["empty_page"])) as pdf:
        blocks = extract_table_blocks(pdf.pages[0])
    assert blocks == []


def test_two_tables_on_one_page_returns_two_blocks_in_find_tables_order(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["two_tables"])) as pdf:
        page = pdf.pages[0]
        blocks = extract_table_blocks(page)
        raw_tables = page.find_tables()
    assert len(blocks) == 2
    # find_tables() 순서를 그대로 따르는지 bbox로 확인(재호출도 결정론적).
    assert blocks[0].bbox == raw_tables[0].bbox
    assert blocks[1].bbox == raw_tables[1].bbox
    # 두 표의 bbox가 서로 겹치지 않아야 한다(top/bottom 구간 분리).
    b0, b1 = blocks[0].bbox, blocks[1].bbox
    assert b0[3] <= b1[1] or b1[3] <= b0[1]
    assert blocks[0].rows == 3 and blocks[0].cols == 3
    assert blocks[1].rows == 2 and blocks[1].cols == 2


def test_table_bbox_matches_pdfplumber_table_bbox_exactly(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["plain"])) as pdf:
        page = pdf.pages[0]
        blocks = extract_table_blocks(page)
        raw_tables = page.find_tables()
    assert len(raw_tables) == 1
    assert blocks[0].bbox == raw_tables[0].bbox
    assert isinstance(blocks[0].bbox, tuple)
    assert len(blocks[0].bbox) == 4


def test_table_settings_none_forwards_no_kwarg_to_find_tables():
    fake_table = _FakeTable(
        bbox=(0, 0, 10, 10),
        rows=[_FakeRow(bbox=(0, 0, 10, 10), cells=[(0, 0, 10, 10)])],
        extract_result=[["X"]],
    )
    page = _FakeTablePage([fake_table])
    blocks = extract_table_blocks(page)
    assert page.calls == [{}]
    assert len(blocks) == 1
    assert blocks[0].cells[0].text == "X"


def test_table_settings_dict_is_forwarded_verbatim():
    fake_table = _FakeTable(
        bbox=(0, 0, 10, 10),
        rows=[_FakeRow(bbox=(0, 0, 10, 10), cells=[(0, 0, 10, 10)])],
        extract_result=[["X"]],
    )
    page = _FakeTablePage([fake_table])
    settings = {"vertical_strategy": "text"}
    extract_table_blocks(page, table_settings=settings)
    assert page.calls == [{"table_settings": settings}]


# ==========================================================================
# AC-5: 알려진 미탐 한계(회귀 검증용 -- "실패"가 아니라 "설계된 한계")
# ==========================================================================


def test_known_limitation_whole_column_never_resolved_stays_unmerged_false():
    """unit-3-note.md §1-2/AC-5, 모듈 docstring "알려진 한계" 재현.

    pdfplumber의 실제 선-검출 알고리즘에 이 극단적 배치(어느 행에서도 실제
    사각형을 얻을 수 없는 열)를 강제로 만들도록 유도하는 것은 비결정적이라
    (pdfplumber 내부 구현에 따라 애초에 그런 grid 자체가 안 만들어질 수 있음),
    문서화된 알고리즘 동작을 화이트박스로 직접 재현한다(``_build_table_block``
    직접 호출 -- unit-1이 `_sanitize_text`를 직접 검증한 것과 동일한 관례).

    구성: 2열 3행 격자에서 0번 열은 모든 행에서 실제 사각형이 전혀 없고
    (col_x0[0]이 끝까지 None), 위/왼쪽 어느 쪽으로도 소유자 사슬을 이어갈
    실제 bbox가 없다 -- 코드 1-2절 2-c 경로(독립 빈 셀)로만 빠지는 조건.
    """

    class _Row:
        def __init__(self, bbox):
            self.bbox = bbox

    rows = [_Row((0, 0, 20, 10)), _Row((0, 10, 20, 20)), _Row((0, 20, 20, 30))]
    grid_bbox = [
        [None, (10, 0, 20, 10)],
        [None, (10, 10, 20, 20)],
        [None, (10, 20, 20, 30)],
    ]
    grid_text = [[None, "B1"], [None, "B2"], [None, "B3"]]

    block = _build_table_block(
        bbox=(0, 0, 20, 30),
        rows=rows,
        grid_bbox=grid_bbox,
        grid_text=grid_text,
        n_rows=3,
        n_cols=2,
    )

    # 핵심 주장: 이 배치는 실제로 "병합처럼 보이지만" 기하학적으로 확정할
    # 근거가 전혀 없으므로 has_merged_cells는 False로 남아야 한다(지어내지
    # 않음 -- 이것이 버그가 아니라 note/docstring이 명시한 설계된 한계다).
    assert block.has_merged_cells is False
    col0_cells = [c for c in block.cells if c.text == ""]
    assert len(col0_cells) == 3
    assert all(c.row_span == 1 and c.col_span == 1 for c in col0_cells)
    # 0번 열이 크래시 없이 독립 빈 셀 3개로 안전하게 남았는지 확인(text는 ""
    # 이지 None이 아님 -- dataclass 필드 타입 계약 유지).
    assert all(isinstance(c.text, str) for c in block.cells)
    # 나머지(1번 열)는 정상적으로 실제 텍스트를 보존한다.
    col1_texts = sorted(c.text for c in block.cells if c.text != "")
    assert col1_texts == ["B1", "B2", "B3"]


# ==========================================================================
# 명시적 AC 범위는 아니지만 위험한 입력/방어 분기라 판단해 추가한 케이스
# (06-unit-tester 필수 원칙: 명백히 위험한 케이스는 범위를 벗어나도 기록)
# ==========================================================================


def test_degenerate_zero_row_and_zero_col_tables_are_skipped_via_continue():
    """게이트2 체크리스트가 언급한 "빈 행/빈 열의 표 감지 결과" 방어 분기
    (``continue``)는 실제 pdfplumber 출력으로는 재현 불가로 보여(note 확인),
    스텁으로 직접 트리거해 해당 표만 조용히 건너뛰고 정상 표는 영향받지
    않는지 확인한다."""
    zero_row_table = _FakeTable(bbox=(0, 0, 5, 5), rows=[], extract_result=[])

    class _RowNoCols:
        def __init__(self, bbox):
            self.bbox = bbox
            self.cells: list = []

    zero_col_table = _FakeTable(
        bbox=(0, 0, 5, 5), rows=[_RowNoCols((0, 0, 5, 5))], extract_result=[[]]
    )
    normal_table = _FakeTable(
        bbox=(0, 0, 10, 10),
        rows=[_FakeRow(bbox=(0, 0, 10, 10), cells=[(0, 0, 10, 10)])],
        extract_result=[["OK"]],
    )
    page = _FakeTablePage([zero_row_table, normal_table, zero_col_table])
    blocks = extract_table_blocks(page)
    assert len(blocks) == 1
    assert blocks[0].cells[0].text == "OK"


def test_none_page_raises_attribute_error_fail_fast_not_swallowed():
    """이 함수는 시스템 경계(사용자 입력)를 직접 받지 않는다는 note §4의
    전제를 확인 -- None을 넘기면 조용히 삼키지 않고 즉시 AttributeError로
    실패해야 한다(예외를 삼키는 코드가 없음을 실측으로 재확인, 결함 아님)."""
    with pytest.raises(AttributeError):
        extract_table_blocks(None)  # type: ignore[arg-type]


def test_table_recognizer_only_imports_ir_and_does_not_redefine_shared_contracts():
    """범위 외 파일(ir.py/loader.py) 미접촉 -- 코드 리뷰로 확인 가능해야 한다는
    note §2 "설계서 대비 편차 없음"을 소스 텍스트 검사로 보강 확인."""
    import pdf_to_hwpx.pdf_reader.table_recognizer as table_recognizer_module

    source = Path(table_recognizer_module.__file__).read_text(encoding="utf-8")
    assert "from pdf_to_hwpx.pdf_reader.ir import TableBlockIR, TableCellIR" in source
    assert "class TableBlockIR" not in source
    assert "class TableCellIR" not in source
    assert "class PdfDocument" not in source
