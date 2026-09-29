"""tools/hwpx_profile_extract.py 검증. 입력은 합성 패키지뿐이다(참조 HWPX를 읽지 않는다)."""

from __future__ import annotations

import json

import pytest

SEC = "Contents/section0.xml"
HDR = "Contents/header.xml"
SECRET_TEXT = "SECRETBODY-Qz7"
SECRET_FACE = "SECRETFACE-Qz7"


def _extract(emod, pkg, tmp_path, name="ref.hwpx"):
    ex = emod.Extractor()
    ex.add_reference(pkg.write(tmp_path / name))
    profile = ex.build()
    return ex, profile, ex.leak_scan(profile)


def _clean_scan(scan):
    return {k: v for k, v in scan.items() if not k.endswith("_info_only")}


def test_roundtrip_profile_from_synthetic_reference_accepts_it(pkg, emod, vmod, tmp_path):
    ex, profile, scan = _extract(emod, pkg, tmp_path)
    assert all(v == 0 for v in _clean_scan(scan).values())
    path = pkg.write(tmp_path / "again.hwpx")
    assert vmod.validate_hwpx(path, profile) == []


def test_no_document_specific_value_reaches_the_profile(pkg, emod, tmp_path):
    pkg.els(SEC, "hp:t")[0].text = SECRET_TEXT
    pkg.els(HDR, "hh:font")[0].set("face", SECRET_FACE)
    pkg.one(HDR, "hh:style").set("name", SECRET_FACE)
    pkg.one("Contents/content.hpf", "opf:metadata").append(pkg.E("opf:title", text=SECRET_TEXT))
    _ex, profile, scan = _extract(emod, pkg, tmp_path)
    blob = json.dumps(profile)
    assert "SECRET" not in blob
    assert "enum" not in profile["elements"]["hh:font"]["attrs"]["face"]
    assert all(v == 0 for v in _clean_scan(scan).values())
    assert profile["elements"]["hp:t"]["text"] is True  # 텍스트 유무만 기록


def test_required_versus_optional_attributes(pkg, emod, tmp_path):
    pkg.els(SEC, "hp:p")[1].attrib.pop("styleIDRef")
    _ex, profile, _ = _extract(emod, pkg, tmp_path)
    attrs = profile["elements"]["hp:p"]["attrs"]
    assert attrs["styleIDRef"]["required"] is False
    assert attrs["paraPrIDRef"]["required"] is True


def test_derived_order_counts_and_switch_rules(pkg, emod, tmp_path):
    _ex, profile, _ = _extract(emod, pkg, tmp_path)
    assert "hp:linesegarray" in profile["elements"]["hp:p"]["order"]["hp:run"]
    assert profile["elements"]["hp:tbl"]["count_attrs"] == {"rowCnt": "hp:tr"}
    assert profile["elements"]["hh:charProperties"]["count_attrs"] == {"itemCnt": "hh:charPr"}
    assert ["hc:left", "value"] in profile["switch"]["scaled"]
    assert {"element": "hh:lineSpacing", "attr": "value", "when": {"type": "PERCENT"}} in profile["switch"]["equal"]
    assert "Contents/masterpage{N}.xml" not in profile["parts"]  # 합성 참조에는 바탕쪽이 없다
    assert profile["parts"]["Contents/section{N}.xml"]["in_spine"] is True
    assert profile["parts"]["settings.xml"]["in_manifest"] is True and profile["parts"]["settings.xml"]["in_spine"] is False


def test_unreviewed_enum_value_is_reported_and_blocks_output(pkg, emod, tmp_path):
    pkg.one(SEC, "hp:tbl").set("dropcapstyle", "ZZZ_CUSTOM")
    ref = pkg.write(tmp_path / "ref.hwpx")
    _ex, _profile, scan = _extract(emod, pkg, tmp_path, "ref2.hwpx")
    assert scan["unreviewed_enum_values"] == 1
    out = tmp_path / "out.json"
    assert emod.main([str(ref), "-o", str(out)]) == 3
    assert not out.exists()


def test_non_ascii_names_block_output(pkg, emod, tmp_path):
    pkg.trees[SEC].append(pkg.E("hp:한글"))
    ref = pkg.write(tmp_path / "ref.hwpx")
    out = tmp_path / "out.json"
    assert emod.main([str(ref), "-o", str(out)]) == 3
    assert not out.exists()


def test_main_writes_deterministic_json(pkg, emod, tmp_path, capsys):
    ref = pkg.write(tmp_path / "ref.hwpx")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert emod.main([str(ref), "-o", str(a)]) == 0
    assert emod.main([str(ref), "-o", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    printed = capsys.readouterr().out
    assert "non_ascii_strings=0" in printed and "SECRET" not in printed


def test_dangling_id_in_reference_is_rejected(pkg, emod, tmp_path):
    pkg.els(SEC, "hp:run")[0].set("charPrIDRef", "999")
    ex = emod.Extractor()
    ex.add_reference(pkg.write(tmp_path / "ref.hwpx"))
    with pytest.raises(emod.ExtractError):
        ex.build()


def test_non_zip_and_bad_first_entry_are_rejected(pkg, emod, tmp_path):
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(b"nope")
    assert emod.main([str(bad), "-o", str(tmp_path / "o.json")]) == 2
    pkg.order.remove("mimetype")
    pkg.order.insert(2, "mimetype")
    ref = pkg.write(tmp_path / "order.hwpx")
    assert emod.main([str(ref), "-o", str(tmp_path / "o.json")]) == 2


def test_merge_of_two_references_intersects_required(pkg, emod, tmp_path):
    from .synth import build

    a = pkg.write(tmp_path / "a.hwpx")
    other = build(json.loads(json.dumps(pkg.profile)))
    other.els(SEC, "hp:p")[0].attrib.pop("styleIDRef")
    b = other.write(tmp_path / "b.hwpx")
    ex = emod.Extractor()
    ex.add_reference(a)
    ex.add_reference(b)
    profile = ex.build()
    assert profile["elements"]["hp:p"]["attrs"]["styleIDRef"]["required"] is False


def test_validator_flags_what_the_extracted_profile_forbids(pkg, emod, vmod, tmp_path):
    """추출 프로파일이 다른 문서에도 일관되게 적용되는지: 추출본에 없는 요소를 넣으면 V4.ELEMENT."""
    _ex, profile, _ = _extract(emod, pkg, tmp_path)
    pkg.trees[SEC].append(pkg.E("hp:tab"))
    v = vmod.validate_hwpx(pkg.write(tmp_path / "x.hwpx"), profile)
    assert any(x.code == "V4.ELEMENT" for x in v)
