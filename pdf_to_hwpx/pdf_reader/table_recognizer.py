"""PDF 표 구조 인식 (docs/harness/03-system-design.md §1-3 unit-3, REQ-004).

``pdfplumber``의 ``Page.find_tables()``가 반환하는 :class:`pdfplumber.table.Table`
객체를 :class:`pdf_to_hwpx.pdf_reader.ir.TableBlockIR` 목록으로 변환한다.
이 모듈은 "인식"만 담당하며(03 §1-2 컴포넌트 다이어그램: ``table_recognizer.py``
-> ``TABLEB``(unit-6)로 IR을 넘김), HWPX 표 객체로 실제로 그려내는 것은
``hwpx_writer/table_builder.py``(unit-6)의 책임이다.

## 병합 셀(REQ-004) 처리는 best-effort다 — 반드시 읽을 것

``pdfplumber``는 셀 병합을 "병합"이라는 개념으로 알려주지 않는다. 내부적으로
표는 감지된 선(rule line)들의 교차로 만들어진 사각형 격자일 뿐이고, 병합된
영역은 "그 위치에 경계선이 없어서 별도 셀 사각형이 잡히지 않은 격자 칸"으로만
나타난다(``Table.rows[i].cells``에서 해당 위치가 ``None``). 즉 병합 여부 자체를
직접 알려주는 API가 없으므로, 이 모듈은 아래 휴리스틱으로 "이 빈 칸이 왼쪽/위쪽의
어느 실제 셀에 흡수된 것인지"를 기하학적으로 추정한다:

1. 격자를 좌상단에서 우하단으로 훑으면서, 실제 사각형이 있는 칸은 자기 자신을
   소유자(owner)로 기록한다.
2. 사각형이 없는(``None``) 칸을 만나면:
   a. 먼저 **왼쪽 칸의 소유자** 사각형의 오른쪽 끝(x1)이 이 칸이 속한 열의
      시작 x좌표를 넘어서는지 확인한다 — 넘어서면 그 왼쪽 셀이 가로로 병합되어
      이 칸까지 덮은 것으로 판단한다(가로 병합).
   b. 가로 병합이 아니면 **위쪽 칸의 소유자** 사각형의 아래쪽 끝(bottom)이 이
      칸이 속한 행의 시작 y좌표(top)를 넘어서는지 확인한다 — 넘어서면 그
      위쪽 셀이 세로로 병합되어 이 칸까지 덮은 것으로 판단한다(세로 병합).
   c. 둘 다 기하학적으로 확인되지 않으면(예: 해당 열/행에 대해 비교할 실제
      사각형 기준선 자체를 한 번도 얻지 못한 경우) 병합으로 단정하지 않고,
      **내용 없는 독립된 1x1 빈 셀**로 남긴다 — 이 경우는 이 모듈이 병합을
      "놓친" 것일 수 있다(아래 한계 참고). 지어내지 않고 있는 그대로 둔다.
3. 같은 소유자를 공유하는 격자 칸들을 모아 하나의 :class:`TableCellIR`로
   합치고, 칸 범위로부터 ``row_span``/``col_span``을 계산한다.
4. 위 과정에서 실제로 하나 이상의 병합이 (a) 또는 (b)로 확정된 표에 한해서만
   ``TableBlockIR.has_merged_cells = True``로 설정한다. 확정된 병합이 전혀
   없으면(2-c만 발생했거나 애초에 병합이 없으면) ``False``로 둔다 — 감지하지
   못한 잠재적 병합을 "감지했다"고 지어내지 않는다.

### 알려진 한계 (지어내지 않고 명시)
- 병합된 셀들이 표의 첫 행/첫 열에 걸쳐 있어서 비교 기준이 될 실제 사각형을
  전혀 얻을 수 없는 극단적 배치(예: 표 전체 열 하나가 병합만으로 구성된 경우)는
  2-c 경로로 빠져 병합이 아닌 빈 셀로 남을 수 있다.
- 3개 이상의 칸이 얽힌 복합 병합(L자형 등, 즉 사각형이 아닌 병합 영역)은
  pdfplumber의 격자 모델 자체가 표현하지 못하므로 이 모듈도 표현하지 못한다.
- ``pdfplumber``가 애초에 표로 인식하지 못하는 경우(테두리선이 전혀 없는 표 등)는
  이 함수 호출 전 단계(``find_tables()``)에서 걸러지므로 이 모듈의 책임 밖이다.
- 위 한계들은 모두 REQ-004가 명시한 "병합 셀은 best-effort" 조건 안에 있다.
"""

from __future__ import annotations

from typing import Any

import pdfplumber

from pdf_to_hwpx.pdf_reader.ir import TableBlockIR, TableCellIR

# 병합 판정 시 부동소수점 오차를 흡수하기 위한 여유값(포인트 단위).
_GEOMETRY_EPSILON = 0.5


def extract_table_blocks(
    plumber_page: pdfplumber.page.Page,
    table_settings: dict[str, Any] | None = None,
) -> list[TableBlockIR]:
    """페이지에서 감지된 모든 표를 :class:`TableBlockIR` 목록으로 변환한다.

    Args:
        plumber_page: ``pdf_reader.loader.PdfDocument.plumber_pdf.pages[i]``로
            얻는 pdfplumber 페이지 객체(unit-0 산출물, 읽기 전용 소비).
        table_settings: ``Page.find_tables()``에 그대로 전달할 pdfplumber
            표 감지 설정(선 감지 전략 등). ``None``이면 pdfplumber 기본값을
            사용한다 — 03 §2-1이 확정한 대로 ``extract_tables()`` 계열
            기본 동작이 REQ-004 요구 수준을 충족한다고 보았다.

    Returns:
        페이지 내 감지된 표 개수만큼의 :class:`TableBlockIR` 리스트(표가
        없으면 빈 리스트). 순서는 ``find_tables()``가 반환한 순서를 그대로
        따른다(pdfplumber는 대체로 페이지 상단부터 순서를 매김).
    """
    kwargs = {} if table_settings is None else {"table_settings": table_settings}
    tables = plumber_page.find_tables(**kwargs)

    blocks: list[TableBlockIR] = []
    for table in tables:
        rows = table.rows
        n_rows = len(rows)
        if n_rows == 0:
            continue
        n_cols = len(rows[0].cells)
        if n_cols == 0:
            continue

        grid_bbox: list[list[tuple[float, float, float, float] | None]] = [
            list(row.cells) for row in rows
        ]
        grid_text = table.extract()

        blocks.append(
            _build_table_block(
                bbox=table.bbox,
                rows=rows,
                grid_bbox=grid_bbox,
                grid_text=grid_text,
                n_rows=n_rows,
                n_cols=n_cols,
            )
        )

    return blocks


def _build_table_block(
    *,
    bbox: tuple[float, float, float, float],
    rows: list[Any],
    grid_bbox: list[list[tuple[float, float, float, float] | None]],
    grid_text: list[list[str | None]],
    n_rows: int,
    n_cols: int,
) -> TableBlockIR:
    # 열마다 "실제 사각형이 존재하는" 첫 x0 좌표를 기록해, 병합 판정 시
    # "이 칸은 원래 몇 x좌표에서 시작해야 하는가"의 기준선으로 쓴다.
    col_x0: list[float | None] = [None] * n_cols
    for row_cells in grid_bbox:
        for c, cell in enumerate(row_cells):
            if cell is not None and col_x0[c] is None:
                col_x0[c] = cell[0]

    # owner[r][c] = 이 격자 칸이 속한 "원래 셀"의 (행, 열) 좌표.
    owner: list[list[tuple[int, int] | None]] = [[None] * n_cols for _ in range(n_rows)]
    # (r, c) -> 그 원래 셀의 실제 사각형. 병합 판정을 못 한 독립 빈 셀은 None.
    owner_bbox: dict[tuple[int, int], tuple[float, float, float, float] | None] = {}
    confirmed_merge = False

    for r in range(n_rows):
        row_top = rows[r].bbox[1]
        for c in range(n_cols):
            cell = grid_bbox[r][c]
            if cell is not None:
                owner[r][c] = (r, c)
                owner_bbox[(r, c)] = cell
                continue

            resolved: tuple[int, int] | None = None

            if c > 0:
                left_owner = owner[r][c - 1]
                if left_owner is not None:
                    left_bbox = owner_bbox[left_owner]
                    boundary = col_x0[c]
                    if left_bbox is not None and (
                        boundary is None or left_bbox[2] > boundary + _GEOMETRY_EPSILON
                    ):
                        resolved = left_owner

            if resolved is None and r > 0:
                up_owner = owner[r - 1][c]
                if up_owner is not None:
                    up_bbox = owner_bbox[up_owner]
                    if up_bbox is not None and up_bbox[3] > row_top + _GEOMETRY_EPSILON:
                        resolved = up_owner

            if resolved is not None:
                owner[r][c] = resolved
                confirmed_merge = True
            else:
                # 2-c: 기하학적으로 확인 불가 -> 병합으로 단정하지 않고
                # 내용 없는 독립 빈 셀로 남긴다(한계, 모듈 docstring 참고).
                owner[r][c] = (r, c)
                owner_bbox[(r, c)] = None

    # 같은 소유자를 공유하는 격자 칸을 모아 span을 계산한다.
    spans: dict[tuple[int, int], list[int]] = {}  # owner -> [min_r, max_r, min_c, max_c]
    for r in range(n_rows):
        for c in range(n_cols):
            key = owner[r][c]
            assert key is not None
            if key not in spans:
                spans[key] = [r, r, c, c]
            else:
                entry = spans[key]
                entry[0] = min(entry[0], r)
                entry[1] = max(entry[1], r)
                entry[2] = min(entry[2], c)
                entry[3] = max(entry[3], c)

    cells: list[TableCellIR] = []
    for (or_, oc), (min_r, max_r, min_c, max_c) in sorted(spans.items()):
        text = grid_text[or_][oc]
        cells.append(
            TableCellIR(
                row_span=max_r - min_r + 1,
                col_span=max_c - min_c + 1,
                text=text if text is not None else "",
            )
        )

    return TableBlockIR(
        bbox=bbox,
        rows=n_rows,
        cols=n_cols,
        cells=cells,
        has_merged_cells=confirmed_merge,
    )
