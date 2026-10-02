"""constants.py / fonts.py 단위 테스트 (T1)."""

from __future__ import annotations

import re

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel import constants, fonts


def test_fifteen_namespaces_with_observed_uris():
    assert list(constants.NAMESPACES) == [
        "ha", "hp", "hp10", "hs", "hc", "hh", "hhs", "hm", "hpf", "dc", "opf",
        "ooxmlchart", "hwpunitchar", "epub", "config",
    ]
    assert constants.NAMESPACES["hp"] == "http://www.hancom.co.kr/hwpml/2011/paragraph"
    assert constants.NAMESPACES["opf"] == "http://www.idpf.org/2007/opf/"


def test_qn_and_unit_conversion():
    assert constants.qn("hp", "p") == "{http://www.hancom.co.kr/hwpml/2011/paragraph}p"
    assert constants.pt_to_hwpunit(10) == 1000
    assert constants.pt_to_hwpunit(0.125) == 12
    # 분석서 §9: A4 = 59528 x 84188 (210mm x 297mm)
    assert constants.pt_to_hwpunit(210 / 25.4 * 72) == 59528


def test_full_nsmap_is_a_copy():
    m = constants.full_nsmap()
    m["x"] = "y"
    assert "x" not in constants.NAMESPACES


def test_serialize_xml_prolog_bytes_and_no_newline():
    root = constants.new_root("hs", "sec")
    data = constants.serialize_xml(root)
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hs:sec ')
    assert b"\n" not in data
    assert not data.startswith(b"\xef\xbb\xbf")
    assert len(re.findall(rb"xmlns:\w+=", data)) == 15
    etree.fromstring(data)  # well-formed


@pytest.mark.parametrize(
    "name, family",
    [
        (None, fonts.SANS),
        ("", fonts.SANS),
        ("ABCDEF+Arial-BoldMT", fonts.SANS),
        ("ABCDEF+TimesNewRomanPSMT", fonts.SERIF),
        ("Times-Roman", fonts.SERIF),
        ("BatangChe", fonts.SERIF),
        ("바탕", fonts.SERIF),
        ("NotoSans-Regular", fonts.SANS),
        ("NotoSansSerif", fonts.SANS),  # sans를 serif보다 먼저 검사
        ("NotoSerif-Regular", fonts.SERIF),
        ("CourierNewPSMT", fonts.MONO),
        ("Consolas", fonts.MONO),
        ("GulimChe", fonts.MONO),  # gulim(sans)보다 mono 우선
        ("돋움체", fonts.MONO),
        ("Malgun Gothic", fonts.SANS),
        ("TotallyUnknownFont", fonts.SANS),
    ],
)
def test_classify_family(name, family):
    assert fonts.classify_family(name) == family


def test_subset_prefix_only_stripped_when_six_capitals():
    # 접두어 제거 후 "ourier"가 아니라 원래 이름으로 판정되어야 하는 경계 케이스
    assert fonts.classify_family("ABCDE+Courier") == fonts.MONO
    assert fonts.classify_family("ABCDEF+Courier") == fonts.MONO


def test_resolve_font_ids_faces_and_no_original_name():
    sans = fonts.resolve_font("ABCDEF+Arial")
    serif = fonts.resolve_font("Times")
    mono = fonts.resolve_font("Courier")
    assert (sans.font_id, serif.font_id, mono.font_id) == (0, 1, 2)
    assert (sans.face, serif.face, mono.face) == ("돋움", "바탕", "돋움체")
    assert "Arial" not in repr(sans)


def test_choice_for_family_rejects_unknown():
    with pytest.raises(ValueError):
        fonts.choice_for_family("cursive")


def test_type_info_observed_patterns():
    text = fonts.type_info(fonts.SANS, "HANGUL")
    assert text["proportion"] == "0" and text["familyType"] == "FCAT_GOTHIC"
    assert fonts.type_info(fonts.MONO, "LATIN")["proportion"] == "9"
    other = fonts.type_info(fonts.MONO, "OTHER")
    assert other["xHeight"] == "4" and other["proportion"] == "4"
    # 사본 반환: 호출자 변형이 전역을 오염시키지 않는다
    text["weight"] = "x"
    assert fonts.type_info(fonts.SANS, "HANGUL")["weight"] == "6"
