"""schema.py: OWPML 요소 팩토리 (T1). 자체 속성이 없는지, 관찰된 순서인지 확인한다."""

from __future__ import annotations

import pytest
from lxml import etree

from pdf_to_hwpx.common.exceptions import HwpxSchemaError, HwpxWriteError
from pdf_to_hwpx.hwpx_kernel import schema

from .helpers import FORBIDDEN_NAMES, NS


def names(el):
    return [etree.QName(c).localname for c in el]


def test_schema_version_is_2():
    assert schema.SCHEMA_VERSION == "2.0"


def test_sanitize_text():
    assert schema.sanitize_text("a\tb\nc\rd") == "a b c d"
    assert schema.sanitize_text("x\x00y\x0bz\x1f") == "xyz"
    assert schema.sanitize_text("\ud800잘못된") == "잘못된"
    assert schema.sanitize_text("한글 & <tag>") == "한글 & <tag>"
    assert schema.sanitize_text("￾￿") == ""


def test_make_run_variants():
    plain = schema.make_run(3, "안녕")
    assert dict(plain.attrib) == {"charPrIDRef": "3"}
    assert names(plain) == ["t"] and plain[0].text == "안녕"
    empty = schema.make_run(0)
    assert len(empty) == 0
    empty_text = schema.make_run(0, "")
    assert names(empty_text) == ["t"] and empty_text[0].text is None
    child = etree.Element(f"{{{NS['hp']}}}ctrl")
    with_child = schema.make_run(0, children=[child])
    assert names(with_child) == ["ctrl", "t"]  # 자식 다음에 빈 t (분석서 6-3)


def test_make_run_sanitizes_and_escapes():
    run = schema.make_run(0, "a\x00<b>&")
    data = etree.tostring(run)
    assert b"a&lt;b&gt;&amp;" in data


def test_lineseg_relations():
    seg = schema.make_lineseg(vertpos=100, vertsize=1200, horzpos=0, horzsize=42522)
    assert dict(seg.attrib) == {
        "textpos": "0", "vertpos": "100", "vertsize": "1200", "textheight": "1200",
        "baseline": "1020", "spacing": "0", "horzpos": "0", "horzsize": "42522", "flags": "393216",
    }
    assert list(seg.attrib) == [
        "textpos", "vertpos", "vertsize", "textheight", "baseline", "spacing", "horzpos", "horzsize", "flags"
    ]
    # 분석서 7절 예: 표 높이 2580 -> baseline 2193
    assert schema.make_lineseg(vertpos=0, vertsize=2580, horzpos=0, horzsize=1).get("baseline") == "2193"


def test_make_paragraph_structure():
    p = schema.make_paragraph(
        para_pr_id=4,
        runs=[schema.make_run(1, "a"), schema.make_run(2, "b")],
        linesegs=[schema.make_lineseg(vertpos=0, vertsize=1000, horzpos=0, horzsize=100)],
        page_break=True,
    )
    assert list(p.attrib) == ["id", "paraPrIDRef", "styleIDRef", "pageBreak", "columnBreak", "merged"]
    assert p.get("id") == "2147483648" and p.get("paraPrIDRef") == "4"
    assert (p.get("styleIDRef"), p.get("pageBreak"), p.get("columnBreak"), p.get("merged")) == ("0", "1", "0", "0")
    assert names(p) == ["run", "run", "linesegarray"]


def test_make_paragraph_without_lineseg_and_run_required():
    p = schema.make_paragraph(para_pr_id=0, runs=[schema.make_run(0)])
    assert names(p) == ["run"]
    p2 = schema.make_paragraph(para_pr_id=0, runs=[schema.make_run(0)], linesegs=[])
    assert names(p2) == ["run"]
    with pytest.raises(HwpxSchemaError):
        schema.make_paragraph(para_pr_id=0, runs=[])
    assert issubclass(HwpxSchemaError, HwpxWriteError)


def para(text="x"):
    return schema.make_paragraph(para_pr_id=0, runs=[schema.make_run(0, text)])


def cell(col, row, cs=1, rs=1, w=1000, h=500):
    return schema.make_table_cell(
        col=col, row=row, col_span=cs, row_span=rs, width=w, height=h, border_fill_id=2, paragraphs=[para()]
    )


def test_table_cell_structure_and_order():
    tc = cell(1, 2, cs=2, rs=3, w=2000, h=1500)
    assert list(tc.attrib) == ["name", "header", "hasMargin", "protect", "editable", "dirty", "borderFillIDRef"]
    assert names(tc) == ["subList", "cellAddr", "cellSpan", "cellSz", "cellMargin"]
    assert dict(tc.find("hp:cellAddr", NS).attrib) == {"colAddr": "1", "rowAddr": "2"}
    assert dict(tc.find("hp:cellSpan", NS).attrib) == {"colSpan": "2", "rowSpan": "3"}
    assert dict(tc.find("hp:cellSz", NS).attrib) == {"width": "2000", "height": "1500"}
    assert dict(tc.find("hp:cellMargin", NS).attrib) == {"left": "141", "right": "141", "top": "141", "bottom": "141"}
    sub = tc.find("hp:subList", NS)
    assert sub.get("vertAlign") == "CENTER" and sub.get("id") == "" and len(sub.attrib) == 10


def test_table_cell_validation():
    with pytest.raises(HwpxSchemaError):
        schema.make_table_cell(col=0, row=0, col_span=1, row_span=1, width=1, height=1, border_fill_id=1, paragraphs=[])
    with pytest.raises(HwpxSchemaError):
        schema.make_table_cell(
            col=0, row=0, col_span=1, row_span=1, width=1, height=1, border_fill_id=1,
            paragraphs=[para()], vert_align="MIDDLE",
        )
    with pytest.raises(HwpxSchemaError):
        schema.make_table_cell(
            col=0, row=0, col_span=0, row_span=1, width=1, height=1, border_fill_id=1, paragraphs=[para()]
        )


def make_tbl(rows, row_cnt, col_cnt):
    return schema.make_table(
        tbl_id=1000000001, z_order=0, rows=rows, row_cnt=row_cnt, col_cnt=col_cnt,
        width=2000, height=1000, border_fill_id=2,
    )


def test_table_structure_2x2():
    tbl = make_tbl([[cell(0, 0), cell(1, 0)], [cell(0, 1), cell(1, 1)]], 2, 2)
    assert list(tbl.attrib) == [
        "id", "zOrder", "numberingType", "textWrap", "textFlow", "lock", "dropcapstyle", "pageBreak",
        "repeatHeader", "rowCnt", "colCnt", "cellSpacing", "borderFillIDRef", "noAdjust",
    ]
    assert tbl.get("pageBreak") == "CELL" and tbl.get("dropcapstyle") == "None"
    assert names(tbl) == ["sz", "pos", "outMargin", "inMargin", "tr", "tr"]
    pos = tbl.find("hp:pos", NS)
    assert pos.get("treatAsChar") == "1" and pos.get("horzRelTo") == "PARA"
    assert tbl.find("hp:sz", NS).get("widthRelTo") == "ABSOLUTE"
    assert tbl.find("hp:outMargin", NS).get("left") == "141"
    assert tbl.find("hp:inMargin", NS).get("top") == "140"
    assert len(tbl.findall("hp:tr/hp:tc", NS)) == 4


def test_table_merged_cells_skip_covered():
    rows = [
        [cell(0, 0, cs=3)],
        [cell(0, 1, rs=2), cell(1, 1), cell(2, 1)],
        [cell(1, 2), cell(2, 2)],
    ]
    tbl = make_tbl(rows, 3, 3)
    assert [len(tr) for tr in tbl.findall("hp:tr", NS)] == [1, 3, 2]


@pytest.mark.parametrize(
    "rows, row_cnt, col_cnt",
    [
        ([[cell(0, 0)]], 2, 1),  # tr 수 != rowCnt
        ([[cell(0, 0)], [cell(0, 0)]], 2, 1),  # rowAddr != tr 인덱스
        ([[cell(1, 0), cell(0, 0)]], 1, 2),  # colAddr 역순
        ([[cell(0, 0, cs=2), cell(1, 0)]], 1, 2),  # 겹침
        ([[cell(0, 0)]], 1, 2),  # 덮이지 않음
        ([[cell(0, 0, cs=3)]], 1, 2),  # 그리드 밖
    ],
)
def test_table_grid_errors(rows, row_cnt, col_cnt):
    with pytest.raises(HwpxSchemaError):
        make_tbl(rows, row_cnt, col_cnt)


def test_table_argument_validation():
    good = [[cell(0, 0)]]
    with pytest.raises(HwpxSchemaError):
        schema.make_table(
            tbl_id=1, z_order=0, rows=good, row_cnt=1, col_cnt=1, width=1, height=1,
            border_fill_id=1, page_break="ALL",
        )
    with pytest.raises(HwpxSchemaError):
        schema.make_table(tbl_id=1, z_order=0, rows=good, row_cnt=1, col_cnt=1, width=0, height=1, border_fill_id=1)


def test_no_nonstandard_names_in_factories():
    tbl = make_tbl([[cell(0, 0)]], 1, 1)
    p = schema.make_paragraph(para_pr_id=0, runs=[schema.make_run(0, children=[tbl])])
    for el in p.iter():
        assert etree.QName(el).localname not in FORBIDDEN_NAMES
        assert not ({etree.QName(k).localname for k in el.attrib} & FORBIDDEN_NAMES)


def test_old_ir_direct_api_is_gone():
    assert not hasattr(schema, "text_block_to_paragraph_fragment")
    assert not hasattr(schema, "build_reference_section_body")
