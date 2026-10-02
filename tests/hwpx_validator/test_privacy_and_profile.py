"""(1) 검증기 결과에 텍스트 내용이 실리지 않는다. (2) 커밋되는 프로파일 JSON은 구조 정보만 담는다.

참조 HWPX는 읽지 않는다: 프로파일 JSON 자체의 불변식(한글/긴 문자열/숫자 값/허용 키)으로 위생을 검사한다.
"""

from __future__ import annotations

import re

from .helpers import run_validator

SECRET_TEXT = "SECRETBODYTEXT-Zx9"
SECRET_ATTR = "SECRETATTRVALUE-Zx9"


def test_violations_never_contain_document_text_or_attribute_values(pkg, vmod, profile, tmp_path):
    sec = "Contents/section0.xml"
    pkg.els(sec, "hp:t")[0].text = SECRET_TEXT + " 한글본문"
    pkg.els(sec, "hp:p")[0].set("zzz", SECRET_ATTR)  # 미지 속성: 이름만 보고되어야 한다
    pkg.one(sec, "hp:tbl").set("textWrap", SECRET_ATTR)  # 어휘 밖 enum: 비표준 값은 가려져야 한다
    pkg.els(sec, "hp:run")[0].text = SECRET_TEXT  # 잘못된 위치의 텍스트
    pkg.els(sec, "hp:p")[0].set("paraPrIDRef", SECRET_TEXT)  # 끊긴 참조
    v = run_validator(vmod, profile, pkg, tmp_path)
    assert v, "사례가 위반을 만들지 못했다"
    blob = "\n".join(str(x) for x in v)
    assert "SECRET" not in blob and "한글본문" not in blob


def test_known_standard_constants_used_in_wrong_place_may_be_shown(pkg, vmod, profile, tmp_path):
    pkg.one("Contents/section0.xml", "hp:tbl").set("textWrap", "CENTER")
    v = run_validator(vmod, profile, pkg, tmp_path)
    assert any("CENTER" in x.message for x in v)


# ---- 프로파일 위생 ----
TOP_KEYS = {
    "profile_version", "generator", "content_policy", "zip", "xml_prolog", "namespaces", "parts", "elements",
    "part_count_attrs", "id_defs", "id_refs", "unique_ids", "sequences", "switch",
}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_\-]*$")


def _strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    elif isinstance(node, str):
        yield node


def test_profile_has_only_known_top_level_keys(profile_raw):
    assert set(profile_raw) == TOP_KEYS


def test_profile_is_pure_ascii_and_short_strings(profile_raw):
    for s in _strings(profile_raw):
        assert s.isascii(), "비ASCII 문자열(한글 등)이 프로파일에 들어 있다"
        assert len(s) <= 120


def test_profile_has_no_numeric_leaves_or_free_text(profile_raw):
    def walk(n):
        if isinstance(n, dict):
            for v in n.values():
                yield from walk(v)
        elif isinstance(n, list):
            for v in n:
                yield from walk(v)
        else:
            yield n

    for leaf in walk(profile_raw):
        assert not (isinstance(leaf, (int, float)) and not isinstance(leaf, bool)), "수치 값이 들어 있다"


def test_profile_element_and_attr_names_are_identifiers(profile_raw):
    for q, e in profile_raw["elements"].items():
        assert NAME_RE.match(q)
        for a in e["attrs"]:
            assert NAME_RE.match(a)
        for c in e["children"]:
            assert NAME_RE.match(c)
        assert set(e) <= {"attrs", "children", "required_children", "text", "order", "count_attrs"}
        for info in e["attrs"].values():
            assert set(info) <= {"required", "enum", "enum_open"}


def test_profile_enum_vocabulary_is_reviewed_standard_constants(profile_raw, emod):
    for e in profile_raw["elements"].values():
        for a, info in e["attrs"].items():
            for v in info.get("enum", []):
                assert v in emod.REVIEWED_ENUM_VALUES, "검토되지 않은 enum 값"
            if info.get("enum"):
                assert a not in emod.FREE_VALUE_ATTRS


def test_profile_contains_no_free_valued_attribute_vocabulary(profile_raw):
    """글꼴 이름·스타일 이름·작성자 등이 들어갈 자리에는 어휘(enum)가 없어야 한다."""
    for e in profile_raw["elements"].values():
        for a in ("face", "name", "engName", "lastsaveby", "content", "href", "path"):
            assert "enum" not in e["attrs"].get(a, {})


def test_profile_part_list_is_standard_layout(profile_raw):
    assert set(profile_raw["parts"]) <= {
        "mimetype", "version.xml", "settings.xml", "Contents/header.xml", "Contents/content.hpf",
        "Contents/section{N}.xml", "Contents/masterpage{N}.xml", "META-INF/container.xml",
        "META-INF/manifest.xml", "Preview/PrvText.txt", "Preview/PrvImage.png",
    }
