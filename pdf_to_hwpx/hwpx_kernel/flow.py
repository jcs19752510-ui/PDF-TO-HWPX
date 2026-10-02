"""레이아웃 정책 상수와 FlowTracker (03 §3-3-4, 결정 L1, DEC-057).

PDF 좌표(pt, 좌상단 원점, y 아래로 증가)는 여기서 문단 서식(정렬/들여쓰기/앞 간격)과
lineseg 추정값을 정하는 데만 쓰고 절대 좌표 속성으로 출력하지 않는다.
아래 상수는 모두 튜닝 대상이며(실험 G1/P4), 값의 근거는 03 §3-3-2/§3-3-4다.
"""

from __future__ import annotations

from dataclasses import dataclass

from pdf_to_hwpx.hwpx_kernel.constants import HWPUNIT_PER_PT, pt_to_hwpunit

DEFAULT_FONT_PT = 10.0
TABLE_FONT_PT = 10.0
LINE_SPACING_PERCENT = 100  # 03 §3-3-4 4: 세로 모델을 가산적으로 만들기 위해 100% (추론, P4에서 확인)
MIN_ROW_HEIGHT = 1782  # 03 §3-3-5

# 양자화 단위 (03 §3-3-2). StyleRegistry의 paraPr 키 폭발을 막는다.
LEFT_QUANTUM = 200  # 2pt
PREV_QUANTUM = 100  # 1pt
PREV_MAX_HWPUNIT = 200 * HWPUNIT_PER_PT  # 문단 앞 간격 상한 200pt

# 정렬 판정 (03 §3-3-4 2).
CENTER_TOLERANCE = 0.02
CENTER_MIN_SIDE_GAP = 0.1
RIGHT_TOLERANCE = 0.02
RIGHT_MIN_LEFT_GAP = 0.3

# lineseg 추정 (03 §3-3-4 6, 분석서 §6-4).
EMIT_LINESEGS = True
BASELINE_RATIO = 0.85
LINESEG_FLAGS_FIRST = 393216  # 값의 비트 의미는 【미확인】. 관찰값 그대로 사용.

ALIGN_LEFT = "LEFT"
ALIGN_CENTER = "CENTER"
ALIGN_RIGHT = "RIGHT"


def quantize(value: float, quantum: int) -> int:
    if quantum <= 0:
        raise ValueError("quantum must be positive")
    return round(value / quantum) * quantum


@dataclass(frozen=True)
class FlowPlacement:
    align: str
    left: int  # HWPUNIT, 양자화됨 (paraPr margin left)
    intent: int  # HWPUNIT (첫줄 들여쓰기/내어쓰기, L1에서는 항상 0)
    prev: int  # HWPUNIT, 양자화됨 (paraPr margin prev)
    line_spacing: int  # PERCENT
    vertpos: int  # HWPUNIT, 쪽 안 세로 위치 (lineseg 추정용)
    horzpos: int  # HWPUNIT (= left)
    horzsize: int  # HWPUNIT (콘텐츠 폭 - left, 하한 1)
    size: int  # HWPUNIT, 블록 높이 (bottom-top)


class FlowTracker:
    """한 구역의 콘텐츠 상자 안에서 블록을 위에서 아래로 놓으며 서식을 산정한다."""

    def __init__(self, content_left_pt: float, content_width_pt: float, content_top_pt: float):
        if content_width_pt <= 0:
            raise ValueError("content_width_pt must be positive")
        self.left_pt = float(content_left_pt)
        self.width_pt = float(content_width_pt)
        self.top_pt = float(content_top_pt)
        self._prev_top: float | None = None
        self._prev_size: float = 0.0

    @classmethod
    def for_page(cls, page_setup) -> FlowTracker:  # PageSetup (순환 import 회피를 위해 타입 생략)
        return cls(
            page_setup.margin_left / HWPUNIT_PER_PT,
            page_setup.text_width / HWPUNIT_PER_PT,
            page_setup.margin_top / HWPUNIT_PER_PT,
        )

    @property
    def content_width(self) -> int:
        return pt_to_hwpunit(self.width_pt)

    def new_page(self) -> None:
        """쪽이 바뀌었음을 알린다. 다음 블록의 앞 간격은 페이지 상단 기준."""
        self._prev_top = None
        self._prev_size = 0.0

    def _align(self, x0: float, x1: float) -> str:
        w = self.width_pt
        left_gap = x0 - self.left_pt
        right_gap = self.left_pt + w - x1
        center_off = abs((x0 + x1) / 2 - (self.left_pt + w / 2))
        if (
            center_off <= CENTER_TOLERANCE * w
            and left_gap >= CENTER_MIN_SIDE_GAP * w
            and right_gap >= CENTER_MIN_SIDE_GAP * w
        ):
            return ALIGN_CENTER
        if right_gap <= RIGHT_TOLERANCE * w and left_gap >= RIGHT_MIN_LEFT_GAP * w:
            return ALIGN_RIGHT
        return ALIGN_LEFT

    def place(self, top_pt: float, bottom_pt: float, x0_pt: float, x1_pt: float) -> FlowPlacement:
        size_pt = max(0.0, bottom_pt - top_pt)
        align = self._align(x0_pt, x1_pt)
        left = quantize(max(0.0, x0_pt - self.left_pt) * HWPUNIT_PER_PT, LEFT_QUANTUM) if align == ALIGN_LEFT else 0

        if self._prev_top is None:
            gap_pt = top_pt - self.top_pt
        else:
            gap_pt = (top_pt - self._prev_top) - self._prev_size
        prev = 0
        if gap_pt > 0:
            prev = min(quantize(gap_pt * HWPUNIT_PER_PT, PREV_QUANTUM), PREV_MAX_HWPUNIT)

        self._prev_top = top_pt
        self._prev_size = size_pt

        return FlowPlacement(
            align=align,
            left=left,
            intent=0,
            prev=prev,
            line_spacing=LINE_SPACING_PERCENT,
            vertpos=max(0, pt_to_hwpunit(top_pt - self.top_pt)),
            horzpos=left,
            horzsize=max(1, self.content_width - left),
            size=pt_to_hwpunit(size_pt),
        )
