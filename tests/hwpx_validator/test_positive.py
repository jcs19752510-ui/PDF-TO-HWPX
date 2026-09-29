"""양성 사례: 프로파일 규칙만 만족하는 합성 최소 정상 fixture는 위반 0건이어야 한다."""

from __future__ import annotations

import io
import subprocess
import sys
import zipfile
from pathlib import Path

from lxml import etree

from .helpers import codes, run_validator

ROOT = Path(__file__).resolve().parents[2]


def test_minimal_valid_package_has_no_violations(pkg, vmod, profile, tmp_path):
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_source_can_be_a_file_object(pkg, vmod, profile, tmp_path):
    path = pkg.write(tmp_path / "ok.hwpx")
    with path.open("rb") as fh:
        assert vmod.validate_hwpx(fh, profile) == []
    assert vmod.validate_hwpx(io.BytesIO(path.read_bytes()), profile) == []


def test_default_profile_path_is_loadable(pkg, vmod, tmp_path):
    path = pkg.write(tmp_path / "ok.hwpx")
    assert vmod.validate_hwpx(path) == []  # profile 인자 생략 = tests/fixtures/hwpx_profile.json


def test_minimal_package_layout_matches_profile_facts(pkg, tmp_path, profile_raw):
    path = pkg.write(tmp_path / "ok.hwpx")
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype" and infos[0].compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == profile_raw["zip"]["mimetype_content"].encode()
        assert zf.read("Contents/section0.xml").startswith(profile_raw["xml_prolog"].encode() + b"<")


def test_optional_parts_and_open_enum_are_accepted(pkg, vmod, profile, tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    pkg.order.append("Preview/PrvImage.png")
    pkg.raw["Preview/PrvImage.png"] = png
    pkg.one("Contents/section0.xml", "hp:pagePr").set("landscape", "NARROWLY")  # 관찰되지 않은 가로 값은 오탐 금지
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_empty_run_multiple_runs_and_line_break_are_accepted(pkg, vmod, profile, tmp_path):
    sec = "Contents/section0.xml"
    p = pkg.els(sec, "hp:p")[-1]
    run2 = pkg.E("hp:run", {"charPrIDRef": "0"})
    t = pkg.E("hp:t", text="a")
    t.append(pkg.E("hp:lineBreak"))
    t[0].tail = "b"
    run2.append(t)
    p.insert(1, run2)
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_unobserved_child_combinations_are_not_rejected(pkg, vmod, profile, tmp_path):
    """관찰된 적 없는 조합(예: 표 위 두 번째 문단 없이 표만)이 순서 규칙 오탐을 만들지 않는다."""
    sec = pkg.trees["Contents/section0.xml"]
    sec.remove(sec[2])
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_table_width_tolerance_boundary(pkg, vmod, profile, tmp_path):
    cell = pkg.els("Contents/section0.xml", "hp:cellSz")[0]
    cell.set("width", str(5000 - vmod.DEFAULT_TABLE_WIDTH_TOLERANCE))
    assert run_validator(vmod, profile, pkg, tmp_path) == []
    cell.set("width", str(5000 - vmod.DEFAULT_TABLE_WIDTH_TOLERANCE - 1))
    assert codes(run_validator(vmod, profile, pkg, tmp_path)) == {"V10.WIDTH_SUM"}
    assert run_validator(vmod, profile, pkg, tmp_path, table_width_tolerance=11) == []


def test_merged_cells_are_accepted(pkg, vmod, profile, tmp_path):
    """가로 병합: 두 번째 행을 colSpan=2 한 셀로 바꾸고 덮이지 않는 셀 tc는 만들지 않는다."""
    sec = "Contents/section0.xml"
    tcs = pkg.els(sec, "hp:tc")
    second = tcs[3]
    second.getparent().remove(second)
    first_of_row2 = tcs[2]
    first_of_row2.find(pkg.tag("hp:cellSpan")).set("colSpan", "2")
    first_of_row2.find(pkg.tag("hp:cellSz")).set("width", "10000")
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_rowspan_merge_is_accepted(pkg, vmod, profile, tmp_path):
    sec = "Contents/section0.xml"
    tcs = pkg.els(sec, "hp:tc")
    tcs[0].find(pkg.tag("hp:cellSpan")).set("rowSpan", "2")
    victim = tcs[2]  # 0번 열 2행 셀은 위 셀에 덮인다
    victim.getparent().remove(victim)
    assert run_validator(vmod, profile, pkg, tmp_path) == []


def test_cli_exit_codes(pkg, tmp_path):
    good = pkg.write(tmp_path / "good.hwpx")
    r = subprocess.run(
        [sys.executable, str(ROOT / "pdf_to_hwpx" / "hwpx_kernel" / "validator.py"), str(good)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 0 and "위반 0건" in r.stdout
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(b"nope")
    r = subprocess.run(
        [sys.executable, str(ROOT / "pdf_to_hwpx" / "hwpx_kernel" / "validator.py"), str(bad)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 1 and "V1.NOT_ZIP" in r.stdout


def test_synthetic_xml_is_wellformed_and_prolog_exact(pkg):
    for name in pkg.trees:
        data = pkg.serialize(name)
        assert data.startswith(pkg.prolog + b"<")
        etree.fromstring(data)


def test_ignore_can_target_one_missing_child_only(pkg, vmod, profile, tmp_path):
    """E-L 프로브(linesegarray 생략)처럼 특정 자식 생략만 허용하고 나머지 누락은 계속 잡는다."""
    sec = "Contents/section0.xml"
    for seg in pkg.els(sec, "hp:linesegarray"):
        seg.getparent().remove(seg)
    plain = run_validator(vmod, profile, pkg, tmp_path)
    assert codes(plain) == {"V5.CHILD_MISSING"}
    assert run_validator(vmod, profile, pkg, tmp_path, ignore={"V5.CHILD_MISSING:hp:linesegarray"}) == []
    pkg.one(sec, "hp:tbl").remove(pkg.one(sec, "hp:sz"))
    still = codes(run_validator(vmod, profile, pkg, tmp_path, ignore={"V5.CHILD_MISSING:hp:linesegarray"}))
    assert still == {"V5.CHILD_MISSING"}
