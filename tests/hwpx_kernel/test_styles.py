"""StyleRegistry: interning, 양자화, header 직렬화 (T1)."""

from __future__ import annotations

import logging

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel import styles
from pdf_to_hwpx.hwpx_kernel.styles import (
    NO_BORDER,
    SOLID_THIN,
    BorderSide,
    BorderSpec,
    CharSpec,
    ParaSpec,
    StyleRegistry,
)

from .helpers import NS, check_reference_integrity, open_zip, parse

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def header_root(reg: StyleRegistry, sec_cnt: int = 1) -> etree._Element:
    return etree.fromstring(reg.serialize_header(sec_cnt))


def test_reserved_ids_and_start_values():
    reg = StyleRegistry()
    assert reg.char_pr(CharSpec()) == 0  # charPr는 0부터
    assert reg.para_pr(ParaSpec()) == 0  # paraPr는 0부터
    assert reg.border_fill(NO_BORDER) == 1  # borderFill은 1부터
    assert (reg.char_pr_count, reg.para_pr_count, reg.border_fill_count) == (1, 1, 1)


def test_interning_returns_same_id_and_sequential_new_ids():
    reg = StyleRegistry()
    a = reg.char_pr(CharSpec(height=2000, bold=True))
    assert a == 1
    assert reg.char_pr(CharSpec(height=2000, bold=True)) == a
    assert reg.char_pr(CharSpec(height=2000, bold=False)) == 2
    assert reg.char_pr(CharSpec(height=2000, family="serif")) == 3
    assert reg.border_fill(SOLID_THIN) == 2
    assert reg.border_fill(SOLID_THIN) == 2


def test_para_pr_quantization_merges_close_values():
    reg = StyleRegistry()
    a = reg.para_pr(ParaSpec(left=2001, prev=1049))
    b = reg.para_pr(ParaSpec(left=1950, prev=951))
    assert a == b
    c = reg.para_pr(ParaSpec(left=2400, prev=1000))
    assert c != a
    root = header_root(reg)
    lefts = [int(e.get("value")) for e in root.iterfind(f".//{HC}left")]
    assert 2000 in lefts and 2400 in lefts


def test_para_pr_clamps_negative_left_and_prev():
    reg = StyleRegistry()
    assert reg.para_pr(ParaSpec(left=-500, prev=-500)) == 0  # 기본과 동일하게 정규화
    assert reg.para_pr(ParaSpec(prev=10**9)) == 1
    root = header_root(reg)
    prevs = [int(e.get("value")) for e in root.iterfind(f".//{HC}prev")]
    assert max(prevs) == 2 * 20000  # default 분기(2배)에서 상한 20000


def test_validation_errors():
    reg = StyleRegistry()
    with pytest.raises(ValueError):
        reg.char_pr(CharSpec(height=0))
    with pytest.raises(ValueError):
        reg.char_pr(CharSpec(family="cursive"))
    with pytest.raises(ValueError):
        reg.char_pr(CharSpec(text_color="red"))
    with pytest.raises(ValueError):
        reg.para_pr(ParaSpec(align="DISTRIBUTE"))
    with pytest.raises(ValueError):
        reg.para_pr(ParaSpec(line_spacing=0))
    with pytest.raises(ValueError):
        reg.border_fill(BorderSpec.all_sides(BorderSide("DASHED")))
    with pytest.raises(ValueError):
        reg.border_fill(BorderSpec.all_sides(BorderSide("SOLID", "thick")))
    with pytest.raises(ValueError):
        reg.serialize_header(0)


def test_soft_limit_doubles_quantum(monkeypatch, caplog):
    monkeypatch.setattr(styles, "STYLE_SOFT_LIMIT", 3)
    reg = StyleRegistry()
    with caplog.at_level(logging.WARNING):
        reg.para_pr(ParaSpec(prev=100))
        reg.para_pr(ParaSpec(prev=200))  # 3번째 등록에서 한도 도달
    assert any("양자화" in r.message for r in caplog.records)
    # 이후에는 단위가 200으로 커져 (100 단위에서는 다른) 140/160이 같은 id로 합쳐진다
    assert reg.para_pr(ParaSpec(prev=140)) == reg.para_pr(ParaSpec(prev=160))


def test_header_top_level_order_and_attributes():
    reg = StyleRegistry()
    root = header_root(reg, 2)
    assert root.tag == f"{{{NS['hh']}}}head"
    assert root.get("version") == "1.4" and root.get("secCnt") == "2"
    top = [etree.QName(c).localname for c in root]
    assert top == ["beginNum", "refList", "compatibleDocument", "docOption", "trackchageConfig"]
    ref = [etree.QName(c).localname for c in root.find("hh:refList", NS)]
    assert ref == [
        "fontfaces", "borderFills", "charProperties", "tabProperties", "numberings",
        "paraProperties", "styles",
    ]
    assert root.find("hh:trackchageConfig", NS).get("flags") == "56"
    assert root.find("hh:compatibleDocument", NS).get("targetProgram") == "HWP201X"


def test_header_item_counts_match_children():
    reg = StyleRegistry()
    reg.char_pr(CharSpec(height=1500, bold=True))
    reg.para_pr(ParaSpec(align="CENTER"))
    reg.border_fill(SOLID_THIN)
    root = header_root(reg)
    for container in root.iterfind("hh:refList/*", NS):
        assert int(container.get("itemCnt")) == len(container), container.tag
    for face in root.iterfind(".//hh:fontface", NS):
        assert int(face.get("fontCnt")) == len(face) == 3


def test_fontfaces_seven_langs_three_fonts_each():
    root = header_root(StyleRegistry())
    faces = root.findall(".//hh:fontface", NS)
    assert [f.get("lang") for f in faces] == [
        "HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"
    ]
    for face in faces:
        found = face.findall("hh:font", NS)
        assert [(f.get("id"), f.get("face")) for f in found] == [
            ("0", "돋움"), ("1", "바탕"), ("2", "돋움체")
        ]
        assert all(f.get("type") == "TTF" and f.get("isEmbedded") == "0" for f in found)
        assert all(f.find("hh:typeInfo", NS) is not None for f in found)


def test_border_fill_structure_ids_start_at_one():
    reg = StyleRegistry()
    reg.border_fill(SOLID_THIN)
    root = header_root(reg)
    bfs = root.findall(".//hh:borderFill", NS)
    assert [b.get("id") for b in bfs] == ["1", "2"]
    solid = bfs[1]
    assert [etree.QName(c).localname for c in solid] == [
        "slash", "backSlash", "leftBorder", "rightBorder", "topBorder", "bottomBorder"
    ]
    for side in list(solid)[2:]:
        assert (side.get("type"), side.get("width"), side.get("color")) == ("SOLID", "0.12 mm", "#000000")
    assert solid.find("hh:diagonal", NS) is None
    assert solid.find(f"{HC}fillBrush") is None


def test_char_pr_children_order_and_bold_position():
    reg = StyleRegistry()
    reg.char_pr(CharSpec(height=2000, bold=True, family="mono"))
    root = header_root(reg)
    plain, bold = root.findall(".//hh:charPr", NS)
    expected = ["fontRef", "ratio", "spacing", "relSz", "offset", "underline", "strikeout", "outline", "shadow"]
    assert [etree.QName(c).localname for c in plain] == expected
    expected_bold = expected[:5] + ["bold"] + expected[5:]
    assert [etree.QName(c).localname for c in bold] == expected_bold
    assert bold.get("height") == "2000"
    assert set(bold.find("hh:fontRef", NS).attrib.values()) == {"2"}  # mono = font id 2
    assert set(plain.find("hh:fontRef", NS).attrib.values()) == {"0"}
    assert len(bold.find("hh:fontRef", NS).attrib) == 7


def test_para_pr_switch_doubles_lengths_but_not_percent():
    reg = StyleRegistry()
    reg.para_pr(ParaSpec(align="CENTER", left=2000, intent=-400, prev=300, line_spacing=130))
    root = header_root(reg)
    pp = root.findall(".//hh:paraPr", NS)[1]
    assert [etree.QName(c).localname for c in pp] == [
        "align", "heading", "breakSetting", "autoSpacing", "switch", "border"
    ]
    assert pp.find("hh:align", NS).get("horizontal") == "CENTER"
    case, default = pp.find("hp:switch", NS)
    assert etree.QName(case).localname == "case" and etree.QName(default).localname == "default"
    assert case.get(f"{{{NS['hp']}}}required-namespace") == "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"
    for tag in ("intent", "left", "right", "prev", "next"):
        c = int(case.find(f".//{HC}{tag}").get("value"))
        d = int(default.find(f".//{HC}{tag}").get("value"))
        assert d == 2 * c, tag
    assert case.find(f".//{HC}left").get("value") == "2000"
    assert case.find(f".//{HC}intent").get("value") == "-400"
    for branch in (case, default):
        ls = branch.find("hh:lineSpacing", NS)
        assert (ls.get("type"), ls.get("value")) == ("PERCENT", "130")
    assert [etree.QName(c).localname for c in case] == ["margin", "lineSpacing"]
    assert [etree.QName(c).localname for c in case.find("hh:margin", NS)] == [
        "intent", "left", "right", "prev", "next"
    ]


def test_numbering_tabpr_style_fixed_items():
    root = header_root(StyleRegistry())
    numbering = root.find(".//hh:numbering", NS)
    assert numbering.get("id") == "1"
    heads = numbering.findall("hh:paraHead", NS)
    assert [h.get("level") for h in heads] == [str(i) for i in range(1, 8)]
    assert heads[0].text == "^1." and heads[0].get("charPrIDRef") == "4294967295"
    tab = root.find(".//hh:tabPr", NS)
    assert tab.get("id") == "0" and len(tab) == 0
    style = root.find(".//hh:style", NS)
    assert dict(style.attrib) == {
        "id": "0", "type": "PARA", "name": "바탕글", "engName": "Normal", "paraPrIDRef": "0",
        "charPrIDRef": "0", "nextStyleIDRef": "0", "langID": "1042", "lockForm": "0",
    }


def test_header_deterministic():
    def build():
        reg = StyleRegistry()
        reg.char_pr(CharSpec(height=1300, bold=True))
        reg.para_pr(ParaSpec(prev=500))
        return reg.serialize_header(1)

    assert build() == build()


def test_header_prolog_bytes():
    data = StyleRegistry().serialize_header(1)
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hh:head ')


def test_header_references_are_internally_consistent(ctx):
    from pdf_to_hwpx.hwpx_kernel.container import HwpxPackage
    from pdf_to_hwpx.hwpx_kernel.section import PageSetup, build_section_xml

    ctx.registry.char_pr(CharSpec(height=1800, bold=True))
    ctx.registry.para_pr(ParaSpec(align="RIGHT"))
    pkg = HwpxPackage()
    pkg.set_header(ctx.build_header(1))
    pkg.add_section(build_section_xml([], PageSetup.a4()))
    zf = open_zip(pkg.to_bytes())
    assert check_reference_integrity(zf) == []
    parse(zf, "Contents/header.xml")
