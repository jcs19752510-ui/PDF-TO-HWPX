"""``TextBlockIR`` 목록 -> HWPX 문단(``hp:p``) 프래그먼트 목록 변환 (unit-5).

(docs/harness/03-system-design.md v4 §1-3 unit-5 행 "HWPX 문단/텍스트 빌더",
02-planning.md REQ-002/REQ-006/REQ-008 참고. v5 리비전은 웹 서비스 계층만
다루고 이 파일은 전혀 건드리지 않는다 — 03 §1-1 "라이브러리 vs 서비스 경계".)

이 모듈의 입력은 ``pdf_reader/text_extractor.py``(unit-1)의
``extract_text_blocks(page)``가 반환한, **페이지 1개 분량**의
``TextBlockIR`` 목록이다(줄 단위로 그룹, 각 줄 내부는 x0 오름차순 —
unit-1-note.md 1-2절). 이 함수는 그 목록을 받아
``hwpx_kernel/schema.py``(unit-4)의 계약 함수만 사용해 섹션 본문에
순서대로 삽입 가능한 ``<hp:p>`` 프래그먼트 목록을 만든다.

**호출 규약(중요, unit-8이 지켜야 함)**: 이 함수는 입력 목록 안의 인접한
두 블록을 "같은 시각적 줄인지" bbox 세로 겹침으로 판정한다(아래
``_same_line`` 참고). 이 판정은 **같은 페이지 내부에서만** 유효하다 —
서로 다른 페이지의 블록을 한 번의 호출에 섞어 넣으면 각 페이지가 독립된
좌표계(0,0 기준)를 가지므로 다른 페이지의 줄을 같은 줄로 잘못 묶을 수
있다. 따라서 오케스트레이터(unit-8)는 **페이지마다 이 함수를 한 번씩
호출**하고, 반환된 문단 목록들을 페이지 순서대로 이어 붙여야 한다(페이지
구분 자체를 표현하는 방법은 이 함수의 책임이 아니다).

이 모듈이 스스로 내린 설계 판단(03/04단계가 명시하지 않아 합리적으로
결정한 것들 — 근거는 각 함수 docstring과 unit-5-note.md에 상술):

1. **그래뉼래러티**: "같은 줄"로 판정된 인접 블록들을 문단 1개
   (``<hp:p>``) 안에 run 여러 개로 합친다(1 줄 = 1 문단, unit-1이 폰트
   변화마다 쪼갠 블록을 다시 시각적 줄 단위로 복원). 문단(paragraph)과
   줄바꿈(line wrap)의 구분(여러 줄을 하나의 논리적 문단으로 묶는 것)은
   시도하지 않는다 — 03 설계서가 이를 요구하지 않고, 신뢰할 근거(줄
   간격/들여쓰기 분석 등) 없이 시도하면 과설계다.
2. **``schema.py`` 미수정**: ``schema.text_block_to_paragraph_fragment``는
   블록 1개당 문단 1개(run 1개)만 만드는 저수준 함수라 "여러 run을 가진
   문단 1개"를 직접 만들어주지 않는다. 이 모듈은 ``schema.py``를 고치는
   대신, 병합 대상 블록마다 그 함수를 각각 호출해 만들어진 임시
   ``<hp:p>``에서 ``<hp:run>`` 자식만 꺼내(lxml이 자동으로 원래 부모에서
   떼어낸다) 첫 블록의 ``<hp:p>``에 이어 붙인다(``_group_to_paragraph``).
   run 내부의 굵기/기울임/폰트명/크기/텍스트 조립 로직은 전부
   ``schema.py``가 그대로 수행하므로 이 모듈은 그 로직을 중복 구현하지
   않는다. **다만 이는 임시방편이다** — "여러 run을 가진 문단"이 계약
   차원에서 필요하다는 사실 자체는 ``schema.py`` 확장 대상인 공유 자원
   이슈로 별도 보고한다(unit-5-note.md "공유 문서 갱신 요청").
3. **배치 방식**: bbox를 절대 좌표로 변환해 고정 배치하지 않고, 문단을
   읽기 순서 그대로 순차 흐름형(inline flow)으로 둔다 — 03 §1-1의
   "상태 없는 순수 변환 라이브러리" 의도와, ``schema.py``가 절대 위치
   지정에 필요한 필드/계약을 아직 정의하지 않았다는 사실에 비춰 내린
   판단이다. bbox는 ``bboxPt`` 속성(병합된 블록들의 합집합)으로만
   남겨 추후 정밀 배치(REQ-008 6-6)의 참고 자료로 제공한다.
4. **REQ-006 비적용**: ``block.text``를 있는 그대로 소비한다. NFC
   정규화는 unit-15(``hangul_normalizer``, 아직 Not Started)의 책임이며
   이 모듈은 재정규화하지 않는다.
"""

from __future__ import annotations

from lxml import etree

from pdf_to_hwpx.hwpx_kernel.schema import text_block_to_paragraph_fragment
from pdf_to_hwpx.pdf_reader.ir import TextBlockIR

_DEFAULT_CHAR_SHAPE_ID = "0"
_DEFAULT_PARA_SHAPE_ID = "0"

# unit-1(text_extractor)의 ``_LINE_OVERLAP_RATIO``와 동일한 근거/값을
# 재사용한다(재작업 DEF-001에서 검증된 "세로 구간 겹침 비율" 방식).
# 03 설계서에 구체적 수치가 없어 합리적으로 정한 휴리스틱이며, 근거 있는
# 표준값은 아니다 — 다단(멀티컬럼) 레이아웃에서 같은 세로 구간에 있는
# 다른 컬럼 블록을 같은 줄로 잘못 묶을 수 있는 한계도 그대로 물려받는다.
_LINE_OVERLAP_RATIO = 0.5


def build_paragraph_fragments(
    blocks: list[TextBlockIR],
    *,
    char_shape_id: str = _DEFAULT_CHAR_SHAPE_ID,
    para_shape_id: str = _DEFAULT_PARA_SHAPE_ID,
) -> list[etree._Element]:
    """페이지 1개 분량의 ``TextBlockIR`` 목록을 ``<hp:p>`` 목록으로 변환한다.

    Args:
        blocks: ``extract_text_blocks(page)``(unit-1)가 반환한, 이미 줄
            단위·줄 내부 x0 오름차순으로 정렬된 목록. 빈 목록이면 빈
            목록을 반환한다(페이지에 텍스트가 없는 경우).
        char_shape_id / para_shape_id: ``schema.py``가 정의한 스타일 id.
            기본값 "0"은 ``container.py``의 기본 스타일과 일치한다(모듈
            docstring의 스키마 계약 그대로).

    Returns:
        입력과 같은 읽기 순서를 유지하는 ``<hp:p>`` 프래그먼트 목록.
        시각적으로 같은 줄로 판정된 연속 블록들은 하나의 ``<hp:p>`` 안에
        여러 ``<hp:run>``으로 합쳐진다.
    """
    if not blocks:
        return []

    fragments: list[etree._Element] = []
    current_group: list[TextBlockIR] = [blocks[0]]

    for block in blocks[1:]:
        if _same_line(current_group[-1], block):
            current_group.append(block)
        else:
            fragments.append(
                _group_to_paragraph(
                    current_group, char_shape_id=char_shape_id, para_shape_id=para_shape_id
                )
            )
            current_group = [block]
    fragments.append(
        _group_to_paragraph(current_group, char_shape_id=char_shape_id, para_shape_id=para_shape_id)
    )
    return fragments


def _same_line(prev: TextBlockIR, curr: TextBlockIR) -> bool:
    """두 블록의 bbox 세로 구간이 충분히 겹치는지로 "같은 줄"을 판정한다.

    unit-1의 ``_has_vertical_overlap``과 동일한 방식(어센트/디센트 비대칭
    때문에 ``top`` 단독 비교보다 세로 구간 겹침 비율이 폰트 크기가 섞인
    줄에서 더 안정적이라는 실측 근거, unit-1-note.md DEF-001 재작업 절
    참고)을 인접한 두 블록 사이에만 적용한, 더 단순화된 버전이다. unit-1은
    임의의 word 집합 전체를 클러스터링해야 했지만, 이 모듈의 입력은 이미
    unit-1이 줄 단위로 정렬해 놓은 목록이므로 "인접 블록끼리만" 비교해도
    충분하다(전수 클러스터링을 다시 구현하는 것은 과설계).
    """
    _, prev_top, _, prev_bottom = prev.bbox
    _, curr_top, _, curr_bottom = curr.bbox
    prev_height = max(prev_bottom - prev_top, 0.01)
    curr_height = max(curr_bottom - curr_top, 0.01)

    overlap = min(prev_bottom, curr_bottom) - max(prev_top, curr_top)
    if overlap <= 0:
        return False
    return overlap / min(prev_height, curr_height) >= _LINE_OVERLAP_RATIO


def _group_to_paragraph(
    group: list[TextBlockIR],
    *,
    char_shape_id: str,
    para_shape_id: str,
) -> etree._Element:
    """같은 줄로 판정된 블록 그룹을 run 여러 개를 가진 문단 1개로 합친다.

    각 블록은 ``schema.text_block_to_paragraph_fragment``를 그대로 호출해
    (굵기/기울임/폰트명/크기/텍스트가 반영된) run을 만들고, 첫 블록의
    ``<hp:p>``에 나머지 블록들의 run을 이어 붙인다(``append``는 lxml에서
    이미 다른 트리에 속한 엘리먼트를 자동으로 원래 부모에서 떼어내
    옮긴다). ``bboxPt``는 그룹 전체 블록의 합집합으로 다시 계산해 덮어쓴다.
    """
    paragraph = text_block_to_paragraph_fragment(
        group[0], char_shape_id=char_shape_id, para_shape_id=para_shape_id
    )
    for prev_block, block in zip(group, group[1:]):
        extra = text_block_to_paragraph_fragment(
            block, char_shape_id=char_shape_id, para_shape_id=para_shape_id
        )
        run = extra[0]
        if _has_visual_gap(prev_block, block):
            _prepend_space(run)
        paragraph.append(run)

    x0 = min(b.bbox[0] for b in group)
    y0 = min(b.bbox[1] for b in group)
    x1 = max(b.bbox[2] for b in group)
    y1 = max(b.bbox[3] for b in group)
    paragraph.set("bboxPt", f"{x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f}")
    return paragraph


def _has_visual_gap(prev: TextBlockIR, curr: TextBlockIR) -> bool:
    """두 블록 사이에 가로로 벌어진 간격(원래 별도 단어였을 신호)이 있는지.

    unit-1은 같은 (폰트명, 크기) 구간의 word들만 공백으로 join하고, 폰트가
    바뀌는 지점(=이 모듈이 다시 합치는 블록 경계)에서는 원래 있었을 공백
    문자를 전혀 보존하지 않는다(word 자체가 공백을 포함하지 않으므로).
    이 함수가 없으면 "Hello **World**"처럼 스타일이 섞인 문구가
    "HelloWorld"로 붙어버리는 텍스트 손상이 생긴다. bbox상 두 블록 사이에
    양(+)의 가로 간격이 있으면(겹치거나 맞닿지 않았으면) 원래 단어 경계였다고
    보고 공백 1개를 삽입한다. 간격이 0 이하(맞닿거나 겹침)면 스타일 변화가
    한 단어 내부에서 일어난 것으로 보고 공백을 넣지 않는다.

    **한계(그대로 기록)**: 이 휴리스틱은 실제 단어 사이 공백 폭과 무관하게
    "간격이 있으면 공백 1개"로 단순화한다. 03 설계서에 근거 수치가 없어
    합리적으로 정했다.
    """
    gap = curr.bbox[0] - prev.bbox[2]
    return gap > 0


def _prepend_space(run: etree._Element) -> None:
    t = run[0]
    t.text = " " + (t.text or "")
