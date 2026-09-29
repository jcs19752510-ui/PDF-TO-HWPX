# 내부 검증 로그 (Internal Verification Log)

## 대상 산출물
- 파일: `docs/harness/units/unit-0-test.md` (및 그 근거가 되는 `tests/conftest.py`, `tests/common/test_exceptions.py`, `tests/common/test_logging_setup.py`, `tests/pdf_reader/test_loader.py`, `tests/test_packaging.py`)
- 작성 에이전트: 06-unit-tester
- 적용 Tier: Standard
- 버전: v0 (초안)

## 1차 검증 (작성자 관점 자가 재검토)
- 검증자(역할): 06-unit-tester (작성자 본인)
- 일시: 2026-09-27
- 체크리스트
  - [x] 입력 계약(Input Contract)에 명시된 모든 입력을 실제로 반영했는가 — 5단계 diff(unit-0의 3개 소스 파일 + `pyproject.toml`)와 `unit-0-note.md`의 AC-1~AC-4를 모두 읽고 테스트로 옮겼다.
  - [x] 출력 계약(Output Contract)에 명시된 모든 필수 항목이 빠짐없이 존재하는가 — `test-report-template.md`의 1~10절 전 섹션을 채웠다(L3이므로 5·8·10절도 필수).
  - [x] 상위 단계 산출물과 용어/수치/범위가 모순되지 않는가 — 예외 계층 명칭·상속관계가 03 §4-2 원문과 문자 그대로 일치함을 소스 코드 대조로 확인(`ConversionError`→`PdfLoadError`/`HwpxWriteError`/`OcrEngineError` 및 각 리프). 로깅 정책(`maxBytes=5MB`, `backupCount=5`, INFO/DEBUG 전환, app/python/os 컨텍스트)도 03 §7-1 문구와 일치. 개인정보 마스킹(`doc#N`, verbose 예외) 동작도 03 §6-2 서술과 일치.
  - [x] 추측으로 채운 항목이 있는가 (있다면 "가정" 섹션에 명시했는가) — `pdf_reader/loader.py` 105~106행(pdfplumber.open() 실패 분기)은 실제로 재현하지 못해 커버되지 않았음을 추측이 아니라 "확인된 공백"으로 결과서 5절/8절에 명시했다(가정으로 얼버무리지 않음).
  - [ ] → [x] 20년차 실무자 기준으로 봤을 때 구조적/논리적 결함이 없는가 — **최초 검토 시 결함 발견(아래 참고)**, 조치 후 재확인하여 통과.
  - [x] 오탈자, 형식 오류, 누락된 표/그림 참조가 없는가 — 4절 표의 TC-ID·AC-ID 대응, 5절 커버리지 표, 7절 git status 블록을 재확인했다.
- 발견된 결함 목록:
  1. **테스트 코드 결함(제품 코드 아님)**: `tests/conftest.py`의 `_make_corrupted_page_tree_pdf`가 최초 작성 시 reportlab이 생성하는 PDF의 `/Pages` 객체 참조 번호를 `b"/Kids [ 3 0 R ]"`로 하드코딩했다. 실제로 한글 텍스트가 포함된 픽스처를 생성하자 폰트/인코딩 객체가 추가되어 참조 번호가 `4 0 R`로 밀려났고, 패턴이 매치되지 않아 `RuntimeError`를 던지도록 만든 방어 코드가 실제로 발동 — `pdf_fixtures` 세션 픽스처에 의존하는 19개 테스트 전체가 setup 단계에서 ERROR로 실패했다(pytest 실행 로그로 직접 확인).
- 조치 내용: (수정 후 → v1) `re.subn(rb"/Kids \[ \d+ 0 R \]", b"/Kids 42", data, count=1)`로 객체 번호에 의존하지 않는 패턴 매칭으로 교체(`tests/conftest.py`). 재실행하여 76개 테스트 전부 PASS(당시 기준)로 확인.

## 2차 검증 (독립 심사자 관점 — 역할 전환 재검토)
- 검증자(역할): 06-unit-tester (독립 심사자 관점으로 역할 전환 — "이 결과서를 오늘 처음 받은 07단계 담당자라면?")
- 일시: 2026-09-27
- 체크리스트
  - [x] 1차 검증에서 지적된 항목이 실제로 반영되었는가 (재확인) — `tests/conftest.py`의 정규식 패턴 치환 코드와 전체 재실행 결과(76 passed)를 재확인함.
  - [ ] → [x] 엣지 케이스/예외 상황이 누락되지 않았는가 — **재검토 중 결함 발견(아래 참고)**, 조치 후 재확인.
  - [x] 문서만 보고 다음 단계 에이전트가 추가 질문 없이 작업을 시작할 수 있는가 — 4절 표의 "비고" 열에 AC-ID와 정확한 테스트 함수 경로를 병기해 추적 가능하게 했고, 2절에서 Out-of-Scope 사유(특히 105~106행 미커버)를 구체적으로 설명해 07단계가 "왜 100%가 아닌가"를 재질문하지 않아도 되게 했다.
  - [x] 되돌리기 어려운 결정(비가역적 결정)에 대한 근거가 명시되어 있는가 — "mock으로 강제 실패시키지 않고 정직하게 커버리지 공백으로 남긴다"는 판단 근거를 5절에 명시(06단계 페르소나 원칙 "실행해보니 에러 없음만으로 PASS 처리하지 않는다"와 일관).
  - [x] 보안/성능/운영 관점에서 명백히 위험한 내용이 없는가 — 테스트가 네트워크를 전혀 사용하지 않음(REQ-011/§6-3과 일관), 하드코딩된 시크릿 없음(암호화 PDF 테스트용 패스워드는 테스트 전용 더미 문자열), 격리 venv/픽스처가 모두 `.harness-tmp/`에서 생성·정리됨을 확인.
- 발견된 결함 목록:
  1. **테스트 커버리지 공백(제품 코드 결함 아님)**: AC-3-4("0페이지 PDF → EmptyPdfError")는 "구조는 유효하나 페이지가 없는" 경우만 다루는데, "파일 자체가 완전히 비어있는(0바이트)" 경우는 별개의 경계값임에도 원래 테스트 스위트에 없었다. `load_pdf`가 이 경우에도 올바르게 `CorruptedPdfError`로 처리하는지 실증되지 않은 상태였다(06단계 필수 원칙 "명백히 위험한 케이스는 범위를 벗어나더라도 테스트" 위반 소지).
- 조치 내용: (수정 후 → v2, 최종) `tests/conftest.py`에 `zero_byte.pdf` 픽스처(`_make_zero_byte_file`)를 추가하고, `tests/pdf_reader/test_loader.py`에 `test_load_pdf_zero_byte_file_raises_corrupted_pdf_error`를 추가해 실제로 `CorruptedPdfError`가 발생함을 확인(사전에 격리 venv에서 수동 스크립트로 먼저 재현 확인 후 정식 테스트로 편입). 전체 스위트 재실행 결과 **77 passed, 0 failed**. 결과서(`unit-0-test.md`) 4절(TC-028)·5절·10절에 반영 완료.

## 최종 판정
- [x] PASS (결함 0건, 최소 2회 검증 완료) — 다음 단계로 handoff 가능
