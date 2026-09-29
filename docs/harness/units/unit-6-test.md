# 단위 테스트 결과서 — unit-6 `pdf_to_hwpx/hwpx_writer/table_builder.py` (06-unit-tester)

> 배경: 이 unit-6의 06단계는 최초 착수 후 사용자의 긴급 중단 지시로 약 36초 만에
> 강제 종료되어 사실상 진행이 거의 없었다(코드/테스트 산출물 없음, `.harness-tmp/`에도
> 잔여물 없음을 착수 시점에 확인). 본 문서는 처음부터 새로 완전하게 수행한 결과다.

## 1. 개요
- 테스트 대상: 작업 단위 unit-6 — `pdf_to_hwpx/hwpx_writer/table_builder.py`의 공개 함수
  `table_block_to_fragment`, `table_blocks_to_fragments`, 내부 핵심 헬퍼
  `_resolve_cell_positions` (REQ-004, "PDF 표 구조 인식 → HWPX 표 객체 변환, 셀 병합은
  best-effort")
- 테스트 유형: 단위
- 적용 Tier: **Standard** (`docs/harness/decisions.md` DEC-001 — 06·07 병합 없음, 규칙 B
  원문대로 최소 2회 검증 적용)
- 적용 속도 트랙: **L3(일반)** (`docs/harness/units/unit-6-note.md` 서두 — 오케스트레이터로부터
  별도 지정 없어 기본값. 전 섹션 정식 작성 + 규칙 B 2회 검증 원문 적용)
- 병렬 실행 정보: 단독 실행. (참고: unit-6의 **05단계**는 unit-5/unit-7과 병렬 웨이브로
  진행되었으나, 이 **06단계** 호출 자체는 오케스트레이터로부터 "병렬 웨이브" 지시 없이
  단일 호출로 받았다. 다만 실행 도중 `.harness-tmp/`를 관찰한 결과 동시에 unit-5의
  06단계도 별도로 진행 중이었음을 확인했다 — 7절 Teardown 참고. 이 문서의 판정은
  unit-6 단독 범위로 한정한다.)
- 테스트 목적: unit-6의 인수 조건(AC-1~AC-6) 전항 충족 여부를 실제 실행으로 증명하고,
  05단계 게이트(정적분석/코드리뷰) 통과 여부를 재확인하며, 정상/경계/예외 입력 전반에서
  결함을 찾아낸다.
- 관련 산출물: `docs/harness/units/unit-6-note.md`(인수조건 §6), `docs/harness/03-system-design.md`
  v5(§1-2/§1-3/§3-1, 이 unit 범위에서는 v4 내용 유효), `pdf_to_hwpx/hwpx_kernel/schema.py`
  (unit-4 계약, `table_cell_to_cell_fragment`), `pdf_to_hwpx/pdf_reader/table_recognizer.py`
  (unit-3, `TableBlockIR.cells` 생성 순서 근거), `pdf_to_hwpx/pdf_reader/ir.py`
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - `table_block_to_fragment`, `table_blocks_to_fragments`, `_resolve_cell_positions`의
    전체 로직(정상 N행 M열 표, 가로/세로/복합 병합, 빈 셀, 빈 표, 손상된 IR에 대한
    방어적 `ValueError`, XML 구조/네임스페이스/well-formed 여부)
  - `hwpx_kernel.schema.table_cell_to_cell_fragment`와의 계약(호출 시 넘기는
    `row`/`col`/`char_shape_id`/`para_shape_id` 인자, 반환된 `<hp:tc>` 하위 구조)이
    이 unit이 기대하는 그대로 동작하는지 — 단, `table_cell_to_cell_fragment` 자체의
    내부 구현 정합성은 unit-4-test.md(AC-2)가 이미 검증한 범위이므로 여기서는 "unit-6이
    그 계약을 올바르게 소비하는지"만 재확인한다(중복 검증 아님).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 실제 한글(한컴오피스)에서 결과 문서가 열리는지 — 개발 환경에 한글 미설치로
    검증 불가능(DEC-017, unit-4/unit-6-note.md가 이미 명시한 승계 리스크). 태그/속성
    이름 자체가 실제 OWPML 스펙과 일치하는지도 동일 사유로 범위 밖.
  - `table_block_to_table_fragment`(schema.py의 divmod 기반 "간단 편의 함수") 자체의
    동작 검증 — 이미 `tests/hwpx_kernel/test_schema.py`(unit-4-test.md)가 검증했고,
    unit-6은 그 함수를 아예 쓰지 않는다(note §1-2, "왜 이 함수를 쓰지 않는가").
  - unit-3(`table_recognizer.py`)가 실제 PDF에서 만들어내는 `TableBlockIR`의 정확성 —
    unit-3-test.md 범위(이미 PASS). 이 unit은 unit-3의 계약을 신뢰하고 소비하는 쪽만
    검증한다(다만 "신뢰하되 방어적으로 검증"하는 `_resolve_cell_positions`의 방어
    로직 자체는 In-Scope).
  - unit-8(orchestrator)이 `bboxPt` 속성을 실제로 어떻게 활용해 세로 위치를 정밀화할지 —
    unit-8 책임(note §1-5), 이 unit은 속성을 올바른 형식으로 부착하는지까지만 확인.
  - 뮤테이션 테스트 도구(mutmut) 실행 — 시도했으나 mutmut 3.8.0이 네이티브 Windows를
    지원하지 않음(`mutmut` 실행 시 "To run mutmut on Windows, please use the WSL" 메시지
    확인, 이 환경에 WSL 없음). 5절에 대체 근거(수동 뮤테이션 추론 + 정확값 단언 위주
    설계)를 기록한다.

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.13.15, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.16.2,
  lxml 6.1.3 — 전부 이 unit 전용 격리 가상환경(`.harness-tmp/venv_06_unit6/`)에 설치.
  `pdf-to-hwpx` 패키지는 `pip install -e ".[dev]"`로 편집 가능 설치, 추가로
  `pytest-cov`·`reportlab`(테스트 루트 `tests/conftest.py`가 다른 unit의 PDF 픽스처
  생성에 사용하므로 전체 테스트 스위트 수집 시 필요, 공유 conftest 의존성)을 설치.
- 테스트 데이터: 실제 PDF 파일 불필요 — `TableBlockIR`/`TableCellIR`(순수 dataclass)를
  테스트 코드 안에서 직접 구성한 인메모리 픽스처만 사용(`make_cell()` 헬퍼).
- 전제 조건: unit-4(`schema.py`)·unit-3(`table_recognizer.py`)가 이미 06단계 PASS
  상태(traceability.md REQ-004/008 행 확인)이고, unit-6의 05단계 산출물
  (`pdf_to_hwpx/hwpx_writer/table_builder.py`)이 코드 diff로 존재함을 확인 후 착수.

## 4. 테스트 케이스 및 결과

전체 32개 테스트 케이스, 파일: `tests/hwpx_writer/test_table_builder.py`.
실행 결과: **32/32 PASS** (`pytest tests/hwpx_writer/test_table_builder.py -v` 전체 로그
기준, 아래 표는 인수조건(AC) 및 위험 케이스별 요약).

| ID | 시나리오 (대응 AC) | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----|----|----|----|----|----|----|
| TC-R1 | `_resolve_cell_positions` 병합 없음 2x3 (AC-1 기반) | 6개 1x1 셀, rows=2 cols=3 | `_resolve_cell_positions(block)` 호출 | `[(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)]` (divmod와 동일) | 동일 | Pass | `test_resolve_positions_no_merge_2x3_matches_row_major_divmod` |
| TC-R2 | `_resolve_cell_positions` 가로 병합 (AC-2 기반) | note §5 케이스2와 동일 입력 | 위와 동일 | `[(0,0),(1,0),(1,1)]` | 동일 | Pass | `test_resolve_positions_horizontal_merge_matches_note_example` |
| TC-R3 | `_resolve_cell_positions` 세로 병합 (AC-3 기반) | note §5 케이스3과 동일 입력 | 위와 동일 | `[(0,0),(0,1),(1,1)]` | 동일 | Pass | `test_resolve_positions_vertical_merge_matches_note_example` |
| TC-R4 | `_resolve_cell_positions` 복합(3x3 좌상단 2x2 병합) — **위험 케이스, 범위 확장** | 3x3, 좌상단 2x2 병합 셀 1개+단일셀 5개 | 위와 동일 | `[(0,0),(0,2),(1,2),(2,0),(2,1),(2,2)]` | 동일 | Pass | note의 단순 h/v 예시보다 복잡한 배치에서도 알고리즘 검증 |
| TC-R5 | `_resolve_cell_positions` 1x1 경계값 | 1행 1열, 셀 1개 | 위와 동일 | `[(0,0)]` | 동일 | Pass | 최소 표 경계값 |
| TC-R6 | `_resolve_cell_positions` 0x0 빈 표 — **위험 케이스** | rows=0, cols=0, cells=[] | 위와 동일 | `[]`, 예외 없음 | 동일 | Pass | 빈 입력 방어 확인 |
| TC-AC5-1 | AC-5-1: 셀 부족(1개/필요 4개) | rows=2 cols=2, cells 1개 | `_resolve_cell_positions(block)` | `ValueError` (메시지에 `rows=2, cols=2` 포함) | 동일 | Pass | `test_ac5_resolve_positions_insufficient_cells_raises_value_error` |
| TC-AC5-2 | AC-5-1을 공개 API 경로로 재확인 | 위와 동일 입력 | `table_block_to_fragment(block)` | `ValueError` | 동일 | Pass | `test_ac5_table_block_to_fragment_insufficient_cells_raises_value_error` — 조용히 잘못된 XML을 만들지 않음을 공개 API 레벨에서 재확인 |
| TC-AC5-3 | 셀 초과(2개/필요 1개) — **위험 케이스, 범위 확장** | rows=1 cols=1, cells 2개 | `_resolve_cell_positions(block)` | `ValueError` | 동일 | Pass | AC-5 원문은 "부족" 방향만 언급하나 "초과" 방향도 실제로 방어됨을 확인 |
| TC-AC5-4 | 셀 0개인데 grid는 비어있지 않음(null에 준하는 입력) — **위험 케이스** | rows=2 cols=2, cells=[] | 위와 동일 | `ValueError` | 동일 | Pass | 명백히 위험한 빈 입력 |
| TC-AC5-5 | row_span=0 퇴화 셀 — **위험 케이스(내부검증 2차 추가)** | rows=1 cols=1, 셀의 row_span=0 | 위와 동일 | `ValueError`(그리드 미점유 감지) | 동일 | Pass | 2차 검증에서 "span=0/음수류 손상 입력"을 놓쳤음을 인지하고 추가, 실제로 방어됨을 확인 |
| TC-AC1-1 | AC-1-1: 2x3 표 기본 반환값 | 6개 1x1 셀 | `table_block_to_fragment(block)` | `<hp:tbl>` 1개, `rowCnt="2"`, `colCnt="3"` | 동일 | Pass | |
| TC-AC1-2 | AC-1-2: tr/tc 개수 | 위와 동일 | 위와 동일 | `<hp:tr>` 2개, 전체 `<hp:tc>` 6개 | 동일 | Pass | |
| TC-AC1-3 | AC-1-3: rowAddr/colAddr 행우선 순서 | 위와 동일 | 위와 동일 | (0,0)..(1,2) 순서대로, 텍스트도 c0..c5 순서 | 동일 | Pass | 좌표뿐 아니라 "어떤 셀이 어디로 갔는지"까지 검증 |
| TC-AC1-4 | AC-1-4: 병합 없음 → `hasMergedCells` 속성 없음 | `has_merged_cells=False` | 위와 동일 | 속성 `None` | 동일 | Pass | |
| TC-AC2-1 | AC-2-1: 가로 병합 시작 좌표/colSpan | 2x2, row0 col_span=2 | `table_block_to_fragment(block)` | 첫 tc: `rowAddr=0,colAddr=0,colSpan=2` | 동일 | Pass | |
| TC-AC2-2 | AC-2-2: 병합 덮인 칸은 별도 tc 없음, 총 tc==len(cells) | 위와 동일 | 위와 동일 | tc 3개(cells 3개와 일치), 텍스트 순서 A,B,C | 동일 | Pass | |
| TC-AC2-3 | AC-2-3: `hasMergedCells="1"` | `has_merged_cells=True` | 위와 동일 | 속성 `"1"` | 동일 | Pass | |
| TC-AC3-1 | AC-3-1: 세로 병합 rowSpan/시작좌표/tr 그룹핑 | 2x2, col0 row_span=2 | `table_block_to_fragment(block)` | row0 tr에 A(rowSpan=2),B / row1 tr에 C만(덮인 칸은 tc 없음) | 동일 | Pass | |
| TC-AC4-1 | AC-4-1: 리스트 헬퍼 개수/순서 | block1(1x1), block2(1x2) | `table_blocks_to_fragments([block1,block2])` | 길이 2, colCnt 순서대로 "1","2", 내용도 순서 보존 | 동일 | Pass | |
| TC-AC4-2 | AC-4-2: 빈 리스트 | `[]` | 위와 동일 | `[]` 반환, 예외 없음 | 동일 | Pass | |
| TC-AC4-3 | 리스트 헬퍼의 커스텀 shape id 전파 — **범위 확장** | char_shape_id="9", para_shape_id="8" | `table_blocks_to_fragments([block], char_shape_id=..., para_shape_id=...)` | tc 내부 p/run에 반영됨 | 동일 | Pass | kwargs 전달 경로 검증 |
| TC-AC6-1a/b/c | AC-6-1: plain/hmerge/vmerge 각각 well-formed round-trip | 3가지 파라미터화 | `tostring`→`fromstring` | 예외 없이 재파싱, 태그 동일 | 동일 | Pass | `pytest.mark.parametrize` |
| TC-AC6-2 | AC-6-2: 네임스페이스/자식 구조 계약 | 1x1 표 | `table_block_to_fragment` | `tbl` localname/네임스페이스 정확, `tr→tc→subList→p→run→t` 구조 일치 | 동일 | Pass | |
| TC-RISK-1 | 빈 표(0행0열) — **위험 케이스** | rows=0,cols=0,cells=[] | `table_block_to_fragment` | 예외 없이 빈 `<hp:tbl>` | 동일 | Pass | schema.py의 동일 성격 경계값과 대응 |
| TC-RISK-2 | 빈 셀 텍스트("") — **위험 케이스(명시 요청)** | 셀 텍스트="" | 위와 동일 | 예외 없음, `<hp:t>` 텍스트 None 또는 "" | 동일 | Pass | |
| TC-RISK-3 | 3x3 좌상단 2x2 병합 — fragment 레벨(tr/tc 그룹핑)까지 — **불규칙 구조** | 위 TC-R4와 동일 입력 | `table_block_to_fragment` | tr 3개, row0=[A,B] row1=[C] row2=[D,E,F], A의 rowSpan=colSpan=2 | 동일 | Pass | `_resolve_cell_positions` 정확성을 fragment 단까지 end-to-end로 재확인 |
| TC-RISK-4 | bboxPt 속성 포맷 | bbox=(1.5,2.25,30.0,40.125) | 위와 동일 | `"1.50,2.25,30.00,40.12"` | 동일 | Pass | schema.py 관례(소수 2자리, 콤마구분)와 일치 확인 |
| TC-RISK-5 | 커스텀 char/para shape id 전파(단일 블록) | char_shape_id="5",para_shape_id="4" | `table_block_to_fragment(block, char_shape_id=..., para_shape_id=...)` | p/run에 반영 | 동일 | Pass | |
| TC-RISK-6 | **oversized col_span(그리드 경계 초과)** — 결함 발견 케이스 | rows=2,cols=2, 한 셀의 col_span=5 | `table_block_to_fragment(block)` | (기대: 방어적으로 거부되거나 clamp됨) | **`ValueError` 없이 `colSpan="5"` (colCnt="2"보다 큼)가 그대로 XML에 새어나감** | Pass(현재 동작 고정, but 결함 기록) | **DEF-001** — 6절 참고. 테스트 자체는 "현재 동작"을 정확히 단언해 통과하지만, 이 동작 자체가 결함이다 |

> 표에 없는 나머지 항목(각 테스트 함수명)은 위 시나리오들의 세부 assertion이며,
> 전체 32개 함수명·1:1 pass 여부는 5절의 pytest 원본 로그로 재현 가능하다.

## 5. 커버리지
- 커버리지 지표: `pytest --cov=pdf_to_hwpx.hwpx_writer.table_builder --cov-branch`
  결과 — **라인 커버리지 100%(50/50), 브랜치 커버리지 100%(22/22, 부분분기 0)**.
  ```
  Name                                       Stmts   Miss Branch BrPart  Cover   Missing
  --------------------------------------------------------------------------------------
  pdf_to_hwpx\hwpx_writer\table_builder.py      50      0     22      0   100%
  --------------------------------------------------------------------------------------
  TOTAL                                         50      0     22      0   100%
  32 passed
  ```
- 커버되지 않은 부분: 없음(라인/브랜치 모두 100%).
- 뮤테이션 테스트: `mutmut`(3.8.0)을 설치해 시도했으나 **"To run mutmut on Windows,
  please use the WSL."** 메시지로 네이티브 실행이 차단됨(이 환경에 WSL 미설치, 2절
  제외범위 참고). 대신 아래 수동 뮤테이션 추론으로 대체 근거를 남긴다:
  - `if occupied[r][c]: continue`를 반전(`if not occupied[r][c]`)하면 TC-R2/R3/R4/TC-AC2-*/TC-AC3-1이
    모두 정확한 `(row, col)` 튜플 시퀀스나 rowSpan/colSpan 값을 단언하므로 즉시 실패한다
    (단순 "개수만" 확인했다면 놓쳤을 뮤테이션).
  - `for rr in range(r, min(r + cell.row_span, rows))`의 `min`을 `max`로 바꾸면(경계
    클램프 제거) TC-R4/TC-RISK-3(3x3 복합 병합, 경계에 걸치지 않는 케이스라 이 경우는
    영향 없을 수 있음)보다는 TC-RISK-6(oversized col_span) 계열에서 `IndexError`로
    드러난다 — 별도 케이스로 이미 존재.
  - `cell_idx != n_cells or not fully_covered`의 `or`를 `and`로 바꾸면 TC-AC5-1(부족,
    fully_covered=False지만 cell_idx==n_cells인 케이스)이 `ValueError` 대신 정상
    반환을 시도해 즉시 실패한다 — AC-5 케이스가 이 정확한 뮤테이션을 잡아내도록
    의도적으로 설계됨(1차 검증에서 확인).
  - `tbl.set("hasMergedCells", "1")`을 호출하는 조건을 제거/반전하면 TC-AC1-4/TC-AC2-3이
    즉시 실패한다.
  - 결론: 정확한 값(개수만이 아니라 좌표 튜플 시퀀스, 속성 문자열 값)을 단언하는
    설계 덕분에 핵심 분기 대부분이 수동 추론으로도 뮤테이션에 취약하지 않음을
    확인했다. 다만 이는 도구 기반 정량 지표를 대체하지 못하므로, WSL이 확보되면
    `mutmut`로 정량 재검증을 권고한다(8절 리스크로 기록).

## 6. 결함(Defect) 목록

| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | `_resolve_cell_positions`의 방어 검증(1-4절, "소비한 셀 개수 일치 + 그리드 전체 점유 완료")이 "각 셀의 `row_span`/`col_span`이 선언된 `rows`/`cols` 경계를 넘지 않는지"는 검사하지 않는다. `rows=2,cols=2`인 표에서 한 셀의 `col_span=5`(그리드보다 훨씬 큼)를 넣으면, 점유 배열 마킹은 `min(c+col_span, cols)`로 클램프되어 "전체 점유 완료" 조건은 우연히 만족되므로 `ValueError`가 발생하지 않고, 결과 `<hp:tc>`에는 `colSpan="5"`가 그대로 노출되어 상위 `<hp:tbl colCnt="2">`와 내적으로 모순되는(그러나 well-formed한) XML이 생성된다. | `TableBlockIR(rows=2, cols=2, cells=[TableCellIR(row_span=1, col_span=5, text="A"), TableCellIR(1,1,"B"), TableCellIR(1,1,"C")], has_merged_cells=True)`로 `table_block_to_fragment()` 호출 → 예외 없이 반환되고 `colSpan="5"` 확인 (`test_risk_oversized_col_span_beyond_grid_bounds_is_not_rejected`) | **Low** | Open (Deferred) | 미조치. 사유: (1) 이 값은 "사소한 오탈자" 수정 범위를 넘는 로직 변경(별도 경계 검증 추가)이 필요해 06단계에서 직접 고치지 않는 것이 원칙에 맞음. (2) 상위 프로듀서(unit-3 `table_recognizer.py`)의 `col_span`/`row_span` 계산은 `max_c-min_c+1` 형태로 항상 `n_cols` 이내로 산출되므로, 정상 파이프라인에서는 이 입력이 실제로 발생하지 않는다(코드 직접 확인, `table_recognizer.py` `_build_table_block` 참고) — 순수 방어 계층의 이론적 한계이지 REQ-004 정상 경로 결함이 아니다. (3) 심각도가 Low라 규칙에 따라 FAIL 처리 대상이 아니다. **권고**: unit-8(orchestrator) 통합 시점 또는 향후 `table_builder.py` 리팩터링 시 `_resolve_cell_positions`에 "각 셀 span이 grid 경계를 넘지 않는지"를 추가 검증 조건으로 넣는 것을 권장(회귀 테스트 `test_risk_oversized_col_span_beyond_grid_bounds_is_not_rejected`가 이미 존재하므로, 수정 시 이 테스트의 기대값을 "ValueError 발생"으로 뒤집어야 함). |

- 그 외 결함: **없음**. 근거: AC-1~AC-6 전 항목(1:1 대응 테스트 32개 중 26개가 AC 직접
  대응, 나머지 6개는 명시적 위험 케이스)이 전부 PASS, 라인/브랜치 커버리지 100%,
  `pytest tests/ -q` 전체 스위트(379개, 다른 병렬 unit 포함) 회귀 없음(§7 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit6/` (이 unit 전용 격리 가상환경, `pip install -e ".[dev]" pytest-cov reportlab`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: **완료** — `.harness-tmp/venv_06_unit6/`를 재귀 삭제함(다른
  아티팩트는 건드리지 않음).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
  ```
  On branch PROD
  Changes not staged for commit:
    modified:   docs/harness/02-planning.md
    modified:   docs/harness/03-system-design.md
    modified:   docs/harness/04-ux-design.md
    modified:   docs/harness/decisions.md
    modified:   docs/harness/traceability.md
    modified:   docs/harness/verify-log_02-planning.md
    modified:   docs/harness/verify-log_03-system-design.md
    modified:   docs/harness/verify-log_04-ux-design.md
    modified:   pdf_to_hwpx/hwpx_kernel/container.py
    modified:   pdf_to_hwpx/pdf_reader/text_extractor.py
    modified:   pyproject.toml

  Untracked files:
    docs/harness/units/unit-1-note.md
    docs/harness/units/unit-1-test.md
    docs/harness/units/unit-2-note.md
    docs/harness/units/unit-2-test.md
    docs/harness/units/unit-3-note.md
    docs/harness/units/unit-3-test.md
    docs/harness/units/unit-4-note.md
    docs/harness/units/unit-4-test.md
    docs/harness/units/unit-5-note.md
    docs/harness/units/unit-6-note.md
    docs/harness/units/unit-7-note.md
    docs/harness/units/unit-7-test.md          # unit-7의 06단계(병렬로 동시 진행 중) 소유
    docs/harness/verify-log_unit-2-test.md
    docs/harness/verify-log_unit-4-test.md
    docs/harness/verify-log_unit-7-test.md     # unit-7 소유
    pdf_to_hwpx/hwpx_kernel/schema.py
    pdf_to_hwpx/hwpx_writer/image_embedder.py
    pdf_to_hwpx/hwpx_writer/paragraph_builder.py
    pdf_to_hwpx/hwpx_writer/table_builder.py   # unit-6 05단계 산출물(내가 만든 것 아님, 이미 존재)
    pdf_to_hwpx/pdf_reader/image_extractor.py
    pdf_to_hwpx/pdf_reader/table_recognizer.py
    tests/hwpx_kernel/                         # 하위에 test_container_bin_data.py 포함 — unit-7 소유
    tests/hwpx_writer/                         # 하위에 test_table_builder.py(이 unit이 신규 작성) +
                                                #   test_image_embedder.py/test_paragraph_builder.py(unit-5/7 소유)
    tests/pdf_reader/test_image_extractor.py
    tests/pdf_reader/test_table_recognizer.py
    tests/pdf_reader/test_text_extractor.py
  ```
- 병렬 실행이었다면: 이 06 호출 자체는 "병렬 웨이브" 지시 없이 단일 호출로 받았으나,
  실행 중 `.harness-tmp/`에 `venv_06_unit5/`·`cov_06_unit5/`가 동시에 나타난 것을 확인해
  **unit-5의 06단계가 이 세션과 동시에 별도로 진행 중**임을 인지했다. 이 문서가 소유·
  생성한 아티팩트는 `.harness-tmp/venv_06_unit6/` 하나뿐이며 이를 정리 후 재확인한 결과
  `.harness-tmp/`에는 unit-5 소유(`venv_06_unit5/`, `cov_06_unit5/`)만 남아 있음을
  확인했다(내 소유 잔여물 없음). `git status`의 `unit-7-test.md`·`verify-log_unit-7-test.md`·
  `tests/hwpx_kernel/`·`tests/hwpx_writer/test_image_embedder.py`·`test_paragraph_builder.py`는
  unit-5/unit-7의 06단계가 동시에 만든 산출물로 위 목록에 소유 주석을 표기했다.
  `pdf_to_hwpx/hwpx_writer/table_builder.py` 자체와 `unit-6-note.md`는 05단계가 이미
  만들어둔 이 unit의 산출물이며(내가 이번에 수정하지 않음), 내가 이번에 신규로 만든
  파일은 `tests/hwpx_writer/test_table_builder.py`와 이 결과서(`unit-6-test.md`)뿐이다.
  웨이브 종료 후 오케스트레이터의 전체 트리 점검(`harness-janitor.sh --check`, 전체
  `git status`)은 이 단위 테스트 범위 밖이라 여기서는 수행하지 않았다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음 (단, 착수 전 이전 세션의
  강제 중단 잔여물 유무를 `.harness-tmp/` 스캔으로 먼저 확인했고 잔여물이 없었음을
  확인한 뒤 시작했다 — 배경 문단 참고. 또한 실행 중 무관한 쉘 명령 오타로 인해 대기 중인
  파이썬 REPL 프로세스 2개가 남았는데, 이는 `.harness-tmp/`나 저장소 파일과 무관한 유휴
  프로세스이고 강제 종료 권한이 샌드박스 정책으로 거부되어 그대로 방치했다 — 파일
  시스템/git 상태에는 영향 없음을 확인했다.)
- **7절 확인 완료 — 8절 결론에서 PASS 판정 가능.**

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - 실제 한글(한컴오피스) 호환성 전면 미검증(DEC-017 승계, unit-4/5/6/7 공통).
  - DEF-001(6절): 그리드 경계를 넘는 손상된 `row_span`/`col_span` 입력에 대한 방어
    검증 공백. 정상 파이프라인(unit-3 산출물)에서는 발생하지 않음이 코드로 확인됐으나,
    향후 unit-3 로직이 바뀌거나 제3의 IR 생성 경로가 추가되면 재검토 필요.
  - 뮤테이션 테스트 정량화 미실시(WSL 부재, 5절). 수동 추론으로 핵심 분기의 견고성은
    확인했으나 도구 기반 정량 지표는 아니다.
  - unit-6이 만드는 프래그먼트가 실제 unit-8(orchestrator)의 섹션 조립 로직과 통합됐을 때
    (예: 여러 표가 한 섹션에 연속 배치될 때 `bboxPt` 활용 방식) 발생할 수 있는 문제는
    07/08단계 범위다.
- 후속 조치가 필요한 항목:
  - DEF-001 권고사항(6절)을 unit-8 통합 또는 차기 리팩터링 시 반영 검토.
  - WSL 확보 시 `mutmut`로 이 모듈의 뮤테이션 스코어를 정량 재검증 권고.
  - traceability.md REQ-004 행 갱신(§ 하단 "공유 문서 갱신 요청" 참고).

## 9. 결론 및 판정
- [x] **PASS** — 다음 단계(07단계, `feature-A-integration-test.md`) 진행 가능.
  - 근거: AC-1~AC-6 전 항목 1:1 테스트 존재 및 32/32 PASS, 라인·브랜치 커버리지 100%,
    발견된 결함(DEF-001)은 Low 심각도로 FAIL 기준(Critical/High)에 해당하지 않으며
    정상 파이프라인 경로에서는 재현 불가함을 코드로 확인, 05단계 게이트(정적분석/
    코드리뷰)도 재확인 완료(아래), 7절 Teardown 확인 완료.
  - 05단계 게이트 재확인: `unit-6-note.md` §3(게이트1)이 주장한 "lint/type-check 설정
    없음, `py_compile` 성공"을 이 06단계에서 `python -m py_compile
    pdf_to_hwpx/hwpx_writer/table_builder.py`로 재실행해 동일하게 성공을 확인했고,
    `pyproject.toml`에 ruff/flake8/mypy/pylint 설정이 없음을 재확인했다(§4 게이트2
    체크리스트는 소스 코드를 직접 읽고 각 항목을 대조해 타당함을 확인 — 범위 이탈 없음,
    신규 의존성 없음, 시크릿 없음, 에러 처리 누락 없음).

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 작성자 관점 자가 재검토 — AC-1~AC-6 전 항목이 테스트 케이스와
  1:1 대응됨을 표로 재확인, 05단계 게이트 재확인 완료, 전체 회귀(`pytest tests/ -q`,
  379개) 무손상 확인. 이 과정에서 `_resolve_cell_positions`의 경계 검증 로직을 직접
  코드로 따라가며 "oversized col_span" 케이스를 시험 삼아 실행해 DEF-001을 발견,
  결함 목록에 기록.
- 2차 검증 결과 요약: 독립 심사자 관점("이 테스트를 07에 넘겨도 되는가") 재검토 —
  1차가 놓친 경계 조건을 의심하던 중 "span=0/음수류 퇴화 입력"이 테스트되지 않았음을
  발견해 `test_ac5_zero_row_span_degenerate_cell_raises_value_error`를 추가하고 실제
  `ValueError`가 발생함을 실행으로 확인(이후 전체 재실행 32/32 PASS, 커버리지 100%
  유지 재확인). 그 외 엣지 케이스(빈 표, 빈 셀 텍스트, 리스트 헬퍼 개수/순서, 커스텀
  shape id 전파, XML 네임스페이스/구조)도 이미 1차 설계에 포함되어 있음을 재확인했고,
  추가로 놓친 항목은 발견되지 않았다.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-6-test.md`

## 11. 공유 문서 갱신 요청 (오케스트레이터 반영용 — 이 unit이 직접 수정하지 않음)

### traceability.md — REQ-004 행

| 컬럼 | 현재값 | 요청값 |
|---|---|---|
| 구현 상태 | `Partially Implemented (unit-3: Verified — 06단계 PASS, ... unit-6: Implemented — hwpx_writer/table_builder.py, 05단계 완료, 06단계 단위테스트 대기)` | `Partially Implemented (unit-3: Verified — 06단계 PASS, pdf_reader/table_recognizer.py, 결함 0건. unit-6: Verified — 06단계 PASS, hwpx_writer/table_builder.py, 결함 0건(Low 심각도 DEF-001 Open/Deferred, FAIL 기준 미해당), 07단계 handoff 가능)` |
| 단위테스트 (unit-n-test) | `unit-3분: PASS (...). unit-6분: 미정(06 대기)` | `unit-3분: PASS (docs/harness/units/unit-3-test.md — 20개 테스트, AC-1~AC-5 전 항목 커버). unit-6분: PASS (docs/harness/units/unit-6-test.md — 32개 테스트, AC-1~AC-6 전 항목 1:1 커버, 라인/브랜치 커버리지 100%, 결함 1건(DEF-001, Low, Open/Deferred — FAIL 기준 미해당))` |
| 비고 | (기존 문구 유지) | 기존 문구에 다음 추가 권장: `unit-6 06단계 결과: docs/harness/units/unit-6-test.md, 검증로그: docs/harness/verify-log_unit-6-test.md. DEF-001(Low, Open) — _resolve_cell_positions가 row_span/col_span이 선언된 rows/cols 경계를 넘는 손상 입력까지는 방어하지 못함(정상 파이프라인에서는 재현 불가로 확인됨), unit-8 통합 또는 차기 리팩터링 시 보강 권장. mutmut는 이 환경(Windows, WSL 없음)에서 실행 불가 확인됨 — WSL 확보 시 재시도 권고.` |

### decisions.md
별도 신규 결정(DEC) 추가 요청 없음 — 이 06단계 수행은 unit-6-note.md가 이미 확정한
설계/구현 결정을 검증했을 뿐, 새로운 비가역적 프로젝트 결정을 만들지 않았다. 다만
"mutmut가 이 프로젝트 환경(Windows 네이티브)에서 전면적으로 사용 불가하다"는 사실은
향후 다른 unit의 06단계가 동일 시행착오를 반복하지 않도록 decisions.md 또는
`docs/harness/`의 공용 참고 노트에 한 줄 기록해 둘 것을 오케스트레이터에 권고한다
(강제 아님).
