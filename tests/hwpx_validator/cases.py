"""음성 사례 카탈로그: B0(고치기 전 우리 출력) 유형 결함을 합성 fixture로 재현한다.

각 사례 = (id, 변형 함수, 반드시 나와야 하는 위반 코드 집합). B0 파일은 복사하지 않고 결함 유형을 코드로 만든다.
새 사례를 추가하면 test_negative.py가 자동으로 (1) 기대 코드 검출, (2) 해당 검사를 끄면 검출 실패(뮤턴트) 두 가지를 검사한다.
"""

from __future__ import annotations

import copy
import zipfile
from collections.abc import Callable

from lxml import etree

from .helpers import replace_bytes, strip_ns_decl

SEC = "Contents/section0.xml"
HDR = "Contents/header.xml"
HPF = "Contents/content.hpf"

Mutate = Callable[["Pkg"], None]  # noqa: F821


def _paras(p):
    return p.els(SEC, "hp:p")[:3]  # 최상위 문단 3개(표 셀 안 문단은 뒤에 온다)


def _top_paras(p):
    return [c for c in p.trees[SEC] if isinstance(c.tag, str)]


def _b0_own_attrs(p):
    top = _top_paras(p)
    top[0].set("bboxPt", "0,0,10,10")
    run = p.els(SEC, "hp:run")[0]
    run.set("fontName", "X")
    run.set("fontSizeHwpunit", "1000")
    run.set("bold", "1")


def _rename_charpr(p):
    run = p.els(SEC, "hp:run")[0]
    del run.attrib["charPrIDRef"]
    run.set("charShapeIDRef", "0")


def _header_minimal(p):
    head = p.trees[HDR]
    for c in list(head):
        head.remove(c)
    shapes = p.E("hh:charShapes")
    shapes.append(p.E("hh:charShape", {"id": "0"}))
    head.append(shapes)
    head.append(p.E("hh:paraShapes"))


def _remove_secpr(p):
    sp = p.one(SEC, "hp:secPr")
    sp.getparent().remove(sp)


def _second_secpr(p):
    top = _top_paras(p)
    run = p.els(SEC, "hp:run")
    target = [r for r in run if r.getparent() is top[2]][0]
    target.append(copy.deepcopy(p.one(SEC, "hp:secPr")))


def _misplaced_secpr(p):
    sp = p.one(SEC, "hp:secPr")
    top = _top_paras(p)
    target = [r for r in p.els(SEC, "hp:run") if r.getparent() is top[2]][0]
    sp.getparent().remove(sp)
    target.insert(0, sp)


def _drop_run(p):
    last = _top_paras(p)[2]
    for r in [c for c in last if p.qn(c) == "hp:run"]:
        last.remove(r)


def _swap_p_children(p):
    last = _top_paras(p)[2]
    seg = [c for c in last if p.qn(c) == "hp:linesegarray"][0]
    last.remove(seg)
    last.insert(0, seg)


def _t_under_sec(p):
    p.trees[SEC].append(p.E("hp:t", text=None))


def _text_in_run(p):
    p.els(SEC, "hp:run")[0].text = "x"


def _set(part, q, attr, value, index=0):
    def _fn(p):
        p.els(part, q)[index].set(attr, value)

    return _fn


def _dup_charpr(p):
    cps = p.one(HDR, "hh:charProperties")
    cps.append(copy.deepcopy(cps[0]))
    cps.set("itemCnt", str(len(cps)))


def _dup_tbl(p):
    top = _top_paras(p)
    tbl = p.one(SEC, "hp:tbl")
    target = [r for r in p.els(SEC, "hp:run") if r.getparent() is top[2]][0]
    target.append(copy.deepcopy(tbl))


def _bad_charpr_id(p):
    p.one(HDR, "hh:charPr").set("id", "abc")


def _tc(p, idx):
    return p.els(SEC, "hp:tc")[idx]


def _tbl_overlap(p):
    _tc(p, 3).find(p.tag("hp:cellAddr")).set("colAddr", "0")


def _tbl_hole(p):
    tc = _tc(p, 3)
    tc.getparent().remove(tc)


def _tbl_rowaddr(p):
    _tc(p, 2).find(p.tag("hp:cellAddr")).set("rowAddr", "5")


def _tbl_out(p):
    _tc(p, 1).find(p.tag("hp:cellSpan")).set("colSpan", "3")


def _tbl_width(p):
    _tc(p, 0).find(p.tag("hp:cellSz")).set("width", "4000")


def _tbl_span0(p):
    _tc(p, 0).find(p.tag("hp:cellSpan")).set("colSpan", "0")


def _default_child(p, q, index=0):
    dflt = p.one(HDR, "hp:default")
    return [e for e in dflt.iter(etree.Element) if p.qn(e) == q][index]


def _switch_scale(p):
    _default_child(p, "hc:left").set("value", "201")


def _switch_equal(p):
    _default_child(p, "hh:lineSpacing").set("value", "320")


def _switch_struct(p):
    m = _default_child(p, "hh:margin")
    m.getparent().remove(m)


def _hpf_item(p, item_id):
    return [i for i in p.els(HPF, "opf:item") if i.get("id") == item_id][0]


def _hpf_drop_section_item(p):
    it = _hpf_item(p, "section0")
    it.getparent().remove(it)


def _hpf_dup_item(p):
    it = _hpf_item(p, "settings")
    it.getparent().append(copy.deepcopy(it))


def _hpf_drop_spine_section(p):
    for r in p.els(HPF, "opf:itemref"):
        if r.get("idref") == "section0":
            r.getparent().remove(r)


def _swap_fontfaces(p):
    ffs = p.one(HDR, "hh:fontfaces")
    a, b = ffs[0], ffs[1]
    ffs.remove(a)
    ffs.insert(1, a)
    assert ffs[1] is a and ffs[0] is b


def _foreign_ns(p):
    p.trees[SEC].append(etree.Element("{urn:example:not-hancom}foo"))


def _add_extra(name, data):
    def _fn(p):
        p.extra_entries.append((name, data))

    return _fn


def _many_bogus_attrs(p):
    for e in _top_paras(p):
        e.set("zzz", "1")
    for i in range(40):
        p.trees[SEC].append(copy.deepcopy(_top_paras(p)[2]))
        p.trees[SEC][-1].set("zzz", str(i))


def _mt_compressed(p):
    p.mimetype_method = zipfile.ZIP_DEFLATED


def _mt_not_first(p):
    p.order.remove("mimetype")
    p.order.insert(1, "mimetype")


def _mt_newline(p):
    p.mimetype = p.mimetype + b"\n"


def _mt_extra(p):
    p.mimetype_extra = b"\x99\x99\x00\x00"


def _prv_lf(p):
    p.raw["Preview/PrvText.txt"] = b"<x>\n"


def _prv_bom(p):
    p.raw["Preview/PrvText.txt"] = b"\xef\xbb\xbf<x>\r\n"


def _prv_png_bad(p):
    p.order.append("Preview/PrvImage.png")
    p.raw["Preview/PrvImage.png"] = b"not a png"


def _patch(part, fn):
    def _f(p):
        p.patches[part] = fn

    return _f


_LXML_PROLOG = b"<?xml version='1.0' encoding='UTF-8'?>\n"


def _prolog_patch(p, new):
    prolog = p.prolog
    p.patches[SEC] = replace_bytes(prolog, new)


def _bom(p):
    p.patches[SEC] = lambda d: b"\xef\xbb\xbf" + d


def _broken_xml(p):
    p.patches[SEC] = lambda d: d[: len(d) // 2]


def _doctype(p):
    p.patches[SEC] = lambda d: d.replace(p.prolog, p.prolog + b"<!DOCTYPE hs:sec>", 1)


def _wrong_root(p):
    p.trees[SEC].tag = p.tag("hh:head")


def _wrong_opf_ns(p):
    p.patches[HPF] = replace_bytes(b"http://www.idpf.org/2007/opf/", b"http://www.hancom.co.kr/hwpml/2011/package")


def _b0_composite(p):
    _mt_compressed(p)
    _header_minimal(p)
    _remove_secpr(p)
    _b0_own_attrs(p)
    _rename_charpr(p)
    _wrong_opf_ns(p)
    p.drop_part("settings.xml")
    p.patches["META-INF/container.xml"] = replace_bytes(
        b"urn:oasis:names:tc:opendocument:xmlns:container", b"http://www.hancom.co.kr/hwpml/2011/container"
    )


# (id, mutate, expected codes)
CASES: list[tuple[str, Mutate, set[str]]] = [
    ("mimetype_compressed", _mt_compressed, {"V1.MIMETYPE_COMPRESSED"}),
    ("mimetype_not_first", _mt_not_first, {"V1.MIMETYPE_ORDER"}),
    ("mimetype_trailing_newline", _mt_newline, {"V1.MIMETYPE_CONTENT"}),
    ("mimetype_extra_field", _mt_extra, {"V1.MIMETYPE_EXTRA"}),
    ("duplicate_entry", _add_extra("settings.xml", b"<a/>"), {"V1.DUPLICATE"}),
    ("path_traversal", _add_extra("../evil.xml", b"<a/>"), {"V1.PATH"}),
    ("unknown_part", _add_extra("Contents/bogus.xml", b"<a/>"), {"V2.UNKNOWN_PART"}),
    ("part_missing_settings", lambda p: p.drop_part("settings.xml"), {"V2.PART_MISSING", "V13.HREF_DANGLING"}),
    ("part_missing_header", lambda p: p.drop_part(HDR), {"V2.PART_MISSING", "V7.DANGLING_REF"}),
    ("part_missing_container", lambda p: p.drop_part("META-INF/container.xml"), {"V2.PART_MISSING"}),
    ("part_missing_version", lambda p: p.drop_part("version.xml"), {"V2.PART_MISSING"}),
    ("section_gap", _add_extra("Contents/section2.xml", b"<a/>"), {"V2.SECTION_GAP"}),
    ("prolog_lxml_default", lambda p: _prolog_patch(p, _LXML_PROLOG), {"V3.PROLOG"}),
    ("bom", _bom, {"V3.PROLOG"}),
    ("xml_broken", _broken_xml, {"V3.XML_PARSE"}),
    ("doctype", _doctype, {"V3.DOCTYPE"}),
    ("wrong_root", _wrong_root, {"V3.ROOT"}),
    ("ns_uri_mismatch_opf", _wrong_opf_ns, {"V3.NS_MISMATCH", "V3.NS_UNKNOWN"}),
    ("ns_container_uri_wrong", _patch("META-INF/container.xml", replace_bytes(
        b"urn:oasis:names:tc:opendocument:xmlns:container", b"http://www.hancom.co.kr/hwpml/2011/container")),
     {"V3.NS_MISMATCH", "V3.NS_UNKNOWN"}),
    ("ns_declaration_missing", _patch(SEC, strip_ns_decl("epub")), {"V3.NS_MISSING"}),
    ("ns_foreign_element", _foreign_ns, {"V3.NS_UNKNOWN"}),
    ("prvtext_bare_lf", _prv_lf, {"V3.TEXT_ENCODING"}),
    ("prvtext_bom", _prv_bom, {"V3.TEXT_ENCODING"}),
    ("prvimage_not_png", _prv_png_bad, {"V3.PNG_SIGNATURE"}),
    ("own_attrs_b0", _b0_own_attrs, {"V4.ATTR"}),
    ("charShapeIDRef_rename", _rename_charpr, {"V4.ATTR", "V5.ATTR_MISSING"}),
    ("header_minimal_b0", _header_minimal, {"V4.ELEMENT", "V5.CHILD_MISSING", "V7.DANGLING_REF"}),
    ("t_directly_under_sec", _t_under_sec, {"V4.CHILD"}),
    ("text_in_run", _text_in_run, {"V4.TEXT"}),
    ("required_attr_missing", lambda p: p.els(SEC, "hp:p")[0].attrib.pop("styleIDRef"), {"V5.ATTR_MISSING"}),
    ("required_child_missing_linesegarray", lambda p: _top_paras(p)[2].remove(_top_paras(p)[2][-1]), {"V5.CHILD_MISSING"}),
    ("order_swapped_in_p", _swap_p_children, {"V6.ORDER"}),
    ("fontface_sequence_swapped", _swap_fontfaces, {"V6.SEQUENCE"}),
    ("dangling_run_charpr", _set(SEC, "hp:run", "charPrIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_p_parapr", _set(SEC, "hp:p", "paraPrIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_p_style", _set(SEC, "hp:p", "styleIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_tbl_borderfill", _set(SEC, "hp:tbl", "borderFillIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_outline_numbering", _set(SEC, "hp:secPr", "outlineShapeIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_fontref", _set(HDR, "hh:fontRef", "hangul", "999"), {"V7.DANGLING_REF"}),
    ("dangling_style_charpr", _set(HDR, "hh:style", "charPrIDRef", "999"), {"V7.DANGLING_REF"}),
    ("dangling_ref_not_int", _set(SEC, "hp:run", "charPrIDRef", "abc"), {"V7.DANGLING_REF"}),
    ("dup_charpr_id", _dup_charpr, {"V7.DUP_ID"}),
    ("dup_tbl_id", _dup_tbl, {"V7.DUP_ID"}),
    ("charpr_id_not_int", _bad_charpr_id, {"V7.BAD_ID"}),
    ("itemcnt_mismatch", _set(HDR, "hh:charProperties", "itemCnt", "5"), {"V8.COUNT_MISMATCH"}),
    ("fontcnt_mismatch", _set(HDR, "hh:fontface", "fontCnt", "9"), {"V8.COUNT_MISMATCH"}),
    ("rowcnt_mismatch", _set(SEC, "hp:tbl", "rowCnt", "3"), {"V8.COUNT_MISMATCH"}),
    ("masterpagecnt_mismatch", _set(SEC, "hp:secPr", "masterPageCnt", "1"), {"V8.COUNT_MISMATCH"}),
    ("seccnt_mismatch", _set(HDR, "hh:head", "secCnt", "2"), {"V8.SECCNT"}),
    ("enum_out_of_vocab", _set(SEC, "hp:tbl", "textWrap", "SQUARE"), {"V9.ENUM"}),
    ("enum_out_of_vocab_lang", _set(HDR, "hh:fontface", "lang", "KLINGON"), {"V9.ENUM", "V6.SEQUENCE", "V7.DANGLING_REF"}),
    ("tbl_cells_overlap", _tbl_overlap, {"V10.OVERLAP", "V10.COVERAGE"}),
    ("tbl_hole", _tbl_hole, {"V10.COVERAGE"}),
    ("tbl_rowaddr_wrong", _tbl_rowaddr, {"V10.ROW_ADDR", "V10.OUT_OF_GRID"}),
    ("tbl_out_of_grid", _tbl_out, {"V10.OUT_OF_GRID", "V10.COVERAGE"}),
    ("tbl_first_row_width_sum", _tbl_width, {"V10.WIDTH_SUM"}),
    ("tbl_span_zero", _tbl_span0, {"V10.SPAN_INVALID", "V10.COVERAGE"}),
    ("tbl_colcnt_not_int", _set(SEC, "hp:tbl", "colCnt", "x"), {"V10.ATTR_INT"}),
    ("tbl_grid_huge", lambda p: (p.one(SEC, "hp:tbl").set("rowCnt", "100000"), p.one(SEC, "hp:tbl").set("colCnt", "100000")),
     {"V10.TOO_LARGE", "V8.COUNT_MISMATCH"}),
    ("switch_default_not_double", _switch_scale, {"V11.SCALE"}),
    ("switch_percent_not_equal", _switch_equal, {"V11.SCALE"}),
    ("switch_structure_differs", _switch_struct, {"V11.STRUCT"}),
    ("secpr_absent_b0", _remove_secpr, {"V12.SECPR_COUNT"}),
    ("secpr_twice", _second_secpr, {"V12.SECPR_COUNT"}),
    ("secpr_misplaced", _misplaced_secpr, {"V12.SECPR_POSITION"}),
    ("p_without_run", _drop_run, {"V12.RUN_MISSING"}),
    ("hpf_section_not_in_manifest", _hpf_drop_section_item, {"V13.MANIFEST_MISSING", "V13.SPINE_IDREF"}),
    ("hpf_href_dangling", lambda p: _hpf_item(p, "settings").set("href", "nope.xml"), {"V13.HREF_DANGLING", "V13.MANIFEST_MISSING"}),
    ("hpf_spine_idref_unknown", lambda p: p.els(HPF, "opf:itemref")[0].set("idref", "ghost"), {"V13.SPINE_IDREF", "V13.SPINE_MISSING"}),
    ("hpf_section_not_in_spine", _hpf_drop_spine_section, {"V13.SPINE_MISSING"}),
    ("hpf_dup_item_id", _hpf_dup_item, {"V13.DUP_ITEM_ID"}),
    ("b0_composite", _b0_composite, {
        "V1.MIMETYPE_COMPRESSED", "V2.PART_MISSING", "V3.NS_MISMATCH", "V4.ELEMENT", "V4.ATTR",
        "V5.CHILD_MISSING", "V12.SECPR_COUNT", "V13.MANIFEST_MISSING",
    }),
]
