"""합성 HWPX 픽스처 생성기 (unit-27 테스트 전용).

참조 HWPX 파일은 읽지 않는다. 프로파일 JSON(내용 없는 구조 규칙)만 입력으로, '프로파일 규칙만 만족하는
최소 정상 문서'를 lxml로 조립한다. 의미가 걸린 골격(ID 정의, 표 격자, switch 2배 관계, secPr 위치, 파트 목록)은
손으로 만들고, 프로파일이 요구하는 나머지 필수 속성/자식은 ``complete()``가 프로파일에서 읽어 채운다.

음성 사례는 ``build()``가 만든 ``Pkg``의 트리를 테스트가 직접 변형한 뒤 ``write()``한다(B0 파일 복사 없음).
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
PART_ORDER = [
    "version.xml",
    "Contents/header.xml",
    "Contents/section0.xml",
    "Preview/PrvText.txt",
    "settings.xml",
    "META-INF/container.xml",
    "Contents/content.hpf",
    "META-INF/manifest.xml",
]


class Pkg:
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.ns: dict[str, str] = profile["namespaces"]
        self.rules: dict[str, dict[str, Any]] = profile["elements"]
        self.trees: dict[str, etree._Element] = {}
        self.raw: dict[str, bytes] = {}
        self.patches: dict[str, Callable[[bytes], bytes]] = {}
        self.order: list[str] = ["mimetype", *PART_ORDER]
        self.mimetype = profile["zip"]["mimetype_content"].encode("ascii")
        self.mimetype_method = zipfile.ZIP_STORED
        self.mimetype_extra = b""
        self.extra_entries: list[tuple[str, bytes]] = []
        self.prolog = profile["xml_prolog"].encode("ascii")

    # ---- 이름 ----
    def tag(self, q: str) -> str:
        if ":" in q:
            p, local = q.split(":", 1)
            return f"{{{self.ns[p]}}}{local}"
        return q

    def qn(self, el: etree._Element) -> str:
        t = el.tag
        if t.startswith("{"):
            uri, local = t[1:].split("}", 1)
            prefix = next(p for p, u in self.ns.items() if u == uri)
            return f"{prefix}:{local}"
        return t

    def akey(self, a: str) -> str:
        return self.tag(a) if ":" in a else a

    def E(self, q: str, attrs: dict[str, str] | None = None, *children: etree._Element, text: str | None = None) -> etree._Element:
        el = etree.Element(self.tag(q))
        for k, v in (attrs or {}).items():
            el.set(self.akey(k), v)
        for c in children:
            el.append(c)
        if text is not None:
            el.text = text
        return el

    def root(self, part: str, q: str, attrs: dict[str, str] | None = None) -> etree._Element:
        meta = self.profile["parts"][self._pattern(part)]
        el = etree.Element(self.tag(q), nsmap=dict(meta["root_ns"]))
        for k, v in (attrs or {}).items():
            el.set(self.akey(k), v)
        return el

    @staticmethod
    def _pattern(part: str) -> str:
        return part.replace("section0", "section{N}").replace("masterpage0", "masterpage{N}")

    # ---- 자동 완성 ----
    def complete(self, el: etree._Element) -> None:
        q = self.qn(el)
        rule = self.rules[q]
        have = {k for k in el.attrib}
        for a, info in rule["attrs"].items():
            if info["required"] and self.akey(a) not in have:
                enum = info.get("enum")
                el.set(self.akey(a), enum[0] if enum else "0")
        for c in rule["required_children"]:
            if not any(self.qn(x) == c for x in el if isinstance(x.tag, str)):
                self._insert(el, self.E(c))
        for child in list(el):
            if isinstance(child.tag, str):
                self.complete(child)

    def _insert(self, parent: etree._Element, new: etree._Element) -> None:
        before = set(self.rules[self.qn(parent)].get("order", {}).get(self.qn(new), ()))
        for i, c in enumerate(parent):
            if isinstance(c.tag, str) and self.qn(c) in before:
                parent.insert(i, new)
                return
        parent.append(new)

    def fix_counts(self, el: etree._Element) -> None:
        for child in el:
            if isinstance(child.tag, str):
                self.fix_counts(child)
        rule = self.rules[self.qn(el)]
        kids = [self.qn(c) for c in el if isinstance(c.tag, str)]
        for attr, spec in rule.get("count_attrs", {}).items():
            el.set(attr, str(len(kids) if spec == "*" else kids.count(spec)))

    def wire_refs(self) -> None:
        defs: dict[tuple[str, str | None], list[str]] = {}
        by_el = {d["element"]: d for d in self.profile["id_defs"]}
        for tree in self.trees.values():
            for el in tree.iter(etree.Element):
                d = by_el.get(self.qn(el))
                if d:
                    group = el.getparent().get(d["group_attr"]) if "group_parent" in d else None
                    defs.setdefault((d["kind"], group), []).append(el.get(d["attr"]))
        refs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in self.profile["id_refs"]:
            refs.setdefault((r["element"], r["attr"]), []).append(r)
        for tree in self.trees.values():
            for el in tree.iter(etree.Element):
                q = self.qn(el)
                for key in list(el.attrib):
                    for r in refs.get((q, key), ()):
                        ids = defs.get((r["kind"], r.get("group")), [])
                        if r.get("none") == "zero" or r.get("none") == "uint32_max":
                            continue
                        if ids and el.get(key) not in ids:
                            el.set(key, ids[0])

    # ---- 조회/변형 ----
    def els(self, part: str, q: str) -> list[etree._Element]:
        return [e for e in self.trees[part].iter(etree.Element) if self.qn(e) == q]

    def one(self, part: str, q: str) -> etree._Element:
        found = self.els(part, q)
        assert found, f"{part}에 {q}가 없다"
        return found[0]

    def drop_part(self, name: str) -> None:
        self.trees.pop(name, None)
        self.raw.pop(name, None)
        self.order.remove(name)

    # ---- 직렬화 ----
    def serialize(self, name: str) -> bytes:
        if name in self.trees:
            body = etree.tostring(self.trees[name], encoding="unicode").encode("utf-8")
            data = self.prolog + body
        else:
            data = self.raw[name]
        patch = self.patches.get(name)
        return patch(data) if patch else data

    def write(self, path: Path) -> Path:
        with zipfile.ZipFile(path, "w") as zf:
            for name in self.order:
                if name == "mimetype":
                    zi = zipfile.ZipInfo("mimetype", FIXED_DATE)
                    zi.compress_type = self.mimetype_method
                    zi.extra = self.mimetype_extra
                    zf.writestr(zi, self.mimetype)
                    continue
                zi = zipfile.ZipInfo(name, FIXED_DATE)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, self.serialize(name))
            for name, data in self.extra_entries:
                zi = zipfile.ZipInfo(name, FIXED_DATE)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, data)
        return path


# ---------------------------------------------------------------------------------------------
# 골격
# ---------------------------------------------------------------------------------------------

def _para(s: Pkg, text: str | None, *, run_children: tuple[etree._Element, ...] = ()) -> etree._Element:
    run = s.E("hp:run", {"charPrIDRef": "0"}, *run_children)
    if text is not None:
        run.append(s.E("hp:t", text=text))
    return s.E("hp:p", {"paraPrIDRef": "0", "styleIDRef": "0"}, run, s.E("hp:linesegarray", None, s.E("hp:lineseg")))


def _header(s: Pkg) -> etree._Element:
    head = s.root("Contents/header.xml", "hh:head", {"version": "1.4", "secCnt": "1"})
    langs = next(x["values"] for x in s.profile["sequences"] if x["child"] == "hh:fontface")
    fontfaces = s.E("hh:fontfaces", None, *[
        s.E("hh:fontface", {"lang": lang}, s.E("hh:font", {"id": "0", "face": "F0"})) for lang in langs
    ])
    margin_case = s.E("hh:margin", None, *[s.E(f"hc:{n}", {"value": v, "unit": "HWPUNIT"}) for n, v in
                                           (("intent", "0"), ("left", "100"), ("right", "200"), ("prev", "300"), ("next", "400"))])
    margin_def = s.E("hh:margin", None, *[s.E(f"hc:{n}", {"value": v, "unit": "HWPUNIT"}) for n, v in
                                          (("intent", "0"), ("left", "200"), ("right", "400"), ("prev", "600"), ("next", "800"))])
    switch = s.E(
        "hp:switch", None,
        s.E("hp:case", {"hp:required-namespace": s.rules["hp:case"]["attrs"]["hp:required-namespace"]["enum"][0]},
            margin_case, s.E("hh:lineSpacing", {"type": "PERCENT", "value": "160", "unit": "HWPUNIT"})),
        s.E("hp:default", None, margin_def, s.E("hh:lineSpacing", {"type": "PERCENT", "value": "160", "unit": "HWPUNIT"})),
    )
    ref = s.E(
        "hh:refList", None,
        fontfaces,
        s.E("hh:borderFills", None, s.E("hh:borderFill", {"id": "1"})),
        s.E("hh:charProperties", None, s.E("hh:charPr", {"id": "0"})),
        s.E("hh:tabProperties", None, s.E("hh:tabPr", {"id": "0"})),
        s.E("hh:numberings", None, s.E("hh:numbering", {"id": "1"})),
        s.E("hh:paraProperties", None, s.E("hh:paraPr", {"id": "0"}, switch)),
        s.E("hh:styles", None, s.E("hh:style", {"id": "0"})),
    )
    head.append(ref)
    return head


def _cell(s: Pkg, col: int, row: int) -> etree._Element:
    return s.E(
        "hp:tc", None,
        s.E("hp:subList", None, _para(s, "c")),
        s.E("hp:cellAddr", {"colAddr": str(col), "rowAddr": str(row)}),
        s.E("hp:cellSpan", {"colSpan": "1", "rowSpan": "1"}),
        s.E("hp:cellSz", {"width": "5000", "height": "1000"}),
        s.E("hp:cellMargin"),
    )


def _table(s: Pkg) -> etree._Element:
    return s.E(
        "hp:tbl", {"id": "1", "rowCnt": "2", "colCnt": "2"},
        s.E("hp:sz", {"width": "10000", "height": "2000"}),
        s.E("hp:tr", None, _cell(s, 0, 0), _cell(s, 1, 0)),
        s.E("hp:tr", None, _cell(s, 0, 1), _cell(s, 1, 1)),
    )


def _section(s: Pkg) -> etree._Element:
    sec = s.root("Contents/section0.xml", "hs:sec")
    pbf = [s.E("hp:pageBorderFill", {"type": t}) for t in next(x["values"] for x in s.profile["sequences"] if x["child"] == "hp:pageBorderFill")]
    secpr = s.E("hp:secPr", None, *pbf)
    ctrl = s.E("hp:ctrl", None, s.E("hp:colPr"))
    sec.append(_para(s, "s", run_children=(secpr, ctrl)))
    sec.append(_para(s, None, run_children=(_table(s),)))
    sec.append(_para(s, None))
    return sec


def _hpf(s: Pkg) -> etree._Element:
    pkg = s.root("Contents/content.hpf", "opf:package")
    mt = {"media-type": "application/xml"}
    manifest = s.E(
        "opf:manifest", None,
        s.E("opf:item", {"id": "header", "href": "Contents/header.xml", **mt}),
        s.E("opf:item", {"id": "section0", "href": "Contents/section0.xml", **mt}),
        s.E("opf:item", {"id": "settings", "href": "settings.xml", **mt}),
    )
    spine = s.E(
        "opf:spine", None,
        s.E("opf:itemref", {"idref": "header", "linear": "yes"}),
        s.E("opf:itemref", {"idref": "section0", "linear": "yes"}),
    )
    pkg.append(s.E("opf:metadata"))
    pkg.append(manifest)
    pkg.append(spine)
    return pkg


def build(profile: dict[str, Any]) -> Pkg:
    """프로파일 규칙만 만족하는 최소 정상 패키지(구역 1개, 표 1개, 그림 없음, 바탕쪽/PrvImage 없음)."""
    s = Pkg(profile)
    s.trees["version.xml"] = s.root("version.xml", "hv:HCFVersion")
    s.trees["Contents/header.xml"] = _header(s)
    s.trees["Contents/section0.xml"] = _section(s)
    s.trees["settings.xml"] = s.root("settings.xml", "ha:HWPApplicationSetting")
    container = s.root("META-INF/container.xml", "ocf:container")
    container.append(s.E("ocf:rootfiles", None,
                         s.E("ocf:rootfile", {"full-path": "Contents/content.hpf", "media-type": "application/hwpml-package+xml"}),
                         s.E("ocf:rootfile", {"full-path": "Preview/PrvText.txt", "media-type": "text/plain"})))
    s.trees["META-INF/container.xml"] = container
    s.trees["Contents/content.hpf"] = _hpf(s)
    s.trees["META-INF/manifest.xml"] = s.root("META-INF/manifest.xml", "odf:manifest")
    s.raw["Preview/PrvText.txt"] = b"<sample>\r\n"
    for tree in s.trees.values():
        s.complete(tree)
    for tree in s.trees.values():
        s.fix_counts(tree)
    s.wire_refs()
    return s
