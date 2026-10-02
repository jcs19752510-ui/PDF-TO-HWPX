"""hwpx_kernel 테스트 공용 픽스처 (규칙 K: 파일 산출물은 .harness-tmp/ 아래에만)."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdf_to_hwpx.hwpx_kernel.container import PackageMeta
from pdf_to_hwpx.hwpx_kernel.context import DocContext

_TMP_ROOT = Path(__file__).resolve().parents[2] / ".harness-tmp" / "_05_unit4R" / "pytest"


@pytest.fixture
def out_dir() -> Iterator[Path]:
    path = _TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def ctx() -> DocContext:
    return DocContext.new()


@pytest.fixture
def fixed_meta() -> PackageMeta:
    return PackageMeta(created=datetime(2026, 9, 29, 15, 4, 5, tzinfo=UTC))
