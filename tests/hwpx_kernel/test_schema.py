"""unit-4 AC-2 — `pdf_to_hwpx/hwpx_kernel/schema.py` (IR->XML 프래그먼트 계약) 검증.

근거: docs/harness/units/unit-4-note.md §7 AC-2(1~7번),
docs/harness/decisions.md DEC-017.

**범위의 근본적 한계(반드시 읽을 것)**: 여기서 "well-formed XML이고 기대하는
태그/네임스페이스를 갖는다"는 것만 증명한다. 태그/속성 이름 자체(`hp:p`,
`binDataIDRef` 등)가 실제 한글(한컴오피스)이 요구하는 정확한 스펙과 일치하는지는
개발 환경에 한글이 없어 검증하지 못했다(DEC-017, unit-4-test.md §8 참고).
"""

from __future__ import annotations

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.hwpx_kernel.schema import (
    HWPUNIT_PER_POINT,
    SCHEMA_VERSION,
    build_reference_section_body,
    fragment_to_bytes,
    image_block_to_picture_fragment,
    pt_to_hwpunit,
    table_block_to_table_fragment,
    table_cell_to_cell_fragment,
    text_block_to_paragraph_fragment,
)
from pdf_to_hwpx.pdf_reader.ir import (
    ImageBlockIR,
    TableBlockIR,
    TableCellIR,
    TextBlockIR,
)


def qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def assert_round_trips_as_well_formed(element: etree._Element) -> bytes:
    """프래그먼트를 직렬화 -> 재파싱해 well-formed임을 실제로 증명한다."""
    data = fragment_to_bytes(element)
    reparsed = etree.fromstring(data)
    assert reparsed.tag == element.tag
    return data


# ---------------------------------------------------------------------------
# AC-2-1, AC-2-2: 모듈 상수/변환 헬퍼
# ---------------------------------------------------------------------------


def test_schema_version_is_1_0():
    assert SCHEMA_VERSION == "1.0"


@pytest.mark.parametrize(
    "value_pt, expected_hwpunit",
    [
        (1.0, 100),
        (0.0, 0),
        (10.0, 1000),
        (0.5, 50),
    ],
)
def test_pt_to_hwpunit_conversion(value_pt, expected_hwpunit):
    assert pt_to_hwpunit(value_pt) == expected_hwpunit


def test_hwpunit_per_point_constant_matches_conversion_factor():
    assert HWPUNIT_PER_POINT == 100
    assert pt_to_hwpunit(1.0) == HWPUNIT_PER_POINT


def test_pt_to_hwpunit_negative_value_does_not_raise():
    """경계값: 음수 좌표(bbox 계산 오류로 발생할 수 있는 값)를 넣어도 예외 없이
    정수로 변환된다(검증 자체는 이 함수의 책임이 아님 — 상위 unit이 bbox 유효성을
    보장한다는 계약, unit-4-note.md 2-2절)."""
    assert pt_to_hwpunit(-5.0) == -500


# ---------------------------------------------------------------------------
# AC-2-3: text_block_to_paragraph_fragment — 정상 경로(한글 텍스트) + 경계값
# ---------------------------------------------------------------------------


def _make_text_block(**overrides) -> TextBlockIR:
    defaults = dict(
        bbox=(10.0, 20.0, 100.0, 40.0),
        text="안녕하세요 한글 변환 테스트",  # 안녕하세요 한글 변환 테스트
        font_name="함초체",  # 함초체
        font_size=12.0,
        bold=False,
        italic=False,
        to_unicode_missing=False,
    )
    defaults.update(overrides)
    return TextBlockIR(**defaults)


def test_text_block_to_paragraph_fragment_basic_structure_and_korean_text():
    block = _make_text_block()
    p = text_block_to_paragraph_fragment(block)

    assert isinstance(p, etree._Element)
    assert etree.QName(p).localname == "p"
    assert p.tag == qname("hp", "p")
    # AC-2-3 원문 그대로: NAMESPACES 상수를 거치지 않고 리터럴 문자열로도 재확인
    # (NAMESPACES 자체가 실수로 바뀌어도 이 단언은 별도로 잡아낸다).
    assert p.tag == "{http://www.hancom.co.kr/hwpml/2011/paragraph}p"

    run = p.find(qname("hp", "run"))
    assert run is not None
    t = run.find(qname("hp", "t"))
    assert t is not None
    assert t.text == block.text

    assert_round_trips_as_well_formed(p)


def test_text_block_to_paragraph_fragment_bbox_attribute_preserved():
    block = _make_text_block(bbox=(1.5, 2.5, 3.5, 4.5))
    p = text_block_to_paragraph_fragment(block)
    assert p.get("bboxPt") == "1.50,2.50,3.50,4.50"


def test_text_block_to_paragraph_fragment_bold_italic_font_attributes():
    block = _make_text_block(bold=True, italic=True, font_size=14.0)
    p = text_block_to_paragraph_fragment(block)
    run = p.find(qname("hp", "run"))
    assert run.get("bold") == "1"
    assert run.get("italic") == "1"
    assert run.get("fontName") == block.font_name
    assert run.get("fontSizeHwpunit") == str(pt_to_hwpunit(14.0))


def test_text_block_to_paragraph_fragment_omits_optional_attrs_when_falsy():
    block = _make_text_block(bold=False, italic=False, font_name=None, font_size=None)
    p = text_block_to_paragraph_fragment(block)
    run = p.find(qname("hp", "run"))
    assert run.get("bold") is None
    assert run.get("italic") is None
    assert run.get("fontName") is None
    assert run.get("fontSizeHwpunit") is None


def test_text_block_to_paragraph_fragment_custom_shape_ids():
    block = _make_text_block()
    p = text_block_to_paragraph_fragment(block, char_shape_id="7", para_shape_id="3")
    assert p.get("paraShapeIDRef") == "3"
    run = p.find(qname("hp", "run"))
    assert run.get("charShapeIDRef") == "7"


def test_text_block_to_paragraph_fragment_empty_text_boundary():
    """경계값: 빈 문자열 텍스트도 예외 없이 처리되고 well-formed하다."""
    block = _make_text_block(text="")
    p = text_block_to_paragraph_fragment(block)
    run = p.find(qname("hp", "run"))
    t = run.find(qname("hp", "t"))
    assert t.text in (None, "")
    assert_round_trips_as_well_formed(p)


def test_text_block_to_paragraph_fragment_replacement_char_passthrough():
    """REQ-007 계약: to_unicode_missing=True인 경우 이미 치환된 텍스트를
    그대로 통과시키고 추가로 치환하지 않는다."""
    block = _make_text_block(text="정상텍스트□누락", to_unicode_missing=True)
    p = text_block_to_paragraph_fragment(block)
    t = p.find(qname("hp", "run")).find(qname("hp", "t"))
    assert t.text == block.text
    assert "□" in t.text


# ---------------------------------------------------------------------------
# AC-2-4: table_cell_to_cell_fragment / table_block_to_table_fragment
# ---------------------------------------------------------------------------


def _make_cell(text: str, row_span: int = 1, col_span: int = 1) -> TableCellIR:
    return TableCellIR(row_span=row_span, col_span=col_span, text=text)


def test_table_cell_to_cell_fragment_basic():
    cell = _make_cell("셀내용", row_span=2, col_span=3)  # 셀내용
    tc = table_cell_to_cell_fragment(cell, row=1, col=2)

    assert etree.QName(tc).localname == "tc"
    assert tc.get("rowAddr") == "1"
    assert tc.get("colAddr") == "2"
    assert tc.get("rowSpan") == "2"
    assert tc.get("colSpan") == "3"

    t = tc.find(f"{qname('hp', 'subList')}/{qname('hp', 'p')}/{qname('hp', 'run')}/{qname('hp', 't')}")
    assert t is not None
    assert t.text == cell.text
    assert_round_trips_as_well_formed(tc)


def test_table_block_to_table_fragment_2x2_produces_2_rows_4_cells():
    cells = [
        _make_cell("A1"),
        _make_cell("A2"),
        _make_cell("B1"),
        _make_cell("B2"),
    ]
    block = TableBlockIR(
        bbox=(0.0, 0.0, 200.0, 100.0),
        rows=2,
        cols=2,
        cells=cells,
        has_merged_cells=False,
    )
    tbl = table_block_to_table_fragment(block)

    assert etree.QName(tbl).localname == "tbl"
    assert tbl.get("rowCnt") == "2"
    assert tbl.get("colCnt") == "2"
    assert tbl.get("hasMergedCells") is None

    trs = tbl.findall(qname("hp", "tr"))
    assert len(trs) == 2
    total_tcs = sum(len(tr.findall(qname("hp", "tc"))) for tr in trs)
    assert total_tcs == 4

    # 행 우선 순서로 텍스트가 배치되었는지 확인 (divmod 계약).
    all_texts = [
        tc.find(f"{qname('hp', 'subList')}/{qname('hp', 'p')}/{qname('hp', 'run')}/{qname('hp', 't')}").text
        for tr in trs
        for tc in tr.findall(qname("hp", "tc"))
    ]
    assert all_texts == ["A1", "A2", "B1", "B2"]

    assert_round_trips_as_well_formed(tbl)


def test_table_block_to_table_fragment_merged_cells_flag_sets_attribute():
    block = TableBlockIR(
        bbox=(0.0, 0.0, 100.0, 100.0),
        rows=1,
        cols=1,
        cells=[_make_cell("병합셀", row_span=1, col_span=1)],  # 병합셀
        has_merged_cells=True,
    )
    tbl = table_block_to_table_fragment(block)
    assert tbl.get("hasMergedCells") == "1"


def test_table_block_to_table_fragment_empty_cells_boundary():
    """경계값: 셀이 0개인 표(rows=0, cols=0)도 예외 없이 빈 <hp:tbl>을 만든다."""
    block = TableBlockIR(bbox=(0.0, 0.0, 0.0, 0.0), rows=0, cols=0, cells=[], has_merged_cells=False)
    tbl = table_block_to_table_fragment(block)
    assert tbl.get("rowCnt") == "0"
    assert tbl.get("colCnt") == "0"
    assert tbl.findall(qname("hp", "tr")) == []
    assert_round_trips_as_well_formed(tbl)


def test_table_block_to_table_fragment_ragged_cell_count_does_not_crash():
    """경계값(위험 케이스): cols*rows보다 셀 개수가 적은 "안 맞는" 입력이 와도
    divmod 기반 배치가 예외 없이 동작한다(단순화된 기본 구현의 알려진 한계,
    unit-4-note.md 2-2절 — 실제 병합 셀은 unit-6이 table_cell_to_cell_fragment를
    직접 호출해야 한다는 계약의 근거가 되는 케이스)."""
    block = TableBlockIR(
        bbox=(0.0, 0.0, 100.0, 100.0),
        rows=2,
        cols=2,
        cells=[_make_cell("온솔")],  # 온셀 — 셀 1개만 있음(3개 부족)
        has_merged_cells=True,
    )
    tbl = table_block_to_table_fragment(block)
    trs = tbl.findall(qname("hp", "tr"))
    assert len(trs) == 1  # 셀 1개 -> row 0 하나만 생성됨
    assert_round_trips_as_well_formed(tbl)


# ---------------------------------------------------------------------------
# AC-2-5: image_block_to_picture_fragment
# ---------------------------------------------------------------------------


def test_image_block_to_picture_fragment_bin_data_id_ref():
    block = ImageBlockIR(bbox=(0.0, 0.0, 72.0, 144.0), raw_bytes=b"\x89PNG\r\n\x1a\n", image_format="png")
    pic = image_block_to_picture_fragment(block, bin_data_id="X")

    assert etree.QName(pic).localname == "pic"
    assert pic.get("binDataIDRef") == "X"
    assert pic.get("format") == "png"
    assert_round_trips_as_well_formed(pic)


def test_image_block_to_picture_fragment_position_and_size_hwpunit():
    block = ImageBlockIR(bbox=(10.0, 20.0, 30.0, 60.0), raw_bytes=b"data", image_format="jpeg")
    pic = image_block_to_picture_fragment(block, bin_data_id="bin0")

    pos = pic.find(qname("hp", "pos"))
    sz = pic.find(qname("hp", "sz"))
    assert pos.get("xHwpunit") == str(pt_to_hwpunit(10.0))
    assert pos.get("yHwpunit") == str(pt_to_hwpunit(20.0))
    assert sz.get("widthHwpunit") == str(pt_to_hwpunit(20.0))  # 30-10
    assert sz.get("heightHwpunit") == str(pt_to_hwpunit(40.0))  # 60-20


def test_image_block_to_picture_fragment_zero_size_boundary():
    """경계값: 너비/높이가 0인 이미지(bbox 좌표가 같은 경우)도 예외 없이 처리된다."""
    block = ImageBlockIR(bbox=(5.0, 5.0, 5.0, 5.0), raw_bytes=b"", image_format="png")
    pic = image_block_to_picture_fragment(block, bin_data_id="bin1")
    sz = pic.find(qname("hp", "sz"))
    assert sz.get("widthHwpunit") == "0"
    assert sz.get("heightHwpunit") == "0"


# ---------------------------------------------------------------------------
# AC-2-6: fragment_to_bytes — XML 선언 미포함
# ---------------------------------------------------------------------------


def test_fragment_to_bytes_has_no_xml_declaration():
    block = _make_text_block()
    p = text_block_to_paragraph_fragment(block)
    data = fragment_to_bytes(p)
    assert not data.startswith(b"<?xml")
    assert b"<?xml" not in data


def test_fragment_to_bytes_preserves_korean_text_utf8():
    block = _make_text_block(text="한글 UTF-8 인코딩 확인")  # 한글 UTF-8 인코딩 확인
    p = text_block_to_paragraph_fragment(block)
    data = fragment_to_bytes(p)
    assert block.text.encode("utf-8") in data


# ---------------------------------------------------------------------------
# 참고용 편의 함수 build_reference_section_body — 계약의 필수부분은 아니지만
# unit-4가 로컬 동작 확인에 쓴 조립기이므로, 여러 프래그먼트 혼합 시에도
# well-formed한지 확인한다.
# ---------------------------------------------------------------------------


def test_build_reference_section_body_combines_fragments_well_formed():
    text_block = _make_text_block()
    p = text_block_to_paragraph_fragment(text_block)

    table_block = TableBlockIR(
        bbox=(0.0, 0.0, 50.0, 50.0),
        rows=1,
        cols=1,
        cells=[_make_cell("표")],  # 표
        has_merged_cells=False,
    )
    tbl = table_block_to_table_fragment(table_block)

    image_block = ImageBlockIR(bbox=(0.0, 0.0, 10.0, 10.0), raw_bytes=b"x", image_format="png")
    pic = image_block_to_picture_fragment(image_block, bin_data_id="bin0")

    section_bytes = build_reference_section_body([p, tbl, pic])

    assert section_bytes.startswith(b"<?xml")
    root = etree.fromstring(section_bytes)
    assert etree.QName(root).localname == "sec"
    assert root.tag == qname("hs", "sec")

    # 세 프래그먼트가 모두 자식으로 들어가 있고, 각자의 태그를 유지한다.
    child_localnames = [etree.QName(child).localname for child in root]
    assert child_localnames == ["p", "tbl", "pic"]


def test_build_reference_section_body_empty_fragment_list_is_well_formed():
    """경계값: 프래그먼트가 하나도 없는 경우도 예외 없이 빈 <hs:sec/>를 만든다."""
    section_bytes = build_reference_section_body([])
    root = etree.fromstring(section_bytes)
    assert etree.QName(root).localname == "sec"
    assert len(root) == 0
