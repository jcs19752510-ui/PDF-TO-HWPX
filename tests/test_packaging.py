"""unit-0 AC-4 — 패키지/스캐폴딩 검증.

근거: unit-0-note.md AC-4, `pyproject.toml`, 03 §1-3(패키지 레이아웃 확정표).
"""

from __future__ import annotations

import importlib
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SUBPACKAGES = ["common", "pdf_reader", "hwpx_kernel", "hwpx_writer", "core", "cli", "gui"]

UNIT0_PY_FILES = [
    REPO_ROOT / "pdf_to_hwpx" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "common" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "common" / "exceptions.py",
    REPO_ROOT / "pdf_to_hwpx" / "common" / "logging_setup.py",
    REPO_ROOT / "pdf_to_hwpx" / "pdf_reader" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "pdf_reader" / "loader.py",
    REPO_ROOT / "pdf_to_hwpx" / "hwpx_kernel" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "hwpx_writer" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "core" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "cli" / "__init__.py",
    REPO_ROOT / "pdf_to_hwpx" / "gui" / "__init__.py",
]


# AC-4-1: 리포지토리 루트에서 pip install -e ".[dev]"가 오류 없이 성공한다.
# 이 테스트를 실행할 수 있다는 사실 자체가(= pdf_to_hwpx가 import 가능하다는
# 사실이) 이미 최소 1회의 성공한 설치를 전제하지만, 여기서는 "재실행해도
# 오류 없이 성공하는가"(멱등성 포함)를 현재 인터프리터로 다시 확인한다.
def test_editable_install_succeeds():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "-e", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"pip install -e . 실패\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# AC-4-2: import pdf_to_hwpx; pdf_to_hwpx.__version__ == "0.1.0"
def test_package_version_is_0_1_0():
    import pdf_to_hwpx

    importlib.reload(pdf_to_hwpx)
    assert pdf_to_hwpx.__version__ == "0.1.0"


# AC-4-3: python -m py_compile 대상 파일 전부가 문법 오류 없이 통과한다.
@pytest.mark.parametrize("py_file", UNIT0_PY_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_py_compile_succeeds(py_file: Path):
    assert py_file.exists(), f"파일이 존재하지 않음: {py_file}"
    py_compile.compile(str(py_file), doraise=True)


# AC-4-4: pdf_to_hwpx/{common,pdf_reader,hwpx_kernel,hwpx_writer,core,cli,gui}/__init__.py가
# 모두 존재하고 import 가능하다.
@pytest.mark.parametrize("subpackage", SUBPACKAGES)
def test_subpackage_init_exists_and_importable(subpackage: str):
    init_path = REPO_ROOT / "pdf_to_hwpx" / subpackage / "__init__.py"
    assert init_path.exists(), f"{subpackage}/__init__.py 가 없음"

    module = importlib.import_module(f"pdf_to_hwpx.{subpackage}")
    assert module is not None
