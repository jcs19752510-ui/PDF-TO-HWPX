"""구역(section) 조립: PageSetup, hp:secPr, hs:sec 직렬화 (03 §3-3-3, 분석서 §6-2).

secPr는 구역의 첫 문단 첫 run 안에 들어간다(구역마다 정확히 1개). 바탕쪽은 만들지
않는다(분석서 구역 2 형태: ``masterPageCnt=0``, ``hp:masterPage`` 자식 없음).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lxml import etree

from pdf_to_hwpx.common.exceptions import HwpxSchemaError
from pdf_to_hwpx.hwpx_kernel.constants import new_root, pt_to_hwpunit, qn, serialize_xml
from pdf_to_hwpx.hwpx_kernel.flow import DEFAULT_FONT_PT, EMIT_LINESEGS
from pdf_to_hwpx.hwpx_kernel.schema import make_lineseg, make_paragraph, make_run
from pdf_to_hwpx.hwpx_kernel.styles import (
    DEFAULT_CHAR_PR_ID,
    DEFAULT_PARA_PR_ID,
    NO_BORDER_ID,
    NUMBERING_ID,
)

# 03 §3-3-3 여백 클램프 (10~50 mm / 15~50 mm).
MARGIN_SIDE_MIN, MARGIN_SIDE_MAX = 2835, 14173
MARGIN_VERT_MIN, MARGIN_VERT_MAX = 4251, 14173
HEADER_FOOTER_DEFAULT = 4251


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class PageSetup:
    """HWPUNIT 단위 쪽 설정. ``landscape``는 R1에서 세로 A4에 ``WIDELY``만 관찰됐다.

    가로 용지(폭>높이)의 값은 【미확인】(분석서 §6-2)이라 폭/높이 숫자만 그대로 쓰고
    ``WIDELY``를 유지한다.
    """

    width: int
    height: int
    margin_left: int
    margin_right: int
    margin_top: int
    margin_bottom: int
    margin_header: int = HEADER_FOOTER_DEFAULT
    margin_footer: int = HEADER_FOOTER_DEFAULT
    margin_gutter: int = 0
    landscape: str = "WIDELY"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise HwpxSchemaError("용지 크기는 양수여야 합니다.")
        if self.text_width <= 0 or self.text_height <= 0:
            raise HwpxSchemaError("여백이 용지보다 큽니다.")

    @property
    def text_width(self) -> int:
        return self.width - self.margin_left - self.margin_right - self.margin_gutter

    @property
    def text_height(self) -> int:
        return self.height - self.margin_top - self.margin_bottom

    @classmethod
    def a4(cls) -> PageSetup:
        """분석서 §6-2 관찰 값 (A4 세로, 좌우 30 mm, 위 20 mm, 아래 15 mm)."""
        return cls(59528, 84188, 8503, 8503, 5669, 4251)

    @classmethod
    def from_content_bounds(
        cls,
        width_pt: float,
        height_pt: float,
        min_x0_pt: float,
        max_x1_pt: float,
        min_y0_pt: float,
        max_y1_pt: float,
    ) -> PageSetup:
        """구역 내 블록 bbox의 경계에서 여백을 유도한다 (03 §3-3-3)."""
        width, height = pt_to_hwpunit(width_pt), pt_to_hwpunit(height_pt)
        left = _clamp(pt_to_hwpunit(min_x0_pt), MARGIN_SIDE_MIN, MARGIN_SIDE_MAX)
        right = _clamp(width - pt_to_hwpunit(max_x1_pt), MARGIN_SIDE_MIN, MARGIN_SIDE_MAX)
        top = _clamp(pt_to_hwpunit(min_y0_pt), MARGIN_VERT_MIN, MARGIN_VERT_MAX)
        bottom = _clamp(height - pt_to_hwpunit(max_y1_pt), MARGIN_VERT_MIN, MARGIN_VERT_MAX)
        return cls(
            width, height, left, right, top, bottom,
            margin_header=min(HEADER_FOOTER_DEFAULT, top),
            margin_footer=min(HEADER_FOOTER_DEFAULT, bottom),
        )


def _sub(parent: etree._Element, tag: str, **attrs: object) -> etree._Element:
    return etree.SubElement(parent, qn("hp", tag), {k: str(v) for k, v in attrs.items()})


def _note_pr(parent: etree._Element, tag: str, place: str) -> None:
    note = _sub(parent, tag)
    _sub(note, "autoNumFormat", type="DIGIT", userChar="", prefixChar="", suffixChar=")", supscript=0)
    _sub(note, "noteLine", length=-1, type="SOLID", width="0.1 mm", color="#000000")
    _sub(note, "noteSpacing", betweenNotes=850, belowLine=567, aboveLine=567)
    _sub(note, "numbering", type="CONTINUOUS", newNum=1)
    _sub(note, "placement", place=place, beneathText=0)


def build_sec_pr(page: PageSetup) -> etree._Element:
    sec = etree.Element(
        qn("hp", "secPr"),
        {
            "id": "", "textDirection": "HORIZONTAL", "spaceColumns": "1134", "tabStop": "8000",
            "tabStopVal": "4000", "tabStopUnit": "HWPUNIT", "outlineShapeIDRef": str(NUMBERING_ID),
            "memoShapeIDRef": "0", "textVerticalWidthHead": "0", "masterPageCnt": "0",
        },
    )
    _sub(sec, "grid", lineGrid=0, charGrid=0, wonggojiFormat=0)
    _sub(sec, "startNum", pageStartsOn="BOTH", page=0, pic=0, tbl=0, equation=0)
    _sub(
        sec, "visibility",
        hideFirstHeader=0, hideFirstFooter=0, hideFirstMasterPage=0, border="SHOW_ALL",
        fill="SHOW_ALL", hideFirstPageNum=0, hideFirstEmptyLine=0, showLineNumber=0,
    )
    _sub(sec, "lineNumberShape", restartType=0, countBy=0, distance=0, startNumber=0)
    page_pr = _sub(sec, "pagePr", landscape=page.landscape, width=page.width, height=page.height, gutterType="LEFT_ONLY")
    _sub(
        page_pr, "margin",
        header=page.margin_header, footer=page.margin_footer, gutter=page.margin_gutter,
        left=page.margin_left, right=page.margin_right, top=page.margin_top, bottom=page.margin_bottom,
    )
    _note_pr(sec, "footNotePr", "EACH_COLUMN")
    _note_pr(sec, "endNotePr", "END_OF_DOCUMENT")
    for fill_type in ("BOTH", "EVEN", "ODD"):
        fill = _sub(
            sec, "pageBorderFill",
            type=fill_type, borderFillIDRef=NO_BORDER_ID, textBorder="PAPER",
            headerInside=0, footerInside=0, fillArea="PAPER",
        )
        _sub(fill, "offset", left=1417, right=1417, top=1417, bottom=1417)
    return sec


def build_col_pr_ctrl() -> etree._Element:
    ctrl = etree.Element(qn("hp", "ctrl"))
    _sub(ctrl, "colPr", id="", type="NEWSPAPER", layout="LEFT", colCount=1, sameSz=1, sameGap=0)
    return ctrl


def inject_section_properties(paragraph: etree._Element, page: PageSetup) -> None:
    """구역 첫 문단의 첫 run 맨 앞에 ``secPr``, ``ctrl(colPr)``를 넣는다 (분석서 구역 1 순서).

    run 안에 이미 ``secPr``가 있으면 오류. run에 ``hp:t``가 없으면 R1 관찰대로 빈 ``hp:t``를 붙인다.
    """
    run = paragraph.find(qn("hp", "run"))
    if run is None:
        raise HwpxSchemaError("첫 문단에 hp:run이 없습니다.")
    if run.find(qn("hp", "secPr")) is not None:
        raise HwpxSchemaError("이 구역은 이미 secPr를 가지고 있습니다.")
    run.insert(0, build_col_pr_ctrl())
    run.insert(0, build_sec_pr(page))
    if run.find(qn("hp", "t")) is None:
        etree.SubElement(run, qn("hp", "t"))


def build_section_xml(paragraphs: Sequence[etree._Element], page: PageSetup) -> bytes:
    """``hs:sec`` 파트 바이트. ``paragraphs[0]``이 변경된다(secPr 주입).

    문단이 없으면 빈 문단 1개를 만든다(구역마다 secPr를 담을 첫 문단이 필요).
    """
    root = new_root("hs", "sec")
    items = list(paragraphs)
    if not items:
        seg = make_lineseg(
            vertpos=0, vertsize=pt_to_hwpunit(DEFAULT_FONT_PT), horzpos=0, horzsize=page.text_width
        )
        items = [
            make_paragraph(
                para_pr_id=DEFAULT_PARA_PR_ID,
                runs=[make_run(DEFAULT_CHAR_PR_ID)],
                linesegs=[seg] if EMIT_LINESEGS else None,
            )
        ]
    inject_section_properties(items[0], page)
    for p in items:
        root.append(p)
    return serialize_xml(root)
