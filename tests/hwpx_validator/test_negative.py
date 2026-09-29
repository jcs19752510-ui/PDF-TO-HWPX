"""음성 사례: B0 유형 결함 fixture는 각각 정확한 위반 코드로 FAIL해야 한다."""

from __future__ import annotations

import pytest

from .cases import CASES
from .helpers import codes, run_validator

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")  # zipfile의 중복 이름 경고(의도된 사례)


def test_case_ids_unique():
    ids = [c[0] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("cid,mutate,expected", CASES, ids=[c[0] for c in CASES])
def test_defect_is_detected(cid, mutate, expected, pkg, vmod, profile, tmp_path):
    mutate(pkg)
    found = codes(run_validator(vmod, profile, pkg, tmp_path))
    assert expected <= found, f"{cid}: 기대 {sorted(expected)} 중 누락 {sorted(expected - found)} (실제 {sorted(found)})"


@pytest.mark.parametrize("cid,mutate,expected", CASES, ids=[c[0] for c in CASES])
def test_turning_a_check_off_loses_the_detection(cid, mutate, expected, pkg, vmod, profile, tmp_path):
    """검사 하나를 끄면(ignore) 그 사례의 기대 코드가 사라진다 = 사례가 그 검사에 실제로 의존한다."""
    mutate(pkg)
    for code in sorted(expected):
        found = codes(run_validator(vmod, profile, pkg, tmp_path, ignore={code}))
        assert code not in found
        assert not expected <= found, f"{cid}: {code}를 꺼도 기대 집합이 유지된다(사례가 검사와 무관)"


def test_not_a_zip(vmod, profile, tmp_path):
    p = tmp_path / "x.hwpx"
    p.write_bytes(b"PK this is not a zip")
    assert codes(vmod.validate_hwpx(p, profile)) == {"V1.NOT_ZIP"}


def test_missing_file_raises(vmod, profile, tmp_path):
    with pytest.raises(FileNotFoundError):
        vmod.validate_hwpx(tmp_path / "nope.hwpx", profile)


def test_zip_part_size_limit(pkg, vmod, profile, tmp_path, monkeypatch):
    monkeypatch.setattr(vmod, "MAX_PART_BYTES", 100)
    found = codes(run_validator(vmod, profile, pkg, tmp_path))
    assert "V1.TOO_LARGE" in found


def test_violation_cap_and_summary(pkg, vmod, profile, tmp_path):
    from .cases import _many_bogus_attrs

    _many_bogus_attrs(pkg)
    v = run_validator(vmod, profile, pkg, tmp_path)
    attr_hits = [x for x in v if x.code == "V4.ATTR"]
    assert len(attr_hits) == vmod.PER_CODE_CAP
    summary = [x for x in v if x.code == "V0.SUPPRESSED"]
    assert summary and "V4.ATTR" in summary[0].message


def test_prefix_ignore_turns_off_whole_family(pkg, vmod, profile, tmp_path):
    from .cases import _b0_composite

    _b0_composite(pkg)
    found = codes(run_validator(vmod, profile, pkg, tmp_path, ignore={"V4", "V13"}))
    assert not any(c.startswith(("V4.", "V13.")) for c in found)
    assert "V12.SECPR_COUNT" in found


def test_b0_composite_reports_many_distinct_defects(pkg, vmod, profile, tmp_path):
    from .cases import _b0_composite

    _b0_composite(pkg)
    v = run_validator(vmod, profile, pkg, tmp_path)
    assert len(codes(v)) >= 8
