"""PDF 표(``TableBlockIR``) -> HWPX 표(``hp:tbl``) 프래그먼트 변환 (unit-6, REQ-004).

``pdf_to_hwpx.pdf_reader.table_recognizer``(unit-3)가 만든 :class:`TableBlockIR`
목록을 받아, HWPX 섹션 본문에 삽입 가능한 ``<hp:tbl>`` 프래그먼트(lxml
``etree._Element``) 목록으로 변환한다. 실제 XML 태그 생성 자체는
``hwpx_kernel.schema``(unit-4)의 계약 함수(``table_cell_to_cell_fragment``)에
위임하고, 이 모듈은 "병합 셀이 있는 실제 표를 정확한 그리드 좌표로 배치하는"
도메인 로직만 책임진다(unit-4-note.md §2-2 "unit-6이 직접 (row, col)을
계산해 넘기는 방식을 쓰라"는 안내를 따름).

## 왜 ``hwpx_kernel.schema.table_block_to_table_fragment``(unit-4의 편의 함수)를
## 쓰지 않는가

그 함수는 ``block.cells``가 병합 포함 rows*cols 그리드를 행 우선(row-major)
순서로 빠짐없이 채운다고 가정하고 단순 ``divmod(idx, cols)``로 좌표를
추정하는 단순화된 기본 구현이다. 그러나 unit-3이 실제로 만드는
``TableBlockIR.cells``는 병합이 있으면 ``rows*cols``보다 항목 수가 적다
(unit-3-note.md §1-4) — 즉 ``divmod`` 가정이 병합 표에서 깨진다. 이 모듈은
``row_span``/``col_span``만으로 각 셀이 채워야 할 실제 그리드 좌표를
직접 복원한다(:func:`_resolve_cell_positions`).

## ``has_merged_cells`` 플래그에 분기하지 않는 이유

unit-3의 병합 감지는 best-effort이고 ``has_merged_cells=False``는 "병합이
없음이 확정"이 아니라 "확정된 병합을 찾지 못함"이라는 보수적 판정이다
(unit-3-note.md §1-2, "미탐(false negative) 가능성"). 만약 이 플래그를
기준으로 "``False``면 단순 divmod 배치, ``True``면 정밀 배치"로 분기하면,
미탐 상황에서 실제로는 병합이 있는데도(그리고 ``cells`` 개수가
``rows*cols``보다 적은데도) 단순 배치 경로를 타 잘못된 그리드가 만들어질
위험이 있다. 반면 :func:`_resolve_cell_positions`는 ``row_span``/``col_span``
값 자체로 그리드를 채워나가므로, 병합이 실제로 있든 없든(``has_merged_cells``
값과 무관하게) 항상 정확한 좌표를 만든다 — 따라서 이 모듈은 그 플래그를
좌표 계산 분기에 전혀 사용하지 않는다(``<hp:tbl>``에 표시용 속성으로만 남김).

## bbox(배치) 처리

``TableBlockIR.bbox``(pdfplumber 좌표계, pt 단위)는 unit-5
(``paragraph_builder.py``)의 ``text_block_to_paragraph_fragment``가 이미
채택한 것과 동일한 방식으로 처리한다 — 이 모듈은 순수 변환 라이브러리이고
상태를 갖지 않으므로, 실제 절대/상대 배치 방식을 확정하지 않고 참고용
``bboxPt`` 속성("x0,y0,x1,y1", pt 단위 문자열)만 ``<hp:tbl>``에 부착한다.
실제 세로 위치 정밀화(REQ-008 6-6)는 unit-8(orchestrator)이 이 속성을
활용해 처리해야 한다(unit-4-note.md §2-2 문단 프래그먼트와 동일한 판단
기준, 04단계 지시).
"""

from __future__ import annotations

from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.hwpx_kernel.schema import table_cell_to_cell_fragment
from pdf_to_hwpx.pdf_reader.ir import TableBlockIR

# hwpx_kernel/container.py의 _build_header_xml()이 정의한 기본 스타일 id와
# 반드시 일치해야 한다(hwpx_kernel/schema.py의 동일 상수와 같은 계약).
_DEFAULT_CHAR_SHAPE_ID = "0"
_DEFAULT_PARA_SHAPE_ID = "0"


def _qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def _resolve_cell_positions(block: TableBlockIR) -> list[tuple[int, int]]:
    """``block.cells``의 각 항목이 채워야 할 (row, col) 그리드 좌표를 계산한다.

    격자를 좌상단에서 우하단으로(행 우선) 훑으며, 아직 다른 셀이 점유하지
    않은 첫 칸을 다음 ``cells`` 항목의 시작 좌표로 배정하고, 그 셀의
    ``row_span``/``col_span``만큼 칸을 점유 처리한다. unit-3이 ``cells``를
    만드는 순서(각 병합 그룹의 좌상단 좌표 기준 오름차순, table_recognizer.py
    ``sorted(spans.items())``)와 정확히 대응하는 복원 알고리즘이다.
    """
    rows, cols = block.rows, block.cols
    occupied = [[False] * cols for _ in range(rows)]
    positions: list[tuple[int, int]] = []

    cell_idx = 0
    n_cells = len(block.cells)
    for r in range(rows):
        for c in range(cols):
            if cell_idx >= n_cells:
                break
            if occupied[r][c]:
                continue
            cell = block.cells[cell_idx]
            positions.append((r, c))
            for rr in range(r, min(r + cell.row_span, rows)):
                for cc in range(c, min(c + cell.col_span, cols)):
                    occupied[rr][cc] = True
            cell_idx += 1
        if cell_idx >= n_cells:
            break

    fully_covered = all(all(row) for row in occupied)
    if cell_idx != n_cells or not fully_covered:
        raise ValueError(
            "TableBlockIR.cells가 rows*cols 그리드를 정확히 채우지 못했습니다 "
            f"(rows={rows}, cols={cols}, 배치된 셀={cell_idx}, 전달된 셀={n_cells}, "
            f"전체 그리드 점유 완료={fully_covered}). "
            "table_recognizer(unit-3)가 만든 IR과 다른 값이 들어온 것으로 보입니다."
        )
    return positions


def table_block_to_fragment(
    block: TableBlockIR,
    *,
    char_shape_id: str = _DEFAULT_CHAR_SHAPE_ID,
    para_shape_id: str = _DEFAULT_PARA_SHAPE_ID,
) -> etree._Element:
    """``TableBlockIR`` 1개를 표(``hp:tbl``) 프래그먼트로 변환한다.

    병합 셀 유무와 무관하게(위 모듈 docstring 참고) 항상
    :func:`_resolve_cell_positions`로 계산한 정확한 (row, col)을
    ``hwpx_kernel.schema.table_cell_to_cell_fragment``에 명시적으로 넘긴다.
    """
    positions = _resolve_cell_positions(block)

    tbl = etree.Element(
        _qname("hp", "tbl"),
        attrib={"rowCnt": str(block.rows), "colCnt": str(block.cols)},
    )
    if block.has_merged_cells:
        tbl.set("hasMergedCells", "1")
    x0, y0, x1, y1 = block.bbox
    tbl.set("bboxPt", f"{x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f}")

    rows_xml: dict[int, etree._Element] = {}
    for cell, (row, col) in zip(block.cells, positions):
        tr = rows_xml.get(row)
        if tr is None:
            tr = etree.SubElement(tbl, _qname("hp", "tr"))
            rows_xml[row] = tr
        tr.append(
            table_cell_to_cell_fragment(
                cell,
                row=row,
                col=col,
                char_shape_id=char_shape_id,
                para_shape_id=para_shape_id,
            )
        )
    return tbl


def table_blocks_to_fragments(
    blocks: list[TableBlockIR],
    *,
    char_shape_id: str = _DEFAULT_CHAR_SHAPE_ID,
    para_shape_id: str = _DEFAULT_PARA_SHAPE_ID,
) -> list[etree._Element]:
    """``PageIR.table_blocks`` 전체를 ``<hp:tbl>`` 프래그먼트 목록으로 변환한다.

    호출자(orchestrator, unit-8)는 반환된 프래그먼트를 순서대로 섹션
    본문에 삽입하면 된다(``hwpx_kernel.schema.fragment_to_bytes`` 또는
    ``build_reference_section_body`` 참고).
    """
    return [
        table_block_to_fragment(
            block, char_shape_id=char_shape_id, para_shape_id=para_shape_id
        )
        for block in blocks
    ]
