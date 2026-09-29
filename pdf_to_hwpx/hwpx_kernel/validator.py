"""HWPX 구조 검증기 (unit-27, REQ-008, DEC-051/061).

자체 스키마 기준 테스트가 '한글이 못 여는 파일'을 통과시켰던 사각지대를 줄이기 위해, 출력 zip이
한글이 저장한 정상 HWPX의 **구조 프로파일**(``tests/fixtures/hwpx_profile.json``, 내용 없음)과
얼마나 다른지 검사한다. 이 검사를 통과해도 한글이 여는 것을 보장하지 않는다(필요조건 후보일 뿐).
한글에서 실제로 여는 확인(게이트 G1/G2)이 별도로 필요하다.

설계 메모
- zip과 프로파일만 읽는다. 다른 커널 모듈을 import하지 않는다(런타임 변환 경로에서도 호출하지 않는다).
- 결과에는 텍스트 내용을 싣지 않는다: 위반은 (코드, 파트, 위치(요소 경로), 설명)이며 설명에는
  요소/속성 이름과 짧은 표준 토큰 값만 나온다.
- 검사 코드는 03 §3-4의 V1~V13에 대응한다. ``V<n>.<이름>`` 형식이며 ``ignore``로 코드 또는 ``V<n>``
  접두어 단위로 끌 수 있다(G1 실험 프로브처럼 의도적으로 요소를 생략할 때, 그리고 검증기 자체의
  뮤테이션 테스트에서 사용).

사용
    from pdf_to_hwpx.hwpx_kernel.validator import validate_hwpx
    violations = validate_hwpx("out.hwpx")          # 빈 리스트 = 프로파일 위반 없음
    python pdf_to_hwpx/hwpx_kernel/validator.py out.hwpx
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from lxml import etree

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "hwpx_profile.json"

MAX_PART_BYTES = 256 * 1024 * 1024  # zip 폭탄 방어: 파트 하나의 선언 크기 상한
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_GRID_CELLS = 1_000_000  # 악의적 rowCnt/colCnt 방어
DEFAULT_TABLE_WIDTH_TOLERANCE = 10  # 참조 표 17개 중 1개가 표 폭과 10 HWPUNIT 차이(한글 자체 저장본) — 분석서 §7
PER_CODE_CAP = 25  # (코드, 파트)당 보고 상한. 초과분은 V0.SUPPRESSED 한 줄로 요약
_UINT32_MAX = 0xFFFFFFFF
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class ProfileError(Exception):
    """프로파일 JSON을 읽을 수 없거나 형식이 맞지 않는다."""


@dataclass(frozen=True)
class Violation:
    code: str
    part: str
    location: str
    message: str

    def __str__(self) -> str:
        loc = f" {self.location}" if self.location else ""
        return f"[{self.code}] {self.part}{loc}: {self.message}"


class _ElemRule:
    __slots__ = (
        "name", "attrs", "required_attrs", "enums", "open_enums", "children", "required_children",
        "order", "text", "count_attrs", "ref_attrs",
    )

    def __init__(self, name: str, raw: dict[str, Any]) -> None:
        self.name = name
        self.attrs = set(raw["attrs"])
        self.required_attrs = frozenset(a for a, i in raw["attrs"].items() if i.get("required"))
        self.enums = {a: frozenset(i["enum"]) for a, i in raw["attrs"].items() if "enum" in i}
        self.open_enums = frozenset(a for a, i in raw["attrs"].items() if i.get("enum_open"))
        self.children = frozenset(raw["children"])
        self.required_children = frozenset(raw["required_children"])
        self.order = {a: frozenset(bs) for a, bs in raw.get("order", {}).items()}
        self.text = bool(raw["text"])
        self.count_attrs = dict(raw.get("count_attrs", {}))
        self.ref_attrs: dict[str, list[dict[str, Any]]] = {}


class Profile:
    """프로파일 JSON을 검사에 쓰기 좋게 컴파일한 것."""

    def __init__(self, raw: dict[str, Any]) -> None:
        try:
            if raw["profile_version"] != "1":
                raise ProfileError("지원하지 않는 프로파일 버전")
            self.raw = raw
            self.mimetype = raw["zip"]["mimetype_content"].encode("ascii")
            self.prolog = raw["xml_prolog"].encode("ascii")
            self.uri2prefix = {u: p for p, u in raw["namespaces"].items()}
            self.parts: list[tuple[re.Pattern[str], str, dict[str, Any]]] = []
            for pat, meta in raw["parts"].items():
                rx = re.escape(pat).replace(re.escape("{N}"), r"(\d+)").replace(re.escape("{name}"), r"[^/]+")
                self.parts.append((re.compile("^" + rx + "$"), pat, meta))
            self.elements = {n: _ElemRule(n, r) for n, r in raw["elements"].items()}
            self.id_defs = {d["element"]: d for d in raw["id_defs"]}
            self.unique_ids = {u["element"]: u["attr"] for u in raw["unique_ids"]}
            for ref in raw["id_refs"]:
                rule = self.elements.get(ref["element"])
                if rule is None:
                    raise ProfileError("id_refs가 프로파일에 없는 요소를 가리킨다")
                rule.ref_attrs.setdefault(ref["attr"], []).append(ref)
            self.vocab = frozenset(v for r in raw["elements"].values() for i in r["attrs"].values() for v in i.get("enum", ()))
            self.sequences = raw["sequences"]
            sw = raw["switch"]
            self.switch_scaled = {(e, a) for e, a in sw["scaled"]}
            self.switch_equal = {(r["element"], r["attr"]): r.get("when") for r in sw["equal"]}
            self.part_count_attrs = raw["part_count_attrs"]
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProfileError("프로파일 형식이 올바르지 않다") from exc

    def match_part(self, name: str) -> tuple[str, dict[str, Any]] | None:
        for rx, pat, meta in self.parts:
            if rx.match(name):
                return pat, meta
        return None


def load_profile(path: str | Path | None = None) -> Profile:
    p = Path(path) if path is not None else DEFAULT_PROFILE_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProfileError("프로파일 JSON을 읽을 수 없다") from exc
    return Profile(raw)


def _safe(v: str | None, vocab: frozenset[str]) -> str:
    """속성 값은 프로파일 어휘에 있는 표준 상수일 때만 보여 준다(그 밖의 값은 문서 내용일 수 있다)."""
    if v is None:
        return "<없음>"
    return v if v in vocab else "<비표준 값>"


def _to_int(v: str | None) -> int | None:
    if v is None or not re.fullmatch(r"-?\d{1,18}", v):
        return None
    return int(v)


class _Run:
    def __init__(self, prof: Profile, ignore: Iterable[str], table_width_tolerance: int) -> None:
        self.prof = prof
        self.ignore = frozenset(ignore)
        self.tol = table_width_tolerance
        self.out: list[Violation] = []
        self.counts: Counter[tuple[str, str]] = Counter()
        self.suppressed: Counter[tuple[str, str]] = Counter()
        self._tag_cache: dict[str, str | None] = {}
        self._attr_cache: dict[str, str | None] = {}
        self._unknown_ns_seen: set[tuple[str, str]] = set()

    # ---- 보고 ----
    def emit(
        self, code: str, part: str, message: str, el: etree._Element | None = None, detail: str = "",
    ) -> None:
        if code in self.ignore or code.split(".", 1)[0] in self.ignore or (detail and f"{code}:{detail}" in self.ignore):
            return
        key = (code, part)
        self.counts[key] += 1
        if self.counts[key] > PER_CODE_CAP:
            self.suppressed[key] += 1
            return
        self.out.append(Violation(code, part, self.path_of(el) if el is not None else "", message))

    def finish(self) -> list[Violation]:
        for (code, part), n in sorted(self.suppressed.items()):
            self.out.append(Violation("V0.SUPPRESSED", part, "", f"{code} 위반 {n}건은 보고 상한으로 생략"))
        return self.out

    def path_of(self, el: etree._Element) -> str:
        segs: list[str] = []
        node: etree._Element | None = el
        while node is not None:
            name = self.canon(node.tag) or "?"
            parent = node.getparent()
            if parent is None:
                segs.append(name)
            else:
                same = [c for c in parent if c.tag == node.tag]
                segs.append(name if len(same) == 1 else f"{name}[{same.index(node) + 1}]")
            node = parent
        return "/" + "/".join(reversed(segs))

    # ---- 이름 ----
    def canon(self, tag: Any) -> str | None:
        if not isinstance(tag, str):
            return None
        if tag in self._tag_cache:
            return self._tag_cache[tag]
        if tag.startswith("{"):
            uri, local = tag[1:].split("}", 1)
            prefix = self.prof.uri2prefix.get(uri)
            res = f"{prefix}:{local}" if prefix else None
        else:
            res = tag
        self._tag_cache[tag] = res
        return res

    def canon_attr(self, key: str) -> str | None:
        if key in self._attr_cache:
            return self._attr_cache[key]
        if key.startswith("{"):
            uri, local = key[1:].split("}", 1)
            prefix = self.prof.uri2prefix.get(uri)
            res = f"{prefix}:{local}" if prefix else None
        else:
            res = key
        self._attr_cache[key] = res
        return res


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def validate_hwpx(
    source: str | Path | BinaryIO,
    profile: Profile | dict[str, Any] | str | Path | None = None,
    *,
    ignore: Iterable[str] = (),
    table_width_tolerance: int = DEFAULT_TABLE_WIDTH_TOLERANCE,
) -> list[Violation]:
    """HWPX 하나를 프로파일과 대조해 위반 목록을 반환한다(빈 리스트 = 위반 없음).

    ``ignore``: 끌 검사 코드(예: ``"V13.SPINE_MISSING"``) 또는 ``"V13"`` 같은 접두어. 필수 자식 누락은
    ``"V5.CHILD_MISSING:hp:linesegarray"`` 형태로 특정 자식만 끌 수 있다. 의도적 생략 실험(G1 P4b 등) 전용.
    ``table_width_tolerance``: 첫 행 셀 폭 합과 표 폭 차이 허용치(HWPUNIT). 참조(한글 저장본)에서 관찰된 최대 편차 10이 기본값.
    """
    if isinstance(profile, Profile):
        prof = profile
    elif isinstance(profile, dict):
        prof = Profile(profile)
    else:
        prof = load_profile(profile)
    run = _Run(prof, ignore, table_width_tolerance)
    try:
        zf = zipfile.ZipFile(source)  # type: ignore[arg-type]
    except zipfile.BadZipFile:
        run.emit("V1.NOT_ZIP", "", "zip 파일이 아니다")
        return run.finish()
    with zf:
        _validate_zip(run, zf)
    return run.finish()


def _validate_zip(run: _Run, zf: zipfile.ZipFile) -> None:
    prof = run.prof
    infos = zf.infolist()
    files = [i for i in infos if not i.filename.endswith("/")]
    name_counts = Counter(i.filename for i in files)
    for name, n in name_counts.items():
        if n > 1:
            run.emit("V1.DUPLICATE", name, "같은 이름의 엔트리가 중복된다")

    # V1: mimetype
    mt = next((i for i in files if i.filename == "mimetype"), None)
    if mt is None:
        run.emit("V1.MIMETYPE_MISSING", "mimetype", "mimetype 엔트리가 없다")
    else:
        if files[0].filename != "mimetype":
            run.emit("V1.MIMETYPE_ORDER", "mimetype", "mimetype이 첫 엔트리가 아니다")
        if mt.compress_type != zipfile.ZIP_STORED:
            run.emit("V1.MIMETYPE_COMPRESSED", "mimetype", "mimetype이 비압축(stored)이 아니다")
        if mt.extra:
            run.emit("V1.MIMETYPE_EXTRA", "mimetype", "mimetype에 extra field가 있다")
        if mt.file_size <= 64:
            try:
                if zf.read(mt) != prof.mimetype:
                    run.emit("V1.MIMETYPE_CONTENT", "mimetype", "mimetype 내용이 정확하지 않다(개행/공백 포함)")
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
                run.emit("V1.UNREADABLE", "mimetype", "mimetype을 읽을 수 없다")
        else:
            run.emit("V1.MIMETYPE_CONTENT", "mimetype", "mimetype 내용이 정확하지 않다(길이)")

    # 경로 안전성 + 크기 + 읽기
    data: dict[str, bytes] = {}
    total = 0
    for info in files:
        name = info.filename
        parts = name.split("/")
        if name.startswith("/") or "\\" in name or ".." in parts or ":" in parts[0] or "" in parts:
            run.emit("V1.PATH", name, "엔트리 경로가 안전하지 않다(절대경로/상위 이동/백슬래시)")
            continue
        if info.file_size > MAX_PART_BYTES or total + info.file_size > MAX_TOTAL_BYTES:
            run.emit("V1.TOO_LARGE", name, "파트 크기가 상한을 넘는다")
            continue
        total += info.file_size
        if name in data or name == "mimetype":
            continue
        try:
            data[name] = zf.read(info)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
            run.emit("V1.UNREADABLE", name, "엔트리를 읽을 수 없다(손상/암호화/미지원 압축)")

    # V2: 파트 목록
    present: dict[str, list[str]] = defaultdict(list)
    matched: dict[str, tuple[str, dict[str, Any]]] = {}
    for name in data:
        m = prof.match_part(name)
        if m is None:
            run.emit("V2.UNKNOWN_PART", name, "프로파일에 없는 파트다")
            continue
        matched[name] = m
        present[m[0]].append(name)
    for pat, meta in prof.raw["parts"].items():
        if meta.get("required") and meta["role"] != "mimetype" and pat not in present:
            run.emit("V2.PART_MISSING", pat, "필수 파트가 없다")
    for pat in ("Contents/section{N}.xml", "Contents/masterpage{N}.xml"):
        idx = sorted(int(re.search(r"(\d+)\.xml$", n).group(1)) for n in present.get(pat, []))  # type: ignore[union-attr]
        if idx and idx != list(range(len(idx))):
            run.emit("V2.SECTION_GAP", pat, "파트 번호가 0부터 연속이지 않다")

    # 파트별 검사
    docs = _DocState()
    for name, (pat, meta) in matched.items():
        kind, role = meta["kind"], meta["role"]
        raw = data[name]
        if kind == "xml":
            _check_xml_part(run, docs, name, pat, meta, raw)
        elif role == "prvtext":
            _check_prvtext(run, name, raw)
        elif role == "prvimage" and not raw.startswith(_PNG_MAGIC):
            run.emit("V3.PNG_SIGNATURE", name, "PNG 서명이 아니다")

    # 교차 검사
    _resolve_ids(run, docs)
    n_sections = len(present.get("Contents/section{N}.xml", []))
    for name, val, el in docs.sec_cnt:
        iv = _to_int(val)
        if iv is None or iv != n_sections:
            run.emit("V8.SECCNT", name, "secCnt가 section 파트 수와 다르다", el)
    if docs.hpf is not None:
        _check_hpf(run, docs, data, matched)


class _DocState:
    def __init__(self) -> None:
        self.defs: dict[tuple[str, str | None], set[int]] = defaultdict(set)
        self.refs: list[tuple[str, etree._Element, dict[str, Any], str, str]] = []
        self.unique_seen: dict[str, set[str]] = defaultdict(set)
        self.sec_cnt: list[tuple[str, str | None, etree._Element]] = []
        self.hpf: tuple[str, etree._Element] | None = None
        self.hpf_items: list[tuple[str, str, etree._Element]] = []
        self.hpf_itemrefs: list[tuple[str, etree._Element]] = []


def _check_prvtext(run: _Run, name: str, raw: bytes) -> None:
    if raw.startswith(b"\xef\xbb\xbf"):
        run.emit("V3.TEXT_ENCODING", name, "BOM이 있다")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        run.emit("V3.TEXT_ENCODING", name, "UTF-8이 아니다")
        return
    if re.search(r"(?<!\r)\n", text):
        run.emit("V3.TEXT_ENCODING", name, "CRLF가 아닌 줄바꿈이 있다")


def _check_xml_part(run: _Run, docs: _DocState, name: str, pat: str, meta: dict[str, Any], raw: bytes) -> None:
    prof = run.prof
    if not raw.startswith(prof.prolog) or raw[len(prof.prolog):len(prof.prolog) + 1] != b"<":
        run.emit("V3.PROLOG", name, "XML 프롤로그가 참조 형태와 다르다(BOM/따옴표/공백/개행 포함)")
    try:
        root = etree.fromstring(raw, _parser())
    except etree.XMLSyntaxError as exc:
        line = exc.position[0] if exc.position else 0
        run.emit("V3.XML_PARSE", name, f"XML 구문 오류(줄 {line})")
        return
    if root.getroottree().docinfo.doctype:
        run.emit("V3.DOCTYPE", name, "DOCTYPE 선언이 있다")
    role = meta["role"]

    root_name = run.canon(root.tag)
    if root_name != meta.get("root"):
        run.emit("V3.ROOT", name, f"루트 요소가 다르다(기대 {meta.get('root')})", root)
    declared = {p: u for p, u in root.nsmap.items() if p is not None}
    for prefix, uri in meta.get("root_ns", {}).items():
        if prefix not in declared:
            run.emit("V3.NS_MISSING", name, f"루트에 네임스페이스 접두어 {prefix}가 선언되지 않았다", root)
        elif declared[prefix] != uri:
            run.emit("V3.NS_MISMATCH", name, f"네임스페이스 접두어 {prefix}의 URI가 참조와 다르다", root)

    secpr_elems: list[etree._Element] = []
    for el in root.iter(etree.Element):
        cname = run.canon(el.tag)
        if cname is None:
            uri = el.tag[1:].split("}", 1)[0] if el.tag.startswith("{") else ""
            if (name, uri) not in run._unknown_ns_seen:
                run._unknown_ns_seen.add((name, uri))
                run.emit("V3.NS_UNKNOWN", name, "프로파일에 없는 네임스페이스의 요소가 있다", el)
            continue
        rule = prof.elements.get(cname)
        if rule is None:
            run.emit("V4.ELEMENT", name, f"프로파일에 없는 요소 {cname}", el)
            continue
        _check_element(run, docs, name, role, el, cname, rule, is_root=el is root)
        if cname == "hp:tbl":
            _check_table(run, name, el)
        elif cname == "hp:switch":
            _check_switch(run, name, el)
        elif cname == "hp:secPr":
            secpr_elems.append(el)
        if role == "hpf":
            if cname == "opf:item":
                docs.hpf_items.append((el.get("id", ""), el.get("href", ""), el))
            elif cname == "opf:itemref":
                docs.hpf_itemrefs.append((el.get("idref", ""), el))
    if role == "hpf":
        docs.hpf = (name, root)
    if role == "section":
        _check_secpr(run, name, root, secpr_elems)
    for pc in prof.part_count_attrs:
        if root_name == pc["element"]:
            docs.sec_cnt.append((name, root.get(pc["attr"]), root))
    for seq in prof.sequences:
        for parent in root.iter(etree.Element):
            if run.canon(parent.tag) != seq["parent"]:
                continue
            got = [c.get(seq["attr"], "") for c in parent if run.canon(c.tag) == seq["child"]]
            if got != seq["values"]:
                run.emit(
                    "V6.SEQUENCE", name,
                    f"{seq['child']}의 {seq['attr']} 순서가 참조와 다르다", parent,
                )


def _check_element(
    run: _Run, docs: _DocState, part: str, role: str, el: etree._Element, cname: str, rule: _ElemRule,
    *, is_root: bool,
) -> None:
    prof = run.prof
    present_attrs: set[str] = set()
    for key, val in el.attrib.items():
        an = run.canon_attr(key)
        if an is None or an not in rule.attrs:
            run.emit("V4.ATTR", part, f"{cname}에 프로파일에 없는 속성 {an or '<미지 네임스페이스>'}", el)
            continue
        present_attrs.add(an)
        enum = rule.enums.get(an)
        if enum is not None and an not in rule.open_enums and val not in enum:
            run.emit("V9.ENUM", part, f"{cname}@{an}의 값 {_safe(val, prof.vocab)}이(가) 관찰 어휘 밖이다", el)
        for ref in rule.ref_attrs.get(an, ()):
            docs.refs.append((part, el, ref, val, an))
    for missing in sorted(rule.required_attrs - present_attrs):
        run.emit("V5.ATTR_MISSING", part, f"{cname}에 필수 속성 {missing}이(가) 없다", el)

    kids = [c for c in el if isinstance(c.tag, str)]
    names: list[str | None] = [run.canon(c.tag) for c in kids]
    name_set = {n for n in names if n is not None}

    if not rule.text and el.text and el.text.strip():
        run.emit("V4.TEXT", part, f"{cname}은(는) 텍스트를 가질 수 없다", el)
    if not rule.text:
        for c in kids:
            if c.tail and c.tail.strip():
                run.emit("V4.TEXT", part, f"{cname} 안에 요소 사이 텍스트가 있다", el)
                break

    for c, n in zip(kids, names):
        if n is not None and n in prof.elements and n not in rule.children:
            run.emit("V4.CHILD", part, f"{cname} 아래에 {n}이(가) 올 수 없다(관찰되지 않은 계층)", c)
    for req in sorted(rule.required_children - name_set):
        if cname == "hp:p" and req == "hp:run":
            run.emit("V12.RUN_MISSING", part, "hp:p에 hp:run이 없다", el)
        else:
            run.emit("V5.CHILD_MISSING", part, f"{cname}에 필수 자식 {req}이(가) 없다", el, detail=req)

    if rule.order and len(name_set) > 1:
        first: dict[str, int] = {}
        last: dict[str, int] = {}
        for i, n in enumerate(names):
            if n is not None:
                first.setdefault(n, i)
                last[n] = i
        for a, afters in rule.order.items():
            if a not in first:
                continue
            for b in afters:
                if b in first and first[b] < last[a]:
                    run.emit("V6.ORDER", part, f"{cname} 안에서 {a}은(는) {b}보다 앞에 와야 한다", el)

    for attr, spec in rule.count_attrs.items():
        val = el.get(attr)
        if val is None:
            continue
        expected = len(kids) if spec == "*" else names.count(spec)
        iv = _to_int(val)
        if iv is None or iv != expected:
            run.emit("V8.COUNT_MISMATCH", part, f"{cname}@{attr}이(가) 실제 자식 수({spec})와 다르다", el)

    d = prof.id_defs.get(cname)
    if d is not None:
        iv = _to_int(el.get(d["attr"]))
        if iv is None:
            run.emit("V7.BAD_ID", part, f"{cname}@{d['attr']}이(가) 정수가 아니다", el)
        else:
            group = None
            if "group_parent" in d:
                parent = el.getparent()
                group = parent.get(d["group_attr"]) if parent is not None else None
            bucket = docs.defs[(d["kind"], group)]
            if iv in bucket:
                run.emit("V7.DUP_ID", part, f"{cname}@{d['attr']} 값이 같은 종류 안에서 중복된다", el)
            bucket.add(iv)
    ua = prof.unique_ids.get(cname)
    if ua is not None:
        v = el.get(ua)
        if v is not None:
            if v in docs.unique_seen[cname]:
                run.emit("V7.DUP_ID", part, f"{cname}@{ua} 값이 문서 안에서 중복된다", el)
            docs.unique_seen[cname].add(v)


def _resolve_ids(run: _Run, docs: _DocState) -> None:
    for part, el, ref, val, an in docs.refs:
        iv = _to_int(val)
        if iv is None:
            run.emit("V7.DANGLING_REF", part, f"{ref['element']}@{an}이(가) 정수가 아니다", el)
            continue
        if ref.get("none") == "zero" and iv == 0:
            continue
        if ref.get("none") == "uint32_max" and iv == _UINT32_MAX:
            continue
        if iv not in docs.defs.get((ref["kind"], ref.get("group")), ()):
            run.emit("V7.DANGLING_REF", part, f"{ref['element']}@{an}이(가) 존재하지 않는 {ref['kind']} id를 가리킨다", el)


def _direct(run: _Run, parent: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in parent if run.canon(c.tag) == name]


def _check_secpr(run: _Run, part: str, root: etree._Element, secprs: list[etree._Element]) -> None:
    if len(secprs) != 1:
        run.emit("V12.SECPR_COUNT", part, f"구역마다 hp:secPr이 정확히 1개여야 한다(현재 {len(secprs)}개)", root)
        return
    sp = secprs[0]
    run_el = sp.getparent()
    p_el = run_el.getparent() if run_el is not None else None
    first_p = next(iter(_direct(run, root, "hp:p")), None)
    ok = (
        run_el is not None and p_el is not None and run.canon(run_el.tag) == "hp:run"
        and run.canon(p_el.tag) == "hp:p" and p_el is first_p and p_el.getparent() is root
        and next(iter(_direct(run, p_el, "hp:run")), None) is run_el
    )
    if not ok:
        run.emit("V12.SECPR_POSITION", part, "hp:secPr이 구역 첫 문단의 첫 hp:run 안에 있지 않다", sp)


def _check_table(run: _Run, part: str, tbl: etree._Element) -> None:
    rows, cols = _to_int(tbl.get("rowCnt")), _to_int(tbl.get("colCnt"))
    if rows is None or cols is None or rows < 1 or cols < 1:
        run.emit("V10.ATTR_INT", part, "rowCnt/colCnt가 양의 정수가 아니다", tbl)
        return
    if rows * cols > MAX_GRID_CELLS:
        run.emit("V10.TOO_LARGE", part, "표 격자가 상한을 넘는다", tbl)
        return
    grid = bytearray(rows * cols)
    row0_width = 0
    trs = _direct(run, tbl, "hp:tr")
    for r_idx, tr in enumerate(trs):
        for tc in _direct(run, tr, "hp:tc"):
            addr = next(iter(_direct(run, tc, "hp:cellAddr")), None)
            span = next(iter(_direct(run, tc, "hp:cellSpan")), None)
            size = next(iter(_direct(run, tc, "hp:cellSz")), None)
            if addr is None or span is None or size is None:
                continue  # 필수 자식 누락은 V5가 이미 보고
            col_a, row_a = _to_int(addr.get("colAddr")), _to_int(addr.get("rowAddr"))
            col_s, row_s = _to_int(span.get("colSpan")), _to_int(span.get("rowSpan"))
            width = _to_int(size.get("width"))
            if col_a is None or row_a is None or col_s is None or row_s is None or width is None:
                run.emit("V10.ATTR_INT", part, "셀 주소/병합/크기 속성이 정수가 아니다", tc)
                continue
            if row_a != r_idx:
                run.emit("V10.ROW_ADDR", part, "셀의 rowAddr가 소속 hp:tr 순번과 다르다", tc)
            if col_s < 1 or row_s < 1:
                run.emit("V10.SPAN_INVALID", part, "colSpan/rowSpan이 1 미만이다", tc)
                continue
            if col_a < 0 or row_a < 0 or col_a + col_s > cols or row_a + row_s > rows:
                run.emit("V10.OUT_OF_GRID", part, "셀이 표 격자를 벗어난다", tc)
                continue
            overlap = False
            for rr in range(row_a, row_a + row_s):
                base = rr * cols
                for cc in range(col_a, col_a + col_s):
                    if grid[base + cc]:
                        overlap = True
                    grid[base + cc] = 1
            if overlap:
                run.emit("V10.OVERLAP", part, "셀이 다른 셀과 겹친다", tc)
            if row_a == 0:
                row0_width += width
    if trs and 0 in grid:
        run.emit("V10.COVERAGE", part, "병합 후에도 덮이지 않은 격자 칸이 있다", tbl)
    sz = next(iter(_direct(run, tbl, "hp:sz")), None)
    tbl_w = _to_int(sz.get("width")) if sz is not None else None
    if tbl_w is not None and trs and abs(row0_width - tbl_w) > run.tol:
        run.emit("V10.WIDTH_SUM", part, "첫 행 셀 폭 합이 표 폭(hp:sz@width)과 다르다", tbl)


def _check_switch(run: _Run, part: str, sw: etree._Element) -> None:
    case = next(iter(_direct(run, sw, "hp:case")), None)
    default = next(iter(_direct(run, sw, "hp:default")), None)
    if case is None or default is None:
        return  # V5가 보고
    a_els = [e for e in case.iter(etree.Element) if e is not case]
    b_els = [e for e in default.iter(etree.Element) if e is not default]
    if [run.canon(e.tag) for e in a_els] != [run.canon(e.tag) for e in b_els]:
        run.emit("V11.STRUCT", part, "hp:case와 hp:default의 구조가 다르다", sw)
        return
    for ea, eb in zip(a_els, b_els):
        q = run.canon(ea.tag)
        if q is None:
            continue
        for key, va in ea.attrib.items():
            an = run.canon_attr(key)
            if an is None:
                continue
            vb = eb.get(key)
            ia, ib = _to_int(va), _to_int(vb)
            if ia is None or ib is None:
                continue
            if (q, an) in run.prof.switch_scaled:
                if ib != 2 * ia:
                    run.emit("V11.SCALE", part, f"{q}@{an}: default 값이 case 값의 2배가 아니다", eb)
            elif (q, an) in run.prof.switch_equal:
                when = run.prof.switch_equal[(q, an)]
                if when and any(ea.get(k) != v for k, v in when.items()):
                    continue
                if ib != ia:
                    run.emit("V11.SCALE", part, f"{q}@{an}: default 값이 case 값과 같아야 한다", eb)


def _check_hpf(run: _Run, docs: _DocState, data: dict[str, bytes], matched: dict[str, tuple[str, dict[str, Any]]]) -> None:
    part, _root = docs.hpf  # type: ignore[misc]
    ids: Counter[str] = Counter(i for i, _h, _e in docs.hpf_items)
    id_to_href = {i: h for i, h, _e in docs.hpf_items}
    for n in ids.values():
        if n > 1:
            run.emit("V13.DUP_ITEM_ID", part, "manifest item id가 중복된다")
    hrefs = {h for _i, h, _e in docs.hpf_items}
    for _i, h, el in docs.hpf_items:
        if h not in data:
            run.emit("V13.HREF_DANGLING", part, "manifest item의 href가 zip에 없다", el)
    spine_hrefs = set()
    for idref, el in docs.hpf_itemrefs:
        if idref not in id_to_href:
            run.emit("V13.SPINE_IDREF", part, "spine itemref의 idref가 manifest에 없다", el)
        else:
            spine_hrefs.add(id_to_href[idref])
    for name, (pat, meta) in sorted(matched.items()):
        if pat in ("Contents/content.hpf", "mimetype"):
            continue
        if meta.get("in_manifest") and name not in hrefs:
            run.emit("V13.MANIFEST_MISSING", part, f"파트 {pat}이(가) manifest에 등재되지 않았다")
        if meta.get("in_spine") and name not in spine_hrefs:
            run.emit("V13.SPINE_MISSING", part, f"파트 {pat}이(가) spine에 없다")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    profile: str | None = None
    if "--profile" in args:
        i = args.index("--profile")
        profile = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: validator.py [--profile profile.json] file.hwpx", file=sys.stderr)
        return 2
    try:
        violations = validate_hwpx(args[0], profile)
    except (ProfileError, OSError) as exc:
        print(f"[오류] {type(exc).__name__}", file=sys.stderr)
        return 2
    for v in violations:
        print(v)
    print(f"위반 {len(violations)}건")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
