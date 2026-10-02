#!/usr/bin/env python3
"""참조 HWPX(한글이 직접 저장한 정상 파일)에서 '내용 없는 구조 프로파일' JSON을 추출한다.

unit-27 (DEC-051/054/060/061). 프로파일은 저장소에 커밋되므로 아래를 절대 담지 않는다:
본문/제목/고유명사/작성자/날짜/글꼴 이름 등 문서 특유의 값, 그리고 수치 값.
담는 것은 파트 목록, 요소/속성 *이름*, 요소 자식 순서 관계, 필수 여부, 표준 enum 어휘,
ID 참조/개수 규칙(이름과 기호로만)이다.

사용:
    python tools/hwpx_profile_extract.py <참조.hwpx> [<참조2.hwpx> ...] -o tests/fixtures/hwpx_profile.json

- 참조 파일은 로컬에서 읽기만 한다(메모리 처리, 임시 파일 없음). 여러 개를 주면 병합한다
  (필수 = 모든 발생에서 존재, 어휘 = 합집합).
- 저장 직전에 누출 스캔을 수행한다: 프로파일의 모든 문자열 토큰과 참조 파일의 본문/문서 특유 값 토큰의
  교집합이 1건이라도 있으면 파일을 쓰지 않고 실패한다. 출력에는 '개수'만 표시한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

PROFILE_VERSION = "1"
MAX_PART_BYTES = 256 * 1024 * 1024

# 분석서(hwpx-reference-structure.md) §11: '관찰상 생략 사례가 있는' 파트만 선택 파트.
OPTIONAL_PART_PATTERNS = frozenset({"Contents/masterpage{N}.xml", "Preview/PrvImage.png"})
# 분석서 §3-4: PrvImage는 content.hpf manifest에 없다. manifest/spine 소속은 아래에서 관찰로 산출한다.

# 분석서 §5-4 ID 참조 그래프 + fontRef + 각 컨테이너 정의. 참조 파일에서 무결성을 검증한 뒤에만 기록한다.
ID_DEFS = [
    {"kind": "borderFill", "element": "hh:borderFill", "attr": "id"},
    {"kind": "charPr", "element": "hh:charPr", "attr": "id"},
    {"kind": "paraPr", "element": "hh:paraPr", "attr": "id"},
    {"kind": "tabPr", "element": "hh:tabPr", "attr": "id"},
    {"kind": "numbering", "element": "hh:numbering", "attr": "id"},
    {"kind": "style", "element": "hh:style", "attr": "id"},
    {"kind": "font", "element": "hh:font", "attr": "id", "group_parent": "hh:fontface", "group_attr": "lang"},
]
_FONT_LANG_ATTRS = {
    "hangul": "HANGUL", "latin": "LATIN", "hanja": "HANJA", "japanese": "JAPANESE",
    "other": "OTHER", "symbol": "SYMBOL", "user": "USER",
}
ID_REFS = [
    {"element": "hp:p", "attr": "paraPrIDRef", "kind": "paraPr"},
    {"element": "hp:p", "attr": "styleIDRef", "kind": "style"},
    {"element": "hp:run", "attr": "charPrIDRef", "kind": "charPr"},
    {"element": "hp:t", "attr": "charStyleIDRef", "kind": "style"},
    {"element": "hh:style", "attr": "paraPrIDRef", "kind": "paraPr"},
    {"element": "hh:style", "attr": "charPrIDRef", "kind": "charPr"},
    {"element": "hh:style", "attr": "nextStyleIDRef", "kind": "style"},
    {"element": "hh:charPr", "attr": "borderFillIDRef", "kind": "borderFill"},
    {"element": "hh:paraPr", "attr": "tabPrIDRef", "kind": "tabPr"},
    {"element": "hh:heading", "attr": "idRef", "kind": "numbering", "none": "zero"},
    {"element": "hh:border", "attr": "borderFillIDRef", "kind": "borderFill"},
    {"element": "hh:paraHead", "attr": "charPrIDRef", "kind": "charPr", "none": "uint32_max"},
    {"element": "hp:tbl", "attr": "borderFillIDRef", "kind": "borderFill"},
    {"element": "hp:tc", "attr": "borderFillIDRef", "kind": "borderFill"},
    {"element": "hp:secPr", "attr": "outlineShapeIDRef", "kind": "numbering"},
    {"element": "hp:pageBorderFill", "attr": "borderFillIDRef", "kind": "borderFill"},
] + [
    {"element": "hh:fontRef", "attr": a, "kind": "font", "group": g} for a, g in _FONT_LANG_ATTRS.items()
]
# 개수 속성 -> 세는 자식('*' = 모든 자식). 이름이 우연히 같은 값을 갖는 경우(예: 2x2 표의 colCnt)를 규칙으로
# 오인하지 않도록 자동 유추하지 않고 이 표로 고정한다.
COUNT_ATTR_CHILD = {"itemCnt": "*", "fontCnt": "hh:font", "rowCnt": "hp:tr", "masterPageCnt": "hp:masterPage"}
UNIQUE_IDS = [{"element": "hp:tbl", "attr": "id"}]
SEQUENCES = [
    {"parent": "hh:fontfaces", "child": "hh:fontface", "attr": "lang"},
    {"parent": "hp:secPr", "child": "hp:pageBorderFill", "attr": "type"},
]
# 관찰 어휘가 확실히 불완전한 enum(분석서 §6-2: 가로 용지 값 미확인). V9에서 제외한다.
OPEN_ENUM_ATTRS = frozenset({"hp:pagePr@landscape"})
# 값이 문서 특유일 수 있는 속성 이름: 어휘 후보에서 무조건 제외
FREE_VALUE_ATTRS = frozenset({
    "face", "name", "engName", "path", "full-path", "href", "content", "id", "idref",
    "application", "appVersion", "lastsaveby", "binaryItemIDRef",
})

# 문서 특유 값을 담을 수 있는 속성(누출 스캔 대상). 값 자체가 어휘로 채택되는 일은 FREE_VALUE_ATTRS가 막는다.
DOC_IDENTIFYING_ATTRS = frozenset({
    "face", "name", "engName", "lastsaveby", "application", "appVersion", "binaryItemIDRef", "path",
})

_ENUM_RES = (
    re.compile(r"^[A-Z][A-Z0-9_]*$"),
    re.compile(r"^(None|none|yes|no)$"),
    re.compile(r"^(application|text|image)/[a-z0-9+.\-]+$"),
    re.compile(r"^(https?://www\.hancom\.co\.kr/[A-Za-z0-9/._\-]*|urn:[a-z0-9:.\-]+)$"),
)
MAX_ENUM_SIZE = 16
INFO_KEY = "reviewed_standard_coincidence_info_only"
INFO_NAME_KEY = "name_token_coincidence_info_only"
# 사람이 검토해 '표준 OWPML 상수이며 문서 특유 값이 아님'을 확인한 enum 값(2026-09 R1 추출 결과 61종).
# 이 집합 밖의 값이 어휘로 채택되면 추출을 중단한다(새 어휘는 검토 후 여기에 추가 — 공개 저장소 유출 방지 장치).
REVIEWED_ENUM_VALUES = frozenset("""
ABSOLUTE BASELINE BOTH BOTH_SIDES BOTTOM BOTTOM_CENTER BREAK BREAK_WORD CELL CENTER CENTER_BELOW CHAR
CIRCLED_DIGIT COLUMN CONTINUOUS DIGIT DOUBLE_SLIM EACH_COLUMN END_OF_DOCUMENT EVEN FCAT_GOTHIC FCAT_MYUNGJO
HANGUL HANGUL_SYLLABLE HANJA HFT HORIZONTAL HWP201X HWPUNIT JAPANESE JUSTIFY KEEP_WORD LATIN LEFT LEFT_ONLY
NEWSPAPER NONE None ODD OTHER PAPER PARA PERCENT RIGHT SHOW_ALL SOLID SYMBOL TABLE TOP TOP_AND_BOTTOM TTF USER
WIDELY WORDPROCESSOR no none yes
application/hwpml-package+xml application/xml text/plain http://www.hancom.co.kr/hwpml/2016/HwpUnitChar
""".split())
_TOKEN_RE = re.compile(r"[0-9A-Za-z_가-힣ㄱ-ㆎ]+")
_HANGUL_RE = re.compile(r"[ㄱ-ㆎ가-힣]")
_XML_DECL_RE = re.compile(rb"^<\?xml[^>]*\?>")


class ExtractError(Exception):
    pass


def _is_enum_value(name: str, value: str) -> bool:
    if name in FREE_VALUE_ATTRS:
        return False
    return any(r.match(value) for r in _ENUM_RES)


def normalize_part_name(name: str) -> str:
    if re.fullmatch(r"Contents/(section|masterpage)\d+\.xml", name):
        return re.sub(r"\d+", "{N}", name)
    if name.startswith("BinData/") and not name.endswith("/"):
        return "BinData/{name}"
    return name


_ROLES = {
    "mimetype": "mimetype",
    "version.xml": "version",
    "META-INF/container.xml": "container",
    "META-INF/manifest.xml": "manifest",
    "Contents/content.hpf": "hpf",
    "Contents/header.xml": "header",
    "Contents/section{N}.xml": "section",
    "Contents/masterpage{N}.xml": "masterpage",
    "settings.xml": "settings",
    "Preview/PrvText.txt": "prvtext",
    "Preview/PrvImage.png": "prvimage",
    "BinData/{name}": "bindata",
}


def _kind_for(pattern: str) -> str:
    if pattern == "mimetype":
        return "raw"
    if pattern.endswith(".xml") or pattern.endswith(".hpf"):
        return "xml"
    if pattern.endswith(".txt"):
        return "text"
    return "binary"


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


class _ElemStat:
    def __init__(self) -> None:
        self.n = 0
        self.attr_present: Counter[str] = Counter()
        self.attr_values: dict[str, set[str] | None] = {}
        self.child_present: Counter[str] = Counter()
        self.child_names: set[str] = set()
        self.before: set[tuple[str, str]] = set()
        self.has_text = False
        self.cnt_obs: dict[str, list[tuple[int, Counter[str]]]] = defaultdict(list)


class Extractor:
    def __init__(self) -> None:
        self.namespaces: dict[str, str] = {}
        self.uri2prefix: dict[str, str] = {}
        self.stats: dict[str, _ElemStat] = defaultdict(_ElemStat)
        self.parts: dict[str, dict] = {}
        self.compression: dict[str, set[str]] = defaultdict(set)
        self.observed_order: list[str] = []
        self.part_presence: Counter[str] = Counter()
        self.ref_count = 0
        self.prolog: bytes | None = None
        self.mimetype: bytes | None = None
        self.switch_obs: dict[tuple[str, str], list[tuple[int, int, dict]]] = defaultdict(list)
        self.part_count_attr_ok: dict[tuple[str, str], bool] = {}
        self.seq_obs: dict[tuple[str, str, str], list[tuple[str, ...]]] = defaultdict(list)
        self.def_ids: list[tuple[str, str | None, str]] = []
        self.unresolved = 0
        self.dup_ids = 0
        self.content_tokens: set[str] = set()
        self.enum_attrs_seen: set[tuple[str, str]] = set()
        self.root_ns: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
        self._attr_value_tokens: dict[tuple[str, str], set[str]] = {}
        self.manifest_membership: dict[str, list[bool]] = defaultdict(list)
        self.spine_membership: dict[str, list[bool]] = defaultdict(list)

    # ---- 이름 ----
    def qname(self, el: etree._Element) -> str:
        q = etree.QName(el)
        if q.namespace is None:
            return q.localname
        prefix = self.uri2prefix.get(q.namespace)
        if prefix is None:
            raise ExtractError("루트에서 선언되지 않은 네임스페이스를 가진 요소가 있다")
        return f"{prefix}:{q.localname}"

    def attr_name(self, key: str) -> str:
        if key.startswith("{"):
            uri, local = key[1:].split("}", 1)
            prefix = self.uri2prefix.get(uri)
            if prefix is None:
                raise ExtractError("루트에서 선언되지 않은 네임스페이스를 가진 속성이 있다")
            return f"{prefix}:{local}"
        return key

    # ---- 입력 ----
    def add_reference(self, path: Path) -> None:
        self.ref_count += 1
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise ExtractError("zip이 아니다") from exc
        with zf:
            infos = [i for i in zf.infolist() if not i.filename.endswith("/")]
            if not infos or infos[0].filename != "mimetype":
                raise ExtractError("첫 엔트리가 mimetype이 아니다")
            if infos[0].compress_type != zipfile.ZIP_STORED:
                raise ExtractError("mimetype이 stored가 아니다")
            mt = zf.read("mimetype")
            if self.mimetype not in (None, mt):
                raise ExtractError("참조 파일 간 mimetype이 다르다")
            self.mimetype = mt
            data: dict[str, bytes] = {}
            order: list[str] = []
            for info in infos:
                pat = normalize_part_name(info.filename)
                self.compression[pat].add("stored" if info.compress_type == zipfile.ZIP_STORED else "deflated")
                if pat not in order:
                    order.append(pat)
                if info.file_size > MAX_PART_BYTES:
                    raise ExtractError("파트 크기가 너무 크다")
                data[info.filename] = zf.read(info.filename)
            if not self.observed_order:
                self.observed_order = order
        # 1) 네임스페이스 표 (모든 XML 파트 루트)
        xml_names = [n for n in data if _kind_for(normalize_part_name(n)) == "xml"]
        trees: dict[str, etree._Element] = {}
        for n in xml_names:
            root = etree.fromstring(data[n], _parser())
            if root.getroottree().docinfo.doctype:
                raise ExtractError("DOCTYPE이 있는 XML")
            trees[n] = root
            for prefix, uri in root.nsmap.items():
                if prefix is None:
                    continue
                if self.namespaces.get(prefix, uri) != uri:
                    raise ExtractError("같은 접두어가 서로 다른 URI에 매핑된다")
                if self.uri2prefix.get(uri, prefix) != prefix:
                    raise ExtractError("같은 URI에 접두어가 둘 이상이다")
                self.namespaces[prefix] = uri
                self.uri2prefix[uri] = prefix
        # 2) 파트 메타
        seen_patterns: set[str] = set()
        for n, raw in data.items():
            pat = normalize_part_name(n)
            seen_patterns.add(pat)
            meta = self.parts.setdefault(pat, {"kind": _kind_for(pat), "role": _ROLES.get(pat, "other")})
            if meta["kind"] == "xml":
                m = _XML_DECL_RE.match(raw)
                if not m or raw[m.end():m.end() + 1] != b"<":
                    raise ExtractError("XML 프롤로그가 관찰 가능한 형태가 아니다")
                if self.prolog not in (None, m.group(0)):
                    raise ExtractError("파트 간 XML 프롤로그가 다르다")
                self.prolog = m.group(0)
                root = trees[n]
                meta_root = self.qname(root)
                if meta.setdefault("root", meta_root) != meta_root:
                    raise ExtractError("같은 종류 파트의 루트 요소가 다르다")
                ns_now = {p: u for p, u in root.nsmap.items() if p is not None}
                prev = self.root_ns[pat].get("map")
                self.root_ns[pat]["map"] = dict(ns_now) if prev is None else {
                    p: u for p, u in prev.items() if ns_now.get(p) == u
                }
        for pat in seen_patterns:
            self.part_presence[pat] += 1
        # 3) 요소 통계 / 전용 규칙 관찰
        header_defs: dict[tuple[str, str | None], set[int]] = defaultdict(set)
        refs: list[tuple[dict, int, str | None]] = []
        unique_seen: dict[str, set[str]] = defaultdict(set)
        section_names = sorted(n for n in data if normalize_part_name(n) == "Contents/section{N}.xml")
        for n, root in trees.items():
            pat = normalize_part_name(n)
            self._collect_part(root, header_defs, refs, unique_seen)
            self._collect_text_tokens(root)
            self._sequences(root)
            self._switches(root)
            if pat == "Contents/header.xml":
                head_stat_attr = root.get("secCnt")
                ok = head_stat_attr is not None and head_stat_attr.isdigit() and int(head_stat_attr) == len(section_names)
                key = ("hh:head", "secCnt")
                self.part_count_attr_ok[key] = self.part_count_attr_ok.get(key, True) and ok
            if pat == "Contents/content.hpf":
                self._hpf_membership(root, data)
        for n, raw in data.items():
            if normalize_part_name(n) == "Preview/PrvText.txt":
                self.content_tokens.update(_TOKEN_RE.findall(raw.decode("utf-8", "replace")))
        for rule, value, group in refs:
            if rule.get("none") == "zero" and value == 0:
                continue
            if rule.get("none") == "uint32_max" and value == 0xFFFFFFFF:
                continue
            if value not in header_defs.get((rule["kind"], group), set()):
                self.unresolved += 1

    def _collect_text_tokens(self, root: etree._Element) -> None:
        for el in root.iter(etree.Element):
            if el.text and el.text.strip():
                self.content_tokens.update(_TOKEN_RE.findall(el.text))
            if el.tail and el.tail.strip():
                self.content_tokens.update(_TOKEN_RE.findall(el.tail))
            # 속성값 토큰은 모든 속성에 대해 모은다. 스캔 시 프로파일의 enum 어휘와의 겹침만 별도 판정한다.
            q = self.qname(el)
            for k, v in el.attrib.items():
                if _HANGUL_RE.search(v) or self.attr_name(k) in DOC_IDENTIFYING_ATTRS:
                    self._attr_value_tokens.setdefault((q, self.attr_name(k)), set()).update(_TOKEN_RE.findall(v))

    def _collect_part(self, root, header_defs, refs, unique_seen) -> None:
        def_by_el = {d["element"]: d for d in ID_DEFS}
        refs_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in ID_REFS:
            refs_by_key[(r["element"], r["attr"])].append(r)
        for el in root.iter(etree.Element):
            q = self.qname(el)
            st = self.stats[q]
            st.n += 1
            kids = [c for c in el if isinstance(c.tag, str)]
            names = [self.qname(c) for c in kids]
            cn = Counter(names)
            for name in cn:
                st.child_present[name] += 1
            st.child_names.update(cn)
            first: dict[str, int] = {}
            last: dict[str, int] = {}
            for i, name in enumerate(names):
                first.setdefault(name, i)
                last[name] = i
            for a in first:
                for b in first:
                    if a != b and first[a] < last[b]:
                        st.before.add((a, b))
            if (el.text and el.text.strip()) or any(c.tail and c.tail.strip() for c in kids):
                st.has_text = True
            for k, v in el.attrib.items():
                an = self.attr_name(k)
                st.attr_present[an] += 1
                cur = st.attr_values.get(an, set())
                if cur is not None:
                    if _is_enum_value(an, v):
                        cur.add(v)
                        if len(cur) > MAX_ENUM_SIZE:
                            cur = None
                    else:
                        cur = None
                st.attr_values[an] = cur
                if an.endswith("Cnt") and v.isdigit():
                    st.cnt_obs[an].append((int(v), cn))
                for r in refs_by_key.get((q, an), ()):
                    group = None
                    if "group" in r:
                        group = r["group"]
                    if v.isdigit():
                        refs.append((r, int(v), group))
                    else:
                        self.unresolved += 1
            d = def_by_el.get(q)
            if d is not None:
                idv = el.get(d["attr"])
                if idv is None or not idv.isdigit():
                    raise ExtractError("정의 요소에 정수 id가 없다")
                group = None
                if "group_parent" in d:
                    parent = el.getparent()
                    group = parent.get(d["group_attr"]) if parent is not None else None
                bucket = header_defs[(d["kind"], group)]
                if int(idv) in bucket:
                    self.dup_ids += 1
                bucket.add(int(idv))
            for u in UNIQUE_IDS:
                if q == u["element"]:
                    v = el.get(u["attr"])
                    if v in unique_seen[q]:
                        self.dup_ids += 1
                    unique_seen[q].add(v)

    def _sequences(self, root) -> None:
        for s in SEQUENCES:
            for parent in root.iter(etree.Element):
                if self.qname(parent) != s["parent"]:
                    continue
                seq = tuple(
                    c.get(s["attr"], "") for c in parent
                    if isinstance(c.tag, str) and self.qname(c) == s["child"]
                )
                self.seq_obs[(s["parent"], s["child"], s["attr"])].append(seq)

    def _switches(self, root) -> None:
        for sw in root.iter(etree.Element):
            if self.qname(sw) != "hp:switch":
                continue
            case = default = None
            for c in sw:
                if isinstance(c.tag, str):
                    nm = self.qname(c)
                    if nm == "hp:case":
                        case = c
                    elif nm == "hp:default":
                        default = c
            if case is None or default is None:
                raise ExtractError("hp:switch에 case/default 쌍이 없다")
            for a, b in zip(case.iter(etree.Element), default.iter(etree.Element)):
                if a is case:
                    continue
                if self.qname(a) != self.qname(b):
                    raise ExtractError("switch case/default 구조가 다르다")
                q = self.qname(a)
                for k, va in a.attrib.items():
                    vb = b.get(k)
                    if vb is None or not re.fullmatch(r"-?\d+", va) or not re.fullmatch(r"-?\d+", vb):
                        continue
                    others = {self.attr_name(kk): vv for kk, vv in a.attrib.items() if _is_enum_value(self.attr_name(kk), vv)}
                    self.switch_obs[(q, self.attr_name(k))].append((int(va), int(vb), others))

    def _hpf_membership(self, root, data) -> None:
        items: dict[str, str] = {}
        for el in root.iter(etree.Element):
            if self.qname(el) == "opf:item":
                items[el.get("id", "")] = el.get("href", "")
        listed = set(items.values())
        for href in listed:
            if href not in data:
                raise ExtractError("manifest href가 zip 루트 기준으로 해석되지 않는다")
        spine_hrefs = set()
        for el in root.iter(etree.Element):
            if self.qname(el) == "opf:itemref":
                idref = el.get("idref", "")
                if idref not in items:
                    raise ExtractError("spine idref가 manifest에 없다")
                spine_hrefs.add(items[idref])
        for n in data:
            pat = normalize_part_name(n)
            if pat in {"mimetype", "Contents/content.hpf"}:
                continue
            self.manifest_membership[pat].append(n in listed)
            self.spine_membership[pat].append(n in spine_hrefs)

    # ---- 산출 ----
    def build(self) -> dict:
        if self.ref_count == 0:
            raise ExtractError("참조 파일이 없다")
        if self.unresolved:
            raise ExtractError(f"참조 파일 자체에서 ID 참조 끊김 {self.unresolved}건 — 규칙 표를 재검토해야 한다")
        if self.dup_ids:
            raise ExtractError(f"참조 파일 자체에서 id 중복 {self.dup_ids}건")
        for ok in self.part_count_attr_ok.values():
            if not ok:
                raise ExtractError("secCnt가 section 파트 수와 다르다")
        elements: dict[str, dict] = {}
        for q in sorted(self.stats):
            st = self.stats[q]
            attrs: dict[str, dict] = {}
            for a in sorted(st.attr_present):
                info: dict = {"required": st.attr_present[a] == st.n}
                vals = st.attr_values.get(a)
                if vals:
                    info["enum"] = sorted(vals)
                    if f"{q}@{a}" in OPEN_ENUM_ATTRS:
                        info["enum_open"] = True
                attrs[a] = info
            order: dict[str, list[str]] = {}
            for a, b in sorted(st.before):
                if (b, a) not in st.before:
                    order.setdefault(a, []).append(b)
            entry: dict = {
                "attrs": attrs,
                "children": sorted(st.child_names),
                "required_children": sorted(c for c, k in st.child_present.items() if k == st.n),
                "text": st.has_text,
            }
            if order:
                entry["order"] = {k: sorted(v) for k, v in sorted(order.items())}
            counts = self._count_rules(st)
            if counts:
                entry["count_attrs"] = counts
            elements[q] = entry

        parts: dict[str, dict] = {}
        for pat in sorted(self.parts):
            meta = dict(self.parts[pat])
            present_all = self.part_presence[pat] == self.ref_count
            meta["required"] = present_all and pat not in OPTIONAL_PART_PATTERNS
            if meta["kind"] == "xml":
                meta["root_ns"] = dict(sorted(self.root_ns[pat]["map"].items()))
            if pat in self.manifest_membership:
                meta["in_manifest"] = all(self.manifest_membership[pat])
                meta["in_spine"] = all(self.spine_membership[pat])
            meta["observed_compression"] = "/".join(sorted(self.compression[pat]))
            parts[pat] = meta

        sequences = []
        for (parent, child, attr), obs in sorted(self.seq_obs.items()):
            if obs and all(s == obs[0] for s in obs) and obs[0]:
                sequences.append({"parent": parent, "child": child, "attr": attr, "values": list(obs[0])})

        part_counts = [
            {"element": e, "attr": a, "counts": "section_parts"} for (e, a) in sorted(self.part_count_attr_ok)
        ]
        profile = {
            "profile_version": PROFILE_VERSION,
            "generator": "tools/hwpx_profile_extract.py",
            "content_policy": "structure-only: names, order relations, flags, standard enum vocabulary",
            "zip": {
                "first_entry": "mimetype",
                "mimetype_method": "stored",
                "mimetype_content": (self.mimetype or b"").decode("ascii"),
                # 첫 참조 파일의 엔트리 순서(패턴 기준). 정보용 — 검증기는 mimetype 첫 엔트리만 강제한다(분석서 E-Z 미확정).
                "observed_order": self.observed_order,
            },
            "xml_prolog": (self.prolog or b"").decode("ascii"),
            "namespaces": dict(sorted(self.namespaces.items())),
            "parts": parts,
            "elements": elements,
            "part_count_attrs": part_counts,
            "id_defs": ID_DEFS,
            "id_refs": ID_REFS,
            "unique_ids": UNIQUE_IDS,
            "sequences": sequences,
            "switch": self._switch_rules(),
        }
        return profile

    def _count_rules(self, st: _ElemStat) -> dict[str, str]:
        out: dict[str, str] = {}
        for attr, obs in st.cnt_obs.items():
            hint = COUNT_ATTR_CHILD.get(attr)
            if hint is None:
                continue  # colCnt(격자 규칙 V10)·secCnt(파트 수 규칙)는 별도, 그 밖은 검토 전까지 규칙화하지 않는다
            if st.attr_present[attr] != st.n or len(obs) != st.n:
                raise ExtractError(f"{attr}가 일부 발생에서 없거나 정수가 아니다")
            child = sorted(st.child_names)[0] if hint == "*" and len(st.child_names) == 1 else hint
            for v, cn in obs:
                got = sum(cn.values()) if child == "*" else cn.get(child, 0)
                if got != v:
                    raise ExtractError(f"참조 자체에서 {attr}가 실제 자식 수와 다르다")
            out[attr] = child
        return out

    def _switch_rules(self) -> dict:
        scaled: list[list[str]] = []
        equal: list[dict] = []
        for (q, a), obs in sorted(self.switch_obs.items()):
            if all(d == 2 * c for c, d, _ in obs):
                scaled.append([q, a])
            elif all(d == c for c, d, _ in obs):
                rule: dict = {"element": q, "attr": a}
                types = {o.get("type") for _, _, o in obs}
                if len(types) == 1 and None not in types:
                    rule["when"] = {"type": types.pop()}
                equal.append(rule)
            else:
                raise ExtractError("switch 값 관계가 2배도 동일도 아닌 속성이 있다")
        return {"default_scale": "double", "scaled": scaled, "equal": equal}

    # ---- 누출 스캔 ----
    def leak_scan(self, profile: dict) -> dict[str, int]:
        """개수만 반환한다. 내용(토큰)은 반환/출력하지 않는다."""
        non_ascii_strings = 0
        const_tokens: set[str] = set(_TOKEN_RE.findall(profile["xml_prolog"]))
        const_tokens.update(_TOKEN_RE.findall(profile["zip"]["mimetype_content"]))
        for uri in profile["namespaces"].values():
            const_tokens.update(_TOKEN_RE.findall(uri))
        value_strings: set[str] = set()
        name_tokens: set[str] = set()

        def walk(v, in_value: bool) -> None:
            nonlocal non_ascii_strings
            if isinstance(v, dict):
                for k, x in v.items():
                    walk(k, False)
                    walk(x, in_value)
            elif isinstance(v, list):
                for x in v:
                    walk(x, in_value)
            elif isinstance(v, str):
                if not v.isascii():
                    non_ascii_strings += 1
                (value_strings if in_value else name_tokens_holder).add(v)

        name_tokens_holder: set[str] = set()
        for e in profile["elements"].values():
            for info in e["attrs"].values():
                value_strings.update(info.get("enum", []))
            walk({k: v for k, v in e.items() if k != "attrs"}, False)
            walk(list(e["attrs"]), False)
        for sq in profile["sequences"]:
            value_strings.update(sq["values"])
            walk({k: v for k, v in sq.items() if k != "values"}, False)
        for r in profile["switch"]["equal"]:
            value_strings.update(r.get("when", {}).values())
        walk(profile["parts"], False)
        walk(profile["id_defs"], False)
        walk(profile["id_refs"], False)
        for s_ in name_tokens_holder:
            name_tokens.update(_TOKEN_RE.findall(s_))
        unreviewed = {v for v in value_strings if v not in REVIEWED_ENUM_VALUES}
        value_tokens = set()
        for v in value_strings:
            value_tokens.update(_TOKEN_RE.findall(v))
        # 문서 특유 값 = (A) 본문/메타 텍스트 노드와 PrvText, (B) 이름·식별 속성값(글꼴명/스타일명/작성 도구 등)
        doc_tokens = set(self.content_tokens)
        for toks in self._attr_value_tokens.values():
            doc_tokens.update(toks)
        # 표준 상수(네임스페이스 URI, 프롤로그, mimetype)는 문서에서 온 값이 아니므로 스캔 대상에서 제외
        reviewed_tokens: set[str] = set()
        for v in REVIEWED_ENUM_VALUES:
            reviewed_tokens.update(_TOKEN_RE.findall(v))
        name_overlap = (name_tokens - const_tokens - reviewed_tokens) & doc_tokens
        value_overlap = (value_tokens - const_tokens - reviewed_tokens) & doc_tokens
        # 검토 완료된 표준 상수가 우연히 본문 단어와 같은 경우: 정보용(실패 아님)
        coincidence = len(((name_tokens | value_tokens) & reviewed_tokens) & doc_tokens)
        self._last_overlap = name_overlap | value_overlap
        return {
            "non_ascii_strings": non_ascii_strings,
            "unreviewed_enum_values": len(unreviewed),
            "enum_token_overlap": len(value_overlap),
            # 요소/속성 이름은 XML 태그에서 왔으므로 본문 단어와 우연히 같아도(예: type, header) 누출이 아니다 — 정보용
            INFO_KEY: coincidence,
            INFO_NAME_KEY: len(name_overlap),
        }


def extract(paths: list[Path]) -> tuple[dict, dict[str, int]]:
    ex = Extractor()
    for p in paths:
        ex.add_reference(p)
    profile = ex.build()
    return profile, ex.leak_scan(profile)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("references", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        profile, scan = extract(args.references)
    except (ExtractError, etree.XMLSyntaxError, OSError) as exc:
        print(f"[실패] {type(exc).__name__}: {exc if isinstance(exc, ExtractError) else '입력을 처리할 수 없다'}", file=sys.stderr)
        return 2
    print("누출 스캔(개수만): " + ", ".join(f"{k}={v}" for k, v in scan.items()))
    if any(v for k, v in scan.items() if not k.endswith("_info_only")):
        print("[실패] 누출 의심 — 프로파일을 쓰지 않는다", file=sys.stderr)
        return 3
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=True, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"프로파일 기록: 요소 종류 {len(profile['elements'])}개, 파트 패턴 {len(profile['parts'])}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
