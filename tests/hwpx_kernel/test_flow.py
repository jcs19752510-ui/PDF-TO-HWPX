"""flow.py: L1 레이아웃 정책 (T1)."""

from __future__ import annotations

import pytest

from pdf_to_hwpx.hwpx_kernel import flow
from pdf_to_hwpx.hwpx_kernel.section import PageSetup


@pytest.fixture
def tracker():
    # 콘텐츠 상자: 좌 100pt, 폭 400pt, 상 50pt
    return flow.FlowTracker(100, 400, 50)


def test_quantize():
    assert flow.quantize(0, 200) == 0
    assert flow.quantize(99, 200) == 0
    assert flow.quantize(101, 200) == 200
    assert flow.quantize(-101, 200) == -200
    with pytest.raises(ValueError):
        flow.quantize(1, 0)


def test_invalid_width_rejected():
    with pytest.raises(ValueError):
        flow.FlowTracker(0, 0, 0)


def test_for_page_uses_page_setup():
    t = flow.FlowTracker.for_page(PageSetup.a4())
    assert t.left_pt == pytest.approx(85.03)
    assert t.width_pt == pytest.approx(425.22)
    assert t.top_pt == pytest.approx(56.69)
    assert t.content_width == 42522


def test_left_default_and_indent_quantized(tracker):
    p = tracker.place(50, 62, 100, 300)
    assert (p.align, p.left, p.prev) == ("LEFT", 0, 0)
    p2 = tracker.place(70, 82, 122, 300)  # 22pt 들여쓰기 -> 2pt 단위 -> 2200
    assert p2.align == "LEFT" and p2.left == 2200
    assert p2.horzpos == 2200 and p2.horzsize == 40000 - 2200


def test_negative_indent_clamped_to_zero(tracker):
    assert tracker.place(50, 62, 90, 300).left == 0


def test_center_and_right_detection(tracker):
    # 폭 400, 중앙 300. x0=200,x1=400 -> 중앙 정렬
    assert tracker.place(50, 62, 200, 400).align == "CENTER"
    assert tracker.place(80, 92, 300, 500).align == "RIGHT"  # 오른쪽 여유 0, x0-L=200>=0.3W
    # 오른쪽에 붙었지만 시작이 너무 왼쪽이면 RIGHT가 아니다
    assert tracker.place(110, 122, 110, 500).align == "LEFT"
    # 중앙이지만 좌우 여유가 0.1W 미만이면 CENTER가 아니다
    assert tracker.place(140, 152, 100, 500).align == "LEFT"


def test_center_and_right_have_zero_left(tracker):
    assert tracker.place(50, 62, 200, 400).left == 0
    assert tracker.place(80, 92, 300, 500).left == 0


def test_prev_uses_top_difference_without_error_accumulation(tracker):
    tracker.place(50, 62, 100, 300)  # 첫 문단: top - T = 0
    p = tracker.place(74, 86, 100, 300)  # 24 - 12 = 12pt
    assert p.prev == 1200
    p = tracker.place(98.4, 110.4, 100, 300)  # 24.4 - 12 = 12.4 -> 1pt 단위 양자화 1200
    assert p.prev == 1200
    p = tracker.place(110.4, 122.4, 100, 300)  # 촘촘: 갭 0 -> 0
    assert p.prev == 0


def test_prev_first_paragraph_relative_to_content_top(tracker):
    assert tracker.place(80, 92, 100, 300).prev == 3000


def test_prev_capped_and_never_negative(tracker):
    assert tracker.place(1000, 1012, 100, 300).prev == flow.PREV_MAX_HWPUNIT
    tracker.new_page()
    tracker.place(60, 72, 100, 300)
    assert tracker.place(65, 77, 100, 300).prev == 0  # 겹치는 줄


def test_new_page_resets_prev_reference(tracker):
    tracker.place(700, 712, 100, 300)
    tracker.new_page()
    p = tracker.place(60, 72, 100, 300)
    assert p.prev == 1000 and p.vertpos == 1000


def test_backwards_top_gives_zero_prev(tracker):
    tracker.place(300, 312, 100, 300)
    assert tracker.place(100, 112, 100, 300).prev == 0


def test_line_spacing_and_size(tracker):
    p = tracker.place(50, 62, 100, 300)
    assert p.line_spacing == 100 and p.intent == 0 and p.size == 1200
    assert p.vertpos == 0


def test_horzsize_lower_bound(tracker):
    p = tracker.place(50, 62, 100 + 399.9, 600)
    assert p.horzsize >= 1
