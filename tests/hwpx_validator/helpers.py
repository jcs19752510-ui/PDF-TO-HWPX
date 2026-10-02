"""unit-27 테스트 공용 헬퍼."""

from __future__ import annotations

import re
from pathlib import Path


def run_validator(vmod, profile, pkg, tmp_path: Path, **kw):
    path = pkg.write(tmp_path / "case.hwpx")
    return vmod.validate_hwpx(path, profile, **kw)


def codes(violations) -> set[str]:
    return {v.code for v in violations}


def patch_bytes(pkg, part: str, fn) -> None:
    pkg.patches[part] = fn


def replace_bytes(old: bytes, new: bytes):
    def _fn(data: bytes) -> bytes:
        assert old in data, "패치 대상 바이트가 없다"
        return data.replace(old, new, 1)

    return _fn


def strip_ns_decl(prefix: str):
    rx = re.compile(rb' xmlns:' + prefix.encode() + rb'="[^"]*"')

    def _fn(data: bytes) -> bytes:
        out, n = rx.subn(b"", data, count=1)
        assert n == 1, "네임스페이스 선언을 찾지 못했다"
        return out

    return _fn
