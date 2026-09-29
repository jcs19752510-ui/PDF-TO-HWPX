# 테스트 결과서 (Test Result Report) — unit-3

## 1. 개요
- 테스트 대상: `pdf_to_hwpx/pdf_reader/table_recognizer.py` (함수 `extract_table_blocks`, 내부 헬퍼 `_build_table_block`) — unit-3, REQ-004(표 구조 인식 → HWPX 표 객체 변환, 셀 병합은 best-effort)
- 테스트 유형: 단위
- 적용 Tier: Standard
- 적용 속도 트랙: L3(일반) — 전 섹션(1~10절) 정식 작성
- 병렬 실행 정보: 병렬 웨이브에서 실행(동시에 돌던 단위: unit-1 `pdf_reader/text_extractor.py`, unit-2 `pdf_reader/image_extractor.py`, unit-4 `hwpx_kernel/schema.py`/`hwpx_kernel/container.py`의 05/06 호출이 동시 진행 중이었음)
- 테스트 목적: unit-3-note.md §6이 정의한 AC-1~AC-5를 코드가 실제로 만족하는지 증명하고, 5단계 게이트(정적분석/코드리뷰)가 실제로 통과됐는지 재확인
- 관련 산출물: `docs/harness/units/unit-3-note.md`(05단계 산출물), `docs/harness/03-system-design.md` §1-3(unit-3 행)/§2-1(pdfplumber 선정)/§3-1(TableBlockIR), `docs/harness/02-planning.md`(REQ-004), `pdf_to_hwpx/pdf_reader/ir.py`(TableBlockIR/TableCellIR 정의, 수정 금지 참고용), `pdf_to_hwpx/pdf_reader/loader.py`(unit-0, 06단계 이미 PASS)
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): `extract_table_blocks(plumber_page, table_settings=None)` 공개 API의 AC-1~AC-5 전 항목, 그리고 note §4(게이트2 체크리스트)가 언급한 방어적 분기(빈 행/빈 열 표 감지 결과의 `continue`) 및 note §1-2/AC-5가 명시한 "알려진 미탐 한계"의 재현 확인.
- 제외 범위 및 사유:
  - `hwpx_writer/table_builder.py`(unit-6, 아직 미착수) — `TableBlockIR`을 실제 HWPX XML로 그려내는 소비자 쪽 로직은 이 unit의 책임이 아니며(note §0 모듈 docstring 근거), 별도 unit-6의 06단계에서 검증한다.
  - `pdf_reader/loader.py`(unit-0)·`pdf_reader/ir.py`의 자체 정합성 — 이미 06단계 PASS(loader.py)/공유 계약 파일(ir.py, 수정 금지 대상)이므로 재검증하지 않고 import 계약만 통해 소비.
  - pdfplumber 자체의 표 인식 정확도(선 검출 알고리즘 내부 동작) — 03 §2-1에서 이미 "pdfplumber 채택" 근거가 확정된 서드파티 라이브러리 자체의 품질은 이 unit의 책임 범위 밖. 다만 AC-5의 화이트박스 테스트는 pdfplumber 출력을 흉내낸 입력으로 `_build_table_block`의 자체 알고리즘 동작만 검증한다(pdfplumber 내부를 검증하는 것이 아님).
  - 3개 이상 칸이 얽힌 비직사각형(L자형) 복합 병합 — note §1-2/모듈 docstring이 "pdfplumber의 격자 모델 자체가 표현 못함"이라고 이미 명시한 한계이며, 재현 자체가 pdfplumber 격자 모델상 불가능하므로 테스트 케이스로 만들 수 없음(만들 수 없는 것이지 검증을 생략한 것이 아님).

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro, Python 3.13.15(레포지토리 `requires-python = ">=3.11"` 충족), pytest 9.1.1, pdfplumber 0.11.9, reportlab 5.0.1(테스트 전용, 런타임 의존성 아님)
- 테스트 데이터: reportlab 캔버스 API로 즉석 생성한 실제 PDF 7종(병합 없는 3x3 표/블랭크 셀 포함 3x3 표/가로 병합 표/세로 병합 표/표 2개짜리 페이지/표 없는 텍스트 페이지/완전 빈 페이지) + `_build_table_block`/`extract_table_blocks`를 직접 호출하는 화이트박스 duck-typing 스텁 객체(unittest.mock 미사용, unit-1 `_FakePage` 관례와 동일)
- 전제 조건: unit-0(`loader.py`)이 이미 06단계 PASS 상태이며 `PdfDocument.plumber_pdf`를 읽기 전용으로 제공한다는 계약이 유효함. unit-3 05단계(`table_recognizer.py`)가 `docs/harness/units/unit-3-note.md` 기준으로 이미 자체 게이트1/게이트2를 통과했다고 보고됨(본 06단계에서 재확인, 4절 참고).

## 4. 테스트 케이스 및 결과

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | AC-1-1: 병합 없는 3x3 표 기본 추출 | plain.pdf(격자선 전부 존재, A~I) | `extract_table_blocks(page)` 호출 | 블록 1개, rows=3/cols=3, cells 9개, 전부 row_span=1/col_span=1 | 동일 | PASS | `test_plain_table_returns_one_block_with_correct_grid_and_spans` |
| TC-002 | AC-1-2: 병합 없는 표의 has_merged_cells | 상동 | 상동 | `has_merged_cells is False` | 동일 | PASS | `test_plain_table_has_merged_cells_is_false` |
| TC-003 | AC-1-3: 셀 텍스트 정확성 | 상동 | 각 cell.text 수집 | {A..I}와 정확히 일치 | 동일 | PASS | `test_plain_table_cell_text_matches_actual_content` |
| TC-004 | AC-1-3: 빈 셀(실사각형 존재, 텍스트 없음) | plain_blank_cell.pdf(행2/열2만 텍스트 없음) | `extract_table_blocks(page)` | 해당 셀 text=="" (None 아님), row_span=col_span=1 | 동일, 나머지 8칸은 실제 텍스트 보존 | PASS | `test_plain_table_blank_cell_text_is_empty_string_not_none` |
| TC-005 | 입력 계약: unit-0 `load_pdf`를 통한 페이지 소비 | plain.pdf | `load_pdf(path).plumber_pdf.pages[0]`로 호출 | rows=3/cols=3 정상 | 동일 | PASS | `test_extract_table_blocks_via_loader_pdfdocument_input_contract` — note §1-1이 명시한 실제 입력 계약 재확인 |
| TC-006 | AC-2-1: 가로 병합 span | hmerge.pdf(0행 0/1열 세로선 생략) | `extract_table_blocks(page)` | 병합 셀 1개, col_span=2, row_span=1, text=="A" | 동일 | PASS | `test_hmerge_table_merged_cell_has_col_span_2_row_span_1` |
| TC-007 | AC-2-2: 가로 병합 has_merged_cells | 상동 | 상동 | `True` | 동일 | PASS | `test_hmerge_table_has_merged_cells_is_true` |
| TC-008 | AC-2-3: 가로 병합 cells 개수 | 상동 | 상동 | cells 8개 < rows*cols(9) | 동일 | PASS | `test_hmerge_table_cell_count_is_less_than_rows_times_cols` |
| TC-009 | AC-3-1: 세로 병합 span | vmerge.pdf(1열 0/1행 가로선 생략) | `extract_table_blocks(page)` | 병합 셀 1개, row_span=2, col_span=1, text=="B" | 동일 | PASS | `test_vmerge_table_merged_cell_has_row_span_2_col_span_1` |
| TC-010 | AC-3-2: 세로 병합 has_merged_cells | 상동 | 상동 | `True` | 동일 | PASS | `test_vmerge_table_has_merged_cells_is_true` |
| TC-011 | AC-4-1: 표 없는 페이지 | no_table.pdf(일반 텍스트만) | `extract_table_blocks(page)` | 예외 없이 `[]` | 동일 | PASS | `test_no_table_page_returns_empty_list` |
| TC-012 | 경계값(범위 밖, 위험 케이스): 완전히 빈 페이지 | empty_page.pdf(텍스트/도형 전무) | `extract_table_blocks(page)` | 예외 없이 `[]` | 동일 | PASS | `test_completely_empty_page_returns_empty_list_without_exception` — AC엔 없으나 "빈 입력" 계열 위험 케이스로 판단해 포함 |
| TC-013 | AC-4-2: 표 2개 이상 | two_tables.pdf(3x3 표 + 2x2 표, bbox 비중첩) | `extract_table_blocks(page)` vs `page.find_tables()` | 블록 2개, `find_tables()` 순서와 bbox 일치, bbox 비중첩 | 동일 (rows/cols도 3x3/2x2로 각각 정확) | PASS | `test_two_tables_on_one_page_returns_two_blocks_in_find_tables_order` |
| TC-014 | AC-4-3: bbox가 pdfplumber Table.bbox와 동일 | plain.pdf | 동일 페이지에서 `extract_table_blocks()`와 `find_tables()` 각각 호출 후 bbox 비교 | 4-튜플 동일 | 동일 | PASS | `test_table_bbox_matches_pdfplumber_table_bbox_exactly` |
| TC-015 | table_settings=None 기본 동작(note §1-1) | 화이트박스 스텁 페이지 | `extract_table_blocks(page)` (table_settings 생략) | `find_tables()`가 kwargs 없이 호출됨(`{}`) | 동일 | PASS | `test_table_settings_none_forwards_no_kwarg_to_find_tables` |
| TC-016 | table_settings 전달(note §1-1) | 화이트박스 스텁 페이지 | `extract_table_blocks(page, table_settings={...})` | `find_tables(table_settings={...})`로 그대로 전달됨 | 동일 | PASS | `test_table_settings_dict_is_forwarded_verbatim` |
| TC-017 | AC-5: 알려진 미탐 한계(회귀 검증용, 설계된 한계 — 결함 아님) | `_build_table_block`에 "0번 열 전체가 실제 사각형을 한 번도 얻지 못하는" 극단 배치 입력 | `_build_table_block(...)` 직접 호출(화이트박스) | `has_merged_cells is False`, 0번 열 3칸이 크래시 없이 독립 빈 셀(row_span=col_span=1, text=="")로 남고 1번 열은 실제 텍스트 보존 | 동일 | PASS | `test_known_limitation_whole_column_never_resolved_stays_unmerged_false` — note §1-2/AC-5, 모듈 docstring "알려진 한계"와 일치. **PASS의 의미는 "버그가 없다"가 아니라 "문서화된 설계 한계가 실제로 재현되고, 그 한계가 안전하게(크래시·None 없이) 처리된다"는 것** |
| TC-018 | 방어 분기(범위 밖, 위험 케이스): 빈 행/빈 열 표는 조용히 건너뜀 | 화이트박스 스텁 표 3개(0행/0열/정상) | `extract_table_blocks(page)` | 정상 표만 블록 1개로 반환, 나머지는 예외 없이 스킵 | 동일 | PASS | `test_degenerate_zero_row_and_zero_col_tables_are_skipped_via_continue` — note §4 게이트2가 언급한 방어 분기, 실제 pdfplumber로는 재현 불가로 판단해 화이트박스로 커버 |
| TC-019 | 예외 입력(범위 밖, 위험 케이스): `plumber_page=None` | 없음 | `extract_table_blocks(None)` | 예외를 삼키지 않고 `AttributeError`로 즉시 실패(입력 검증은 이 계층 책임 아님, note §4) | 동일 | PASS | `test_none_page_raises_attribute_error_fail_fast_not_swallowed` |
| TC-020 | 설계서 대비 편차 회귀 가드 | 소스 텍스트 | `ir.py` import만 하고 재정의 안 함, `PdfDocument`/`PageIR` 미참조 확인 | 조건 충족 | 동일 | PASS | `test_table_recognizer_only_imports_ir_and_does_not_redefine_shared_contracts` — note §2 "편차 없음" 보강 확인 |

> 위 20개 테스트 모두 `tests/pdf_reader/test_table_recognizer.py`에 구현되어 실행됨(`pytest tests/pdf_reader/test_table_recognizer.py`, 3절 환경에서 20 passed).

## 5. 커버리지
- 커버리지 지표: 별도 커버리지 측정 도구(`pytest-cov` 등)는 프로젝트에 설치되어 있지 않아 라인/브랜치 수치는 산출하지 않음. 대신 `_build_table_block`의 핵심 분기를 코드 리딩으로 전수 대조했다:
  - 격자 칸에 실제 사각형이 있는 경우(owner=self) — TC-001 등 다수에서 도달.
  - `c>0`이고 왼쪽 소유자 존재 + 가로 병합 조건 True — TC-006(hmerge)에서 도달.
  - `c>0`이고 왼쪽 소유자 존재 + 가로 병합 조건 False(경계 미충족) — TC-009(vmerge)에서 세로 케이스 진입 전 좌측 체크가 False로 지나가는 경로로 도달.
  - `r>0`이고 위쪽 소유자 존재 + 세로 병합 조건 True — TC-009(vmerge)에서 도달.
  - 둘 다 False → 2-c(독립 빈 셀) — TC-017(AC-5 화이트박스)에서 도달.
  - `n_rows==0`/`n_cols==0` 방어 `continue` — TC-018(스텁)에서 도달.
  - `table_settings is None` / `dict 전달` 분기 — TC-015/TC-016에서 도달.
  - 위 목록으로 `_build_table_block`/`extract_table_blocks`의 모든 조건 분기가 최소 1회씩 실행됨을 코드 대조로 확인했다(브랜치 커버리지 100% 상당, 도구 미측정이므로 "상당"으로 표기).
- 커버되지 않은 부분과 사유: pdfplumber `find_tables()`/`Table.extract()` 자체의 내부 구현 — 서드파티 라이브러리이며 03 §2-1에서 이미 채택 근거가 확정되었으므로 이 unit의 커버리지 대상이 아님. 3개 이상 칸이 얽힌 비직사각형 병합 — pdfplumber 격자 모델 자체가 표현 불가하여 테스트 케이스 구성이 원천적으로 불가능(2절 제외범위 참고).

## 6. 결함(Defect) 목록

결함 없음. 근거: 4절의 TC-001~TC-020 전부 PASS. 추가로 "테스트가 결함을 실제로 잡아낼 수 있는가"를 자체 검증하기 위해 **뮤테이션 테스트 3건**을 수행했다(코드를 일부러 훼손한 뒤 원래대로 복구, 결함 주입이 아니라 테스트 유효성 검증 목적):

1. `confirmed_merge = True` → `confirmed_merge = False`로 변조 → `test_hmerge_table_has_merged_cells_is_true`, `test_vmerge_table_has_merged_cells_is_true` 2건이 즉시 FAIL로 반응(정상 검출력 확인).
2. `text=text if text is not None else ""` → `text=text`로 변조(None 폴백 제거) → `test_known_limitation_whole_column_never_resolved_stays_unmerged_false`가 즉시 FAIL로 반응.
3. `row_span=max_r - min_r + 1` → `row_span=1`로 변조 → `test_vmerge_table_merged_cell_has_row_span_2_col_span_1`이 즉시 FAIL로 반응.

3건 모두 변조 직후 실패, 복구 직후 `filecmp.cmp`로 원본과 바이트 단위 동일함을 확인 후 재실행하여 20 passed로 복귀함을 확인했다(아래 10절 검증 로그에 상세 기록). 이로써 "실행해보니 에러 없음"이 아니라 테스트 스위트가 실제로 회귀를 탐지할 수 있음을 근거로 남긴다.

5단계 게이트 확인(note §3/§4 재검토):
- 게이트1(정적분석/린트): 프로젝트에 lint/type-check 설정 없음을 `pyproject.toml`에서 재확인. `py_compile`을 06단계에서도 독립적으로 재실행해 컴파일 성공을 재확인함(3절 환경, 별도 명령 실행 결과: `COMPILE OK`).
- 게이트2(자체 코드 리뷰 체크리스트): note §4의 6개 항목(설계 일치/에러처리/입력검증 경계/시크릿/신규의존성/범위이탈) 전부 근거와 함께 체크됨을 확인했고, 06단계 테스트 결과(4절)가 이 체크 내용과 모순되지 않음을 확인했다(예: "신규 의존성 없음" 주장은 `pyproject.toml`에 unit-3 관련 diff가 없음을 3절 실행 시 재확인).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit3/` (unit-3 전용 격리 venv, `pip install -e ".[dev]" reportlab`)
  - `.harness-tmp/probe_unit3/` (본 테스트 설계 전 pdfplumber 병합 감지 동작을 사전 확인한 1회성 프로브 PDF 6종)
  - `.harness-tmp/table_recognizer_unit3_backup.py` (뮤테이션 테스트용 원본 백업)
  - `tests/.harness-tmp/pdf_fixtures_06_unit3/` (pytest 모듈 스코프 픽스처가 테스트 실행 중 생성한 PDF 7종 — pytest 자체 teardown으로 세션 종료 시 자동 삭제됨)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. `venv_06_unit3/`, `probe_unit3/`, `table_recognizer_unit3_backup.py`를 명시적으로 삭제했고, `tests/.harness-tmp/pdf_fixtures_06_unit3/`는 pytest 픽스처 teardown이 이미 삭제함을 확인함(테스트 종료 직후 `find tests/.harness-tmp`로 재확인, 하위 항목 없음).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
  ```
  On branch PROD
  Changes not staged for commit:
    (use "git add <file>..." to update what will be committed)
    (use "git restore <file>..." to discard changes in working directory)
  	modified:   docs/harness/02-planning.md
  	modified:   docs/harness/03-system-design.md
  	modified:   docs/harness/decisions.md
  	modified:   docs/harness/traceability.md
  	modified:   docs/harness/verify-log_03-system-design.md
  	modified:   pyproject.toml

  Untracked files:
    (use "git add <file>..." to include in what will be committed)
  	docs/harness/units/unit-1-note.md
  	docs/harness/units/unit-2-note.md
  	docs/harness/units/unit-3-note.md
  	docs/harness/units/unit-4-note.md
  	docs/harness/units/unit-4-test.md
  	docs/harness/verify-log_unit-4-test.md
  	pdf_to_hwpx/hwpx_kernel/schema.py
  	pdf_to_hwpx/pdf_reader/image_extractor.py
  	pdf_to_hwpx/pdf_reader/table_recognizer.py
  	tests/hwpx_kernel/
  	tests/pdf_reader/test_image_extractor.py
  	tests/pdf_reader/test_table_recognizer.py
  	tests/pdf_reader/test_text_extractor.py

  no changes added to commit (use "git add" and/or "git commit -a")
  ```
- 병렬 실행이었다면: 위 `git status`의 `modified:` 6개 파일(02-planning.md/03-system-design.md/decisions.md/traceability.md/verify-log_03-system-design.md/pyproject.toml)은 이 06 호출 시작 이전부터 이미 존재하던 상위 단계 변경분(사전 스냅샷)이며 이 unit-3 06 실행이 만든 것이 아니다. `docs/harness/units/unit-1-note.md`, `unit-2-note.md`, `unit-4-note.md`, `unit-4-test.md`, `docs/harness/verify-log_unit-4-test.md`, `pdf_to_hwpx/hwpx_kernel/schema.py`, `pdf_to_hwpx/pdf_reader/image_extractor.py`, `tests/hwpx_kernel/`, `tests/pdf_reader/test_image_extractor.py`, `tests/pdf_reader/test_text_extractor.py`는 **다른 단위(unit-1/unit-2/unit-4) 소유**로 판단한다(파일명이 그 단위 산출물과 정확히 일치, 이 실행이 접촉한 파일 범위 밖). 이 실행이 만든 것은 `docs/harness/units/unit-3-note.md`(05단계 산출물, 이미 입력으로 존재), `pdf_to_hwpx/pdf_reader/table_recognizer.py`(05단계 산출물, 06단계에서 뮤테이션 테스트 후 원본과 바이트 단위 동일하게 복구 완료 — 6절 참고), `tests/pdf_reader/test_table_recognizer.py`(이번 06단계가 신규 작성)뿐이다. 판정 근거: 이번 실행의 임시 아티팩트(`.harness-tmp/venv_06_unit3`, `.harness-tmp/probe_unit3`, `.harness-tmp/table_recognizer_unit3_backup.py`, `tests/.harness-tmp/pdf_fixtures_06_unit3`)는 모두 삭제되어 위 `git status`에 나타나지 않으며, `.harness-tmp/venv_06_unit2`·`.harness-tmp/scratch_06_unit2`(동시 진행 중인 unit-2 소유, 건드리지 않음)만 로컬에 남아 있음을 별도로 확인했다(`git status`는 `.gitignore` 대상이라 애초에 표시되지 않음). 웨이브 종료 후 오케스트레이터의 전체 트리 점검(`harness-janitor.sh --check`, 전체 `git status`)은 이 결과서 작성 시점에서는 아직 수행되지 않았으며 오케스트레이터 책임으로 남긴다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 준수, `git status`가 이 unit-3 실행 기준으로 깨끗함(추가·잔여 임시 아티팩트 없음)을 확인함 — 8절 PASS 판정의 전제조건 충족.

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - AC-5(전체 열이 통째로 병합된 극단적 배치의 미탐)는 note와 코드 docstring이 이미 "결함 아님, best-effort 범위 안"이라고 명시한 설계된 한계이며, 이번 06단계가 화이트박스로 재현해 "안전하게 처리됨(크래시 없음, None 유출 없음)"을 확인했다. 다만 실제 서비스에서 이런 극단적 표가 얼마나 자주 나타나는지는 이 unit 범위 밖(실사용 데이터 기반 빈도 측정 필요 — unit-8/orchestrator 통합 이후 quality_report 축적 시 재평가 권장).
  - pytest-cov 등 커버리지 측정 도구 부재로 정량적 라인/브랜치 수치를 제시하지 못했다(5절 참고). 정성적 전수 분기 대조로 대체함.
  - `table_settings` 파라미터에 실제 pdfplumber 선 감지 전략 튜닝 값(예: `vertical_strategy="text"`)을 넣었을 때의 종단 동작(진짜 pdfplumber 대상)은 화이트박스 스텁으로만 "전달됨"을 확인했고, 실제 pdfplumber `find_tables(table_settings=...)`가 그 값을 받아 다르게 동작하는지는 pdfplumber 자체 책임이라 검증 범위 밖으로 남긴다(2절 제외범위와 동일 사유).
- 후속 조치가 필요한 항목:
  - unit-6(`hwpx_writer/table_builder.py`)이 `TableBlockIR.has_merged_cells=False`를 "병합 없음 확정"으로 오독하지 않고 "확정된 병합 없음(미탐 가능)"으로 다뤄야 한다는 계약을 unit-6의 05단계 note에 반드시 반영해야 한다(공유 문서 갱신 요청 참고).
  - 07단계(업무단위 통합테스트)에서 unit-1(text_extractor)/unit-2(image_extractor)/unit-3(table_recognizer)이 같은 페이지에서 동시에 동작할 때(예: 텍스트+표+이미지가 섞인 실제 페이지) `PageIR.table_blocks` 채우기가 다른 블록 추출과 간섭하지 않는지 확인이 필요함(이 06단계는 unit-3 단독 검증이라 페이지 수준 상호작용은 범위 밖).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능 (7절 Teardown 확인 완료가 전제조건, 충족됨)

## 10. 내부 검증 (최소 2회)
- 1차 검증 결과 요약: (작성자 관점) AC-1~AC-5 각 항목에 최소 1개 이상의 테스트 케이스가 1:1로 대응하는지 표(4절)로 재확인했고, 각 테스트의 예상 결과가 note §6(AC 원문)과 코드 docstring(§1-2 휴리스틱 설명)에서 직접 도출되었는지(추측이 섞이지 않았는지) 문장 단위로 대조했다. 발견된 결함: 0건. 다만 초안 작성 중 "빈 셀 텍스트가 None 폴백 코드를 실제로 태우는지" 의심이 들어(실제로는 pdfplumber가 실사각형이 있는 빈 칸에 이미 `""`를 반환해 그 폴백 코드를 안 태울 수 있다는 가능성) 2차 검증에서 뮤테이션 테스트로 직접 확인하기로 함.
- 2차 검증 결과 요약: (독립 심사자 관점 — "내가 이 결과서를 오늘 처음 받은 심사자라면?") "테스트가 통과했다"는 사실만으로는 테스트 자체가 헐거워서 결함을 놓쳤을 가능성을 배제할 수 없다고 보고, 3건의 뮤테이션 테스트(6절)를 수행함. 그 결과 1차에서 의심했던 지점(None→"" 폴백)이 실제로는 real-PDF 기반 TC-004가 아니라 AC-5 화이트박스 테스트(TC-017)에서만 그 코드 경로를 태운다는 것을 확인했다 — TC-004는 여전히 유효하지만("실사각형이 있는 빈 칸은 pdfplumber가 이미 `""`를 반환한다"는 사실 자체를 검증), None 폴백 로직 자체의 회귀 가드는 TC-017이 담당한다는 역할 분리를 명확히 했다(결과서 6절에 반영). 그 외 2건의 뮤테이션(has_merged_cells 오검출, row_span 오계산)도 각각 대응하는 테스트가 정확히 잡아냄을 확인해, "다음 단계(07 통합테스트)로 넘겨도 되는가"에 대해 긍정 판단. 추가로 놓쳤을 법한 경계 조건(표 0개/2개, table_settings 전달, None 입력, degenerate 표)도 이미 TC-011~TC-019로 커버되어 있음을 재확인. 발견된 결함: 0건.
- 검증 로그 파일 경로: 별도 `verify-log_unit-3-test.md` 파일을 만들지 않고 위 1차/2차 요약과 6절의 뮤테이션 테스트 기록(구체적 변조 내용·명령·결과)을 이 결과서 자체에 근거 로그로 남김(Standard Tier는 2회 이상 검증이 원칙이며, 본 문서 6절/10절이 그 실행 근거임).

## 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

`docs/harness/traceability.md` REQ-004 행 갱신 요청 (unit-3 관련 부분만, unit-6은 별개):

| 컬럼 | 현재값(unit-3 관련 부분) | 요청값 |
|---|---|---|
| 구현 상태 | `...unit-3: Implemented — pdf_reader/table_recognizer.py, 05단계 완료, 06단계 대기...` | `...unit-3: Verified — pdf_reader/table_recognizer.py, 06단계 단위테스트 PASS(tests/pdf_reader/test_table_recognizer.py, TC-001~TC-020, 결함 0건). 07단계(통합테스트) 대기...` |
| 단위테스트 | (컬럼이 있다면) 미기입/미정 | `PASS — docs/harness/units/unit-3-test.md 참고` |

`docs/harness/units/unit-6-note.md`(아직 작성 전이라면 05단계 착수 시 참고 요청): unit-3이 넘기는 `TableBlockIR.has_merged_cells=False`는 "확정된 병합 없음"이 아니라 "확정된 병합을 발견하지 못함(미탐 가능성 있음)"으로 해석해야 한다는 계약을 unit-6 구현 시 반드시 인지시켜 달라는 요청(근거: unit-3-note.md §1-2, 본 결과서 8절).

규칙 A 질문·결정 기록 요청: 없음(06단계에서 설계 모호성으로 인한 질문 발생하지 않음, 뮤테이션 테스트는 06-unit-tester 자체 판단으로 수행한 내부 검증 기법이며 별도 결정 승인이 필요한 사안이 아니라고 판단).
