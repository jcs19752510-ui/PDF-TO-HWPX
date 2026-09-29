"""DocContext: 문서 하나를 만드는 동안 모든 빌더가 공유하는 상태 (03 §3-3-2).

오케스트레이터가 ``DocContext.new()``로 만들어 모든 빌더에 넘긴다. 그림 등록부
(``bin_data``)는 04_그림 참조 전이라 구조가 미확정이므로 두지 않는다. 그림 같은
미지원 요소는 ``note_unsupported()``로 집계만 하고 출력에서 제외한다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from pdf_to_hwpx.hwpx_kernel.styles import StyleRegistry

_TBL_ID_START = 1_000_000_001  # 32비트 양의 정수 범위 안에서 순증가 (03 §3-3-2)
_UINT32_MAX = 2**32 - 1


@dataclass
class IdAllocator:
    _next_tbl_id: int = _TBL_ID_START
    _next_z_order: int = 0

    def next_table(self) -> tuple[int, int]:
        """(tbl id, zOrder). zOrder는 0부터 표마다 증가한다 (분석서 §7)."""
        if self._next_tbl_id > _UINT32_MAX:
            raise OverflowError("표 id가 32비트 범위를 넘었습니다.")
        tbl_id, z_order = self._next_tbl_id, self._next_z_order
        self._next_tbl_id += 1
        self._next_z_order += 1
        return tbl_id, z_order


@dataclass
class DocContext:
    registry: StyleRegistry = field(default_factory=StyleRegistry)
    ids: IdAllocator = field(default_factory=IdAllocator)
    unsupported: Counter[str] = field(default_factory=Counter)

    @classmethod
    def new(cls) -> DocContext:
        return cls()

    def note_unsupported(self, kind: str) -> None:
        self.unsupported[kind] += 1

    def build_header(self, sec_cnt: int) -> bytes:
        return self.registry.serialize_header(sec_cnt)
