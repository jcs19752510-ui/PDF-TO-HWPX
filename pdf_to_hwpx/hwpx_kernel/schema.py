"""OWPML 본문 요소 팩토리 (unit-4R, 03 §3-3-3 / §3-3-5, SCHEMA_VERSION 2.0).

분석서가 관찰한 요소·속성·자식 순서만 만든다. 자체 속성(``bboxPt``, ``fontName`` 등)은
만들지 않는다. 이 모듈은 IR과 PDF를 모른다 -- 호출자(hwpx_writer)가 IR에서 값을
정해 넘긴다. 그림(``hp:pic``)은 04_그림.hwpx 관찰 전이라 만들지 않는다(unit-4P).

v1.0 계약(``text_block_to_paragraph_fragment`` 등 IR 직접 변환 함수)은 폐기됐다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from lxml import etree

from pdf_to_hwpx.common.exceptions import HwpxSchemaError
from pdf_to_hwpx.hwpx_kernel.constants import PARAGRAPH_ID, qn
from pdf_to_hwpx.hwpx_kernel.flow import BASELINE_RATIO, LINESEG_FLAGS_FIRST

SCHEMA_VERSION = "2.0"

# 표 속성 상수: 03 §3-3-5 (R1 다수값).
TABLE_OUT_MARGIN = 141
TABLE_IN_MARGIN = 140
CELL_MARGIN = 141
TABLE_PAGE_BREAKS = frozenset({"NONE", "CELL"})  # 분석서 §7에서 관찰된 값
CELL_VERT_ALIGNS = frozenset({"CENTER", "TOP", "BOTTOM"})  # 분석서 §7

# XML 1.0에서 허용되지 않는 문자 (lxml이 ValueError를 내는 범위 포함).
_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_TO_SPACE = re.compile("[\t\r\n]")


def sanitize_text(text: str) -> str:
    """금지 문자를 제거하고 탭/줄바꿈은 공백 1개로 치환한다 (03 §3-3-3).

    탭/줄바꿈 요소의 형태가 R1 문단 텍스트에서는 관찰되지 않았기 때문이다.
    """
    return _ILLEGAL_XML.sub("", _TO_SPACE.sub(" ", text))


def _el(prefix: str, tag: str, **attrs: object) -> etree._Element:
    return etree.Element(qn(prefix, tag), {k: str(v) for k, v in attrs.items()})


def _sub(parent: etree._Element, prefix: str, tag: str, **attrs: object) -> etree._Element:
    return etree.SubElement(parent, qn(prefix, tag), {k: str(v) for k, v in attrs.items()})


def make_lineseg(
    *,
    vertpos: int,
    vertsize: int,
    horzpos: int,
    horzsize: int,
    textpos: int = 0,
    textheight: int | None = None,
    baseline: int | None = None,
    spacing: int = 0,
    flags: int = LINESEG_FLAGS_FIRST,
) -> etree._Element:
    """분석서 §6-4: vertsize == textheight, baseline = round(0.85 x vertsize)."""
    return _el(
        "hp", "lineseg",
        textpos=textpos,
        vertpos=vertpos,
        vertsize=vertsize,
        textheight=vertsize if textheight is None else textheight,
        baseline=round(BASELINE_RATIO * vertsize) if baseline is None else baseline,
        spacing=spacing,
        horzpos=horzpos,
        horzsize=horzsize,
        flags=flags,
    )


def make_linesegarray(segs: Iterable[etree._Element]) -> etree._Element:
    arr = _el("hp", "linesegarray")
    for seg in segs:
        arr.append(seg)
    return arr


def make_run(
    char_pr_id: int,
    text: str | None = None,
    *,
    children: Sequence[etree._Element] = (),
) -> etree._Element:
    """``hp:run``. 자식 순서는 ``children`` 다음 ``hp:t``.

    분석서 §6-3: 빈 run 허용(415건), 표/ctrl을 담는 run은 끝에 ``hp:t``(비어 있을 수 있음)가 붙는다.
    ``text``가 None이고 ``children``도 없으면 자식 없는 빈 run이다.
    """
    run = _el("hp", "run", charPrIDRef=char_pr_id)
    for child in children:
        run.append(child)
    if text is not None or children:
        t = _sub(run, "hp", "t")
        if text:
            t.text = sanitize_text(text)
    return run


def make_paragraph(
    *,
    para_pr_id: int,
    runs: Sequence[etree._Element],
    linesegs: Sequence[etree._Element] | None = None,
    style_id: int = 0,
    page_break: bool = False,
    column_break: bool = False,
) -> etree._Element:
    """``hp:p``. ``linesegs``가 None/빈 시퀀스면 ``hp:linesegarray``를 생략한다(실험 E-L용)."""
    if not runs:
        raise HwpxSchemaError("hp:p는 run을 1개 이상 가져야 합니다.")
    p = _el(
        "hp", "p",
        id=PARAGRAPH_ID,
        paraPrIDRef=para_pr_id,
        styleIDRef=style_id,
        pageBreak=int(page_break),
        columnBreak=int(column_break),
        merged=0,
    )
    for run in runs:
        p.append(run)
    if linesegs:
        p.append(make_linesegarray(linesegs))
    return p


def make_table_cell(
    *,
    col: int,
    row: int,
    col_span: int,
    row_span: int,
    width: int,
    height: int,
    border_fill_id: int,
    paragraphs: Sequence[etree._Element],
    vert_align: str = "CENTER",
) -> etree._Element:
    """``hp:tc`` (분석서 §7). 병합으로 덮이는 셀은 호출자가 만들지 않는다."""
    if not paragraphs:
        raise HwpxSchemaError("hp:tc는 문단을 1개 이상 가져야 합니다.")
    if vert_align not in CELL_VERT_ALIGNS:
        raise HwpxSchemaError(f"알 수 없는 셀 세로 정렬: {vert_align!r}")
    if min(col, row) < 0 or min(col_span, row_span) < 1 or min(width, height) <= 0:
        raise HwpxSchemaError("셀 주소/병합/크기 값이 유효하지 않습니다.")
    tc = _el(
        "hp", "tc",
        name="", header=0, hasMargin=0, protect=0, editable=0, dirty=0,
        borderFillIDRef=border_fill_id,
    )
    sub = _sub(
        tc, "hp", "subList",
        id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign=vert_align,
        linkListIDRef=0, linkListNextIDRef=0, textWidth=0, textHeight=0, hasTextRef=0, hasNumRef=0,
    )
    for para in paragraphs:
        sub.append(para)
    _sub(tc, "hp", "cellAddr", colAddr=col, rowAddr=row)
    _sub(tc, "hp", "cellSpan", colSpan=col_span, rowSpan=row_span)
    _sub(tc, "hp", "cellSz", width=width, height=height)
    _sub(tc, "hp", "cellMargin", left=CELL_MARGIN, right=CELL_MARGIN, top=CELL_MARGIN, bottom=CELL_MARGIN)
    return tc


def _cell_geometry(tc: etree._Element) -> tuple[int, int, int, int]:
    addr = tc.find(qn("hp", "cellAddr"))
    span = tc.find(qn("hp", "cellSpan"))
    if addr is None or span is None:
        raise HwpxSchemaError("hp:tc에 cellAddr/cellSpan이 없습니다.")
    return (
        int(addr.get("colAddr")),
        int(addr.get("rowAddr")),
        int(span.get("colSpan")),
        int(span.get("rowSpan")),
    )


def _check_grid(rows: Sequence[Sequence[etree._Element]], row_cnt: int, col_cnt: int) -> None:
    """분석서 §7 병합 규칙(17/17): tr 수=rowCnt, rowAddr=tr 인덱스, 셀이 그리드를 겹침 없이 덮음."""
    if len(rows) != row_cnt:
        raise HwpxSchemaError(f"tr 수({len(rows)})가 rowCnt({row_cnt})와 다릅니다.")
    covered: set[tuple[int, int]] = set()
    for tr_index, cells in enumerate(rows):
        last_col = -1
        for tc in cells:
            col, row, col_span, row_span = _cell_geometry(tc)
            if row != tr_index:
                raise HwpxSchemaError(f"rowAddr({row})가 tr 인덱스({tr_index})와 다릅니다.")
            if col <= last_col:
                raise HwpxSchemaError("한 tr 안의 tc는 colAddr 오름차순이어야 합니다.")
            last_col = col
            if col + col_span > col_cnt or row + row_span > row_cnt:
                raise HwpxSchemaError("셀이 표 그리드를 벗어납니다.")
            for r in range(row, row + row_span):
                for c in range(col, col + col_span):
                    if (r, c) in covered:
                        raise HwpxSchemaError(f"셀이 겹칩니다: ({r},{c})")
                    covered.add((r, c))
    if len(covered) != row_cnt * col_cnt:
        raise HwpxSchemaError("셀이 그리드를 모두 덮지 못합니다.")


def make_table(
    *,
    tbl_id: int,
    z_order: int,
    rows: Sequence[Sequence[etree._Element]],
    row_cnt: int,
    col_cnt: int,
    width: int,
    height: int,
    border_fill_id: int,
    page_break: str = "CELL",
) -> etree._Element:
    """``hp:tbl`` (분석서 §7, 03 §3-3-5). ``rows``는 tr별 ``hp:tc`` 목록이다."""
    if page_break not in TABLE_PAGE_BREAKS:
        raise HwpxSchemaError(f"알 수 없는 표 pageBreak: {page_break!r}")
    if min(row_cnt, col_cnt) < 1 or min(width, height) <= 0:
        raise HwpxSchemaError("표 크기 값이 유효하지 않습니다.")
    _check_grid(rows, row_cnt, col_cnt)
    tbl = _el(
        "hp", "tbl",
        id=tbl_id, zOrder=z_order, numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
        textFlow="BOTH_SIDES", lock=0, dropcapstyle="None", pageBreak=page_break,
        repeatHeader=1, rowCnt=row_cnt, colCnt=col_cnt, cellSpacing=0,
        borderFillIDRef=border_fill_id, noAdjust=0,
    )
    _sub(tbl, "hp", "sz", width=width, widthRelTo="ABSOLUTE", height=height, heightRelTo="ABSOLUTE", protect=0)
    _sub(
        tbl, "hp", "pos",
        treatAsChar=1, affectLSpacing=0, flowWithText=1, allowOverlap=0, holdAnchorAndSO=0,
        vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT",
        vertOffset=0, horzOffset=0,
    )
    m = TABLE_OUT_MARGIN
    _sub(tbl, "hp", "outMargin", left=m, right=m, top=m, bottom=m)
    m = TABLE_IN_MARGIN
    _sub(tbl, "hp", "inMargin", left=m, right=m, top=m, bottom=m)
    for cells in rows:
        tr = _sub(tbl, "hp", "tr")
        for tc in cells:
            tr.append(tc)
    return tbl
