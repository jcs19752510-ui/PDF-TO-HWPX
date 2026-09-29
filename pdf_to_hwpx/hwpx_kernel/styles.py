"""StyleRegistry: header.xml 스타일 표의 중복 제거(interning)와 직렬화 (03 §3-3-2, DEC-056).

id 시작값(분석서 §5-4): borderFill·numbering은 1부터, 나머지(font/charPr/paraPr/tabPr/
style)는 0부터. 요청된 스타일만 등록하므로 미사용 정의를 만들지 않는다.
구조 값(속성 기본값, 자식 순서)은 분석서 §5의 관찰 사실이다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from lxml import etree

from pdf_to_hwpx.hwpx_kernel import fonts
from pdf_to_hwpx.hwpx_kernel.constants import (
    HWPX_XML_VERSION,
    LANG_ATTR_NAMES,
    LANGS,
    NO_CHAR_PR_REF,
    new_root,
    pt_to_hwpunit,
    qn,
    serialize_xml,
)
from pdf_to_hwpx.hwpx_kernel.flow import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    DEFAULT_FONT_PT,
    LEFT_QUANTUM,
    LINE_SPACING_PERCENT,
    PREV_MAX_HWPUNIT,
    PREV_QUANTUM,
    quantize,
)

logger = logging.getLogger(__name__)

# 분석서 §5-3 paraPr/align에서 관찰된 horizontal 값 전부.
ALIGN_VALUES = frozenset({ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT, "JUSTIFY"})
# 분석서 §5-3 borderFill에서 관찰된 border type 전부.
BORDER_TYPES = frozenset({"NONE", "SOLID", "DOUBLE_SLIM"})

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_BORDER_WIDTH = re.compile(r"^\d+(\.\d+)? mm$")

# 03 §3-3-2: 등록이 이 값을 넘으면 경고하고 양자화 단위를 2배로 키운다(실측 후 조정).
STYLE_SOFT_LIMIT = 5000

NO_BORDER_ID = 1
DEFAULT_CHAR_PR_ID = 0
DEFAULT_PARA_PR_ID = 0
DEFAULT_STYLE_ID = 0
NUMBERING_ID = 1
TAB_PR_ID = 0
DEFAULT_BORDER_WIDTH = "0.1 mm"  # R1 id=1(테두리 없음)의 관찰값


@dataclass(frozen=True)
class CharSpec:
    height: int = pt_to_hwpunit(DEFAULT_FONT_PT)  # 1/100 pt
    family: str = fonts.DEFAULT_FAMILY
    bold: bool = False
    text_color: str = "#000000"

    def validated(self) -> CharSpec:
        if not isinstance(self.height, int) or self.height <= 0:
            raise ValueError(f"charPr height must be a positive int: {self.height!r}")
        if self.family not in fonts.FAMILY_ORDER:
            raise ValueError(f"unknown font family: {self.family!r}")
        if not _COLOR.match(self.text_color):
            raise ValueError(f"invalid color: {self.text_color!r}")
        return self


@dataclass(frozen=True)
class ParaSpec:
    align: str = ALIGN_LEFT
    left: int = 0
    intent: int = 0
    prev: int = 0
    line_spacing: int = LINE_SPACING_PERCENT


@dataclass(frozen=True)
class BorderSide:
    type: str = "NONE"
    width: str = DEFAULT_BORDER_WIDTH
    color: str = "#000000"

    def validated(self) -> BorderSide:
        if self.type not in BORDER_TYPES:
            raise ValueError(f"unknown border type: {self.type!r}")
        if not _BORDER_WIDTH.match(self.width):
            raise ValueError(f"invalid border width: {self.width!r}")
        if not _COLOR.match(self.color):
            raise ValueError(f"invalid color: {self.color!r}")
        return self


@dataclass(frozen=True)
class BorderSpec:
    left: BorderSide = field(default_factory=BorderSide)
    right: BorderSide = field(default_factory=BorderSide)
    top: BorderSide = field(default_factory=BorderSide)
    bottom: BorderSide = field(default_factory=BorderSide)

    @classmethod
    def all_sides(cls, side: BorderSide) -> BorderSpec:
        return cls(side, side, side, side)


NO_BORDER = BorderSpec()
# 03 §3-3-5: 표 15/17의 관찰 패턴 (사방 SOLID 0.12 mm 검정).
SOLID_THIN = BorderSpec.all_sides(BorderSide("SOLID", "0.12 mm", "#000000"))

DEFAULT_CHAR = CharSpec()
DEFAULT_PARA = ParaSpec()


def _sub(parent: etree._Element, prefix: str, tag: str, **attrs: object) -> etree._Element:
    return etree.SubElement(parent, qn(prefix, tag), {k: str(v) for k, v in attrs.items()})


def _lang_attrs(value: object) -> dict[str, str]:
    return {name: str(value) for name in LANG_ATTR_NAMES}


class StyleRegistry:
    def __init__(self) -> None:
        self._chars: dict[CharSpec, int] = {}
        self._paras: dict[ParaSpec, int] = {}
        self._borders: dict[BorderSpec, int] = {}
        self._quant_scale = 1
        # 예약 항목 (03 §3-3-2 표): charPr 0, paraPr 0, borderFill 1.
        self.char_pr(DEFAULT_CHAR)
        self.para_pr(DEFAULT_PARA)
        self.border_fill(NO_BORDER)

    # ---- 등록 -------------------------------------------------------------
    def char_pr(self, spec: CharSpec) -> int:
        spec = spec.validated()
        found = self._chars.get(spec)
        if found is not None:
            return found
        new_id = len(self._chars)
        self._chars[spec] = new_id
        return new_id

    def para_pr(self, spec: ParaSpec) -> int:
        if spec.align not in ALIGN_VALUES:
            raise ValueError(f"unknown paragraph alignment: {spec.align!r}")
        if spec.line_spacing <= 0:
            raise ValueError(f"line spacing must be positive: {spec.line_spacing!r}")
        scale = self._quant_scale
        norm = ParaSpec(
            align=spec.align,
            left=quantize(max(0, spec.left), LEFT_QUANTUM * scale),
            intent=quantize(spec.intent, LEFT_QUANTUM * scale),
            prev=min(quantize(max(0, spec.prev), PREV_QUANTUM * scale), PREV_MAX_HWPUNIT),
            line_spacing=int(spec.line_spacing),
        )
        found = self._paras.get(norm)
        if found is not None:
            return found
        new_id = len(self._paras)
        self._paras[norm] = new_id
        if new_id + 1 == STYLE_SOFT_LIMIT:
            self._quant_scale *= 2
            logger.warning(
                "paraPr 등록이 %d건에 도달해 양자화 단위를 %d배로 키웁니다.",
                STYLE_SOFT_LIMIT,
                self._quant_scale,
            )
        return new_id

    def border_fill(self, spec: BorderSpec) -> int:
        for side in (spec.left, spec.right, spec.top, spec.bottom):
            side.validated()
        found = self._borders.get(spec)
        if found is not None:
            return found
        new_id = len(self._borders) + 1  # borderFill은 1부터
        self._borders[spec] = new_id
        return new_id

    # ---- 조회(테스트/검증용) ------------------------------------------------
    @property
    def char_pr_count(self) -> int:
        return len(self._chars)

    @property
    def para_pr_count(self) -> int:
        return len(self._paras)

    @property
    def border_fill_count(self) -> int:
        return len(self._borders)

    # ---- 직렬화 -----------------------------------------------------------
    def serialize_header(self, sec_cnt: int) -> bytes:
        if sec_cnt < 1:
            raise ValueError("sec_cnt must be >= 1")
        head = new_root("hh", "head")
        head.set("version", HWPX_XML_VERSION)
        head.set("secCnt", str(sec_cnt))
        _sub(head, "hh", "beginNum", page=1, footnote=1, endnote=1, pic=1, tbl=1, equation=1)

        ref_list = _sub(head, "hh", "refList")
        self._write_fontfaces(ref_list)
        self._write_border_fills(ref_list)
        self._write_char_properties(ref_list)
        self._write_tab_properties(ref_list)
        self._write_numberings(ref_list)
        self._write_para_properties(ref_list)
        self._write_styles(ref_list)

        compat = _sub(head, "hh", "compatibleDocument", targetProgram="HWP201X")
        _sub(compat, "hh", "layoutCompatibility")
        doc_option = _sub(head, "hh", "docOption")
        _sub(doc_option, "hh", "linkinfo", path="", pageInherit=1, footnoteInherit=0)
        _sub(head, "hh", "trackchageConfig", flags=56)  # 철자는 R1 그대로
        return serialize_xml(head)

    @staticmethod
    def _container(parent: etree._Element, tag: str, count: int) -> etree._Element:
        return _sub(parent, "hh", tag, itemCnt=count)

    def _write_fontfaces(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "fontfaces", len(LANGS))
        for lang in LANGS:
            face_el = _sub(cont, "hh", "fontface", lang=lang, fontCnt=len(fonts.FAMILY_ORDER))
            for font_id, family in enumerate(fonts.FAMILY_ORDER):
                font = _sub(
                    face_el, "hh", "font",
                    id=font_id, face=fonts.FACE_NAMES[family], type="TTF", isEmbedded=0,
                )
                _sub(font, "hh", "typeInfo", **fonts.type_info(family, lang))

    def _write_border_fills(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "borderFills", len(self._borders))
        for spec, bf_id in self._borders.items():
            bf = _sub(
                cont, "hh", "borderFill",
                id=bf_id, threeD=0, shadow=0, centerLine="NONE", breakCellSeparateLine=0,
            )
            _sub(bf, "hh", "slash", type="NONE", Crooked=0, isCounter=0)
            _sub(bf, "hh", "backSlash", type="NONE", Crooked=0, isCounter=0)
            for tag, side in (
                ("leftBorder", spec.left),
                ("rightBorder", spec.right),
                ("topBorder", spec.top),
                ("bottomBorder", spec.bottom),
            ):
                _sub(bf, "hh", tag, type=side.type, width=side.width, color=side.color)

    def _write_char_properties(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "charProperties", len(self._chars))
        for spec, cp_id in self._chars.items():
            font_id = fonts.FAMILY_ORDER.index(spec.family)
            cp = _sub(
                cont, "hh", "charPr",
                id=cp_id, height=spec.height, textColor=spec.text_color, shadeColor="none",
                useFontSpace=0, useKerning=0, symMark="NONE", borderFillIDRef=NO_BORDER_ID,
            )
            _sub(cp, "hh", "fontRef", **_lang_attrs(font_id))
            _sub(cp, "hh", "ratio", **_lang_attrs(100))
            _sub(cp, "hh", "spacing", **_lang_attrs(0))
            _sub(cp, "hh", "relSz", **_lang_attrs(100))
            _sub(cp, "hh", "offset", **_lang_attrs(0))
            if spec.bold:
                _sub(cp, "hh", "bold")
            _sub(cp, "hh", "underline", type="NONE", shape="SOLID", color="#000000")
            _sub(cp, "hh", "strikeout", shape="NONE", color="#000000")
            _sub(cp, "hh", "outline", type="NONE")
            _sub(cp, "hh", "shadow", type="NONE", color="#C0C0C0", offsetX=10, offsetY=10)

    def _write_tab_properties(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "tabProperties", 1)
        _sub(cont, "hh", "tabPr", id=TAB_PR_ID, autoTabLeft=0, autoTabRight=0)

    def _write_numberings(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "numberings", 1)
        numbering = _sub(cont, "hh", "numbering", id=NUMBERING_ID, start=0)
        # 분석서 §5-3 / R1 numbering id=1의 관찰값(7수준).
        heads = (
            ("DIGIT", "^1."),
            ("HANGUL_SYLLABLE", "^2."),
            ("DIGIT", "^3)"),
            ("HANGUL_SYLLABLE", "^4)"),
            ("DIGIT", "(^5)"),
            ("HANGUL_SYLLABLE", "(^6)"),
            ("CIRCLED_DIGIT", "^7"),
        )
        for level, (num_format, text) in enumerate(heads, start=1):
            head = _sub(
                numbering, "hh", "paraHead",
                start=1, level=level, align="LEFT", useInstWidth=0, autoIndent=1,
                widthAdjust=0, textOffsetType="PERCENT", textOffset=50, numFormat=num_format,
                charPrIDRef=NO_CHAR_PR_REF, checkable=1 if level == 7 else 0,
            )
            head.text = text

    def _write_para_properties(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "paraProperties", len(self._paras))
        for spec, pp_id in self._paras.items():
            pp = _sub(
                cont, "hh", "paraPr",
                id=pp_id, tabPrIDRef=TAB_PR_ID, condense=0, fontLineHeight=0, snapToGrid=1,
                suppressLineNumbers=0, checked=0,
            )
            _sub(pp, "hh", "align", horizontal=spec.align, vertical="BASELINE")
            _sub(pp, "hh", "heading", type="NONE", idRef=0, level=0)
            _sub(
                pp, "hh", "breakSetting",
                breakLatinWord="KEEP_WORD", breakNonLatinWord="KEEP_WORD", widowOrphan=0,
                keepWithNext=0, keepLines=0, pageBreakBefore=0, lineWrap="BREAK",
            )
            _sub(pp, "hh", "autoSpacing", eAsianEng=0, eAsianNum=0)
            switch = _sub(pp, "hp", "switch")
            case = etree.SubElement(
                switch,
                qn("hp", "case"),
                {qn("hp", "required-namespace"): "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"},
            )
            default = _sub(switch, "hp", "default")
            # 분석서 §5-6: default 분기의 길이 값은 case의 정확히 2배, PERCENT 값은 그대로.
            for branch, factor in ((case, 1), (default, 2)):
                margin = _sub(branch, "hh", "margin")
                for tag, value in (
                    ("intent", spec.intent),
                    ("left", spec.left),
                    ("right", 0),
                    ("prev", spec.prev),
                    ("next", 0),
                ):
                    _sub(margin, "hc", tag, value=value * factor, unit="HWPUNIT")
                _sub(branch, "hh", "lineSpacing", type="PERCENT", value=spec.line_spacing, unit="HWPUNIT")
            _sub(
                pp, "hh", "border",
                borderFillIDRef=NO_BORDER_ID, offsetLeft=0, offsetRight=0, offsetTop=0,
                offsetBottom=0, connect=0, ignoreMargin=0,
            )

    def _write_styles(self, ref_list: etree._Element) -> None:
        cont = self._container(ref_list, "styles", 1)
        _sub(
            cont, "hh", "style",
            id=DEFAULT_STYLE_ID, type="PARA", name="바탕글", engName="Normal",
            paraPrIDRef=DEFAULT_PARA_PR_ID, charPrIDRef=DEFAULT_CHAR_PR_ID,
            nextStyleIDRef=DEFAULT_STYLE_ID, langID=1042, lockForm=0,
        )
