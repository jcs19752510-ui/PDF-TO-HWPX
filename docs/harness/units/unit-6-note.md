# unit-6 구현 노트 — PDF 표(TableBlockIR) → HWPX 표(hp:tbl) 변환 (05-unit-developer)

- 커버 REQ-ID: REQ-004 (PDF 표 구조 인식 → HWPX 표 객체 변환, 셀 병합은 best-effort)
- 소속: Feature A(코어 변환 파이프라인)
- 속도 트랙: **L3(일반)** — 오케스트레이터로부터 별도 트랙 지정 없어 기본값 적용.
- 선행 단위(모두 완료, PASS): unit-3(`pdf_reader/table_recognizer.py`, `TableBlockIR`/`TableCellIR` 생산), unit-4(`hwpx_kernel/schema.py`의 `table_cell_to_cell_fragment`, `fragment_to_bytes` 등 계약 함수)
- **병렬 웨이브 호출임**: 이 호출과 동시에 unit-5(`hwpx_writer/paragraph_builder.py`), unit-7(`hwpx_writer/image_embedder.py`)가 각각 별도의 05-unit-developer 호출로 동시 실행 중이었다(파일 범위 완전 분리로 충돌 없음).
- 확정 파일 범위: **`pdf_to_hwpx/hwpx_writer/table_builder.py`(신규) 단일 파일만** 수정함. `pdf_reader/ir.py`, `pdf_reader/table_recognizer.py`, `hwpx_kernel/schema.py`, `hwpx_kernel/container.py`는 읽기 전용으로 import만 하고 전혀 수정하지 않았다.
- 선행 문서: `docs/harness/03-system-design.md`(v5, PASS — v4 §1-2/§3-1이 이 unit 범위에서는 그대로 유효, v5는 웹서비스 계층만 개정), `docs/harness/units/unit-3-note.md`(§1-2/§1-4, 병합 best-effort 휴리스틱과 `has_merged_cells` 미탐 가능성), `docs/harness/units/unit-4-note.md`(§2-2, `table_block_to_table_fragment`가 단순 divmod 가정을 쓴다는 한계와 "unit-6이 직접 (row, col)을 계산해 넘기라"는 안내), `pdf_to_hwpx/pdf_reader/ir.py`, `pdf_to_hwpx/hwpx_kernel/schema.py`

---

## 1. 구현 범위

### 1-1. 공개 함수

```python
def table_block_to_fragment(
    block: TableBlockIR,
    *,
    char_shape_id: str = "0",
    para_shape_id: str = "0",
) -> etree._Element: ...

def table_blocks_to_fragments(
    blocks: list[TableBlockIR],
    *,
    char_shape_id: str = "0",
    para_shape_id: str = "0",
) -> list[etree._Element]: ...
```

- `table_block_to_fragment`: `TableBlockIR` 1개를 `<hp:tbl>` 프래그먼트(lxml `etree._Element`)로 변환.
- `table_blocks_to_fragments`: `PageIR.table_blocks`(리스트) 전체를 `<hp:tbl>` 프래그먼트 리스트로 변환하는 편의 함수. orchestrator(unit-8)가 페이지의 표 블록 전체를 한 번에 넘길 수 있게 했다.
- 내부 헬퍼 `_resolve_cell_positions(block) -> list[tuple[int, int]]`: 이 unit의 핵심 로직(아래 1-2).

### 1-2. 핵심 로직 — 병합 셀의 실제 그리드 좌표 복원

**문제**: unit-4의 `hwpx_kernel.schema.table_block_to_table_fragment`(편의 함수)는 `block.cells`가 병합 포함 `rows*cols` 그리드를 행 우선(row-major) 순서로 빠짐없이 채운다고 가정하고 `divmod(idx, cols)`로 좌표를 추정한다. 그러나 unit-3이 실제로 만드는 `cells`는 병합이 있으면 `rows*cols`보다 항목 수가 적다(unit-3-note.md §1-4) — 이 가정이 병합 표에서 깨진다.

**해결**: `_resolve_cell_positions`가 격자를 좌상단→우하단(행 우선)으로 훑으며, 아직 어떤 셀도 점유하지 않은 첫 칸을 다음 `cells` 항목의 시작 좌표로 배정하고, 그 셀의 `row_span`/`col_span`만큼 칸을 점유 처리한다. 이 순서는 unit-3의 `table_recognizer.py`가 `cells`를 만드는 순서(`sorted(spans.items())`, 각 병합 그룹의 좌상단 좌표 기준 오름차순)와 정확히 대응하므로, 항상 정확한 `(row, col)`을 복원한다.

계산된 좌표는 `hwpx_kernel.schema.table_cell_to_cell_fragment(cell, row=..., col=...)`에 셀별로 직접 넘겨 `<hp:tc>`를 만들고, 시작 행이 같은 셀들을 모아 `<hp:tr>`로 묶는다(unit-4 편의 함수와 동일한 tr 그룹핑 관례 — "셀이 시작하는 행"의 `<hp:tr>`에 속함).

### 1-3. `has_merged_cells` 플래그에 분기하지 않기로 한 결정 (요청받은 근거 명시)

unit-3의 병합 감지는 best-effort이며 `has_merged_cells=False`는 "병합이 없음이 확정"이 아니라 "확정된 병합을 찾지 못했다"는 보수적 판정이다(unit-3-note.md §1-2, 미탐(false negative) 가능성 명시됨). 만약 `_resolve_cell_positions`를 "`has_merged_cells=False`면 단순 divmod, `True`면 정밀 계산"으로 분기했다면, 미탐 상황(실제로는 병합이 있는데 플래그가 `False`)에서 잘못된 경로를 탈 위험이 있었다.

`_resolve_cell_positions`는 플래그를 전혀 참조하지 않고 `row_span`/`col_span`만으로 그리드를 채워나간다 — 병합이 있든 없든(플래그 값과 무관하게) 항상 같은 코드 경로로 정확한 좌표가 나온다. 병합이 실제로 없는 표(`row_span=col_span=1`이 `rows*cols`개)에서는 이 알고리즘이 자연스럽게 divmod와 동일한 결과를 낸다(로컬 검증 1번 케이스로 확인). 따라서 **이 모듈은 `has_merged_cells`를 좌표 계산에 전혀 쓰지 않는다** — `<hp:tbl hasMergedCells="1">` 표시 속성 부착 용도로만 참조한다(unit-8/quality_report(unit-14)가 REQ-004 best-effort 경고 근거로 쓰도록, unit-4 편의 함수와 동일한 관례).

### 1-4. 입력 검증 (경계 방어)

`_resolve_cell_positions`는 그리드 채움이 끝난 뒤 (a) 소비한 셀 개수가 `len(block.cells)`와 일치하는지, (b) 그리드 전체 칸이 점유 완료됐는지를 모두 확인하고, 하나라도 어긋나면 `ValueError`를 던진다. `TableBlockIR`이 unit-3이 만든 정상적인 값이라면 항상 통과하지만, 이 함수는 "unit-3의 계약을 신뢰는 하되 방어적으로 검증"하는 시스템 경계(내부 unit 간 계약이라도 입력 무결성 확인은 필요하다고 판단)로 넣었다. 로컬 검증 5번 케이스(칸 수가 부족한 손상된 IR)로 실제 발생을 확인했다.

### 1-5. bbox(배치) 처리

`TableBlockIR.bbox`(pdfplumber 좌표계, pt)는 unit-5(`paragraph_builder.py`)와 **동일한 판단 기준**(이 모듈은 순수 변환 라이브러리이고 상태를 갖지 않음)으로 처리했다 — 실제 절대/상대 배치 방식은 확정하지 않고, `hwpx_kernel.schema.text_block_to_paragraph_fragment`가 `<hp:p>`에 붙이는 것과 동일한 관례로 `<hp:tbl>`에 참고용 `bboxPt`("x0,y0,x1,y1", pt 단위 문자열) 속성만 부착했다. 실제 세로 위치 정밀화(REQ-008 6-6)는 unit-8(orchestrator)의 책임으로 남겨둔다.

---

## 2. 설계서 대비 편차

없음(구조적 편차 없음). 03 설계서는 `hwpx_writer/table_builder.py`(unit-6)의 파일 범위와 "표 프래그먼트 생성" 역할만 정의하고, 병합 셀 좌표 계산의 구체 알고리즘까지는 규정하지 않았다 — 이는 단순 미규정(설계서가 세부 구현을 위임한 부분)이며, unit-3-note.md/unit-4-note.md가 이미 "unit-6이 직접 계산해야 한다"는 방향을 명시해 두었으므로 규칙 A 질문 대상은 아니라고 판단했다(두 가지 이상의 구현 방법이 갈리는 모호함이 아니라, 명확히 위임된 구현 세부사항).

---

## 3. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`)이 **없음을 재확인**했다(`pyproject.toml`, 리포지토리 루트 — unit-0/1/2/3/4-note.md와 동일 결론).
- `python -m py_compile pdf_to_hwpx/hwpx_writer/table_builder.py` — **컴파일 성공**.
- 이 unit이 수정한 파일은 `table_builder.py` 1개뿐이며, 이 파일 단독으로 컴파일 검증했다(병렬 호출 규칙 준수). 동시 실행 중이던 unit-5/7의 미완성 코드로 인한 실행 실패는 없었다(이 파일이 그쪽 파일을 import하지 않으므로 영향 없음).
- 신규 외부 의존성 없음(`lxml`은 unit-0이 이미 `pyproject.toml`에 등록해 둔 기존 의존성을 import만 함, 매니페스트 미접촉).

## 4. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 설계서상 unit-6 파일 범위(`hwpx_writer/table_builder.py`)와 정확히 일치. unit-3/unit-4가 이미 명시한 "병합 셀 정밀 계산은 unit-6 책임" 방향을 그대로 구현.
- [x] 에러 처리가 누락된 경로가 없는가 — `_resolve_cell_positions`가 입력 IR 불일치를 감지하면 `ValueError`를 명시적으로 던진다(조용히 삼키는 코드 없음). 이 함수들은 예외를 잡지 않는다(잡을 필요가 있는 외부 I/O나 서드파티 예외가 없음 — 순수 변환 로직).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 최종 사용자 입력을 직접 받지 않지만(내부 unit-3→unit-6 계약), 위 1-4절과 같이 그리드 무결성(셀 개수·점유 완료 여부)을 방어적으로 검증한다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성이 있는가 — 없음(신규 패키지 추가 없음, `pyproject.toml` 미수정).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `hwpx_writer/table_builder.py` 1개 파일만 신규 생성. `ir.py`/`table_recognizer.py`/`schema.py`/`container.py`는 import만 하고 전혀 수정하지 않았다. `hwpx_writer/__init__.py`의 "아직 생성되지 않음" docstring도 이 unit 파일 범위 밖이라 건드리지 않았다(참고 — unit-4-note.md §3의 `hwpx_kernel/__init__.py`와 동일 성격의 stale docstring, 오케스트레이터 후속 정리 필요).

---

## 5. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

전용 가상환경 `.harness-tmp/venv_05_unit6`(다른 병렬 unit의 venv와 충돌 방지)에서 `pip install -e ".[dev]"` 후, 스크래치패드에 검증 스크립트를 작성해 실행(리포지토리에는 남기지 않음, 확인 후 venv도 삭제함):

1. **병합 없는 2x2 표**: `positions == [(0,0),(0,1),(1,0),(1,1)]`(divmod와 동일 결과), `<hp:tr>` 2개·`<hp:tc>` 4개 생성, `hasMergedCells` 속성 없음. `lxml.etree.fromstring()`으로 재파싱해 well-formed 확인.
2. **가로 병합 표**(2x2, 0행이 `col_span=2`인 셀 1개 + 1행 2개): `positions == [(0,0),(1,0),(1,1)]`, 첫 `<hp:tc>`가 `rowAddr="0" colAddr="0" colSpan="2"`로 정확히 배치됨, `hasMergedCells="1"`. well-formed 확인.
3. **세로 병합 표**(2x2, 0열이 `row_span=2`인 셀 1개 + 나머지 2개): `positions == [(0,0),(0,1),(1,1)]`, 첫 `<hp:tc>`가 `rowSpan="2"`로 정확히 배치됨(1행에는 해당 열 `<hp:tc>`가 생성되지 않음 — 병합으로 덮인 칸이므로 정상). well-formed 확인.
4. `table_blocks_to_fragments([plain, hmerge])` 호출 시 프래그먼트 2개 반환 확인.
5. **경계 검증**: `rows=2, cols=2`인데 `cells`가 1개(1x1)뿐인 손상된 `TableBlockIR`을 넣으면 `ValueError`가 실제로 발생함을 확인(1-4절 방어 로직 동작 확인).

5가지 모두 기대한 결과와 일치함을 확인했다.

**명시적으로 하지 않은 것**: 실제 한글(한컴오피스)에서 이 `<hp:tbl>` 프래그먼트가 포함된 문서가 열리는지는 unit-4 단계부터 이어지는 DEC-017 리스크(개발 환경에 한글 미설치)로 인해 검증 불가능하다. `hp:tbl`/`hp:tr`/`hp:tc`의 정확한 속성 이름·병합 표현 방식(`rowAddr`/`colAddr`/`rowSpan`/`colSpan`)은 unit-4가 이미 "실제 OWPML 스펙 원문 대조 못함, 불확실성 가장 큼"이라 명시한 부분을 그대로 재사용한 것이며, 이 unit은 그 태그/속성 이름 자체를 새로 만들지 않았다(unit-4 계약을 그대로 소비).

---

## 6. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 동작 (병합 없음)
1. 병합 없는 표(모든 `TableCellIR.row_span == col_span == 1`, `cells` 개수 == `rows * cols`)에 대해 `table_block_to_fragment(block)`이 `<hp:tbl>` 1개를 반환하고, `rowCnt`/`colCnt` 속성이 `block.rows`/`block.cols`와 일치한다.
2. `<hp:tr>` 개수가 `block.rows`와 같고, 전체 `<hp:tc>` 개수가 `block.rows * block.cols`와 같다.
3. 각 `<hp:tc>`의 `rowAddr`/`colAddr`가 행 우선 순서(0,0), (0,1), ..., (rows-1, cols-1)로 정확히 매겨진다.
4. `block.has_merged_cells == False`이면 반환된 `<hp:tbl>`에 `hasMergedCells` 속성이 없다.

### AC-2. 가로 병합
1. 특정 행의 인접 열이 병합된(`col_span >= 2`) `TableCellIR`이 포함된 `TableBlockIR`에 대해, 그 셀의 `<hp:tc>`가 정확한 시작 `rowAddr`/`colAddr`와 `colSpan` 속성을 갖는다.
2. 병합된 셀 이후 칸들(병합에 덮인 칸)에는 별도 `<hp:tc>`가 생성되지 않는다(총 `<hp:tc>` 개수가 `len(block.cells)`와 같다).
3. `block.has_merged_cells == True`이면 `<hp:tbl hasMergedCells="1">`이 부착된다.

### AC-3. 세로 병합
1. 특정 열의 인접 행이 병합된(`row_span >= 2`) `TableCellIR`에 대해, 그 셀의 `<hp:tc>`가 정확한 `rowSpan` 속성과 시작 `(rowAddr, colAddr)`를 갖고, 시작 행의 `<hp:tr>`에 소속된다(병합으로 덮인 하위 행에는 해당 열의 `<hp:tc>`가 생성되지 않는다).

### AC-4. 리스트 헬퍼
1. `table_blocks_to_fragments([block1, block2, ...])`가 입력 리스트와 동일한 개수·순서의 `<hp:tbl>` 프래그먼트 리스트를 반환한다.
2. 빈 리스트를 넣으면 빈 리스트를 반환한다(예외 없음).

### AC-5. 경계/방어 검증
1. `TableBlockIR.cells`의 총 점유 칸 수(각 셀의 `row_span * col_span` 합, 단 겹치지 않는 정상 배치 기준)가 `rows * cols`와 맞지 않는 손상된 입력을 넣으면 `table_block_to_fragment`가 `ValueError`를 던진다(조용히 잘못된 XML을 만들지 않는다).

### AC-6. XML 구조 (모든 케이스 공통)
1. 반환된 모든 프래그먼트가 `lxml.etree.tostring()` → `etree.fromstring()` 왕복에서 예외 없이 well-formed XML로 파싱된다.
2. `<hp:tbl>`의 로컬 이름은 `tbl`이고 `hwpx_kernel.container.NAMESPACES["hp"]`로 완전한정된다. 자식 `<hp:tr>` → `<hp:tc>` → `<hp:subList>` → `<hp:p>` → `<hp:run>` → `<hp:t>` 구조가 `hwpx_kernel.schema.table_cell_to_cell_fragment`의 계약과 동일하다(unit-4-test.md AC-2를 그대로 재사용/확장 검증 가능).

### 알려진 한계 (결함 아님, 06단계가 인지해야 함)
- 이 unit은 unit-3이 만든 `TableBlockIR`을 신뢰하는 것을 전제로 하며, `has_merged_cells=False`가 실제로는 미탐일 수 있다는 unit-3의 알려진 한계(unit-3-note.md §1-2/AC-5)를 그대로 승계한다 — 다만 1-3절에서 설명했듯 이 unit의 좌표 계산 자체는 그 플래그와 무관하게 항상 정확하므로, "미탐"이 이 unit 단계에서 추가 오류를 만들지는 않는다(unit-3이 만든 `row_span`/`col_span` 값 자체가 틀렸을 경우에만 이 unit도 영향받는다).
- 실제 한글(한컴오피스) 호환성은 unit-4/unit-5/unit-7과 동일하게 미검증(DEC-017 리스크 승계).

---

## 7. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

### traceability.md — REQ-004 행

| 컬럼 | 현재값 | 요청값 |
|---|---|---|
| 구현 상태 | `Partially Implemented (unit-3: Verified — 06단계 PASS, ... unit-6: Not Started)` | `Partially Implemented (unit-3: Verified — 06단계 PASS, pdf_reader/table_recognizer.py, 결함 0건. unit-6: Implemented — hwpx_writer/table_builder.py, 05단계 완료, 06단계 단위테스트 대기)` |
| 비고 | (기존 문구 유지) | 기존 문구에 다음 추가 권장: `unit-6 구현 상세/인수조건: docs/harness/units/unit-6-note.md — table_recognizer가 만든 row_span/col_span만으로 그리드 좌표를 복원하며 has_merged_cells 플래그에는 분기하지 않음(미탐 가능성 대응, note §1-3 근거). 실제 한글 뷰어 호환성은 unit-4/5/7과 동일하게 미검증(DEC-017 승계).` |

### decisions.md
별도 신규 결정(DEC) 추가 요청 없음 — 이번 구현은 unit-3/unit-4가 이미 문서화한 한계·안내를 그대로 따른 구현 세부사항 결정(1-3절)이며, 새로운 비가역적 프로젝트 전체 결정은 발생하지 않았다.

### 기타 참고 (강제 아님)
- `pdf_to_hwpx/hwpx_writer/__init__.py`의 stale docstring("아직 생성되지 않았다")이 이제 사실과 다르다 — 이 unit 파일 범위 밖이라 직접 수정하지 않았다(unit-4-note.md §3의 동일 패턴 참고). unit-5/unit-7 완료 후 또는 별도 정리 단위에서 갱신 권장.
