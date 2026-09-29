"""unit-5 Acceptance Criteria — `pdf_to_hwpx/hwpx_writer/paragraph_builder.py`
(`build_paragraph_fragments`) 검증.

근거: docs/harness/units/unit-5-note.md §5 AC-1~AC-6(16개 항목),
02-planning.md REQ-002/REQ-006/REQ-008, hwpx_kernel/schema.py(unit-4) 계약.

**범위의 근본적 한계(unit-4-test.md와 동일 사유로 승계)**: 여기서
"well-formed XML이고 코드가 스스로 선언한 규칙(같은 줄 병합/공백 삽입/
bboxPt 계산)을 지키는가"만 증명한다. 실제 한글(한컴오피스) 호환성은
검증 대상이 아니다(DEC-017).
"""

from __future__ import annotations

import copy
import unicodedata

import pytest
from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.hwpx_writer.paragraph_builder import build_paragraph_fragments
from pdf_to_hwpx.pdf_reader.ir import TextBlockIR


def qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


P_TAG = qname("hp", "p")
RUN_TAG = qname("hp", "run")
T_TAG = qname("hp", "t")


def make_block(
    bbox: tuple[float, float, float, float],
    text: str = "text",
    *,
    font_name: str | None = "Malgun Gothic",
    font_size: float | None = 10.0,
    bold: bool = False,
    italic: bool = False,
    to_unicode_missing: bool = False,
) -> TextBlockIR:
    return TextBlockIR(
        bbox=bbox,
        text=text,
        font_name=font_name,
        font_size=font_size,
        bold=bold,
        italic=italic,
        to_unicode_missing=to_unicode_missing,
    )


def assert_round_trips_as_well_formed(element: etree._Element) -> bytes:
    data = etree.tostring(element)
    reparsed = etree.fromstring(data)
    assert reparsed.tag == element.tag
    return data


def runs_of(paragraph: etree._Element) -> list[etree._Element]:
    return list(paragraph.findall(RUN_TAG))


def run_text(run: etree._Element) -> str:
    t = run.find(T_TAG)
    assert t is not None
    return t.text or ""


# ---------------------------------------------------------------------------
# AC-1: 기본 변환
# ---------------------------------------------------------------------------


def test_ac1_1_non_empty_blocks_return_p_elements_with_correct_qname():
    blocks = [make_block((10, 100, 50, 112), text="Hello")]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    assert fragments[0].tag == P_TAG
    assert etree.QName(fragments[0]).localname == "p"
    assert etree.QName(fragments[0]).namespace == NAMESPACES["hp"]
    assert NAMESPACES["hp"] == "http://www.hancom.co.kr/hwpml/2011/paragraph"


def test_ac1_2_empty_list_returns_empty_list_without_exception():
    result = build_paragraph_fragments([])
    assert result == []


def test_ac1_3_output_order_matches_input_reading_order():
    # 세 줄(세로로 겹치지 않는 블록) -> 순서 보존 확인
    blocks = [
        make_block((10, 300, 50, 312), text="첫줄"),
        make_block((10, 200, 50, 212), text="둘째줄"),
        make_block((10, 100, 50, 112), text="셋째줄"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 3
    texts = [run_text(runs_of(p)[0]) for p in fragments]
    assert texts == ["첫줄", "둘째줄", "셋째줄"]


# ---------------------------------------------------------------------------
# AC-2: 줄 병합(그래뉼래러티)
# ---------------------------------------------------------------------------


def test_ac2_4_5_overlapping_adjacent_blocks_merge_into_one_paragraph_with_runs():
    # 세로 구간 [100,112] 완전 겹침, 가로 간격 있음(공백 삽입 대상)
    blocks = [
        make_block((10, 100, 40, 112), text="Hello", bold=False, font_name="Arial", font_size=10.0),
        make_block((50, 100, 90, 112), text="World", bold=True, font_name="Arial-Bold", font_size=12.0),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    paragraph = fragments[0]
    runs = runs_of(paragraph)
    assert len(runs) == 2

    assert run_text(runs[0]) == "Hello"
    assert runs[0].get("bold") is None
    assert runs[0].get("fontName") == "Arial"

    # 두 번째 run: bold 반영 + 공백 삽입("World" -> " World")
    assert run_text(runs[1]) == " World"
    assert runs[1].get("bold") == "1"
    assert runs[1].get("fontName") == "Arial-Bold"


def test_ac2_6_non_overlapping_vertical_blocks_stay_separate_paragraphs():
    blocks = [
        make_block((10, 100, 40, 112), text="Line1"),
        make_block((10, 200, 40, 212), text="Line2"),  # 세로로 완전히 분리됨
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 2
    assert run_text(runs_of(fragments[0])[0]) == "Line1"
    assert run_text(runs_of(fragments[1])[0]) == "Line2"


def test_ac2_7_merged_bbox_pt_is_union_of_group_bboxes():
    blocks = [
        make_block((10, 100, 40, 110), text="A"),
        make_block((45, 102, 90, 112), text="B"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    bbox_pt = fragments[0].get("bboxPt")
    assert bbox_pt == "10.00,100.00,90.00,112.00"


def test_ac2_overlap_ratio_boundary_exactly_0_5_merges():
    # prev: [100,112](height 12), curr: [106,118](height 12) -> overlap [106,112]=6 -> 6/12=0.5
    blocks = [
        make_block((10, 100, 40, 112), text="A"),
        make_block((10, 106, 40, 118), text="B"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1, "겹침 비율이 정확히 0.5면 임계값 이상(>=)이므로 병합되어야 한다"


def test_ac2_overlap_ratio_just_below_0_5_does_not_merge():
    # overlap 5.9/12 < 0.5
    blocks = [
        make_block((10, 100, 40, 112), text="A"),
        make_block((10, 106.1, 40, 118.1), text="B"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 2, "겹침 비율이 0.5 미만이면 분리된 문단이어야 한다"


def test_ac2_chain_merge_across_three_blocks_via_adjacent_pairs():
    """인접 블록끼리만 비교하므로, 1-2가 겹치고 2-3이 겹치면 1-3이 직접
    겹치지 않아도 전체가 한 문단으로 합쳐진다(unit-5-note.md 1-2-A절,
    "인접한 두 블록끼리만 비교"가 의도한 동작 — 결함 아님)."""
    blocks = [
        make_block((0, 100, 10, 112), text="A"),
        make_block((10, 106, 20, 118), text="B"),
        make_block((20, 112, 30, 124), text="C"),  # A와는 겹치지 않음([100,112] vs [112,124])
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    assert len(runs_of(fragments[0])) == 3


def test_ac2_zero_height_bbox_degenerate_case_does_not_crash():
    """top==bottom인 퇴화 bbox(높이 0)도 예외 없이 처리된다. 세로 구간이 점(0폭)이면
    overlap = min(bottom,bottom) - max(top,top) = 0이므로 코드의 `overlap <= 0: return False`
    분기에 걸려 "같은 줄이 아님"으로 판정된다(예외 없이 2개 문단으로 분리 — 이것이
    이 경계값의 실제 동작이며 크래시만 없으면 충분하다)."""
    blocks = [
        make_block((10, 100, 40, 100), text="A"),
        make_block((10, 100, 40, 100), text="B"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 2  # 점(0폭) bbox는 overlap<=0으로 판정되어 병합되지 않음(예외만 없으면 PASS)
    assert run_text(runs_of(fragments[0])[0]) == "A"
    assert run_text(runs_of(fragments[1])[0]) == "B"


# ---------------------------------------------------------------------------
# AC-3: 공백 보존(텍스트 무결성)
# ---------------------------------------------------------------------------


def test_ac3_8_positive_horizontal_gap_inserts_single_space():
    blocks = [
        make_block((10, 100, 40, 112), text="Hello"),
        make_block((41, 100, 90, 112), text="World"),  # gap = 41-40 = 1 > 0
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    assert run_text(runs[1]) == " World"


def test_ac3_9_zero_or_negative_gap_inserts_no_space_touching():
    blocks = [
        make_block((10, 100, 40, 112), text="Hello"),
        make_block((40, 100, 90, 112), text="World"),  # gap = 40-40 = 0
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    assert run_text(runs[1]) == "World"


def test_ac3_9_negative_gap_overlapping_bbox_inserts_no_space():
    blocks = [
        make_block((10, 100, 40, 112), text="Hello"),
        make_block((35, 100, 90, 112), text="World"),  # gap = 35-40 = -5 < 0 (겹침)
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    assert run_text(runs[1]) == "World"


def test_ac3_multiple_merges_only_non_first_runs_can_get_space():
    """첫 run은 그룹 내에서 항상 자기 자신의 원문 그대로 유지되고, 공백은
    두 번째 이후 run에만 조건부로 붙는다(간격 있는 3개 블록)."""
    blocks = [
        make_block((0, 100, 10, 112), text="A"),
        make_block((15, 100, 25, 112), text="B"),  # gap 5 -> space
        make_block((25, 100, 35, 112), text="C"),  # gap 0 -> no space
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    assert [run_text(r) for r in runs] == ["A", " B", "C"]


# ---------------------------------------------------------------------------
# AC-4: REQ-006 비적용 (NFC/NFD 재정규화하지 않음)
# ---------------------------------------------------------------------------


def test_ac4_10_nfd_text_passes_through_without_renormalization():
    original = "한글"
    nfd_text = unicodedata.normalize("NFD", original)  # 자모 분리형으로 강제 변환
    assert nfd_text != original  # 실제로 다른 문자열임을 먼저 확인(이 가정이 깨지면 이 테스트 자체가 무의미)
    blocks = [make_block((10, 100, 40, 112), text=nfd_text)]
    fragments = build_paragraph_fragments(blocks)
    result_text = run_text(runs_of(fragments[0])[0])
    # 재정규화(NFC 변환)를 전혀 수행하지 않고 NFD 원문 그대로 보존되어야 한다(REQ-006 비적용).
    assert result_text == nfd_text
    assert result_text != original  # 정규화되었다면 원문(NFC)과 같아졌을 것이다 -> 그렇지 않음을 명시적으로 확인


def test_ac4_10_mixed_nfc_nfd_text_across_merged_blocks_untouched():
    nfc_text = unicodedata.normalize("NFC", "안녕")
    nfd_text = unicodedata.normalize("NFD", "하세요")
    blocks = [
        make_block((0, 100, 20, 112), text=nfc_text),
        make_block((20, 100, 45, 112), text=nfd_text),  # gap 0, no space
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    assert run_text(runs[0]) == nfc_text
    assert run_text(runs[1]) == nfd_text


# ---------------------------------------------------------------------------
# AC-5: XML 유효성 / 안정성(불변성) / 호출 규약
# ---------------------------------------------------------------------------


def test_ac5_11_all_fragments_round_trip_as_well_formed_xml():
    blocks = [
        make_block((10, 100, 40, 112), text="Hello"),
        make_block((41, 100, 90, 112), text="World"),
        make_block((10, 200, 90, 212), text="다음 줄입니다"),
    ]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 2
    for fragment in fragments:
        assert_round_trips_as_well_formed(fragment)


def test_ac5_11_special_xml_characters_are_escaped_safely_on_round_trip():
    """XML 예약 문자(<, >, &, 따옴표)가 포함된 텍스트도 lxml의 자동 이스케이프로
    well-formed 상태를 유지해야 한다(수동 이스케이프 부재로 인한 손상 여부 확인)."""
    dangerous_text = "<script>alert(\"x\")&amp;'quote'</script>"
    blocks = [make_block((10, 100, 90, 112), text=dangerous_text)]
    fragments = build_paragraph_fragments(blocks)
    data = assert_round_trips_as_well_formed(fragments[0])
    reparsed = etree.fromstring(data)
    t = reparsed.find(f".//{T_TAG}")
    assert t.text == dangerous_text  # 왕복 후에도 원문이 정확히 보존됨


def test_ac5_12_input_blocks_are_not_mutated_and_calls_are_idempotent():
    original_blocks = [
        make_block((10, 100, 40, 112), text="Hello", bold=False),
        make_block((41, 100, 90, 112), text="World", bold=True),
    ]
    snapshot = copy.deepcopy(original_blocks)

    first_result = build_paragraph_fragments(original_blocks)
    assert original_blocks == snapshot, "입력 블록 리스트/원소가 변형되면 안 된다"

    second_result = build_paragraph_fragments(original_blocks)
    assert etree.tostring(first_result[0]) == etree.tostring(
        second_result[0]
    ), "같은 입력으로 두 번 호출하면 바이트 단위로 동일한 결과가 나와야 한다(순수 함수)"


def test_ac5_13_mixing_two_pages_in_one_call_is_a_caller_misuse_not_a_defect():
    """호출 규약 문서화 확인(1-4절/AC-5-13): 서로 다른 페이지의 블록을 한 호출에
    섞으면 페이지 경계에서 줄 오판정이 발생할 수 있음을 실제로 재현한다. 이는
    이 함수의 결함이 아니라 잘못된 호출 방식임을 증명하는 탐색적 테스트다."""
    # "페이지 1"의 마지막 줄과 "페이지 2"의 첫 줄이 우연히 같은 좌표 구간에 있으면
    # 서로 다른 페이지임에도 같은 줄로 잘못 병합된다.
    page1_last_line = make_block((10, 100, 40, 112), text="P1-마지막줄")
    page2_first_line = make_block((10, 100, 40, 112), text="P2-첫줄")  # 새 페이지, 좌표 0,0 기준 재시작
    fragments = build_paragraph_fragments([page1_last_line, page2_first_line])
    assert len(fragments) == 1, (
        "페이지 구분 없이 섞으면 좌표가 겹쳐 같은 줄로 오판정된다 — "
        "이것이 바로 호출자가 페이지마다 별도 호출해야 하는 이유(결함 아님)"
    )


# ---------------------------------------------------------------------------
# AC-6: 알려진 한계 (실패로 취급하지 않음 — 한계가 재현됨을 확인만 함)
# ---------------------------------------------------------------------------


def test_ac6_14_multi_column_same_vertical_band_can_be_falsely_merged():
    """다단 레이아웃 한계: 같은 세로 구간의 다른 컬럼 블록이 같은 줄로 잘못
    병합될 수 있음을 재현한다(결함이 아니라 알려진 한계, unit-1로부터 상속)."""
    left_column = make_block((10, 100, 40, 112), text="왼쪽컬럼")
    right_column = make_block((300, 100, 340, 112), text="오른쪽컬럼")  # 가로로 멀리 떨어짐, 세로는 동일
    fragments = build_paragraph_fragments([left_column, right_column])
    assert len(fragments) == 1  # 실제로는 별개 컬럼이지만 1개 문단으로 합쳐짐(알려진 한계)


def test_ac6_15_bbox_pt_is_reference_only_not_absolute_positioning():
    """순차 흐름형 배치: 반환된 <hp:p>에는 위치 지정 엘리먼트(hp:pos 등)가 없고
    bboxPt는 참고용 속성으로만 남는다(REQ-008 6-6 정밀 배치는 미반영)."""
    blocks = [make_block((10, 100, 40, 112), text="A")]
    fragments = build_paragraph_fragments(blocks)
    paragraph = fragments[0]
    assert paragraph.get("bboxPt") is not None
    assert paragraph.find(qname("hp", "pos")) is None


def test_ac6_16_kerning_style_change_mid_word_may_insert_unwanted_space():
    """스타일이 단어 중간에서 바뀌면서도 시각적으로 살짝 간격이 있으면 불필요한
    공백이 삽입될 수 있다는 한계를 재현한다(결함 아님, 문서화된 휴리스틱 단순화)."""
    blocks = [
        make_block((10, 100, 20, 112), text="wo", font_name="Arial"),
        make_block((20.5, 100, 30, 112), text="rld", font_name="Arial-Bold"),  # 커닝으로 인한 미세 간격
    ]
    fragments = build_paragraph_fragments(blocks)
    runs = runs_of(fragments[0])
    # "word"가 아니라 "wo rld"처럼 불필요한 공백이 들어갈 수 있음(한계 재현)
    assert run_text(runs[1]) == " rld"


# ---------------------------------------------------------------------------
# 경계값 / 위험 케이스 (AC에 없지만 06 원칙상 필수 확인)
# ---------------------------------------------------------------------------


def test_boundary_single_block_group_of_one():
    blocks = [make_block((10, 100, 40, 112), text="단독")]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    assert len(runs_of(fragments[0])) == 1


def test_boundary_empty_string_text_does_not_raise():
    blocks = [make_block((10, 100, 40, 112), text="")]
    fragments = build_paragraph_fragments(blocks)
    assert run_text(runs_of(fragments[0])[0]) == ""


def test_risk_none_font_name_and_font_size_omit_optional_attrs():
    blocks = [
        make_block(
            (10, 100, 40, 112),
            text="A",
            font_name=None,
            font_size=None,
            bold=False,
            italic=False,
        )
    ]
    fragments = build_paragraph_fragments(blocks)
    run = runs_of(fragments[0])[0]
    assert run.get("fontName") is None
    assert run.get("fontSizeHwpunit") is None
    assert run.get("bold") is None
    assert run.get("italic") is None


def test_risk_unicode_emoji_and_surrogate_range_text_preserved():
    emoji_text = "긴급 공지 🚨 확인 요망 — café"
    blocks = [make_block((10, 100, 90, 112), text=emoji_text)]
    fragments = build_paragraph_fragments(blocks)
    assert run_text(runs_of(fragments[0])[0]) == emoji_text
    assert_round_trips_as_well_formed(fragments[0])


def test_risk_custom_char_shape_and_para_shape_ids_propagate_to_all_runs():
    blocks = [
        make_block((10, 100, 40, 112), text="A"),
        make_block((41, 100, 90, 112), text="B"),
    ]
    fragments = build_paragraph_fragments(blocks, char_shape_id="7", para_shape_id="3")
    paragraph = fragments[0]
    assert paragraph.get("paraShapeIDRef") == "3"
    for run in runs_of(paragraph):
        assert run.get("charShapeIDRef") == "7"


def test_risk_default_shape_ids_are_zero():
    blocks = [make_block((10, 100, 40, 112), text="A")]
    fragments = build_paragraph_fragments(blocks)
    paragraph = fragments[0]
    assert paragraph.get("paraShapeIDRef") == "0"
    assert runs_of(paragraph)[0].get("charShapeIDRef") == "0"


def test_risk_to_unicode_missing_replacement_char_passthrough():
    """REQ-007 대체문자(□)가 이미 치환된 상태라고 가정 — 이 모듈이 추가 치환하지 않음."""
    blocks = [make_block((10, 100, 40, 112), text="정상텍스트□누락", to_unicode_missing=True)]
    fragments = build_paragraph_fragments(blocks)
    assert run_text(runs_of(fragments[0])[0]) == "정상텍스트□누락"


def test_risk_negative_bbox_coordinates_do_not_raise():
    """음수 좌표(상위 계산 오류로 발생 가능) — pt_to_hwpunit과 동일하게 이 모듈도
    검증 없이 그대로 계산에 사용한다는 계약(unit-4-test.md TC-204와 동일 취지)."""
    blocks = [make_block((-10, -50, 20, -30), text="A")]
    fragments = build_paragraph_fragments(blocks)
    assert fragments[0].get("bboxPt") == "-10.00,-50.00,20.00,-30.00"


def test_risk_large_number_of_blocks_all_same_line_merge_into_single_paragraph_many_runs():
    """다수 블록(20개)이 모두 같은 줄일 때 성능/누락 없이 전부 run으로 반영되는지."""
    blocks = [make_block((i * 10, 100, i * 10 + 8, 112), text=f"w{i}") for i in range(20)]
    fragments = build_paragraph_fragments(blocks)
    assert len(fragments) == 1
    runs = runs_of(fragments[0])
    assert len(runs) == 20
    assert run_text(runs[0]) == "w0"
    assert run_text(runs[-1]) == " w19"  # 간격 2pt(> 0)이므로 공백 삽입


def test_risk_control_character_in_text_propagates_lxml_valueerror_uncaught():
    """(내부검증 2차에서 추가 발견) PDF 추출 텍스트에 NULL/제어문자가 섞여 있으면
    lxml이 엘리먼트 텍스트 대입 시 ValueError를 던진다. unit-5-note.md 3절
    "에러 처리가 누락된 경로가 없는가" 항목은 "이 unit이 예외를 감싸지 않고
    그대로 전파한다"는 정책을 명시했다 — 이 모듈이 그 정책을 실제로 지키는지
    (조용히 삼키거나 손상된 XML을 만들지 않는지) 확인한다. FAIL이 아니라
    정책대로 예외가 전파되는지가 검증 대상이다."""
    blocks = [make_block((10, 100, 40, 112), text="bad\x00text")]
    with pytest.raises(ValueError, match="XML compatible"):
        build_paragraph_fragments(blocks)


def test_risk_control_character_in_second_merged_block_also_propagates():
    """병합 그룹의 두 번째 이후 블록에 제어문자가 있어도 동일하게 예외가
    전파되어야 한다(첫 블록만 검사하고 넘어가는 결함이 없는지 확인)."""
    blocks = [
        make_block((10, 100, 40, 112), text="ok"),
        make_block((41, 100, 90, 112), text="bad\x01text"),
    ]
    with pytest.raises(ValueError, match="XML compatible"):
        build_paragraph_fragments(blocks)
