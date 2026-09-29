"""section.py: PageSetup, secPr, hs:sec (T1)."""

from __future__ import annotations

import re

import pytest
from lxml import etree

from pdf_to_hwpx.common.exceptions import HwpxSchemaError
from pdf_to_hwpx.hwpx_kernel import section
from pdf_to_hwpx.hwpx_kernel.schema import make_paragraph, make_run
from pdf_to_hwpx.hwpx_kernel.section import PageSetup

from .helpers import NS


def names(el):
    return [etree.QName(c).localname for c in el]


def one_para(text="x", children=()):
    return make_paragraph(para_pr_id=0, runs=[make_run(0, text, children=children)])


def test_a4_matches_observed_values():
    p = PageSetup.a4()
    assert (p.width, p.height) == (59528, 84188)
    assert (p.margin_left, p.margin_right, p.margin_top, p.margin_bottom) == (8503, 8503, 5669, 4251)
    assert (p.margin_header, p.margin_footer, p.margin_gutter) == (4251, 4251, 0)
    assert p.landscape == "WIDELY"
    assert p.text_width == 42522 and p.text_height == 74268


def test_page_setup_rejects_impossible_geometry():
    with pytest.raises(HwpxSchemaError):
        PageSetup(0, 100, 0, 0, 0, 0)
    with pytest.raises(HwpxSchemaError):
        PageSetup(1000, 1000, 600, 600, 0, 0)


def test_from_content_bounds_conversion_and_clamps():
    p = PageSetup.from_content_bounds(595.28, 841.89, 85, 510, 56.7, 780)
    assert p.width == 59528 and p.height == 84189
    assert (p.margin_left, p.margin_right) == (8500, 59528 - 51000)
    assert p.margin_top == 5670
    assert p.margin_bottom == 84189 - 78000
    assert p.margin_header == 4251 and p.margin_footer == 4251
    # 너무 좁은/넓은 여백은 클램프 (10~50 mm)
    tight = PageSetup.from_content_bounds(595.28, 841.89, 5, 590, 5, 838)
    assert tight.margin_left == 2835 and tight.margin_right == 2835
    assert tight.margin_top == 4251 and tight.margin_bottom == 4251
    wide = PageSetup.from_content_bounds(595.28, 841.89, 300, 320, 300, 320)
    assert wide.margin_left == 14173 and wide.margin_top == 14173
    assert wide.margin_header == 4251


def test_sec_pr_attributes_and_child_order():
    sec = section.build_sec_pr(PageSetup.a4())
    assert dict(sec.attrib) == {
        "id": "", "textDirection": "HORIZONTAL", "spaceColumns": "1134", "tabStop": "8000",
        "tabStopVal": "4000", "tabStopUnit": "HWPUNIT", "outlineShapeIDRef": "1",
        "memoShapeIDRef": "0", "textVerticalWidthHead": "0", "masterPageCnt": "0",
    }
    assert names(sec) == [
        "grid", "startNum", "visibility", "lineNumberShape", "pagePr", "footNotePr", "endNotePr",
        "pageBorderFill", "pageBorderFill", "pageBorderFill",
    ]
    assert [f.get("type") for f in sec.findall("hp:pageBorderFill", NS)] == ["BOTH", "EVEN", "ODD"]
    assert sec.find("hp:masterPage", NS) is None
    page_pr = sec.find("hp:pagePr", NS)
    assert dict(page_pr.attrib) == {
        "landscape": "WIDELY", "width": "59528", "height": "84188", "gutterType": "LEFT_ONLY"
    }
    assert dict(page_pr.find("hp:margin", NS).attrib) == {
        "header": "4251", "footer": "4251", "gutter": "0", "left": "8503", "right": "8503",
        "top": "5669", "bottom": "4251",
    }
    foot = sec.find("hp:footNotePr", NS)
    assert names(foot) == ["autoNumFormat", "noteLine", "noteSpacing", "numbering", "placement"]
    assert foot.find("hp:placement", NS).get("place") == "EACH_COLUMN"
    assert sec.find("hp:endNotePr/hp:placement", NS).get("place") == "END_OF_DOCUMENT"
    assert sec.find("hp:pageBorderFill", NS).get("borderFillIDRef") == "1"


def test_sec_pr_uses_given_page_setup():
    page = PageSetup(70000, 90000, 3000, 4000, 5000, 6000, margin_header=3000, margin_footer=3500)
    sec = section.build_sec_pr(page)
    pp = sec.find("hp:pagePr", NS)
    assert (pp.get("width"), pp.get("height")) == ("70000", "90000")
    m = pp.find("hp:margin", NS)
    assert (m.get("left"), m.get("right"), m.get("top"), m.get("bottom")) == ("3000", "4000", "5000", "6000")
    assert (m.get("header"), m.get("footer")) == ("3000", "3500")


def test_inject_puts_secpr_then_colpr_before_text():
    p = one_para("본문")
    section.inject_section_properties(p, PageSetup.a4())
    run = p.find("hp:run", NS)
    assert names(run) == ["secPr", "ctrl", "t"]
    assert run.find("hp:ctrl/hp:colPr", NS).get("type") == "NEWSPAPER"


def test_inject_before_table_keeps_observed_order():
    tbl = etree.Element(f"{{{NS['hp']}}}tbl")
    p = one_para("", children=[tbl])
    section.inject_section_properties(p, PageSetup.a4())
    assert names(p.find("hp:run", NS)) == ["secPr", "ctrl", "tbl", "t"]


def test_inject_adds_empty_t_when_missing_and_rejects_duplicates():
    p = make_paragraph(para_pr_id=0, runs=[make_run(0)])
    section.inject_section_properties(p, PageSetup.a4())
    assert names(p.find("hp:run", NS)) == ["secPr", "ctrl", "t"]
    with pytest.raises(HwpxSchemaError):
        section.inject_section_properties(p, PageSetup.a4())


def test_inject_rejects_paragraph_without_run():
    with pytest.raises(HwpxSchemaError):
        section.inject_section_properties(etree.Element(f"{{{NS['hp']}}}p"), PageSetup.a4())


def test_build_section_xml_structure():
    paras = [one_para("a"), one_para("b")]
    data = section.build_section_xml(paras, PageSetup.a4())
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hs:sec ')
    assert len(re.findall(rb"xmlns:\w+=", data)) == 15  # 자식에 중복 선언이 없다
    root = etree.fromstring(data)
    assert root.tag == f"{{{NS['hs']}}}sec" and len(root.attrib) == 0
    assert names(root) == ["p", "p"]
    assert len(root.findall(".//hp:secPr", NS)) == 1
    assert root.find("hp:p[1]/hp:run[1]/hp:secPr", NS) is not None
    assert root.find("hp:p[2]//hp:secPr", NS) is None


def test_build_section_xml_empty_makes_paragraph_with_lineseg():
    root = etree.fromstring(section.build_section_xml([], PageSetup.a4()))
    assert len(root) == 1
    p = root[0]
    assert names(p) == ["run", "linesegarray"]
    seg = p.find("hp:linesegarray/hp:lineseg", NS)
    assert seg.get("horzsize") == "42522" and seg.get("vertsize") == "1000"
    assert root.find(".//hp:secPr", NS) is not None
