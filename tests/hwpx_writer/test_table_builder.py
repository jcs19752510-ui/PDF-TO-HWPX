"""unit-6 인수 조건(AC-1~AC-6) 검증 — `pdf_to_hwpx/hwpx_writer/table_builder.py`.

근거: docs/harness/units/unit-6-note.md §6 AC-1~AC-6, docs/harness/decisions.md
DEC-017(실제 한글 미검증 리스크 승계).

**범위의 근본적 한계(반드시 읽을 것, tests/hwpx_kernel/test_schema.py와 동일)**:
여기서는 "well-formed XML이고 기대하는 태그/속성/그리드 좌표를 갖는다"는 것만
증명한다. 태그/속성 이름 자체가 실제 한글(한컴오피스) 스펙과 일치하는지는
개발 환경에 한글이 없어 검증 불가능하다(DEC-017 승계, unit-6-note.md §5 "명시적으로
하지 않은 것").
"""

from __future__ import annotations

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.hwpx_writer.table_builder import (
    _resolve_cell_positions,
    table_block_to_fragment,
    table_blocks_to_fragments,
)
from pdf_to_hwpx.pdf_reader.ir import TableBlockIR, TableCellIR


def qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def assert_round_trips_as_well_formed(element: etree._Element) -> bytes:
    """프래그먼트를 직렬화 -> 재파싱해 well-formed임을 실제로 증명한다."""
    data = etree.tostring(element, xml_declaration=False, encoding="UTF-8")
    reparsed = etree.fromstring(data)
    assert reparsed.tag == element.tag
    return data


def make_cell(text: str, row_span: int = 1, col_span: int = 1) -> TableCellIR:
    return TableCellIR(row_span=row_span, col_span=col_span, text=text)


def cell_text(tc: etree._Element) -> str | None:
    t = tc.find(f"{qname('hp', 'subList')}/{qname('hp', 'p')}/{qname('hp', 'run')}/{qname('hp', 't')}")
    assert t is not None
    return t.text


def all_tc_in_document_order(tbl: etree._Element) -> list[etree._Element]:
    return tbl.findall(f"{qname('hp', 'tr')}/{qname('hp', 'tc')}")


# ---------------------------------------------------------------------------
# _resolve_cell_positions — 핵심 로직(unit-6-note.md §1-2) 직접 검증
# ---------------------------------------------------------------------------


def test_resolve_positions_no_merge_2x3_matches_row_major_divmod():
    """AC-1 기반: 병합 없는 2행 3열 표는 divmod와 동일한 좌표를 낸다."""
    cells = [make_cell(f"c{i}") for i in range(6)]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=3, cells=cells, has_merged_cells=False)
    positions = _resolve_cell_positions(block)
    assert positions == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]


def test_resolve_positions_horizontal_merge_matches_note_example():
    """AC-2 기반: unit-6-note.md §5 케이스2(가로 병합)와 동일한 입력 -> 동일한 출력."""
    cells = [make_cell("A", col_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    positions = _resolve_cell_positions(block)
    assert positions == [(0, 0), (1, 0), (1, 1)]


def test_resolve_positions_vertical_merge_matches_note_example():
    """AC-3 기반: unit-6-note.md §5 케이스3(세로 병합)과 동일한 입력 -> 동일한 출력."""
    cells = [make_cell("A", row_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    positions = _resolve_cell_positions(block)
    assert positions == [(0, 0), (0, 1), (1, 1)]


def test_resolve_positions_complex_corner_merge_in_3x3_grid():
    """위험 케이스(범위 확장): 3x3 그리드 좌상단에 2x2 병합 + 나머지 5개 단일 셀
    이라는, note의 단순 h/v 병합 예시보다 복잡한 "불규칙한" 배치에서도
    알고리즘이 올바른 좌표를 복원하는지 확인한다."""
    cells = [
        make_cell("A", row_span=2, col_span=2),  # (0,0)-(1,1) 점유
        make_cell("B"),  # (0,2)
        make_cell("C"),  # (1,2)
        make_cell("D"),  # (2,0)
        make_cell("E"),  # (2,1)
        make_cell("F"),  # (2,2)
    ]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=3, cols=3, cells=cells, has_merged_cells=True)
    positions = _resolve_cell_positions(block)
    assert positions == [(0, 0), (0, 2), (1, 2), (2, 0), (2, 1), (2, 2)]


def test_resolve_positions_single_cell_1x1_boundary():
    """경계값: 가장 작은 표(1x1, 병합 없음)."""
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("X")], has_merged_cells=False)
    assert _resolve_cell_positions(block) == [(0, 0)]


def test_resolve_positions_empty_grid_zero_rows_cols_no_exception():
    """위험 케이스(범위 밖이지만 명백히 있을 수 있는 빈 입력): rows=0, cols=0,
    cells=[]인 완전히 빈 표도 예외 없이 빈 좌표 리스트를 반환해야 한다."""
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=0, cols=0, cells=[], has_merged_cells=False)
    assert _resolve_cell_positions(block) == []


# ---------------------------------------------------------------------------
# AC-5: 경계/방어 검증 — _resolve_cell_positions 및 table_block_to_fragment 양쪽에서
# ---------------------------------------------------------------------------


def test_ac5_resolve_positions_insufficient_cells_raises_value_error():
    """AC-5-1: rows*cols=4인데 cells가 1개(부족)뿐인 손상된 입력 -> ValueError."""
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=[make_cell("only-one")], has_merged_cells=False)
    with pytest.raises(ValueError, match="rows=2, cols=2"):
        _resolve_cell_positions(block)


def test_ac5_table_block_to_fragment_insufficient_cells_raises_value_error():
    """AC-5-1을 공개 API(table_block_to_fragment) 경로로도 재확인 —
    조용히 잘못된 XML을 만들지 않고 ValueError가 전파되어야 한다."""
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=[make_cell("only-one")], has_merged_cells=False)
    with pytest.raises(ValueError):
        table_block_to_fragment(block)


def test_ac5_excess_cells_raises_value_error():
    """위험 케이스(범위 확장): rows*cols=1인데 cells가 2개(초과)인 손상된 입력.
    AC-5 원문은 "부족한" 경우만 명시하지만, 코드의 방어 로직(cell_idx != n_cells)이
    "초과" 방향도 실제로 막아주는지는 명백히 위험한 경계이므로 별도로 확인한다."""
    block = TableBlockIR(
        bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("A"), make_cell("B")], has_merged_cells=False
    )
    with pytest.raises(ValueError):
        _resolve_cell_positions(block)


def test_ac5_zero_cells_but_nonzero_grid_raises_value_error():
    """위험 케이스: rows/cols는 0이 아닌데 cells가 아예 빈 리스트(null에 준하는
    입력)인 경우도 "그리드 미점유"로 감지되어 ValueError가 나야 한다(조용히
    빈 표를 만들면 안 된다)."""
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=[], has_merged_cells=False)
    with pytest.raises(ValueError):
        _resolve_cell_positions(block)


def test_ac5_zero_row_span_degenerate_cell_raises_value_error():
    """내부 검증 2차에서 추가된 경계 케이스: row_span=0(퇴화된 손상 입력)인 셀은
    어떤 칸도 점유하지 못하므로 전체 그리드 점유 완료 검사에 걸려 ValueError가
    나야 한다(조용히 절반만 채워진 표를 반환하면 안 된다)."""
    block = TableBlockIR(
        bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("Z", row_span=0)], has_merged_cells=False
    )
    with pytest.raises(ValueError):
        _resolve_cell_positions(block)


# ---------------------------------------------------------------------------
# AC-1: 기본 동작 (병합 없음)
# ---------------------------------------------------------------------------


def test_ac1_1_basic_2x3_returns_single_tbl_with_matching_rowcnt_colcnt():
    cells = [make_cell(f"c{i}") for i in range(6)]
    block = TableBlockIR(bbox=(0.0, 0.0, 300.0, 200.0), rows=2, cols=3, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block)

    assert isinstance(tbl, etree._Element)
    assert etree.QName(tbl).localname == "tbl"
    assert tbl.get("rowCnt") == "2"
    assert tbl.get("colCnt") == "3"


def test_ac1_2_tr_count_matches_rows_and_tc_count_matches_rows_times_cols():
    cells = [make_cell(f"c{i}") for i in range(6)]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=3, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block)

    trs = tbl.findall(qname("hp", "tr"))
    assert len(trs) == 2
    total_tcs = sum(len(tr.findall(qname("hp", "tc"))) for tr in trs)
    assert total_tcs == 6


def test_ac1_3_rowaddr_coladdr_assigned_in_row_major_order():
    cells = [make_cell(f"c{i}") for i in range(6)]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=3, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block)

    tcs = all_tc_in_document_order(tbl)
    actual_addrs = [(tc.get("rowAddr"), tc.get("colAddr")) for tc in tcs]
    expected_addrs = [("0", "0"), ("0", "1"), ("0", "2"), ("1", "0"), ("1", "1"), ("1", "2")]
    assert actual_addrs == expected_addrs
    # 텍스트도 순서대로 c0..c5여야, 좌표뿐 아니라 "어떤 셀이 어떤 칸에 갔는지"까지 증명된다.
    assert [cell_text(tc) for tc in tcs] == [f"c{i}" for i in range(6)]


def test_ac1_4_no_merged_cells_flag_means_no_hasmergedcells_attribute():
    cells = [make_cell(f"c{i}") for i in range(4)]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block)
    assert tbl.get("hasMergedCells") is None


# ---------------------------------------------------------------------------
# AC-2: 가로 병합
# ---------------------------------------------------------------------------


def test_ac2_1_horizontal_merge_start_addr_and_colspan_correct():
    cells = [make_cell("A", col_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    tbl = table_block_to_fragment(block)

    tcs = all_tc_in_document_order(tbl)
    a_tc = tcs[0]
    assert cell_text(a_tc) == "A"
    assert a_tc.get("rowAddr") == "0"
    assert a_tc.get("colAddr") == "0"
    assert a_tc.get("colSpan") == "2"


def test_ac2_2_merged_covered_cells_do_not_get_separate_tc_total_matches_len_cells():
    cells = [make_cell("A", col_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    tbl = table_block_to_fragment(block)

    tcs = all_tc_in_document_order(tbl)
    assert len(tcs) == len(cells) == 3
    assert [cell_text(tc) for tc in tcs] == ["A", "B", "C"]


def test_ac2_3_has_merged_cells_true_sets_attribute():
    cells = [make_cell("A", col_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    tbl = table_block_to_fragment(block)
    assert tbl.get("hasMergedCells") == "1"


# ---------------------------------------------------------------------------
# AC-3: 세로 병합
# ---------------------------------------------------------------------------


def test_ac3_1_vertical_merge_rowspan_start_addr_and_tr_grouping():
    cells = [make_cell("A", row_span=2), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)
    tbl = table_block_to_fragment(block)

    trs = tbl.findall(qname("hp", "tr"))
    assert len(trs) == 2

    row0_tcs = trs[0].findall(qname("hp", "tc"))
    row1_tcs = trs[1].findall(qname("hp", "tc"))

    # row0에는 A(세로 병합 시작)와 B가 있어야 하고, row1에는 병합으로 덮인
    # (1,0) 칸의 tc가 생성되지 않아 C 하나만 있어야 한다.
    assert [cell_text(tc) for tc in row0_tcs] == ["A", "B"]
    assert [cell_text(tc) for tc in row1_tcs] == ["C"]

    a_tc = row0_tcs[0]
    assert a_tc.get("rowAddr") == "0"
    assert a_tc.get("colAddr") == "0"
    assert a_tc.get("rowSpan") == "2"

    c_tc = row1_tcs[0]
    assert c_tc.get("rowAddr") == "1"
    assert c_tc.get("colAddr") == "1"


# ---------------------------------------------------------------------------
# AC-4: 리스트 헬퍼
# ---------------------------------------------------------------------------


def test_ac4_1_table_blocks_to_fragments_returns_matching_count_and_order():
    block1 = TableBlockIR(
        bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("only-block1")], has_merged_cells=False
    )
    block2 = TableBlockIR(
        bbox=(0, 0, 0, 0), rows=1, cols=2, cells=[make_cell("b2-0"), make_cell("b2-1")], has_merged_cells=False
    )
    fragments = table_blocks_to_fragments([block1, block2])

    assert len(fragments) == 2
    assert fragments[0].get("colCnt") == "1"
    assert fragments[1].get("colCnt") == "2"
    # 순서 보존 확인 (내용으로 재확인).
    first_tc = fragments[0].find(f"{qname('hp', 'tr')}/{qname('hp', 'tc')}")
    assert cell_text(first_tc) == "only-block1"


def test_ac4_2_table_blocks_to_fragments_empty_list_returns_empty_list_no_exception():
    assert table_blocks_to_fragments([]) == []


def test_ac4_3_table_blocks_to_fragments_propagates_custom_shape_ids():
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("X")], has_merged_cells=False)
    fragments = table_blocks_to_fragments([block], char_shape_id="9", para_shape_id="8")
    tc = fragments[0].find(f"{qname('hp', 'tr')}/{qname('hp', 'tc')}")
    p = tc.find(f"{qname('hp', 'subList')}/{qname('hp', 'p')}")
    run = p.find(qname("hp", "run"))
    assert p.get("paraShapeIDRef") == "8"
    assert run.get("charShapeIDRef") == "9"


# ---------------------------------------------------------------------------
# AC-6: XML 구조 (모든 케이스 공통)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cells, rows, cols, has_merged",
    [
        ([make_cell(f"c{i}") for i in range(4)], 2, 2, False),  # 병합 없음
        ([make_cell("A", col_span=2), make_cell("B"), make_cell("C")], 2, 2, True),  # 가로 병합
        ([make_cell("A", row_span=2), make_cell("B"), make_cell("C")], 2, 2, True),  # 세로 병합
    ],
    ids=["plain", "hmerge", "vmerge"],
)
def test_ac6_1_all_variants_round_trip_well_formed(cells, rows, cols, has_merged):
    block = TableBlockIR(bbox=(1.0, 2.0, 3.0, 4.0), rows=rows, cols=cols, cells=cells, has_merged_cells=has_merged)
    tbl = table_block_to_fragment(block)
    assert_round_trips_as_well_formed(tbl)


def test_ac6_2_namespace_and_child_structure_matches_schema_contract():
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=1, cols=1, cells=[make_cell("셀내용")], has_merged_cells=False)
    tbl = table_block_to_fragment(block)

    assert etree.QName(tbl).localname == "tbl"
    assert tbl.tag == qname("hp", "tbl")
    assert tbl.tag == "{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl"

    tr = tbl.find(qname("hp", "tr"))
    assert tr is not None
    tc = tr.find(qname("hp", "tc"))
    assert tc is not None
    sub_list = tc.find(qname("hp", "subList"))
    assert sub_list is not None
    p = sub_list.find(qname("hp", "p"))
    assert p is not None
    run = p.find(qname("hp", "run"))
    assert run is not None
    t = run.find(qname("hp", "t"))
    assert t is not None
    assert t.text == "셀내용"


# ---------------------------------------------------------------------------
# 추가 위험 케이스 (AC 범위 밖이지만 "명백히 위험한 케이스"로서 확인)
# ---------------------------------------------------------------------------


def test_risk_empty_table_zero_rows_cols_produces_empty_tbl_without_exception():
    """빈 입력(0행 0열, 셀 없음)도 예외 없이 빈 <hp:tbl>을 만들어야 한다
    (hwpx_kernel/schema.py의 동일 성격 경계값 테스트와 대응)."""
    block = TableBlockIR(bbox=(0.0, 0.0, 0.0, 0.0), rows=0, cols=0, cells=[], has_merged_cells=False)
    tbl = table_block_to_fragment(block)
    assert tbl.get("rowCnt") == "0"
    assert tbl.get("colCnt") == "0"
    assert tbl.findall(qname("hp", "tr")) == []
    assert_round_trips_as_well_formed(tbl)


def test_risk_empty_cell_text_boundary_does_not_crash():
    """빈 셀(텍스트가 빈 문자열인 TableCellIR, table_recognizer.py가 실제로
    만들어내는 값 — 원본이 None이면 ""로 치환됨)도 예외 없이 처리된다."""
    cells = [make_cell(""), make_cell("non-empty")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=1, cols=2, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block)
    tcs = all_tc_in_document_order(tbl)
    assert cell_text(tcs[0]) in (None, "")
    assert cell_text(tcs[1]) == "non-empty"
    assert_round_trips_as_well_formed(tbl)


def test_risk_complex_corner_merge_end_to_end_fragment_structure():
    """위험 케이스(범위 확장): _resolve_cell_positions 레벨에서만이 아니라
    실제 fragment(tr/tc 그룹핑)까지 3x3 좌상단 2x2 병합 케이스가 올바른지 확인한다."""
    cells = [
        make_cell("A", row_span=2, col_span=2),
        make_cell("B"),
        make_cell("C"),
        make_cell("D"),
        make_cell("E"),
        make_cell("F"),
    ]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=3, cols=3, cells=cells, has_merged_cells=True)
    tbl = table_block_to_fragment(block)

    trs = tbl.findall(qname("hp", "tr"))
    assert len(trs) == 3  # row0(A,B), row1(C만 — A의 세로병합이 (1,0)/(1,1) 덮음), row2(D,E,F)

    assert [cell_text(tc) for tc in trs[0].findall(qname("hp", "tc"))] == ["A", "B"]
    assert [cell_text(tc) for tc in trs[1].findall(qname("hp", "tc"))] == ["C"]
    assert [cell_text(tc) for tc in trs[2].findall(qname("hp", "tc"))] == ["D", "E", "F"]

    a_tc = trs[0].findall(qname("hp", "tc"))[0]
    assert a_tc.get("rowSpan") == "2"
    assert a_tc.get("colSpan") == "2"
    assert_round_trips_as_well_formed(tbl)


def test_risk_bboxpt_attribute_format_matches_schema_convention():
    """unit-6-note.md §1-5: bbox는 schema.py의 다른 프래그먼트(hp:p 등)와 동일한
    "x0.00,y0.00,x1.00,y1.00" 형식의 bboxPt 문자열 속성으로 부착되어야 한다."""
    block = TableBlockIR(
        bbox=(1.5, 2.25, 30.0, 40.125), rows=1, cols=1, cells=[make_cell("X")], has_merged_cells=False
    )
    tbl = table_block_to_fragment(block)
    assert tbl.get("bboxPt") == "1.50,2.25,30.00,40.12"


def test_risk_custom_char_and_para_shape_ids_propagate_to_cell_fragment():
    """table_block_to_fragment의 char_shape_id/para_shape_id 키워드 인자가
    실제로 각 셀의 hp:p/hp:run에 전달되는지 확인한다(기본값 "0"이 아닌 값으로)."""
    cells = [make_cell("X")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=1, cols=1, cells=cells, has_merged_cells=False)
    tbl = table_block_to_fragment(block, char_shape_id="5", para_shape_id="4")
    tc = tbl.find(f"{qname('hp', 'tr')}/{qname('hp', 'tc')}")
    p = tc.find(f"{qname('hp', 'subList')}/{qname('hp', 'p')}")
    run = p.find(qname("hp", "run"))
    assert p.get("paraShapeIDRef") == "4"
    assert run.get("charShapeIDRef") == "5"


def test_risk_oversized_col_span_beyond_grid_bounds_is_not_rejected():
    """**알려진 한계(결함, DEF-001로 기록)**: cell.col_span이 실제 block.cols보다
    큰 손상된 입력(예: colCnt=2인데 한 셀의 col_span=5)을 넣으면, 점유 배열은
    grid 경계로 클램프되어 "칸 수/전체 점유" 검증(AC-5, 1-4절)은 통과해 버리고,
    ValueError 없이 colSpan="5" > colCnt="2"인 내적으로 불일치한(그러나
    well-formed한) XML이 그대로 만들어진다. 이 테스트는 그 현재 동작을 고정해
    회귀를 잡아내는 용도이며, PASS를 의미하지 않는다 — 6절 결함 목록 DEF-001 참고.
    """
    cells = [make_cell("A", col_span=5), make_cell("B"), make_cell("C")]
    block = TableBlockIR(bbox=(0, 0, 0, 0), rows=2, cols=2, cells=cells, has_merged_cells=True)

    tbl = table_block_to_fragment(block)  # ValueError가 나지 않는다(현재 동작).
    a_tc = tbl.find(f"{qname('hp', 'tr')}/{qname('hp', 'tc')}")
    assert tbl.get("colCnt") == "2"
    assert a_tc.get("colSpan") == "5"  # 선언된 colCnt(2)보다 큰 값이 그대로 새어나감.
    assert_round_trips_as_well_formed(tbl)  # XML 자체는 well-formed하다(파싱 오류는 아님).
