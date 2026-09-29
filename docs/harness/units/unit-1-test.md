# 테스트 결과서 (Test Result Report) — unit-1

## 1. 개요
- 테스트 대상: 작업 단위 unit-1(`pdf_to_hwpx/pdf_reader/text_extractor.py`, 함수 `extract_text_blocks(plumber_page)` 및 비공개 헬퍼 전체)
- 테스트 유형: 단위(06단계)
- 적용 Tier: Standard
- 적용 속도 트랙: L3(일반) — 전 섹션 작성, 내부 검증(규칙 B) 2회 원문대로 적용, 06·07 병합(Low 등급 전용) 대상 아님(이 프로젝트는 Standard Tier)
- 병렬 실행 정보: **병렬 웨이브에서 실행** — unit-2(`image_extractor.py`)/unit-3(`table_recognizer.py`)/unit-4(`hwpx_kernel/schema.py`)의 06 호출과 동시에 진행 중. 이 결과서는 unit-1 파일 범위(`text_extractor.py`, `tests/pdf_reader/test_text_extractor.py`)만 다룬다.
- 테스트 목적: `docs/harness/units/unit-1-note.md` §5의 AC-1~AC-5(12개 구체 조건, REQ-002/REQ-006(입력측)/REQ-007)를 실제 pytest 코드로 1:1 검증하고, 정상/경계값/예외입력 케이스를 통해 03단계 설계서(§1-3 unit-1 행, §3-1 TextBlockIR)와 구현이 일치하는지 근거를 남긴다.
- 관련 산출물:
  - `docs/harness/03-system-design.md` §1-3(unit-1 행), §3-1(TextBlockIR 정의)
  - `docs/harness/02-planning.md`(REQ-002/REQ-006/REQ-007)
  - `docs/harness/units/unit-1-note.md`(구현 노트, AC-1~AC-5, "재작업(2026-09-28)" 절)
  - `pdf_to_hwpx/pdf_reader/text_extractor.py`(검증 대상), `pdf_to_hwpx/pdf_reader/ir.py`/`pdf_to_hwpx/pdf_reader/loader.py`(참고, 미수정 확인)
  - `tests/pdf_reader/test_text_extractor.py`(이번 06단계가 실행/보완한 테스트 코드)
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-28(1차), 2026-09-28(재검증, 규칙 F)

**이 문서의 최종 판정은 12절 재검증 결과를 따른다 — 1차(FAIL, DEF-001)는 4~11절에 원본 그대로 보존하고, 재검증 결과와 최종 판정은 12절에 별도로 기록한다(이력 보존 원칙).**

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope):
  - `extract_text_blocks`의 기본 추출(AC-1: 반환 타입, 텍스트 join, bbox 순서/유효성 — 3개 조건)
  - 폰트명/크기 변경 지점 블록 분리 및 bold/italic 추정(AC-2: 2개 조건)
  - REQ-007 ToUnicode 매핑 누락 감지 3신호(`(cid:N)`, U+FFFD/빈문자, PUA)와 알려진 미탐 케이스(AC-3: 3개 조건)
  - 빈 페이지/비텍스트 페이지 처리 및 `is_scanned` 비관여(AC-4: 2개 조건)
  - 읽기 전용성(idempotent), 범위 외 파일 미접촉(AC-5: 2개 조건)
  - AC에 없으나 위험도가 높아 추가한 케이스: `word` dict에 `text`/`fontname`/`size` 키 자체가 없는 방어적 경계, `extract_words`가 빈 목록을 반환하는 최소 계약 케이스, 줄 그룹핑 허용오차(`_LINE_TOLERANCE_PT`) 경계값
  - **(재검증분, 12절)** 재작업으로 교체된 겹침 비율(`_LINE_OVERLAP_RATIO=0.5`) 기반 판정 자체의 새 경계 케이스: 비율 정확히 0.5, 0.5 바로 아래, 완전 비겹침, 첨자류(위/아래) 짧은 word, 전이적 병합 사슬, `_group_words_into_lines`/`_has_vertical_overlap` 방어 분기 직접 호출
- 제외 범위(Out-of-Scope) 및 사유:
  - 실제 NFC 정규화 동작(REQ-006 본체): unit-15 소관, 이 모듈은 정규화 이전 원문을 그대로 반환한다는 것만 확인(코드 리뷰 + `TextBlockIR.text` 내용 검사).
  - `is_scanned`/OCR 라우팅 판정: unit-8(orchestrator) 소관, AC-4-10에 따라 이 함수가 `PageIR`을 아예 참조하지 않는다는 시그니처 수준 확인만 수행.
  - 폰트 미스매치로 인한 "그럴듯하지만 틀린" 디코딩 오탐지(AC-3-8 명시): unit-1-note.md §1-3이 미리 공유한 알려진 한계이며, 실제로 이 한계가 재현됨을 확인만 하고(테스트로 포함) 결함으로 보고하지 않는다.
  - 다단(멀티컬럼) 레이아웃에서의 줄 오분류, 회전/기울어진 텍스트: note §1-2가 이미 명시한 한계이며 이번 06단계가 새로 발견한 사항이 아니므로 별도 결함으로 재보고하지 않고 8절 리스크로만 승계.
  - `pdfplumber.extract_words()` 자체의 파싱 정확도(pdfminer.six 내부 동작): 외부 라이브러리 신뢰 전제, unit-0 loader.py가 이미 PDF 유효성을 검증했다는 가정을 note와 동일하게 따름.

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro, Python 3.13.15(`pyproject.toml`이 `>=3.11` 요구, 상한 내 최신 버전)
- 격리 가상환경(규칙 K): `.harness-tmp/venv_06_unit1/`에 신규 venv를 만들고 `pip install -e ".[dev]"` + `reportlab`(픽스처 생성) + `coverage`(라인 커버리지 측정)를 설치했다. 병렬 웨이브 중인 unit-2(`venv_06_unit2`)/unit-3(`venv_06_unit3`)와 이름이 겹치지 않게 `unit1` 식별자를 포함했다.
- 테스트 데이터: `tests/pdf_reader/test_text_extractor.py`의 모듈 스코프 픽스처(`pdf_fixtures`)가 `.harness-tmp/pdf_fixtures_06_unit1/`(프로젝트 루트 기준, 모듈 종료 시 자동 삭제)에 reportlab로 즉석 생성한 실제 PDF 6종:
  - `single_line.pdf`(1줄 텍스트), `multi_line.pdf`(3줄), `mixed_style_line.pdf`(한 줄 안 Normal→Bold→Italic), `mixed_size_line.pdf`(한 줄 안 폰트 크기 10→24), `blank_page.pdf`(콘텐츠 없음), `nontext_content.pdf`(도형만, 텍스트 레이어 없음)
  - REQ-007(cid/PUA/치환문자) 신호는 unit-1-note.md와 동일한 이유(ToUnicode 없는 서브셋 폰트를 가진 실제 PDF를 손으로 만드는 것이 non-trivial)로 실물 PDF 재현 대신 `_sanitize_text` 화이트박스 검증 + `extract_words(...) -> list[dict]` 계약만 구현한 최소 duck-typing 스텁(`_FakePage`, `unittest.mock` 미사용)으로 연동 경로까지 검증
- 전제 조건: `pip install -e ".[dev]"` 성공(unit-0이 이미 검증), `pdf_to_hwpx.pdf_reader.ir.TextBlockIR`/`pdf_to_hwpx.pdf_reader.loader.load_pdf` import 가능.
- **(재검증분)** `.harness-tmp/venv_06_unit1_recheck/`(신규 격리 venv, 1차 검증의 `venv_06_unit1`과 이름 충돌 없도록 `_recheck` 접미사 사용, 확인 후 삭제)에 동일하게 `pip install -e ".[dev]" reportlab coverage` 설치.

## 4. 테스트 케이스 및 결과

> **1차 실행(2026-09-28, DEF-001 발견 당시) 원본 기록 — 그대로 보존.** 36개(파라미터화 포함) pytest 테스트 함수. "비고"에 AC-ID와 실제 함수명을 적어 1:1 추적 가능하게 했다. **34 passed, 2 failed** (전체 실행 로그는 6절 DEF-001 참고). **재검증 결과(재작업 후 재실행)는 12절 참고 — TC-007/TC-026 포함 아래 표의 전 항목이 재검증에서 PASS로 전환되었다.**

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과(1차) | Pass/Fail(1차) | 실제 결과(재검증) | Pass/Fail(재검증) | 비고 (AC-ID / 테스트 함수) |
|----|----------|----------|-----------|-----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 정상 페이지에서 비어있지 않은 `list[TextBlockIR]` 반환 | single_line.pdf | `extract_text_blocks(page)` 호출 | 길이>0, 전부 `TextBlockIR` 인스턴스 | 일치 | Pass | 일치 | Pass | AC-1-1 / `test_extract_text_blocks_normal_page_returns_nonempty_list` |
| TC-002 | 단일 줄 텍스트가 공백 join된 문자열로 반환 | single_line.pdf | 호출 후 `blocks[0].text` 비교 | `"Hello unit one text extractor"` | 일치 | Pass | 일치 | Pass | AC-1-2 / `test_extract_text_blocks_text_joined_with_single_space` |
| TC-003 | 모듈 docstring이 명시한 실제 입력 계약(`load_pdf(...).plumber_pdf.pages[i]`)으로도 동작 | single_line.pdf | `load_pdf` 경유 호출 | TC-002와 동일 | 일치 | Pass | 일치 | Pass | AC-1-2 보강 / `test_extract_text_blocks_via_loader_pdfdocument_input_contract` |
| TC-004 | 3줄 텍스트가 줄당 1블록으로 분리 | multi_line.pdf | 호출 후 `[b.text for b in blocks]` 비교 | 3줄 텍스트 순서대로 | 일치 | Pass | 일치 | Pass | AC-1-2 / `test_extract_text_blocks_multi_line_produces_one_block_per_line` |
| TC-005 | bbox 순서 `(x0,top,x1,bottom)` 및 `x0<=x1`,`top<=bottom`, 줄 순서(top 오름차순) | multi_line.pdf | 각 블록 bbox 검사 | 전부 만족, top 오름차순 | 일치 | Pass | 일치 | Pass | AC-1-3 / `test_extract_text_blocks_bbox_order_and_validity` |
| TC-006 | Normal→Bold→Italic 한 줄에서 3블록 분리, bold/italic 플래그 정확 | mixed_style_line.pdf | 호출 후 텍스트/`bold`/`italic`/`font_name` 검사 | `["Normal","Bold","Italic"]`, 플래그 각각 F/F, T/F, F/T | 일치 | Pass | 일치 | Pass | AC-2-5 / `test_font_switch_creates_separate_blocks_with_correct_style_flags` |
| TC-007 | 같은 폰트, 크기(10→24)만 바뀌는 한 줄에서 2블록 분리 + 읽기순서 보존 | mixed_size_line.pdf | 호출 후 `blocks[0].text`/`blocks[1].text`/`font_size` 검사 | `["Small","BIGGER"]`, size 10.0/24.0 | `["BIGGER","Small"]`(순서 뒤바뀜) | **Fail** | `["Small","BIGGER"]`, size 10.0/24.0 | **Pass** | AC-2-4 / `test_font_size_switch_on_same_line_creates_separate_blocks` → **DEF-001 재검증 PASS** |
| TC-008 | `_is_bold` 대소문자 무관, `None` 안전 | - | 파라미터 4종 확인 | 관례대로 True/False, None→False | 일치 | Pass | 일치 | Pass | AC-2-5 보강 / `test_is_bold_case_insensitive_and_none_safe` |
| TC-009 | `_is_italic` 대소문자 무관, Oblique 변형 인식, `None` 안전 | - | 파라미터 4종 확인 | 관례대로 True/False, None→False | 일치 | Pass | 일치 | Pass | AC-2-5 보강 / `test_is_italic_case_insensitive_oblique_variant_and_none_safe` |
| TC-010 | `_sanitize_text` 3신호(정상/빈문자/cid/FFFD/PUA 6개 경계) 파라미터화 11종 | - | 각 입력에 대해 sanitized/missing 비교 | 표 내 기대값과 일치(cid→치환, PUA 하한 0xE000·상한 0xF8FF·Supp-A·Supp-B 포함) | 11종 전부 일치 | Pass | 11종 전부 일치 | Pass | AC-3-6/AC-3-7 / `test_sanitize_text_detects_three_signal_patterns[*]`(11 파라미터) |
| TC-011 | PUA 범위 바로 밖(U+F900, 한글 완성형 U+D7A3대)은 미탐 처리 | - | `_sanitize_text` 직접 호출 | 변경 없음, `missing=False` | 일치 | Pass | 일치 | Pass | AC-3-7 경계 / `test_sanitize_text_pua_range_boundaries_excluded` |
| TC-012 | `extract_text_blocks` 공개 API 경유로 cid 신호가 실제 반영 | `_FakePage`(cid 워드) | 호출 후 `text`/`to_unicode_missing` 확인 | 치환 문자 반영, `True` | 일치 | Pass | 일치 | Pass | AC-3-6 연동 / `test_extract_text_blocks_integration_cid_pattern_via_stub_page` |
| TC-013 | 공개 API 경유 PUA 신호 반영 | `_FakePage`(PUA 워드) | 상동 | `True` | 일치 | Pass | 일치 | Pass | AC-3-7 연동 / `test_extract_text_blocks_integration_pua_char_via_stub_page` |
| TC-014 | 공개 API 경유 U+FFFD 신호 반영 | `_FakePage`(FFFD 워드) | 상동 | `True` | 일치 | Pass | 일치 | Pass | AC-3-7 연동 / `test_extract_text_blocks_integration_replacement_char_via_stub_page` |
| TC-015 | 정상 단어는 오탐 없음 | `_FakePage`(정상 워드) | 상동 | `False`, 텍스트 그대로 | 일치 | Pass | 일치 | Pass | AC-3-6/7 음성 대조 / `test_extract_text_blocks_integration_clean_word_not_flagged_via_stub_page` |
| TC-016 | 알려진 미탐 케이스: 세 신호 어디에도 안 걸리는 "그럴듯하지만 틀린" 문자열은 감지 못 함(결함 아님, note §1-3/AC-3-8 근거) | - | `_sanitize_text("nnnn")` | 변경 없음, `missing=False` | 일치 | Pass(결함 아님으로 확인) | 일치 | Pass(결함 아님) | AC-3-8 / `test_sanitize_text_known_limitation_plausible_but_wrong_decoding_not_detected` |
| TC-017 | 빈 페이지 → 정확히 `[]` | blank_page.pdf | 호출 | `[]` | 일치 | Pass | 일치 | Pass | AC-4-9 / `test_extract_text_blocks_blank_page_returns_empty_list` |
| TC-018 | 텍스트 레이어 없는(도형만) 페이지 → 정확히 `[]` | nontext_content.pdf | 호출 | `[]` | 일치 | Pass | 일치 | Pass | AC-4-9 / `test_extract_text_blocks_nontext_content_returns_empty_list` |
| TC-019 | 시그니처가 `plumber_page` 1개뿐, `PageIR` 미참조(is_scanned 비관여 구조적 확인) | - | `inspect.signature` + `hasattr` 확인 | 파라미터 1개, `PageIR` 속성 없음 | 일치 | Pass | 일치 | Pass | AC-4-10 / `test_extract_text_blocks_signature_has_no_page_ir_involvement` |
| TC-020 | 같은 페이지 반복 호출 시 결과 동일(읽기 전용) | multi_line.pdf | 2회 호출 후 값 비교(`==`)와 객체 동일성(`is not`) 비교 | 값 동일, 객체는 별개(새 리스트) | 일치 | Pass | 일치 | Pass | AC-5-11 / `test_extract_text_blocks_idempotent_multiple_calls` |
| TC-021 | 소스 텍스트 검사로 범위 외 파일(ir.py/loader.py) 재정의 없음 확인 | - | 소스 문자열에 `class TextBlockIR`/`class PdfDocument`/`class PageIR` 부재 확인 | 전부 부재, import 문만 존재 | 일치 | Pass | 일치 | Pass | AC-5-12 / `test_text_extractor_only_imports_ir_and_does_not_redefine_shared_contracts` |
| TC-022 | 줄 그룹핑 허용오차(2.5pt) 경계 및 x 오름차순 정렬 | 스텁 워드 3개 | `_group_words_into_lines` 직접 호출 | 2줄로 분리, 첫 줄 내부는 x0 순 | 일치 | Pass | 일치(겹침 비율 기반으로도 동일 결과) | Pass | 범위 외 경계(위험 케이스) / `test_group_words_into_lines_respects_tolerance_and_x_order` |
| TC-023 | word dict에 `text` 키 자체가 없는 방어 경로 | 스텁 워드(`text` 없음) | `extract_text_blocks(_FakePage(...))` | 예외 없이 `text=""` | 일치 | Pass | 일치 | Pass | 범위 외 방어(위험 케이스) / `test_build_block_defensively_handles_missing_text_key` |
| TC-024 | word dict에 `fontname`/`size` 자체가 없는 방어 경로 | 스텁 워드 | 상동 | `font_name=None`,`font_size=None`,`bold=False`,`italic=False` | 일치 | Pass | 일치 | Pass | 범위 외 방어(위험 케이스) / `test_build_block_defensively_handles_missing_fontname_and_size` |
| TC-025 | `extract_words`가 빈 목록을 반환하는 최소 계약 경로(스텁) | `_FakePage([])` | 호출 | `[]` | 일치 | Pass | 일치 | Pass | AC-4-9 보강 / `test_extract_text_blocks_empty_words_list_returns_empty_list_via_stub` |
| TC-026 | **DEF-001 재현 확장**: 같은 줄 안에 작은-큰-작은 폰트 크기 3단어가 있을 때 읽기 순서/텍스트 무결성 | 스텁 워드 3개(실측 좌표 그대로) | `extract_text_blocks` 호출 후 텍스트 순서 비교 | `["Small","BIGGER","Tail"]` | `["BIGGER","Small Tail"]`(순서 뒤바뀜 + 오병합) | **Fail** | `["Small","BIGGER","Tail"]` | **Pass** | 내부검증 2차 추가(위험 케이스 확장) / `test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub` → **DEF-001 재검증 PASS**(3-word 변형) |

## 5. 커버리지
- 인수조건(AC) 커버리지: **12/12 (100%)** — AC-1(3)+AC-2(2)+AC-3(3)+AC-4(2)+AC-5(2)=12개 전 항목이 TC-001~TC-005(AC-1), TC-006~TC-009(AC-2), TC-010~TC-016(AC-3), TC-017~TC-019/TC-025(AC-4), TC-020~TC-021(AC-5)에 1:1 매핑됨. **1차 실행 시점에는 AC-2-4(TC-007)가 커버는 됐으나 FAIL — 12절 재검증에서 PASS로 전환되어 현재는 12/12 전 조건이 실제로 PASS 상태다.**
- 라인 커버리지(`coverage.py`, `pdf_to_hwpx/pdf_reader/text_extractor.py` 대상):
  - 1차 실행(실패 테스트 포함 전체 실행 기준): 81 문장, 미실행 0, **100%**(당시 코드 기준, 줄 수는 재작업 전 버전).
  - **재검증(12절, 재작업 후 코드 + 확장 테스트 44개 기준): 102 문장, 미실행 0, 100%**(경계 케이스 테스트 추가로 100% 재확인, 12절 참고).
  - 주의: 라인 커버리지 100%는 "모든 코드 경로가 최소 1회 실행됐다"는 의미일 뿐, "동작이 옳다"는 의미가 아니다(06단계 필수 원칙). 1차 실행에서는 실제로 `_group_words_into_lines`의 정렬/허용오차 분기가 100% 실행되었음에도 TC-007/TC-026에서 오동작이 확인된 바 있다 — 이번 재검증은 라인 커버리지뿐 아니라 기대값 대 실제값 비교(assert)로 판정했다.
- 커버되지 않은 부분과 사유: 없음(라인 기준, 재작업 후 코드 포함). 다만 2절에서 명시한 대로 멀티컬럼/회전 텍스트/실제 ToUnicode-CMap-누락 PDF의 end-to-end 재현은 테스트 대상에서 제외했다(사유 2절 기재, note와 동일한 기존 한계).

## 6. 결함(Defect) 목록

| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | **같은 시각적 줄(같은 baseline) 안에서 폰트 "크기"가 크게 다른 단어들이 섞이면 (1) 읽기 순서가 뒤바뀌고 (2) 사이에 낀 다른 크기 단어를 건너뛰어 서로 떨어진 단어끼리 하나의 블록으로 잘못 합쳐진다.** 근본 원인(1차 실행 당시): `_group_words_into_lines`가 word를 `(round(top,1), x0)` 오름차순으로 정렬한 뒤 `top` 차이가 `_LINE_TOLERANCE_PT`(2.5pt, 고정값) 이내인지로만 "같은 줄"을 판정했다. | 1) `tests/pdf_reader/test_text_extractor.py::test_font_size_switch_on_same_line_creates_separate_blocks` 2) `test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub` | **High** — REQ-002(텍스트 추출)의 핵심 가치인 "원문 텍스트를 있는 그대로 보존"을 침해한다. 단순 순서 문제가 아니라 서로 인접하지 않던 두 단어가 하나의 문자열로 잘못 병합되는 **내용 손상**이며, 예외/경고 없이 조용히 발생했다. | **Fixed(재검증 완료, 12절)** | 05-unit-developer가 `_group_words_into_lines`를 word 세로 구간 `[top,bottom]` 겹침 비율(`_LINE_OVERLAP_RATIO=0.5`) 기반 판정으로 교체하고 "같은 줄 판정"과 "줄 내부 정렬"의 책임을 분리(상세: unit-1-note.md "재작업(2026-09-28)" 절). 06단계가 12절에서 독립적으로 재실행해 PASS 확인, 추가로 새 알고리즘의 경계 케이스(정확히 0.5 임계값, 0.5 바로 아래, 완전 비겹침, 첨자류, 전이적 병합 사슬) 8건을 신규 작성해 결함 재유입 없음을 확인. |

- **결함 1건(DEF-001), 재검증 결과 Fixed 상태로 종결.** (1차 실행 당시에는 Open이었고, 9절 판정도 당시 FAIL이었음 — 12절 참고). 이 결함은 unit-1 자신의 파일(`text_extractor.py`)에 국한되며, 병렬 진행 중인 unit-2/3/4나 공유 자원(`ir.py`, `loader.py`, `pyproject.toml`)과는 무관함을 1차/재검증 양쪽에서 확인했다.
- 참고(결함 아님, 테스트 코드 자체의 인프라 버그, 06단계가 1차 실행 중 직접 수정 — "사소한 오탈자" 범위 내): `tests/pdf_reader/test_text_extractor.py`의 `FIXTURE_DIR` 계산 경로 오류(`parent.parent` → `parent.parent.parent`)를 수정, `tests/.harness-tmp/`에 잘못 생성됐던 디렉터리를 삭제했다. 재검증 시점에는 이 문제가 재발하지 않음을 재확인했다(1개 파일, 순수 경로 계산 수정, 동작/로직/인터페이스 변경 없음).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K

### 1차 실행분
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit1/`(격리 venv) — 정리 완료
  - `.harness-tmp/.coverage_06_unit1`(coverage.py 측정 데이터) — 정리 완료
  - `.harness-tmp/pdf_fixtures_06_unit1/`(pytest 모듈 스코프 픽스처, 자동 삭제) — 이미 자동 정리됨
  - (결함 아닌 부수 발견) `tests/.harness-tmp/`(경로 계산 버그로 잘못 생성) — 발견 즉시 삭제
- 정리 완료 여부: 예.

### 재검증분(2026-09-28, 규칙 F 재작업 후) — 이번 호출
- 재개 전 확인: 이번 호출 시작 시점에 `.harness-tmp/`에 이전 실행이 남긴 잔여물이 있는지 먼저 확인했다(`ls .harness-tmp` → 아무 것도 없음, 빈 디렉터리/미존재 상태) — 중단(TaskStop) 잔여물 없음 확인 후 착수.
- 이번 재검증에서 생성한 임시 아티팩트:
  - `.harness-tmp/venv_06_unit1_recheck/`(신규 격리 venv, `pip install -e ".[dev]" reportlab coverage`) — 정리 완료(`rm -rf`로 삭제, 재검증 종료 직후)
  - `.harness-tmp/.coverage_06_unit1_recheck`(coverage.py 측정 데이터, `--data-file`로 명시 경로 지정) — 정리 완료
  - `.harness-tmp/pdf_fixtures_06_unit1/`(pytest 모듈 스코프 픽스처, 테스트 자체 teardown으로 자동 삭제) — 이미 자동 정리됨(재검증 실행 2회 모두 확인)
- 위 아티팩트를 전부 `.harness-tmp/` 하위(프로젝트 루트 기준)에서만 생성했는가: **[x] 예.**
- 정리(삭제) 완료 여부: **예.**
- 정리 후 `git status --short` 실행 결과(재검증 종료 시점, 그대로 첨부):
  ```
   M docs/harness/02-planning.md
   M docs/harness/03-system-design.md
   M docs/harness/decisions.md
   M docs/harness/traceability.md
   M docs/harness/verify-log_03-system-design.md
   M pdf_to_hwpx/pdf_reader/text_extractor.py
   M pyproject.toml
  ?? docs/harness/units/unit-1-note.md
  ?? docs/harness/units/unit-1-test.md
  ?? docs/harness/units/unit-2-note.md
  ?? docs/harness/units/unit-2-test.md
  ?? docs/harness/units/unit-3-note.md
  ?? docs/harness/units/unit-3-test.md
  ?? docs/harness/units/unit-4-note.md
  ?? docs/harness/units/unit-4-test.md
  ?? docs/harness/verify-log_unit-2-test.md
  ?? docs/harness/verify-log_unit-4-test.md
  ?? pdf_to_hwpx/hwpx_kernel/schema.py
  ?? pdf_to_hwpx/pdf_reader/image_extractor.py
  ?? pdf_to_hwpx/pdf_reader/table_recognizer.py
  ?? tests/hwpx_kernel/
  ?? tests/pdf_reader/test_image_extractor.py
  ?? tests/pdf_reader/test_table_recognizer.py
  ?? tests/pdf_reader/test_text_extractor.py
  ```
- 병렬 실행 관점 소유 분석: `pdf_to_hwpx/pdf_reader/text_extractor.py`(unit-1 소유, 05단계 재작업 산출물)와 `tests/pdf_reader/test_text_extractor.py`(unit-1 소유, 이번 06 재검증이 경계 케이스 8건을 추가로 수정)만 이 실행과 직접 관련된 정식 산출물이다. `docs/harness/units/unit-2/3/4-*.md`, `pdf_to_hwpx/pdf_reader/image_extractor.py`, `pdf_to_hwpx/pdf_reader/table_recognizer.py`, `pdf_to_hwpx/hwpx_kernel/schema.py`, `tests/hwpx_kernel/`, `tests/pdf_reader/test_image_extractor.py`, `tests/pdf_reader/test_table_recognizer.py`, `docs/harness/verify-log_unit-2-test.md`/`verify-log_unit-4-test.md`는 병렬로 동시 진행 중인 unit-2/3/4 소유이며 이번 재검증이 손대지 않았다. `.harness-tmp/`는 `.gitignore`로 인해 애초에 `git status`에 나타나지 않으며, 위에서 설명한 대로 이 재검증이 만든 항목은 전부 정리되었다.
- 이번 재검증 도중 강제 중단(TaskStop 등)이 있었는가: **[x] 없음.** 착수 전 `.harness-tmp/` 잔여물 부재를 먼저 확인했고(위 참고), 재검증 세션 자체는 중단 없이 연속 실행됐다.
- **이 절은 완료되었고 `git status`가 (unit-1 소유 관점에서) 깨끗함을 확인했다. 6절의 DEF-001이 Fixed로 전환되었으므로 12절 최종 판정은 PASS다.**

## 8. 리스크 및 잔존 이슈
- **DEF-001은 재검증(12절)에서 Fixed로 확인되어 더 이상 Open 리스크가 아니다.**
- unit-1-note.md가 이미 공유한 기존 한계(새로 발견한 결함 아님, 06단계가 결함으로 재보고하지 않음. 다만 향후 08/09 전체 테스트 단계에서 실제 영향도를 재평가할 필요는 있음을 남겨둔다):
  - 다단(멀티컬럼) 레이아웃에서 같은 세로 구간에 있는 다른 컬럼 word가 한 줄로 잘못 묶일 수 있음(재작업 이후에도 동일하게 남아있는 한계, 재작업 범위 아님).
  - 회전/기울어진 텍스트는 이 휴리스틱의 대상이 아님.
  - 폰트 미스매치로 인한 "그럴듯하지만 틀린" 디코딩은 REQ-007 감지 로직으로 잡히지 않음(TC-016으로 재현 확인, 결함 아님).
  - PUA 코드포인트 검사는 정당한 기호 폰트(Wingdings류)에 대해 오탐 가능성 있음.
  - bold/italic 추정은 폰트명 명명 관례에 의존하며 커스텀 서브셋 폰트에서 오탐/누락 가능.
  - `(cid:N)` 신호는 합성 문자열로만 검증됐고, 실제 "ToUnicode 없는 서브셋 폰트" PDF로 end-to-end 재현은 이번에도 수행하지 못함(non-trivial, note와 동일).
  - **(재검증분, 신규 문서화 — 새 결함 아님)** 겹침 비율 임계값(0.5) 기반 판정의 알려진 한계 2건을 재검증 과정에서 실제로 재현해 확인했다(12절 TC-032/TC-033 참고):
    1. 위첨자처럼 세로로 살짝만 겹치는(비율<0.5) 짧은 word는 시각적으로 같은 줄이라도 별도 줄로 분리될 수 있음.
    2. 사슬형 전이적 병합(A-B 겹침, B-C 겹침, A-C는 비겹침)이 발생하면 시각적으로 완전히 겹치지 않는 A와 C까지 한 줄로 묶일 수 있음 — unit-1-note.md 재작업 절이 이미 예견한 한계이며, 통상 문서에서는 발생 가능성이 낮다고 판단됨. 08/09 전체 테스트에서 실제 문서 샘플로 이 한계의 실제 영향도를 재평가할 것을 권고한다.
- 후속 조치 필요 항목: 없음(1차 실행 시점의 "05단계로 반려" 항목은 재작업 완료로 해소됨, 12절 참고). 위 신규 문서화 한계 2건은 결함이 아니라 08/09 단계 참고용 리스크로만 승계한다.

## 9. 결론 및 판정
- 1차 실행(2026-09-28) 당시 판정: **FAIL**(DEF-001, 사유는 6절 원본 그대로 보존).
- **최종 판정(재검증 반영): [x] PASS — 12절 참고.** DEF-001이 Fixed로 확인되었고, 나머지 11개 AC 조건 및 새로 추가한 8개 경계 케이스 전부 PASS. 07단계(통합테스트)로 handoff 가능.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)

### 1차 실행 당시 내부 검증(원본 보존)
- 1차 검증 결과 요약: AC-1~AC-5 12개 조건에 대해 테스트 함수가 1:1로 존재하는지 표로 대조(5절 커버리지 100% 확인). 이 과정에서 테스트 코드 자체의 인프라 버그(FIXTURE_DIR 경로 계산 오류)를 발견해 직접 수정. 전체 재실행 결과 `test_font_size_switch_on_same_line_creates_separate_blocks`(AC-2-4) 1건이 FAIL로 확인됨 — 실제 pdfplumber 좌표를 직접 조회해 테스트 기대값이 아니라 제품 코드의 실제 결함임을 검증.
- 2차 검증 결과 요약: "이 테스트를 통과했다고 다음 단계(07 통합테스트)에 넘겨도 되는가"를 의심하며 재검토 — TC-007 실패가 일반화되는 결함인지 확인하기 위해 3단어 스텁 케이스(TC-026)를 추가, 순서 뒤바뀜뿐 아니라 서로 떨어진 두 단어가 하나의 블록으로 잘못 합쳐지는 증상까지 확인해 이 결함이 알고리즘 구조상 재현 가능함을 확증. 07단계로 넘길 수 없는 상태임을 확정.
- 검증 로그 파일 경로: 이 결과서(`docs/harness/units/unit-1-test.md`) 10절에 직접 기록.

**재검증(2026-09-28, 규칙 F)의 내부 검증 1차/2차는 12절에 별도로 기록한다.**

---

## 11. 공유 문서 갱신 요청 (병렬 실행 규칙 — 직접 수정하지 않음)

**이 절의 값은 1차 실행(FAIL) 시점 기준이다. 재검증 완료 후 최신 갱신 요청은 12절 하단을 참고할 것 — 12절 내용이 최신이며 우선한다.**

`docs/harness/traceability.md`에 아래 갱신을 요청한다(1차 실행 시점 기록, 참고용 보존):

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-002 | 단위테스트 | FAIL (unit-1, 06단계 — DEF-001, 05단계 재작업 필요) |
| REQ-006 | 단위테스트 | 조건부 — 입력측(unit-1) DEF-001로 FAIL, unit-15 착수 전 해소 필요 |
| REQ-007 | 단위테스트 | PASS (unit-1, 06단계 — AC-3 6/7/8 전 조건 PASS. 단 같은 파일 내 DEF-001로 unit-1 전체 06단계 최종 판정은 FAIL) |

---

## 12. 재검증(2026-09-28, 규칙 F) — DEF-001 수정 확인

### 12-1. 배경
05-unit-developer가 6절 DEF-001을 수정했다(상세 근거: `docs/harness/units/unit-1-note.md` "재작업(2026-09-28)" 절). 요지: `_group_words_into_lines`의 "같은 줄" 판정을 고정 top 허용오차(2.5pt) 대신 word 세로 구간 `[top, bottom]` 겹침 비율(`_LINE_OVERLAP_RATIO=0.5`) 기반으로 교체하고, "같은 줄 판정"과 "줄 내부 정렬"의 책임을 분리했다. 이번 06단계는 이 재작업 결과를 독립적으로 재검증한다.

### 12-2. 재검증 환경 (규칙 K)
- 착수 전 확인: `.harness-tmp/`에 이전(중단된) 실행의 잔여물이 있는지 먼저 확인 — 없음(빈 디렉터리/미존재).
- `.harness-tmp/venv_06_unit1_recheck/`(신규 격리 venv, 병렬 진행 중인 unit-2 재작업 확인용 venv와 겹치지 않게 `unit1_recheck` 식별자 사용)에 `pip install -e ".[dev]" reportlab coverage` 설치.
- Python 3.13.15, Windows 11 Pro. 05가 제공한 로컬 확인 결과를 그대로 신뢰하지 않고 06이 직접 독립 재실행했다.

### 12-3. 재검증 우선순위 실행 결과

1. **DEF-001 재현 테스트 2건 직접 재실행**:
   - `pytest tests/pdf_reader/test_text_extractor.py::test_font_size_switch_on_same_line_creates_separate_blocks -q` → **PASS**. `blocks[0].text=="Small"`, `blocks[1].text=="BIGGER"`, `font_size` 각각 10.0/24.0 — 기존(1차 실행 당시) 기대값과 동일한 assert 문을 변경 없이 그대로 사용해 재현했으며, 결과가 기대값과 일치함을 확인(과거 `["BIGGER","Small"]`로 뒤바뀌던 증상 해소).
   - `pytest tests/pdf_reader/test_text_extractor.py::test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub -q` → **PASS**. `texts == ["Small","BIGGER","Tail"]` — 순서 뒤바뀜과 오병합("Small Tail") 증상 모두 해소됨을 확인.
2. **`tests/pdf_reader/test_text_extractor.py` 전체 회귀**: `pytest tests/pdf_reader/test_text_extractor.py -q` → 기존 36개 **전부 PASS**(05가 보고한 결과와 06 독립 재실행 결과 일치).
3. **새 겹침 비율 기반 로직의 새 경계 케이스 탐색** — 06단계가 이번에 직접 작성해 `tests/pdf_reader/test_text_extractor.py`에 추가한 8개 테스트(파일 하단, "06단계 재검증(2026-09-28, 규칙 F) 추가" 절):

   | ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail | 테스트 함수 |
   |----|----------|-----------|-----------|-----------|------|
   | TC-027 | 겹침 비율이 **정확히 0.5**(임계값 그 자체, `>=` 비교)인 경계 → 같은 줄로 병합 | 1줄(`["A","B"]`) | 일치 | Pass | `test_group_words_into_lines_overlap_ratio_exactly_at_threshold_merges` |
   | TC-028 | 겹침 비율이 **0.5 바로 아래**(0.499) → 다른 줄로 분리 | 2줄(`["A"]`,`["B"]`) | 일치 | Pass | `test_group_words_into_lines_overlap_ratio_just_below_threshold_splits` |
   | TC-029 | 세로 구간이 **전혀 겹치지 않는**(overlap<=0) 두 word → 다른 줄 | 2줄 | 일치 | Pass | `test_group_words_into_lines_completely_non_overlapping_words_are_different_lines` |
   | TC-030 | 아래첨자류: 짧은 word가 큰 word의 세로 구간 안에 완전히 포함(overlap/min(height)=1.0) → 같은 줄로 병합 | 1줄(`["Main","sub"]`) | 일치 | Pass | `test_group_words_into_lines_subscript_like_short_word_contained_in_line_merges` |
   | TC-031 | 위첨자류: 짧은 word가 본문 word 위쪽 경계에 살짝만 겹침(ratio=0.33<0.5) → 별도 줄로 분리(**알려진 한계**, 8절에 리스크로 승계, 결함 아님) | 2줄 | 일치 | Pass(한계로 확인, 결함 아님) | `test_group_words_into_lines_superscript_like_short_word_offset_above_splits` |
   | TC-032 | 전이적 병합 사슬: A-B(ratio 0.6), B-C(ratio 0.5) 겹치지만 A-C(ratio 0.1)는 임계값 미만 → 셋 다 한 줄로 병합(**알려진 한계**, unit-1-note.md가 이미 예견, 8절 리스크로 승계, 결함 아님) | 1줄(`["A","B","C"]`) | 일치 | Pass(한계로 확인, 결함 아님) | `test_group_words_into_lines_transitive_merge_chain_known_limitation` |
   | TC-033 | `_group_words_into_lines([])` 직접 호출(방어 분기, 커버리지 재확인 중 발견한 미실행 라인) | `[]` | 일치 | Pass | `test_group_words_into_lines_empty_list_direct_call_returns_empty_list` |
   | TC-034 | 클러스터 내 멤버 2개(세로 구간 다름) 중 겹치지 않는 멤버는 건너뛰고(`overlap<=0` → `continue`) 겹치는 멤버로 매칭(커버리지 재확인 중 발견한 미실행 라인) | 1줄(`["W1","W2","W3"]`) | 일치 | Pass | `test_group_words_into_lines_cluster_member_overlap_check_skips_non_overlapping_member` |

   8건 전부 PASS. TC-031/TC-032는 새로 발견한 결함이 아니라 unit-1-note.md 재작업 절 "남은 한계"가 이미 예견한 동작이 실제로 재현됨을 확인한 것이며, 8절에 리스크로 승계했다(6절 결함 목록에는 추가하지 않음).

4. **전체 회귀(`pytest tests/ -q`)**: 최종 **216 passed, 3 failed**(`test_text_extractor.py` 44개 전부 포함해 통과, 실패 3건은 전부 `tests/pdf_reader/test_image_extractor.py`). 실패 3건 전부 파일 경로/내용을 확인한 결과 병렬 진행 중인 **unit-2(`image_extractor.py`)의 자체 DEF-001/DEF-002 관련 실패**이며 unit-1(`text_extractor.py`)과 무관함을 재확인했다(1차 실행 당시 05가 보고한 2 failed와 이번 3 failed의 차이도 unit-2 자체 재작업 진행 상황 변화로 보이며, 이 파일 범위(text_extractor.py) 밖의 일이므로 unit-1 06 판정에 영향 없음. 원인이 이 단위 밖에 있을 가능성이 있음을 명시 — 병렬 규칙 F 관련 보고).
5. **라인 커버리지(`coverage.py`)**: 44개 테스트 기준 `pdf_to_hwpx/pdf_reader/text_extractor.py` **102 문장, 미실행 0, 100%**. TC-033/TC-034를 추가하기 전에는 98%(2줄 미실행: `_group_words_into_lines`의 빈 리스트 방어 분기, `_has_vertical_overlap`의 `overlap<=0` continue 분기)였으나, 두 분기를 직접 겨냥한 테스트를 추가해 100%로 확인했다.

### 12-4. AC-1~AC-5 (12개) 재확인
4절 표(TC-001~TC-034, 재검증 컬럼) 기준으로 12개 조건 전부 실제 PASS로 확인됨(1차 실행 시 유일하게 FAIL이었던 AC-2-4/TC-007 포함). AC-ID ↔ 테스트 함수 1:1 매핑은 4절 "비고" 컬럼과 12-3절 표에서 모두 확인 가능.

### 12-5. 게이트 재확인 (05단계 정적 분석/자체 코드 리뷰)
- `docs/harness/units/unit-1-note.md` "재작업(2026-09-28)" 절의 "게이트 1/게이트 2 재검증" 항목을 확인 — `py_compile` 성공, lint/type-check 설정 부재 재확인, 자체 코드 리뷰 체크리스트 6개 항목 전부 근거와 함께 재확인됨을 note에서 직접 확인했다. 06단계가 별도로 `python -m py_compile pdf_to_hwpx/pdf_reader/text_extractor.py`를 재실행해 컴파일 성공을 독립 확인했다(위 환경에서 실행, 결과 생략 — 정상 종료).

### 12-6. 내부 검증 (재검증분, 최소 2회)
- **1차 검증**: AC-1~AC-5 12개 조건 전부에 대해 4절 표의 "재검증" 컬럼이 실제 pytest 실행 결과(PASS)와 일치하는지 대조했다. 특히 DEF-001의 근본 원인이었던 AC-2-4(TC-007)와 그 확장(TC-026)이 실제로 기대값과 정확히 일치하는 결과를 냈는지(단순히 "에러 없음"이 아니라 `texts == ["Small","BIGGER","Tail"]`처럼 값 자체를 비교) 재확인했다. 테스트 코드 자체가 완화(assert를 느슨하게 바꿔 통과시키는 식)되지 않았는지도 diff 비교로 확인 — TC-007/TC-026의 assert 문은 1차 실행 당시와 재검증 시점에 문자 그대로 동일함을 확인했다(테스트를 쉽게 만들어 억지로 통과시킨 것이 아님).
- **2차 검증**: "이 테스트를 통과했다고 07단계(통합테스트)에 넘겨도 되는가"를 의심하며 재검토 — 05가 교체한 알고리즘(겹침 비율 기반)이 기존 결함만 우연히 피해가고 새로운 유형의 결함을 도입하지 않았는지가 핵심 우려였다. 이를 위해 새 알고리즘의 임계값 경계(정확히 0.5, 0.5 미만) 2건, 완전 비겹침 1건, 첨자류 2건(병합되는 경우/분리되는 경우 양쪽 다), 전이적 병합의 알려진 한계 1건, 방어적 분기 2건 — 총 8건을 직접 설계해 추가했다. 그 결과 새로운 결함은 발견되지 않았고(전부 PASS), 다만 이미 note가 문서화한 두 가지 한계(위첨자 분리, 전이적 병합 사슬)가 실제로 재현 가능함을 확인해 8절 리스크로 명시적으로 승계했다 — 이 한계들이 "새로 발견한 결함"이 아니라 "이미 알려진, 이번 수정 범위 밖의 한계"임을 note 원문과 대조해 확정했다(재작업 범위를 벗어난 것을 06이 결함으로 임의 확대하지 않기 위함). 이 재검토를 통해 07단계로 넘겨도 되는 상태임을 확정했다.
- 검증 로그 파일 경로: 이번 재검증 결과는 이 결과서(`docs/harness/units/unit-1-test.md`) 12절에 직접 기록했다(1차와 동일한 방침 — 결함 발견/재검증 중심 기록이 6·8·9절과 강하게 연결되어 있어 별도 `verify-log_unit-1-test.md` 파일 대신 이 문서 내 기록이 추적성을 더 높인다고 판단).

### 12-7. 최종 판정
- **PASS.** DEF-001 Fixed 확인(재현 테스트 2건 + 확장 3-word 테스트 전부 PASS), 전체 회귀 36개(원본) + 8개(신규 경계 케이스) = 44개 전부 PASS, AC-1~AC-5(12개) 전 조건 실제 PASS, 라인 커버리지 100%, 새로 도입된 알고리즘 자체의 결함 재유입 없음(내부검증 2회 완료). 07단계(통합테스트) handoff 가능 상태로 표시한다.

### 12-8. 공유 문서 갱신 요청 (최신, 병렬 실행 규칙 — 직접 수정하지 않음)

`docs/harness/traceability.md`에 아래로 최종 갱신을 요청한다(11절의 1차 FAIL 기록을 대체):

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-002 | 단위테스트 | **PASS** (unit-1, 06단계 재검증 완료 — DEF-001 Fixed 확인, `docs/harness/units/unit-1-test.md` 12절 참고. AC-1~AC-5 12/12 PASS) |
| REQ-002 | 구현 상태 | Implemented (unit-1, 05단계 재작업 완료 + 06단계 재검증 PASS. `_group_words_into_lines`를 겹침 비율(`_LINE_OVERLAP_RATIO`) 기반 판정으로 교체. 07단계 진행 가능) |
| REQ-006 | 단위테스트 | 조건부 PASS — 입력측(unit-1) 텍스트 추출 DEF-001 Fixed 확인 완료. 실제 NFC 정규화 자체는 여전히 unit-15 소관(Not Started) |
| REQ-007 | 단위테스트 | **PASS** (unit-1, 06단계 — AC-3 6/7/8 전 조건 PASS, 재검증에서도 동일하게 재확인. `docs/harness/units/unit-1-test.md` TC-010~TC-016 참고) |

추가로 이 결과서는 이제 **07단계(통합테스트)로 handoff 가능**하다 — DEF-001이 Fixed로 확인되었고 06단계 재검증(규칙 B 내부검증 2회 포함)이 완료되었다.
