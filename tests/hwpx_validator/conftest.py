"""unit-27 테스트 공용 픽스처.

검증기와 추출기는 경로로 직접 로드한다: ``pdf_to_hwpx.hwpx_kernel``의 ``__init__``(다른 unit이 수정 중일 수
있음)을 거치지 않고 독립적으로 검증하기 위해서다. 참조 HWPX 파일은 어떤 테스트도 읽지 않는다.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "tests" / "fixtures" / "hwpx_profile.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def vmod():
    return _load("hwpx_validator_standalone", ROOT / "pdf_to_hwpx" / "hwpx_kernel" / "validator.py")


@pytest.fixture(scope="session")
def emod():
    return _load("hwpx_profile_extract_standalone", ROOT / "tools" / "hwpx_profile_extract.py")


@pytest.fixture(scope="session")
def profile_raw() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def profile(vmod, profile_raw):
    return vmod.Profile(copy.deepcopy(profile_raw))


@pytest.fixture
def pkg(profile_raw):
    from .synth import build

    return build(copy.deepcopy(profile_raw))
