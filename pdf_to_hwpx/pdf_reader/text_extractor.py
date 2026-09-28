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

# 같은 줄로 간주할 word 간 세로 범위([top, bottom]) 겹침 비율 임계값.
# (재작업 2026-09-28, DEF-001) 이전에는 "top" 값 하나만 놓고 고정 허용치
# (2.5pt)로 비교했으나, pdfplumber의 "top"은 글자 상단(어센트 포함) 기준이라
# 같은 베이스라인 위 단어라도 폰트 "크기"가 크게 다르면 top 차이가 커져
# 오판정이 발생했다(예: size10/size24가 섞인 줄에서 top 차이 11.1pt >
# 2.5pt). 대신 word의 세로 구간이 서로 얼마나 겹치는지(overlap 길이 /
# 두 word 중 더 작은 높이)를 기준으로 판정한다 — 같은 베이스라인 위
# 단어들은 폰트 크기가 달라도 서로의 세로 구간을 상당 부분 포함/겹치는
# 경향이 있다(어센트가 디센트보다 커서 "bottom" 쪽 변동폭이 "top" 쪽보다
# 작기 때문). 근거가 있는 표준값은 아니며, 03단계 설계서에도 구체적
# 수치가 없어 합리적으로 정한 휴리스틱 값이다(unit-note 명시).
_LINE_OVERLAP_RATIO = 0.5

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
    읽기 순서로 정렬된 평평한 목록만 준다), word의 세로 구간([top, bottom])이
    서로 충분히 겹치는지를 기준으로 같은 줄을 판정하는 휴리스틱을 직접
    구현했다(재작업 2026-09-28, DEF-001 — ``_LINE_OVERLAP_RATIO`` 참고).

    "같은 줄인지 판정"(이 함수, 세로 겹침 비율 기준)과 "줄 내부 읽기 순서
    정렬"(``x0`` 오름차순)의 책임을 분리했다 — 이전 구현은 판정 이전에
    이미 ``top``을 1차 정렬 키로 써서 정렬 자체가 틀어지는 문제가 있었다.

    회전되었거나 심하게 기울어진 텍스트, 다단(multi-column) 레이아웃에서
    같은 세로 구간에 있는 다른 컬럼 word를 한 줄로 잘못 묶을 가능성은
    이 휴리스틱의 한계로 남는다(unit-note 명시, 이번 재작업 범위 아님).
    """
    if not words:
        return []

    # 처리 순서만 top 오름차순으로 정한다(줄 클러스터를 만드는 데 필요한
    # 스윕 순서일 뿐, 최종 읽기 순서와는 무관 -- 최종 순서는 아래에서
    # x0/최소 top 기준으로 별도로 정렬한다).
    ordered = sorted(words, key=lambda w: w["top"])

    clusters: list[dict] = []  # {"members": list[dict], "max_bottom": float}
    for word in ordered:
        w_top = word["top"]
        w_bottom = word["bottom"]
        w_height = max(w_bottom - w_top, 0.01)

        matched_cluster = None
        for cluster in clusters:
            if w_top >= cluster["max_bottom"]:
                continue  # 세로로 전혀 겹칠 수 없음(스윕 순서상 이후로도 불가)
            if _has_vertical_overlap(word, w_height, cluster["members"]):
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append({"members": [word], "max_bottom": w_bottom})
        else:
            matched_cluster["members"].append(word)
            matched_cluster["max_bottom"] = max(matched_cluster["max_bottom"], w_bottom)

    lines = [cluster["members"] for cluster in clusters]
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    lines.sort(key=lambda line: min(w["top"] for w in line))
    return lines


def _has_vertical_overlap(word: dict, word_height: float, members: list[dict]) -> bool:
    """``word``가 ``members`` 중 하나와 세로 구간이 충분히 겹치는지 확인한다."""
    for member in members:
        m_top = member["top"]
        m_bottom = member["bottom"]
        m_height = max(m_bottom - m_top, 0.01)
        overlap = min(word["bottom"], m_bottom) - max(word["top"], m_top)
        if overlap <= 0:
            continue
        if overlap / min(word_height, m_height) >= _LINE_OVERLAP_RATIO:
            return True
    return False


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
