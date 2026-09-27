"""PDF 텍스트 추출 -> ``TextBlockIR`` 변환 (unit-1).

(docs/harness/03-system-design.md §1-3 unit-1 행, §3-1 IR 정의,
docs/harness/02-planning.md REQ-002/REQ-006/REQ-007 참고.)

이 모듈의 입력은 ``pdf_reader/loader.py``(unit-0)가 반환한
``PdfDocument.plumber_pdf``의 개별 페이지(``pdfplumber.page.Page``)다.
호출자(orchestrator, unit-8)가 페이지를 순회하며 이 모듈의 함수를 호출해
``pdf_to_hwpx.pdf_reader.ir.PageIR.text_blocks``를 채우는 구조를 가정한다.

책임 범위 (03 §1-3 unit-1 행 그대로):
    - REQ-002: 텍스트 추출 + 폰트명/크기/굵기/기울임 best-effort 보존.
    - REQ-006(적용대상만): 이 모듈은 NFC 정규화를 직접 수행하지 않는다.
      ``TextBlockIR.text``는 pdfplumber가 반환한 원문 그대로이며, 실제
      NFC 정규화는 파이프라인 후처리 단계인
      ``pdf_reader/hangul_normalizer.py``(unit-15)의 책임이다(03 §1-3
      unit-15 행: "unit-1의 텍스트 출력을 입력으로 받아 정규화").
    - REQ-007: ToUnicode 매핑이 누락된 것으로 의심되는 글리프를 감지해
      대체문자(□, U+25A1)로 치환하고 ``to_unicode_missing=True``로
      표시한다. 감지 방식과 한계는 ``_is_missing_char``/``_CID_RUN``
      주석 및 unit-note를 참고할 것 — 완벽한 감지가 불가능한 휴리스틱이다.

명시적으로 다루지 않는 것:
    - ``PageIR.is_scanned`` 판정: 이 모듈은 페이지에서 추출한 텍스트가
      없으면 단순히 빈 리스트를 반환할 뿐, "이 페이지가 스캔본인지"는
      판단하지 않는다. 그 판단(예: text_blocks가 비었으면 스캔본으로
      간주해 unit-12 OCR 경로로 라우팅)은 orchestrator(unit-8)의 책임이다
      (03 §1-3 unit-1 행 비고, 이번 호출 지시문 명시).
"""

from __future__ import annotations

import re

import pdfplumber

from pdf_to_hwpx.pdf_reader.ir import TextBlockIR

# 같은 줄로 간주할 word 간 세로(top) 오차 허용치(pt). pdfplumber 좌표계는
# 페이지 상단을 원점으로 하는 "top" 기준이며, 같은 시각적 줄이라도 폰트
# 베이스라인 차이로 top이 미세하게 다를 수 있어 완충치를 둔다. 근거가 있는
# 표준값은 아니며, 03단계 설계서에도 구체적 수치가 없어 합리적으로 정한
# 휴리스틱 값이다(unit-note 명시).
_LINE_TOLERANCE_PT = 2.5

# pdfminer.six(pdfplumber의 파싱 엔진)는 폰트에 ToUnicode CMap이 없어
# 문자 코드를 유니코드로 되돌릴 수 없을 때, 기본 폴백으로 "(cid:123)"
# 형태의 문자열을 그 글리프의 텍스트로 그대로 흘려보내는 것으로 알려져
# 있다(PDFTextDevice.handle_undefined_char의 기본 동작). 이 패턴이 추출된
# 텍스트 안에 리터럴로 나타나면 ToUnicode 매핑 누락의 강한 신호로 본다.
_CID_RUN = re.compile(r"\(cid:\d+\)")

_REPLACEMENT_CHAR = "□"  # □, REQ-007이 지정한 대체문자
_UNICODE_REPLACEMENT_CHAR = "�"  # 디코딩 실패를 나타내는 표준 대체문자


def extract_text_blocks(plumber_page: pdfplumber.page.Page) -> list[TextBlockIR]:
    """pdfplumber 페이지 객체 하나에서 ``TextBlockIR`` 목록을 만든다.

    Args:
        plumber_page: ``PdfDocument.plumber_pdf.pages[i]`` (unit-0 산출물).
            이 함수는 이 객체를 읽기 전용으로만 소비한다.

    Returns:
        페이지 내 텍스트를 (줄, 폰트/크기 동일 구간) 단위로 묶은
        ``TextBlockIR`` 목록. 페이지에 추출 가능한 텍스트가 전혀 없으면
        빈 리스트를 반환한다(스캔본 여부 판단은 하지 않음, 모듈 docstring
        참고).
    """
    words = plumber_page.extract_words(
        extra_attrs=["fontname", "size"],
        keep_blank_chars=False,
        use_text_flow=False,
    )
    if not words:
        return []

    blocks: list[TextBlockIR] = []
    for line_words in _group_words_into_lines(words):
        blocks.extend(_line_words_to_blocks(line_words))
    return blocks


def _group_words_into_lines(words: list[dict]) -> list[list[dict]]:
    """word들을 시각적 "줄" 단위로 묶는다.

    pdfplumber는 라인 단위 그룹을 직접 제공하지 않으므로(``extract_words``는
    읽기 순서로 정렬된 평평한 목록만 준다), top 좌표를 기준으로 근접한
    word를 같은 줄로 묶는 휴리스틱을 직접 구현했다. 회전되었거나 심하게
    기울어진 텍스트, 다단(multi-column) 레이아웃에서 같은 top대의 다른
    컬럼 word를 한 줄로 잘못 묶을 가능성은 이 휴리스틱의 한계다(unit-note
    명시).
    """
    ordered = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_top: float | None = None
    for word in ordered:
        if current_top is None or abs(word["top"] - current_top) > _LINE_TOLERANCE_PT:
            if current_line:
                lines.append(current_line)
            current_line = [word]
            current_top = word["top"]
        else:
            current_line.append(word)
    if current_line:
        lines.append(current_line)
    return lines


def _line_words_to_blocks(line_words: list[dict]) -> list[TextBlockIR]:
    """한 줄 안에서 폰트명/크기가 동일하게 이어지는 word 구간을 하나의
    ``TextBlockIR``로 합친다.

    ``extract_words``를 ``extra_attrs=["fontname", "size"]``로 호출했으므로
    pdfplumber가 이미 word 내부에서 fontname/size가 바뀌면 word 자체를
    쪼개 준다 — 즉 각 word는 항상 단일 폰트/크기를 가진다는 것이 보장된다.
    여기서는 그 word들을 다시 인접한 "같은 스타일" 구간으로 묶어 블록
    개수를 줄인다.
    """
    blocks: list[TextBlockIR] = []
    run: list[dict] = []
    run_key: tuple[str | None, float | None] | None = None

    for word in line_words:  # 이미 x0 기준 정렬된 상태로 들어옴
        key = (word.get("fontname"), word.get("size"))
        if run and key != run_key:
            blocks.append(_build_block(run))
            run = []
        run_key = key
        run.append(word)
    if run:
        blocks.append(_build_block(run))
    return blocks


def _build_block(run_words: list[dict]) -> TextBlockIR:
    texts: list[str] = []
    missing = False
    for word in run_words:
        sanitized, word_missing = _sanitize_text(word.get("text", ""))
        texts.append(sanitized)
        missing = missing or word_missing

    fontname = run_words[0].get("fontname")
    size = run_words[0].get("size")

    return TextBlockIR(
        bbox=(
            min(w["x0"] for w in run_words),
            min(w["top"] for w in run_words),
            max(w["x1"] for w in run_words),
            max(w["bottom"] for w in run_words),
        ),
        text=" ".join(texts),
        font_name=fontname,
        font_size=float(size) if size is not None else None,
        bold=_is_bold(fontname),
        italic=_is_italic(fontname),
        to_unicode_missing=missing,
    )


def _sanitize_text(text: str) -> tuple[str, bool]:
    """텍스트 내 ToUnicode 매핑 누락 의심 구간을 대체문자(□)로 치환한다.

    REQ-007 감지 방식(휴리스틱, 완벽하지 않음 — unit-note 명시):
        1. ``(cid:123)`` 형태의 리터럴 문자열 — pdfminer.six가 ToUnicode
           매핑이 없을 때 흘려보내는 대표적인 폴백 표현.
        2. 빈 문자열 글자 또는 유니코드 표준 대체문자(U+FFFD).
        3. 사설 영역(Private Use Area, U+E000-F8FF /
           U+F0000-FFFFD / U+100000-10FFFD) 코드포인트 1글자 — 일부
           서브셋 폰트가 매핑 실패 글리프를 이 영역에 놓는 경우가 있으나,
           반대로 정당한 기호 폰트(Wingdings류)가 PUA를 실제 의미로 쓰는
           경우도 있어 **오탐 가능성이 있는 휴리스틱**이다.
    이 세 가지 신호에 해당하지 않지만 실제로는 매핑이 잘못된 경우(예:
    엉뚱하지만 유효해 보이는 일반 문자로 잘못 디코딩된 경우)는 이 함수가
    감지하지 못한다 — 지어낼 수 없는 한계이므로 그대로 명시한다.
    """
    if not text:
        return text, False

    sanitized, cid_hits = _CID_RUN.subn(_REPLACEMENT_CHAR, text)
    missing = cid_hits > 0

    out_chars: list[str] = []
    for ch in sanitized:
        if _is_missing_char(ch):
            out_chars.append(_REPLACEMENT_CHAR)
            missing = True
        else:
            out_chars.append(ch)
    return "".join(out_chars), missing


def _is_missing_char(ch: str) -> bool:
    if ch == "" or ch == _UNICODE_REPLACEMENT_CHAR:
        return True
    codepoint = ord(ch)
    return (
        0xE000 <= codepoint <= 0xF8FF
        or 0xF0000 <= codepoint <= 0xFFFFD
        or 0x100000 <= codepoint <= 0x10FFFD
    )


def _is_bold(fontname: str | None) -> bool:
    """폰트명 문자열에 담긴 관례적 표기(예: ``Arial-BoldMT``)로 굵기를
    추정한다. pdfplumber가 word 단위에서 제공하는 정보는 폰트명/크기뿐이라
    폰트 디스크립터의 실제 weight 플래그에는 접근하지 않는다 — 폰트명이
    관례를 따르지 않는 경우(예: 커스텀 서브셋 이름) 오탐/누락 가능(unit-note
    명시)."""
    if not fontname:
        return False
    return "bold" in fontname.lower()


def _is_italic(fontname: str | None) -> bool:
    """``_is_bold``와 동일한 한계를 가지는 폰트명 기반 기울임 추정."""
    if not fontname:
        return False
    lowered = fontname.lower()
    return "italic" in lowered or "oblique" in lowered
