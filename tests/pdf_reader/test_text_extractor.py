"""unit-1 AC-1~AC-5 -- `pdf_to_hwpx/pdf_reader/text_extractor.py` 검증.

근거: docs/harness/units/unit-1-note.md §5(AC-1~AC-5), 03-system-design.md
§1-3(unit-1 행)/§3-1(TextBlockIR).

PDF 픽스처는 unit-0 테스트(tests/conftest.py `pdf_fixtures`, unit-0 전용으로
문서화되어 있음)를 건드리지 않기 위해 이 파일 전용의 별도 모듈 스코프
픽스처(`.harness-tmp/pdf_fixtures_06_unit1/`, 프로젝트 루트 기준)를 이 파일
안에서 자체적으로 만든다(병렬 웨이브 규칙 -- 다른 단위의 공유 파일을 수정하지
않음).

reportlab로 실제 PDF를 즉석 생성해 검증하는 것을 원칙으로 하되(mock
최소화), AC-3(REQ-007, ToUnicode 매핑 누락 감지)의 `(cid:N)`/PUA/치환문자
신호는 unit-1-note.md §1-3/§4가 이미 명시한 대로 "ToUnicode CMap이 없는
서브셋 폰트를 가진 실제 PDF"를 손으로 만드는 것 자체가 non-trivial해
06단계 시간 내에 실물 PDF로 재현하지 못했다(note와 동일한 한계, 새로
발견한 결함 아님). 대신:
  1. `_sanitize_text` 자체를 화이트박스로 직접 검증하고,
  2. `extract_text_blocks`가 소비하는 유일한 계약인
     `plumber_page.extract_words(...) -> list[word dict]`를 그대로
     만족하는 최소 스텁 객체(``_FakePage``, unittest.mock 미사용)를 통해
     `_build_block`/`_sanitize_text` 연동 경로까지 `extract_text_blocks`
     공개 API로 검증한다.
정상 경로/폰트 스타일/빈 페이지는 전부 reportlab이 만든 실제 PDF를
pdfplumber로 직접 열어 검증한다(mock 없음).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Iterator

import pdfplumber
import pytest
from reportlab.pdfgen import canvas

import pdf_to_hwpx.pdf_reader.text_extractor as text_extractor_module
from pdf_to_hwpx.pdf_reader.ir import TextBlockIR
from pdf_to_hwpx.pdf_reader.loader import load_pdf
from pdf_to_hwpx.pdf_reader.text_extractor import (
    _REPLACEMENT_CHAR,
    _group_words_into_lines,
    _is_bold,
    _is_italic,
    _sanitize_text,
    extract_text_blocks,
)

# 주의(06단계 수정): 이 파일은 tests/pdf_reader/ 아래(프로젝트 루트 기준
# 2단계 하위)에 있으므로, 프로젝트 루트의 `.harness-tmp/`에 픽스처를
# 만들려면 parent가 3번 필요하다(parent.parent만 쓰면 규칙 K를 어기고
# `tests/.harness-tmp/`에 잘못 생성된다 -- 06단계 1차 실행에서 실제로
# 발견해 직접 수정함, 결과서 6절 Fixed 항목 참고).
FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / ".harness-tmp" / "pdf_fixtures_06_unit1"


# --------------------------------------------------------------------------
# 실제 PDF 픽스처 생성 (reportlab, mock 없음)
# --------------------------------------------------------------------------


def _make_single_line_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 12)
    c.drawString(72, 700, "Hello unit one text extractor")
    c.showPage()
    c.save()


def _make_multi_line_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 12)
    y = 700
    for line in ("First line of text", "Second line here", "Third and final line"):
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()


def _make_mixed_style_line_pdf(path: Path) -> None:
    """한 줄 안에서 Normal -> Bold -> Italic으로 폰트가 바뀌는 페이지(AC-2)."""
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 14)
    c.drawString(72, 700, "Normal")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72 + 90, 700, "Bold")
    c.setFont("Helvetica-Oblique", 14)
    c.drawString(72 + 90 + 70, 700, "Italic")
    c.showPage()
    c.save()


def _make_mixed_size_line_pdf(path: Path) -> None:
    """같은 폰트지만 크기가 바뀌는 페이지(AC-2, 그루핑 키가 size도 포함하는지)."""
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "Small")
    c.setFont("Helvetica", 24)
    c.drawString(72 + 60, 700, "BIGGER")
    c.showPage()
    c.save()


def _make_blank_page_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()


def _make_nontext_content_pdf(path: Path) -> None:
    """텍스트 없이 도형만 있는 페이지 -- 스캔본과 유사하게 텍스트 레이어가
    전혀 없는 상황을 흉내낸다(진짜 스캔 이미지가 아니어도 "텍스트 없음"
    분기를 검증하는 데는 충분함)."""
    c = canvas.Canvas(str(path))
    c.rect(50, 50, 100, 100, fill=1)
    c.showPage()
    c.save()


@pytest.fixture(scope="module")
def pdf_fixtures() -> Iterator[dict[str, Path]]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    builders = {
        "single_line": _make_single_line_pdf,
        "multi_line": _make_multi_line_pdf,
        "mixed_style_line": _make_mixed_style_line_pdf,
        "mixed_size_line": _make_mixed_size_line_pdf,
        "blank_page": _make_blank_page_pdf,
        "nontext_content": _make_nontext_content_pdf,
    }
    paths: dict[str, Path] = {}
    for key, builder in builders.items():
        p = FIXTURE_DIR / f"{key}.pdf"
        builder(p)
        paths[key] = p

    yield paths

    for p in paths.values():
        if p.exists():
            p.unlink()
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        pass  # 다른 테스트가 같은 세션에서 추가 생성했다면 강제로 지우지 않음


# --------------------------------------------------------------------------
# 계약을 흉내내는 최소 스텁 (unittest.mock 미사용, 순수 duck-typing 객체)
# --------------------------------------------------------------------------


def _fake_word(
    text: str,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    fontname: str | None = "Helvetica",
    size: float | None = 12.0,
) -> dict:
    word: dict = {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}
    if fontname is not None:
        word["fontname"] = fontname
    if size is not None:
        word["size"] = size
    return word


class _FakePage:
    """``extract_text_blocks``가 실제로 필요로 하는 유일한 계약
    (``extract_words(**kwargs) -> list[dict]``)만 구현한 스텁."""

    def __init__(self, words: list[dict]) -> None:
        self._words = words

    def extract_words(self, **kwargs: object) -> list[dict]:
        return self._words


# ==========================================================================
# AC-1: 기본 추출
# ==========================================================================


def test_extract_text_blocks_normal_page_returns_nonempty_list(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["single_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert isinstance(blocks, list)
    assert len(blocks) > 0
    assert all(isinstance(b, TextBlockIR) for b in blocks)


def test_extract_text_blocks_text_joined_with_single_space(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["single_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert len(blocks) == 1
    assert blocks[0].text == "Hello unit one text extractor"


def test_extract_text_blocks_via_loader_pdfdocument_input_contract(pdf_fixtures):
    """모듈 docstring이 명시한 실제 입력 계약(PdfDocument.plumber_pdf.pages[i])
    그대로 unit-0의 load_pdf를 통해 얻은 페이지로도 동작하는지 확인."""
    doc = load_pdf(pdf_fixtures["single_line"])
    try:
        blocks = extract_text_blocks(doc.plumber_pdf.pages[0])
    finally:
        doc.close()
    assert len(blocks) == 1
    assert blocks[0].text == "Hello unit one text extractor"


def test_extract_text_blocks_multi_line_produces_one_block_per_line(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["multi_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert len(blocks) == 3
    assert [b.text for b in blocks] == [
        "First line of text",
        "Second line here",
        "Third and final line",
    ]


def test_extract_text_blocks_bbox_order_and_validity(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["multi_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert len(blocks) == 3
    for b in blocks:
        x0, top, x1, bottom = b.bbox
        assert x0 <= x1
        assert top <= bottom
        assert x1 - x0 > 0
        assert bottom - top > 0
    # 위에서 아래로 읽는 순서라면 line 1의 top이 line 2보다 작아야 한다.
    assert blocks[0].bbox[1] < blocks[1].bbox[1] < blocks[2].bbox[1]


# ==========================================================================
# AC-2: 폰트/스타일
# ==========================================================================


def test_font_switch_creates_separate_blocks_with_correct_style_flags(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["mixed_style_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert len(blocks) == 3
    assert [b.text for b in blocks] == ["Normal", "Bold", "Italic"]
    assert blocks[0].bold is False and blocks[0].italic is False
    assert blocks[1].bold is True and blocks[1].italic is False
    assert blocks[2].bold is False and blocks[2].italic is True
    assert "Bold" in (blocks[1].font_name or "")
    assert ("Oblique" in (blocks[2].font_name or "")) or ("Italic" in (blocks[2].font_name or ""))


def test_font_size_switch_on_same_line_creates_separate_blocks(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["mixed_size_line"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert len(blocks) == 2
    assert blocks[0].text == "Small"
    assert blocks[1].text == "BIGGER"
    assert blocks[0].font_size == pytest.approx(10.0)
    assert blocks[1].font_size == pytest.approx(24.0)


def test_is_bold_case_insensitive_and_none_safe():
    assert _is_bold("Arial-BOLD") is True
    assert _is_bold("arial-bold") is True
    assert _is_bold("Arial") is False
    assert _is_bold(None) is False


def test_is_italic_case_insensitive_oblique_variant_and_none_safe():
    assert _is_italic("Times-ITALIC") is True
    assert _is_italic("Helvetica-oblique") is True
    assert _is_italic("Arial") is False
    assert _is_italic(None) is False


# ==========================================================================
# AC-3 (REQ-007): ToUnicode 매핑 누락 감지 -- 3가지 신호
# ==========================================================================


@pytest.mark.parametrize(
    "raw, expected_text, expected_missing",
    [
        ("hello", "hello", False),
        ("", "", False),
        ("normal text no issue", "normal text no issue", False),
        ("a(cid:12)b", f"a{_REPLACEMENT_CHAR}b", True),
        ("(cid:1)(cid:2)", _REPLACEMENT_CHAR * 2, True),
        ("�", _REPLACEMENT_CHAR, True),
        (chr(0xE001), _REPLACEMENT_CHAR, True),  # PUA (BMP)
        (chr(0xE000), _REPLACEMENT_CHAR, True),  # PUA 하한 경계
        (chr(0xF8FF), _REPLACEMENT_CHAR, True),  # PUA 상한 경계
        (chr(0xF0000), _REPLACEMENT_CHAR, True),  # PUA (Supplementary-A)
        (chr(0x100000), _REPLACEMENT_CHAR, True),  # PUA (Supplementary-B)
    ],
)
def test_sanitize_text_detects_three_signal_patterns(raw, expected_text, expected_missing):
    sanitized, missing = _sanitize_text(raw)
    assert sanitized == expected_text
    assert missing is expected_missing


def test_sanitize_text_pua_range_boundaries_excluded():
    # PUA 범위 바로 밖(0xF900은 CJK 호환 한자 영역, PUA 아님)은 감지되지 않아야 함
    assert _sanitize_text(chr(0xF900)) == (chr(0xF900), False)
    # 한글 완성형 영역의 마지막 코드포인트(U+D7A3 근방)도 PUA가 아님
    assert _sanitize_text("힣") == ("힣", False)


def test_extract_text_blocks_integration_cid_pattern_via_stub_page():
    """extract_text_blocks 공개 API를 통해 (cid:N) 신호가 실제로 블록의
    text/to_unicode_missing에 반영되는지 확인(연동 경로 검증, unittest.mock
    미사용 -- 순수 duck-typed 스텁, 파일 상단 docstring 근거)."""
    words = [_fake_word("a(cid:12)b", x0=10, top=100, x1=40, bottom=112)]
    blocks = extract_text_blocks(_FakePage(words))
    assert len(blocks) == 1
    assert blocks[0].text == f"a{_REPLACEMENT_CHAR}b"
    assert blocks[0].to_unicode_missing is True


def test_extract_text_blocks_integration_pua_char_via_stub_page():
    words = [_fake_word(chr(0xE010), x0=10, top=100, x1=20, bottom=112)]
    blocks = extract_text_blocks(_FakePage(words))
    assert len(blocks) == 1
    assert blocks[0].text == _REPLACEMENT_CHAR
    assert blocks[0].to_unicode_missing is True


def test_extract_text_blocks_integration_replacement_char_via_stub_page():
    words = [_fake_word("�", x0=10, top=100, x1=20, bottom=112)]
    blocks = extract_text_blocks(_FakePage(words))
    assert len(blocks) == 1
    assert blocks[0].text == _REPLACEMENT_CHAR
    assert blocks[0].to_unicode_missing is True


def test_extract_text_blocks_integration_clean_word_not_flagged_via_stub_page():
    words = [_fake_word("clean", x0=10, top=100, x1=40, bottom=112)]
    blocks = extract_text_blocks(_FakePage(words))
    assert len(blocks) == 1
    assert blocks[0].text == "clean"
    assert blocks[0].to_unicode_missing is False


# AC-3-8: 알려진 미탐 케이스(설계상 한계, 결함 아님) -- 폰트 미스매치로 인한
# "그럴듯하지만 틀린" 디코딩은 세 신호 중 어느 것도 아니므로 감지되지 않음을
# 확인해, 이 한계가 실제로 재현 가능하다는 것을 기록해 둔다(결함으로 보고하지
# 않음, unit-1-note.md §1-3/AC-3-8 근거).
def test_sanitize_text_known_limitation_plausible_but_wrong_decoding_not_detected():
    plausible_but_wrong = "nnnn"  # 세 신호(cid literal/U+FFFD/PUA) 중 어느 것도 아님
    sanitized, missing = _sanitize_text(plausible_but_wrong)
    assert sanitized == plausible_but_wrong
    assert missing is False  # 알려진 한계 -- 결함 아님


# ==========================================================================
# AC-4: 빈 페이지 / 스캔본
# ==========================================================================


def test_extract_text_blocks_blank_page_returns_empty_list(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["blank_page"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert blocks == []


def test_extract_text_blocks_nontext_content_returns_empty_list(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["nontext_content"])) as pdf:
        blocks = extract_text_blocks(pdf.pages[0])
    assert blocks == []


def test_extract_text_blocks_signature_has_no_page_ir_involvement():
    """is_scanned 판정이 구조적으로 이 함수 책임이 될 수 없음을 시그니처/모듈
    수준에서 확인한다(AC-4-10 -- unit-8 소관, 이 unit이 PageIR을 아예 참조하지
    않음)."""
    sig = inspect.signature(extract_text_blocks)
    assert list(sig.parameters.keys()) == ["plumber_page"]
    assert not hasattr(text_extractor_module, "PageIR")


# ==========================================================================
# AC-5: 안정성
# ==========================================================================


def test_extract_text_blocks_idempotent_multiple_calls(pdf_fixtures):
    with pdfplumber.open(str(pdf_fixtures["multi_line"])) as pdf:
        page = pdf.pages[0]
        first = extract_text_blocks(page)
        second = extract_text_blocks(page)
    assert first == second
    assert first is not second


def test_text_extractor_only_imports_ir_and_does_not_redefine_shared_contracts():
    """범위 외 파일(ir.py/loader.py) 미접촉 -- 코드 리뷰로 확인 가능해야 한다는
    AC-5-12를 소스 텍스트 검사로 보강 확인."""
    source = Path(text_extractor_module.__file__).read_text(encoding="utf-8")
    assert "from pdf_to_hwpx.pdf_reader.ir import TextBlockIR" in source
    assert "class TextBlockIR" not in source
    assert "class PdfDocument" not in source
    assert "class PageIR" not in source


# ==========================================================================
# 명시적 AC 범위는 아니지만 위험한 입력이라 판단해 추가한 케이스
# (06-unit-tester 필수 원칙: 명백히 위험한 케이스는 범위를 벗어나도 기록)
# ==========================================================================


def test_group_words_into_lines_respects_tolerance_and_x_order():
    words = [
        _fake_word("A", x0=0, top=100.0, x1=10, bottom=110),
        _fake_word("B", x0=20, top=101.5, x1=30, bottom=111.5),  # 허용오차(2.5pt) 이내
        _fake_word("C", x0=0, top=200.0, x1=10, bottom=210),  # 별도 줄
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["A", "B"]
    assert [w["text"] for w in lines[1]] == ["C"]


def test_build_block_defensively_handles_missing_text_key():
    """word dict에 'text' 키 자체가 없는 방어적 경계 케이스
    (word.get('text', '') 방어 코드 검증)."""
    word = {"x0": 0, "top": 0, "x1": 10, "bottom": 10, "fontname": "Helvetica", "size": 12.0}
    blocks = extract_text_blocks(_FakePage([word]))
    assert len(blocks) == 1
    assert blocks[0].text == ""


def test_build_block_defensively_handles_missing_fontname_and_size():
    """fontname/size 자체가 없는 word -- font_name/font_size가 None으로,
    bold/italic은 False로 안전하게 폴백하는지 확인."""
    word = {"text": "x", "x0": 0, "top": 0, "x1": 10, "bottom": 10}
    blocks = extract_text_blocks(_FakePage([word]))
    assert len(blocks) == 1
    assert blocks[0].font_name is None
    assert blocks[0].font_size is None
    assert blocks[0].bold is False
    assert blocks[0].italic is False


def test_extract_text_blocks_empty_words_list_returns_empty_list_via_stub():
    """extract_words가 빈 목록을 반환하는 경우(AC-4-9와 동일한 분기,
    스텁으로 직접 확인)."""
    blocks = extract_text_blocks(_FakePage([]))
    assert blocks == []


# ==========================================================================
# 내부검증 2차에서 추가: 같은 시각적 줄 안에서 폰트 "크기"가 크게 다를 때
# 읽기 순서가 뒤집히는지 재확인하기 위한 3-word 변형(회귀 고정용).
# 1차 실행에서 test_font_size_switch_on_same_line_creates_separate_blocks가
# 실패해 발견한 결함(DEF-001, 결과서 6절)의 재현 범위를 넓혀 우연이 아님을
# 확인한다.
# ==========================================================================


def test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub():
    """실제 pdfplumber가 아닌, 관찰된 실제 좌표값을 그대로 박아 넣은 스텁으로
    재현한다(reportlab PDF 재생성 없이도 결정론적으로 재현 가능함을 보여
    회귀 테스트로서의 안정성을 높임). 좌표는 6절 DEF-001의 실측값 그대로.
    """
    words = [
        _fake_word("Small", x0=72.0, top=133.9598, x1=100.0, bottom=143.9598, size=10.0),
        _fake_word("BIGGER", x0=132.0, top=122.8578, x1=170.0, bottom=146.8578, size=24.0),
        _fake_word("Tail", x0=175.0, top=134.0, x1=190.0, bottom=144.0, size=10.0),
    ]
    blocks = extract_text_blocks(_FakePage(words))
    texts = [b.text for b in blocks]
    # 기대(명세상 올바른 읽기 순서, DEF-001 재작업 후 통과 기대):
    assert texts == ["Small", "BIGGER", "Tail"]


# ==========================================================================
# 06단계 재검증(2026-09-28, 규칙 F) 추가: DEF-001 수정으로 도입된
# 겹침 비율(_LINE_OVERLAP_RATIO=0.5) 기반 판정 자체의 새 경계 케이스.
# 05가 알고리즘을 교체했으므로 "재작업 전에는 존재하지 않았던" 새로운
# 경계 조건(정확히 0.5, 0.5 바로 아래, 완전 비겹침, 첨자류 짧은 word,
# 전이적 병합 사슬)을 회귀 관점에서 직접 탐색해 결함 재유입 여부를 확인한다.
# ==========================================================================


def test_group_words_into_lines_overlap_ratio_exactly_at_threshold_merges():
    """겹침 비율이 정확히 0.5(임계값, `_has_vertical_overlap`이 `>=`를 사용)인
    경계에서 같은 줄로 판정되는지 확인한다.
    A: top=0..10 (height 10), B: top=5..15 (height 10).
    overlap = min(10,15)-max(0,5) = 5, ratio = 5/10 = 0.5 (경계값 그 자체)."""
    words = [
        _fake_word("A", x0=0, top=0.0, x1=10, bottom=10.0),
        _fake_word("B", x0=20, top=5.0, x1=30, bottom=15.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 1
    assert [w["text"] for w in lines[0]] == ["A", "B"]


def test_group_words_into_lines_overlap_ratio_just_below_threshold_splits():
    """겹침 비율이 0.5 바로 아래(0.499)면 다른 줄로 분리되는지 확인한다.
    A: top=0..10 (height 10), B: top=5.01..15.01 (height 10).
    overlap = 10-5.01 = 4.99, ratio = 4.99/10 = 0.499 (< 0.5)."""
    words = [
        _fake_word("A", x0=0, top=0.0, x1=10, bottom=10.0),
        _fake_word("B", x0=20, top=5.01, x1=30, bottom=15.01),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["A"]
    assert [w["text"] for w in lines[1]] == ["B"]


def test_group_words_into_lines_completely_non_overlapping_words_are_different_lines():
    """세로 구간이 전혀 겹치지 않는(overlap <= 0) 두 word는 명확히 다른
    줄로 분리되어야 한다(겹침 비율 기반 판정의 가장 기본적인 음성 케이스)."""
    words = [
        _fake_word("Top", x0=0, top=0.0, x1=10, bottom=10.0),
        _fake_word("Bottom", x0=0, top=50.0, x1=10, bottom=60.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["Top"]
    assert [w["text"] for w in lines[1]] == ["Bottom"]


def test_group_words_into_lines_subscript_like_short_word_contained_in_line_merges():
    """아래첨자처럼 세로로 짧은 word가 더 큰 word의 세로 구간 "안에"
    완전히 포함되는 경우: overlap/min(height)이 1.0이 되어 같은 줄로
    합쳐진다(현재 알고리즘의 의도된 동작 -- unit-1-note.md 재작업 절 "남은
    한계"에 이미 명시된 대로, 첨자류는 배치에 따라 합쳐지거나 분리될 수
    있음. 이 케이스는 "합쳐지는" 쪽 예시).
    Main: top=100..120 (height 20). Sub: top=115..120 (height 5, Main의
    구간 안에 완전히 포함) -> overlap=5, ratio=5/min(20,5)=1.0."""
    words = [
        _fake_word("Main", x0=0, top=100.0, x1=30, bottom=120.0),
        _fake_word("sub", x0=30, top=115.0, x1=35, bottom=120.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 1
    assert [w["text"] for w in lines[0]] == ["Main", "sub"]


def test_group_words_into_lines_superscript_like_short_word_offset_above_splits():
    """위첨자처럼 세로로 짧은 word가 본문 word 세로 구간의 위쪽 경계에
    살짝만 걸치는 경우: 겹침 비율이 0.5 미만이면 별도 줄로 분리된다(현재
    알고리즘의 알려진 한계 -- 시각적으로는 같은 줄에 붙어 있는 첨자라도
    분리될 수 있음, unit-1-note.md 재작업 절 "남은 한계" 그대로 재현. 결함
    아님 -- 이번 재작업의 수정 대상이 아니라고 note가 명시).
    Main: top=100..120 (height 20). Sup(위첨자): top=98..101 (height 3,
    Main 구간의 최상단과 아주 조금만 겹침) -> overlap=1, ratio=1/3=0.33."""
    words = [
        _fake_word("Main", x0=0, top=100.0, x1=30, bottom=120.0),
        _fake_word("sup", x0=30, top=98.0, x1=35, bottom=101.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 2  # 알려진 한계: 시각적 첨자가 별도 줄로 분리됨


def test_group_words_into_lines_transitive_merge_chain_known_limitation():
    """A-B가 겹치고(ratio>=0.5) B-C가 겹치지만(ratio>=0.5) A-C 자체는
    임계값 미만(0.1)인 "사슬형" 케이스에서, 현재 알고리즘(멤버 중 아무거나와
    임계값 이상 겹치면 편입)은 A/B/C를 전부 한 줄로 묶는다. 이는
    unit-1-note.md 재작업 절 "남은 한계" 3번째 항목이 이미 예견한 동작이며,
    이번 재검증에서 실제로 재현됨을 확인한다(새로 발견한 결함으로 보고하지
    않음 -- 이미 문서화된 한계, 통상 문서에서는 발생 가능성이 낮다고 note가
    판단한 대로 극단적으로 구성한 좌표에서만 재현됨).
    A: top=0..10, B: top=4..14 (A-B overlap=6, ratio=0.6),
    C: top=9..19 (B-C overlap=5, ratio=0.5 / A-C overlap=1, ratio=0.1)."""
    words = [
        _fake_word("A", x0=0, top=0.0, x1=10, bottom=10.0),
        _fake_word("B", x0=10, top=4.0, x1=20, bottom=14.0),
        _fake_word("C", x0=20, top=9.0, x1=30, bottom=19.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 1  # 알려진 한계: 전이적 병합으로 셋이 한 줄로 묶임
    assert [w["text"] for w in lines[0]] == ["A", "B", "C"]


def test_group_words_into_lines_empty_list_direct_call_returns_empty_list():
    """`_group_words_into_lines`를 빈 리스트로 직접 호출하는 방어적 분기
    (공개 API `extract_text_blocks`는 이 지점에 도달하기 전에 이미 빈 words를
    걸러내지만, 이 비공개 헬퍼 자체의 방어 코드도 직접 검증한다 -- 라인
    커버리지 재확인 과정에서 발견한 미실행 분기)."""
    assert _group_words_into_lines([]) == []


def test_group_words_into_lines_cluster_member_overlap_check_skips_non_overlapping_member():
    """한 줄 클러스터에 이미 세로 구간이 서로 다른 멤버 2개(작은 word +
    큰 word)가 섞여 있을 때, 새 word가 그 중 세로 구간이 겹치지 않는
    멤버(작은 쪽)는 건너뛰고(overlap<=0, `_has_vertical_overlap`의 `continue`
    분기) 겹치는 멤버(큰 쪽)로만 판정되어 병합되는지 확인한다(라인 커버리지
    재확인 과정에서 발견한 미실행 분기 -- `overlap<=0`으로 continue하는
    경로).
    W1: top=0..3(height3, 작음) -> 단독 클러스터, max_bottom=3.
    W2: top=1..20(height19, 큼) -> W1과 overlap=2, ratio=2/3=0.667>=0.5로
        같은 클러스터 편입, max_bottom=20.
    W3: top=10..25(height15) -> 클러스터 quick-check(10<20) 통과 후, 먼저
        검사되는 W1과는 overlap=min(25,3)-max(10,0)=3-10=-7<=0 (continue),
        다음으로 검사되는 W2와는 overlap=min(25,20)-max(10,1)=10,
        ratio=10/min(15,19)=0.667>=0.5로 매칭되어 같은 줄로 병합된다."""
    words = [
        _fake_word("W1", x0=0, top=0.0, x1=10, bottom=3.0),
        _fake_word("W2", x0=10, top=1.0, x1=20, bottom=20.0),
        _fake_word("W3", x0=20, top=10.0, x1=30, bottom=25.0),
    ]
    lines = _group_words_into_lines(words)
    assert len(lines) == 1
    assert [w["text"] for w in lines[0]] == ["W1", "W2", "W3"]
