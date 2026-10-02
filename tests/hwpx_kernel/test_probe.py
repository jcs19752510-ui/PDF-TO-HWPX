"""tools/hwpx_probe.py: G1 프로브 생성기 (T1 + 문서 수준 자기 일관성).

한글에서 열리는지는 자동으로 알 수 없다(게이트 G1, 사용자 확인). 여기서는 생성물이
well-formed이고 내부 참조가 일관되며 프로브 간 의도한 차이만 갖는지 확인한다.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from .helpers import NS, check_reference_integrity, forbidden_hits, parse

TOOL = Path(__file__).resolve().parents[2] / "tools" / "hwpx_probe.py"


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("hwpx_probe_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def built(probe, out_dir):
    return probe.build_probes(out_dir)


def test_all_specified_probes_are_built(built):
    assert set(built) == {"P1a", "P1b", "P2", "P3", "P4a", "P4b", "P4c"}
    for path in built.values():
        assert zipfile.is_zipfile(path)


def test_default_output_dir_is_under_harness_tmp(probe):
    assert probe.DEFAULT_OUT.parts[-2:] == (".harness-tmp", "probe")


@pytest.mark.parametrize("name", ["P1a", "P1b", "P2", "P3", "P4a", "P4b", "P4c"])
def test_each_probe_is_well_formed_consistent_and_clean(built, name):
    zf = zipfile.ZipFile(built[name])
    for part in zf.namelist():
        if part.endswith((".xml", ".hpf")):
            etree.fromstring(zf.read(part))
    assert check_reference_integrity(zf) == []
    assert forbidden_hits(zf) == []


def test_p1a_and_p1b_differ_only_in_version_application(probe, out_dir):
    built = probe.build_probes(out_dir, ["P1a", "P1b"])
    a, b = (zipfile.ZipFile(built[n]) for n in ("P1a", "P1b"))
    assert a.namelist() == b.namelist()
    va, vb = parse(a, "version.xml"), parse(b, "version.xml")
    assert {k for k in va.attrib if va.get(k) != vb.get(k)} == {"application", "appVersion"}
    for name in a.namelist():
        if name in ("version.xml", "Contents/content.hpf"):
            continue  # content.hpf는 변환 시각 메타가 다를 수 있다
        assert a.read(name) == b.read(name), name


def test_p1_is_single_empty_paragraph_with_secpr(built):
    root = parse(zipfile.ZipFile(built["P1a"]), "Contents/section0.xml")
    paras = root.findall("hp:p", NS)
    assert len(paras) == 1
    assert "".join(root.itertext()) == ""
    assert paras[0].find("hp:run/hp:secPr", NS) is not None


def test_p2_has_distinct_char_and_para_styles(built):
    zf = zipfile.ZipFile(built["P2"])
    header, sec = parse(zf, "Contents/header.xml"), parse(zf, "Contents/section0.xml")
    assert len(sec.findall("hp:p", NS)) == 7
    assert header.find(".//hh:charPr/hh:bold", NS) is not None
    heights = {c.get("height") for c in header.findall(".//hh:charPr", NS)}
    assert "2000" in heights
    aligns = {a.get("horizontal") for a in header.findall(".//hh:paraPr/hh:align", NS)}
    assert {"LEFT", "CENTER"} <= aligns
    lefts = {e.get("value") for e in header.iterfind(".//{http://www.hancom.co.kr/hwpml/2011/core}left")}
    assert "2000" in lefts
    fonts_used = {
        tuple(set(c.find("hh:fontRef", NS).attrib.values())) for c in header.findall(".//hh:charPr", NS)
    }
    assert {("0",), ("1",), ("2",)} <= fonts_used


def test_p3_tables_and_merges(built):
    zf = zipfile.ZipFile(built["P3"])
    sec = parse(zf, "Contents/section0.xml")
    tbls = sec.findall(".//hp:tbl", NS)
    assert len(tbls) == 2
    assert [(t.get("rowCnt"), t.get("colCnt")) for t in tbls] == [("2", "2"), ("3", "3")]
    assert len(tbls[0].findall(".//hp:tc", NS)) == 4
    assert len(tbls[1].findall(".//hp:tc", NS)) == 1 + 3 + 2
    assert len({t.get("id") for t in tbls}) == 2
    for tbl in tbls:
        widths = [int(c.get("width")) for c in tbl.findall("hp:tr[1]/hp:tc/hp:cellSz", NS)]
        assert sum(widths) == int(tbl.find("hp:sz", NS).get("width")) == 42522
    header = parse(zf, "Contents/header.xml")
    solid = [
        b for b in header.findall(".//hh:borderFill", NS)
        if b.find("hh:leftBorder", NS).get("type") == "SOLID"
    ]
    assert len(solid) == 1
    assert {t.get("borderFillIDRef") for t in tbls} == {solid[0].get("id")}


def test_p4_variants(built):
    a = parse(zipfile.ZipFile(built["P4a"]), "Contents/section0.xml")
    b = parse(zipfile.ZipFile(built["P4b"]), "Contents/section0.xml")
    c = parse(zipfile.ZipFile(built["P4c"]), "Contents/section0.xml")
    assert len(a.findall("hp:p", NS)) == len(b.findall("hp:p", NS)) == 60
    assert len(c.findall("hp:p", NS)) == 100
    for root, has_seg in ((a, True), (b, False), (c, True)):
        assert bool(root.findall(".//hp:linesegarray", NS)) is has_seg
    breaks = [i for i, p in enumerate(a.findall("hp:p", NS)) if p.get("pageBreak") == "1"]
    assert breaks == [30]
    assert [p.get("pageBreak") for p in b.findall("hp:p", NS)].count("1") == 1
    assert all(p.get("pageBreak") == "0" for p in c.findall("hp:p", NS))
    # 강제 쪽 나눔 뒤 vertpos가 위로 리셋된다
    verts = [int(s.get("vertpos")) for s in a.findall(".//hp:lineseg", NS)]
    assert verts[30] < verts[29] and verts[:30] == sorted(verts[:30])
    # 자연 넘김도 쪽 높이를 넘지 않는다
    page_h = 84188 - 5669 - 4251
    assert max(int(s.get("vertpos")) + int(s.get("vertsize")) for s in c.findall(".//hp:lineseg", NS)) <= page_h
    prevs = {e.get("value") for e in parse(zipfile.ZipFile(built["P4a"]), "Contents/header.xml").iterfind(
        ".//{http://www.hancom.co.kr/hwpml/2011/core}prev")}
    assert "300" in prevs


def test_p2_to_p4_use_r1_observed_version(built):
    for name in ("P2", "P3", "P4a", "P4b", "P4c"):
        v = parse(zipfile.ZipFile(built[name]), "version.xml")
        assert v.get("application") == "Hancom Office Hangul", name


def test_readme_written_with_guidance_for_every_probe(probe, built, out_dir):
    text = (out_dir / "README-probe.txt").read_text(encoding="utf-8")
    for info, _ in probe.PROBES.values():
        assert info.filename in text and info.expect in text and info.purpose in text
    assert "다른 이름으로 저장" in text
    assert re.search(r"한글 버전", text)


def test_unknown_probe_name_rejected(probe, out_dir):
    with pytest.raises(ValueError):
        probe.build_probes(out_dir, ["P9"])


def test_cli_writes_to_given_out(probe, out_dir, capsys):
    assert probe.main(["--out", str(out_dir / "cli"), "--only", "P1a"]) == 0
    assert (out_dir / "cli" / "P1a_empty_r1version.hwpx").exists()
    assert "P1a" in capsys.readouterr().out
