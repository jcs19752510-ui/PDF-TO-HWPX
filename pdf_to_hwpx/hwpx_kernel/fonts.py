"""PDF 글꼴명 -> 한글 기본 글꼴 3종 대체 (03 §2-4-4, DEC-059).

R1에서 TTF로 관찰된 기본 글꼴(돋움/바탕/돋움체)만 사용한다. 원본 글꼴명은 출력에
남기지 않는다. 신규 문서의 기본 글꼴이 01_빈문서로 확인되면 이 표 1곳만 고친다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SANS = "sans"
SERIF = "serif"
MONO = "mono"

# 글꼴 id(모든 lang 공통) = 표 순서. charPr 기본(id 0)이 sans가 되도록 돋움이 0번이다.
FAMILY_ORDER: tuple[str, ...] = (SANS, SERIF, MONO)
FACE_NAMES: dict[str, str] = {SANS: "돋움", SERIF: "바탕", MONO: "돋움체"}
DEFAULT_FAMILY = SANS

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
_MONO = re.compile(r"mono|courier|consol|gulimche|돋움체|굴림체")
_SANS = re.compile(r"sans|gothic|고딕|돋움|dotum|arial|helvet|gulim|굴림|malgun|맑은")
_SERIF = re.compile(
    r"serif|times|roman|batang|바탕|myeong|명조|song|mincho|garamond|georgia|palatino|cambria"
)

# 분석서 §5-3 / R1 관찰: lang별 typeInfo. (OTHER만 다른 값 패턴, 돋움체만 proportion=9.)
_TYPE_INFO_TEXT = {
    "familyType": "FCAT_GOTHIC",
    "weight": "6",
    "proportion": "0",
    "contrast": "0",
    "strokeVariation": "1",
    "armStyle": "1",
    "letterform": "1",
    "midline": "1",
    "xHeight": "1",
}
_TYPE_INFO_OTHER = {
    "familyType": "FCAT_GOTHIC",
    "weight": "6",
    "proportion": "4",
    "contrast": "2",
    "strokeVariation": "2",
    "armStyle": "2",
    "letterform": "2",
    "midline": "2",
    "xHeight": "4",
}


@dataclass(frozen=True)
class FontChoice:
    family: str  # sans | serif | mono
    face: str  # header에 등록되는 글꼴 이름
    font_id: int  # 모든 lang에서 공통인 font id


def classify_family(pdf_name: str | None) -> str:
    if not pdf_name:
        return DEFAULT_FAMILY
    name = _SUBSET_PREFIX.sub("", pdf_name).lower()
    # sans를 serif보다 먼저 검사해 "sans-serif"를 오분류하지 않는다.
    if _MONO.search(name):
        return MONO
    if _SANS.search(name):
        return SANS
    if _SERIF.search(name):
        return SERIF
    return DEFAULT_FAMILY


def choice_for_family(family: str) -> FontChoice:
    if family not in FACE_NAMES:
        raise ValueError(f"알 수 없는 글꼴 계열: {family!r}")
    return FontChoice(family, FACE_NAMES[family], FAMILY_ORDER.index(family))


def resolve_font(pdf_name: str | None) -> FontChoice:
    return choice_for_family(classify_family(pdf_name))


def type_info(family: str, lang: str) -> dict[str, str]:
    """``hh:typeInfo`` 속성 (사본)."""
    base = _TYPE_INFO_OTHER if lang == "OTHER" else _TYPE_INFO_TEXT
    info = dict(base)
    if family == MONO and lang != "OTHER":
        info["proportion"] = "9"
    return info
