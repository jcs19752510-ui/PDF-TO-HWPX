# 테스트 결과서 (Test Result Report) — unit-0

## 1. 개요
- 테스트 대상: 작업 단위 unit-0(`pdf_to_hwpx/common/exceptions.py`, `pdf_to_hwpx/common/logging_setup.py`, `pdf_to_hwpx/pdf_reader/loader.py`, 프로젝트 스캐폴딩/`pyproject.toml`)
- 테스트 유형: 단위(06단계)
- 적용 Tier: Standard
- 적용 속도 트랙: L3(일반) — 전 섹션 작성, 내부 검증(규칙 B) 2회 원문대로 적용
- 병렬 실행 정보: 단독 실행 (unit-0은 "공통 선행" 단위로 병렬 웨이브에 속하지 않음)
- 테스트 목적: unit-0-note.md가 명시한 인수조건 AC-1~AC-4(총 25개 구체 조건)를 실제 pytest 코드로 1:1 검증하고, 정상/경계값/예외입력 케이스를 통해 03단계 설계서(§4 예외계층, §6 개인정보/로깅 마스킹, §7 로깅)와 구현이 일치하는지 근거를 남긴다.
- 관련 산출물:
  - `docs/harness/03-system-design.md` §4(API/예외), §6(보안/개인정보), §7(운영/로깅)
  - `docs/harness/units/unit-0-note.md`(구현 노트, AC-1~AC-4)
  - `pdf_to_hwpx/common/exceptions.py`, `pdf_to_hwpx/common/logging_setup.py`, `pdf_to_hwpx/pdf_reader/loader.py`, `pyproject.toml`
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-27

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope):
  - `common/exceptions.py`의 예외 계층 구조·생성자 동작 (AC-1, 5개 조건)
  - `common/logging_setup.py`의 로그 파일 생성/레벨/컨텍스트 부착/개인정보 마스킹/중복 핸들러 방지/로테이션 설정 (AC-2, 7개 조건)
  - `pdf_reader/loader.py`의 정상 로드/타입 계약/암호화·손상·빈 PDF·존재하지 않는 경로 예외 변환/리소스 해제(`close()`, 컨텍스트 매니저)/실패 경로 리소스 누수 방지 (AC-3, 9개 조건)
  - 패키지 스캐폴딩(`pip install -e ".[dev]"`, 버전 문자열, `py_compile`, 서브패키지 `__init__.py` import 가능성) (AC-4, 4개 조건)
  - AC에 명시되지 않았으나 위험도가 높다고 판단해 추가한 케이스: 0바이트 파일(내부검증 2차에서 추가), 페이지 트리 구조가 손상된 PDF(방어 분기 실제 트리거), 상위 디렉터리 자체가 없는 경로, `with` 블록 내부 예외 발생 시 리소스 해제, `get_logger()` 초기화 전/후 동작, `also_log_to_console` 옵션이 중복 방지 로직에 의해 실수로 지워지지 않는지
- 제외 범위(Out-of-Scope) 및 사유:
  - `pdf_reader/loader.py`의 `pdfplumber.open()` 실패 분기(소스 105~106행): pypdf가 이미 페이지 트리를 성공적으로 판독한 PDF는 pdfplumber(pdfminer.six 기반, lazy 파싱)도 `open()` 시점에는 거의 항상 성공하므로, 실제 PDF 바이트 조작으로 이 분기만 독립적으로 재현하는 실험을 반복했으나(§8 리스크 참고) 성공하지 못했다. Mock으로 강제 실패시키는 방법도 있으나, "실제 산출물로 증명"이라는 06단계 원칙에 따라 인위적 mock 대신 정직하게 커버리지 공백으로 남기고 8절에 리스크로 기록했다.
  - 텍스트/이미지/표 실제 파싱(unit-1/2/3 소관), `hwpx_kernel/schema.py`의 IR(unit-4 소관), CLI/GUI 진입점(unit-11/13 소관): unit-0-note.md가 명시적으로 범위 밖으로 선언했으며 이번 호출에서도 해당 파일이 전혀 수정되지 않았음을 확인했다.
  - `HWPX_MIN_SUPPORTED_VERSION` 정확한 버전 값 실측: 03 §8-3 "확인 필요"로 이미 이관된 별도 이슈이며 unit-0 파일 범위에 없음.
  - 대용량(수백MB) PDF 실측 성능: 03 §5는 500MB 초과 시 경고만 요구하며 이는 orchestrator(unit-8)의 `ConversionWarning` 책임이라 unit-0 범위 밖. 대신 확인 가능한 범위인 다중 페이지(20페이지)로 카운팅 정확성의 경계값을 확인했다.

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro, Python 3.13.15(리포지토리 `pyproject.toml`이 `>=3.11` 요구, 실행 환경은 그 상한 내 최신 버전)
- 격리 가상환경(규칙 K): `.harness-tmp/venv_06_unit0/`에 신규 venv를 만들고 `pip install -e ".[dev]"`로 프로젝트를 설치했다. 06단계 테스트 전용으로 `reportlab`(정상 PDF 픽스처 생성용, 프로젝트 런타임 의존성 아님)과 `coverage`(라인 커버리지 측정용)를 추가 설치했다 — 둘 다 `pyproject.toml`에는 반영하지 않았다(테스트 도구일 뿐 제품 의존성이 아님).
- 테스트 데이터: 실제 PDF 바이트로 즉석 생성한 픽스처(모두 `tests/conftest.py`의 `pdf_fixtures` 세션 픽스처가 `.harness-tmp/pdf_fixtures_06_unit0/`에 생성, 세션 종료 시 자동 삭제) — mock을 쓰지 않고 실제 라이브러리(pypdf/reportlab)로 만든 진짜 PDF로 검증했다.
  - `normal_1page.pdf`/`normal_3page.pdf`/`normal_20page.pdf`: reportlab으로 생성한 정상 텍스트 PDF(한글 포함)
  - `empty_0page.pdf`: `pypdf.PdfWriter()`로 페이지를 추가하지 않고 저장한, 구조는 유효하나 0페이지인 PDF
  - `encrypted.pdf`: `pypdf.PdfWriter().encrypt(user_password=..., owner_password=...)`로 만든 실제 암호화 PDF
  - `corrupted_no_header.pdf`: `%PDF-` 헤더 자체가 없는 임의 바이트
  - `corrupted_truncated.pdf`: 정상 PDF를 절반만 남기고 잘라 트레일러/xref가 깨진 PDF
  - `corrupted_page_tree.pdf`: 정상 PDF의 `/Pages` 객체 `/Kids` 배열을 정규식으로 찾아 배열이 아닌 값으로 치환 — pypdf가 `PdfReader()` 생성에는 성공하지만 `len(reader.pages)` 순회에서 실패하는 상황을 재현(loader.py의 별도 방어 분기 실제 트리거)
  - `zero_byte.pdf`: 완전히 빈(0바이트) 파일(0페이지 PDF와는 다른 별개의 경계값, 내부검증 2차에서 추가)
  - `does_not_exist_unit0.pdf`: 실제로 생성하지 않은 경로(파일 부재 케이스), `tmp_path`로 만든 "상위 디렉터리 자체가 없는 경로"도 별도 케이스로 사용
- 전제 조건: `pip install -e ".[dev]"`가 사전에 성공해 `pdf_to_hwpx` 패키지와 `pytest`가 import 가능한 상태(이 전제 자체가 AC-4-1 검증의 일부이기도 함).

## 4. 테스트 케이스 및 결과

> 76개(파라미터화 포함, 최종 77개) pytest 테스트 함수를 AC-ID 단위로 묶어 표시한다. "비고"에 실제 테스트 함수명(파일 경로 포함)을 적어 1:1 추적이 가능하게 했다. 전부 실행하여 **77 passed, 0 failed** (실행 로그는 6절 하단 참고).

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 (AC-ID / 테스트 함수) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | ConversionError/PdfLoadError/HwpxWriteError/OcrEngineError가 ConversionError(자기 자신 포함)의 하위클래스 | - | `issubclass(cls, ConversionError)` 확인(4종 파라미터화) | 4종 전부 True | 4종 전부 True | Pass | AC-1-1 / `tests/common/test_exceptions.py::test_top_level_classes_inherit_conversion_error` |
| TC-002 | EncryptedPdfError/CorruptedPdfError/EmptyPdfError가 PdfLoadError 하위 | - | `issubclass` 확인(3종) | 3종 전부 True | 3종 전부 True | Pass | AC-1-2 / `test_pdf_load_error_subclasses` |
| TC-003 | ContainerBuildError/OutputPathError가 HwpxWriteError 하위 | - | `issubclass` 확인(2종) | 2종 전부 True | 2종 전부 True | Pass | AC-1-3 / `test_hwpx_write_error_subclasses` |
| TC-004 | TesseractNotFoundError가 OcrEngineError 하위 | - | `issubclass` 확인 | True | True | Pass | AC-1-4 / `test_tesseract_not_found_error_subclass` |
| TC-005 | 예외 클래스 10종 전부가 메시지 문자열 1개로 생성 가능 | - | `raise cls("메시지")` 후 `str(e)` 비교(10종 파라미터화) | 10종 전부 메시지 일치 | 10종 전부 일치 | Pass | AC-1-5 / `test_all_classes_constructible_with_message` |
| TC-006(추가) | 예외 계층 클래스 총 개수 정합성(기반1+중간2+리프6+최상위=10) | - | 클래스 집합 크기 확인 | 10 | 10 | Pass | 범위 외 방어 확인 / `test_exception_hierarchy_has_exactly_nine_classes_plus_base` |
| TC-007 | `setup_logging(log_dir=<임시디렉터리>)` 호출 후 로그 파일 생성 | tmp_path | 호출 후 `<tmp>/pdf-to-hwpx.log` 존재 확인 | 파일 존재 | 파일 존재 | Pass | AC-2-1 / `tests/common/test_logging_setup.py::test_setup_logging_creates_log_file` |
| TC-008 | 기본(verbose=False) 로거 레벨 INFO | tmp_path | `setup_logging(log_dir=tmp_path)` 후 `.level` 확인 | INFO | INFO | Pass | AC-2-2 / `test_default_level_is_info` |
| TC-009 | verbose=True 로거 레벨 DEBUG | tmp_path | `setup_logging(verbose=True, ...)` 후 `.level` 확인 | DEBUG | DEBUG | Pass | AC-2-2 / `test_verbose_level_is_debug` |
| TC-010 | 로그 각 줄에 app=/python=/os= 포함 | tmp_path | INFO 로그 1줄 기록 후 파일 내용 파싱 | 3개 토큰 모두 포함 | 모두 포함 | Pass | AC-2-3 / `test_log_lines_include_app_python_os_context` |
| TC-011 | `SessionFileRegistry(verbose=False)`가 doc#1, doc#2로 마스킹, 원본 경로 미포함 | - | 민감 경로 2개 연속 register | "doc#1","doc#2", 원본 문자열/이름 미포함 | 일치 | Pass | AC-2-4 / `test_session_file_registry_masks_paths_by_default` |
| TC-012 | `SessionFileRegistry(verbose=True)`는 `str(path)`와 동일 문자열 반환 | - | register 호출 | `str(path)`와 동일 | 동일 | Pass | AC-2-5 / `test_session_file_registry_exposes_full_path_when_verbose` |
| TC-013(추가) | 경계값: 파일 10개 연속 등록 시 순번 어긋나지 않음 | - | register x10 | doc#1..doc#10 순서 | 일치 | Pass | 범위 외 경계 / `test_session_file_registry_sequence_increments_across_many_files` |
| TC-014(추가) | `describe_input_for_log` 저수준 헬퍼가 verbose 플래그를 따름 | - | verbose=False/True 각각 호출 | False→라벨, True→전체경로 | 일치 | Pass | 범위 외(§6-2 보완 헬퍼) / `test_describe_input_for_log_helper_respects_verbose_flag` |
| TC-015 | `setup_logging()` 2회 호출해도 핸들러 중복(로그 중복 기록) 없음 | tmp_path | 2회 호출 후 핸들러 개수 및 로그 1줄 기록 후 중복 라인 수 확인 | 핸들러 1개, 중복 라인 0 | 핸들러 1개, 중복 없음 | Pass | AC-2-6 / `test_setup_logging_twice_does_not_duplicate_handlers` |
| TC-016(추가) | `also_log_to_console=True`가 두 번째 핸들러를 실제로 추가(중복방지 로직이 과도하게 지우지 않는지) | tmp_path | 호출 후 `len(logger.handlers)` | 2 | 2 | Pass | 범위 외 방어 확인 / `test_setup_logging_also_log_to_console_adds_second_handler` |
| TC-017 | `RotatingFileHandler` 상수(maxBytes=5MB, backupCount=5) | - | 모듈 상수 값 확인 | 5*1024*1024, 5 | 일치 | Pass | AC-2-7(설정값) / `test_rotating_file_handler_configured_constants` |
| TC-018 | 실제 rollover 동작(작은 maxBytes 주입) | tmp_path, monkeypatch | MAX_BYTES=200, BACKUP_COUNT=2로 주입 후 로그 200줄 기록 | `.log.1` 등 회전 파일 생성, backupCount 이내 | 회전 파일 생성 확인 | Pass | AC-2-7(실동작) / `test_rotating_file_handler_actually_rolls_over` |
| TC-019(추가) | `get_logger()`가 `setup_logging()`이 반환한 것과 동일 인스턴스 | tmp_path | setup 후 get_logger() 비교 | `is` 동일 | 동일 | Pass | 범위 외 API 확인 / `test_get_logger_returns_same_logger_after_setup` |
| TC-020(추가) | `setup_logging()` 미호출 상태에서 `get_logger()`가 예외 없이 핸들러 없는 로거 반환 | - | 핸들러 제거 후 get_logger() 호출 | 예외 없음, handlers=[] | 일치 | Pass | 범위 외 방어 확인 / `test_get_logger_before_setup_returns_handlerless_logger_without_raising` |
| TC-021(추가) | `get_default_log_dir()`가 platformdirs 기반 경로 반환 | - | 반환값에 "pdf-to-hwpx" 포함 확인 | 포함 | 포함 | Pass | 범위 외 확인 / `test_get_default_log_dir_uses_platformdirs` |
| TC-022 | 정상 PDF(1/3/20페이지)에서 `load_pdf`가 예외 없이 `PdfDocument` 반환, `page_count` 일치 | 픽스처 | load_pdf 호출 후 page_count 비교(20페이지=경계값) | 1/3/20 각각 일치 | 일치 | Pass | AC-3-1 / `tests/pdf_reader/test_loader.py::test_load_pdf_normal_returns_correct_page_count` |
| TC-023 | `plumber_pdf`가 `pdfplumber.PDF`, `pypdf_reader`가 `pypdf.PdfReader` 인스턴스 | 픽스처 | `isinstance` 확인 | 둘 다 True | 둘 다 True | Pass | AC-3-2 / `test_load_pdf_returns_correct_handle_types` |
| TC-024 | 암호화 PDF → `EncryptedPdfError` | 픽스처(encrypted.pdf) | load_pdf 호출 | EncryptedPdfError 발생 | 발생 | Pass | AC-3-3 / `test_load_pdf_encrypted_raises_encrypted_pdf_error` |
| TC-025 | 0페이지 PDF → `EmptyPdfError` | 픽스처(empty_0page.pdf) | load_pdf 호출 | EmptyPdfError 발생 | 발생 | Pass | AC-3-4 / `test_load_pdf_zero_pages_raises_empty_pdf_error` |
| TC-026 | PDF 헤더 없는 파일 → `CorruptedPdfError` | 픽스처(corrupted_no_header.pdf) | load_pdf 호출 | CorruptedPdfError 발생 | 발생 | Pass | AC-3-5 / `test_load_pdf_no_header_raises_corrupted_pdf_error` |
| TC-027 | 절단되어 구조가 깨진 PDF → `CorruptedPdfError` | 픽스처(corrupted_truncated.pdf) | load_pdf 호출 | CorruptedPdfError 발생 | 발생 | Pass | AC-3-5 / `test_load_pdf_truncated_structure_raises_corrupted_pdf_error` |
| TC-028(추가) | 0바이트 파일 → `CorruptedPdfError`(0페이지 PDF와 별개 경계값) | 픽스처(zero_byte.pdf) | load_pdf 호출 | CorruptedPdfError 발생 | 발생 | Pass | 내부검증 2차 추가 / `test_load_pdf_zero_byte_file_raises_corrupted_pdf_error` |
| TC-029(추가) | `/Pages`의 `/Kids`가 배열이 아닌 손상 PDF(pypdf 생성은 성공, 페이지 순회만 실패) → `CorruptedPdfError` | 픽스처(corrupted_page_tree.pdf) | load_pdf 호출 | CorruptedPdfError 발생(loader.py 별도 방어 분기 실제 트리거) | 발생 | Pass | 방어 분기 실증 / `test_load_pdf_corrupted_page_tree_raises_corrupted_pdf_error` |
| TC-030 | 존재하지 않는 경로 → `CorruptedPdfError` | 픽스처(생성 안 함) | load_pdf 호출 | CorruptedPdfError 발생 | 발생 | Pass | AC-3-6 / `test_load_pdf_nonexistent_path_raises_corrupted_pdf_error` |
| TC-031(추가) | 상위 디렉터리 자체가 없는 깊은 경로 → `CorruptedPdfError` | tmp_path | load_pdf 호출 | CorruptedPdfError 발생 | 발생 | Pass | 범위 외 경계 / `test_load_pdf_nonexistent_path_deep_missing_directory` |
| TC-032 | `close()` 호출 후 내부 스트림이 닫힘 | 픽스처 | close() 전/후 `_stream.closed` 확인 | False→True | 일치 | Pass | AC-3-7 / `test_close_marks_internal_stream_closed` |
| TC-033 | `with load_pdf(path) as doc:` 정상 동작, 블록 종료 시 자동 해제 | 픽스처 | with 블록 진입/종료 후 스트림 상태 확인 | 블록 내 open, 종료 후 closed | 일치 | Pass | AC-3-8 / `test_context_manager_closes_resources_on_exit` |
| TC-034(추가) | with 블록 내부에서 임의 예외 발생해도 `__exit__`이 호출되어 해제됨 | 픽스처 | 블록 내부에서 ValueError 발생시키고 예외 전파 확인 | ValueError 전파 + 스트림 closed | 일치 | Pass | 범위 외 경계 / `test_context_manager_closes_resources_even_on_exception_inside_block` |
| TC-035 | 실패 경로(암호화/0페이지/손상2종/페이지트리손상)에서 내부 스트림 누수 없음 | 픽스처 5종 | `Path.open`을 spy로 감싸 열린 스트림 추적, 예외 후 `.closed` 확인(5종 파라미터화) | 5종 전부 closed=True | 5종 전부 True | Pass | AC-3-9 / `test_no_stream_leak_on_failure_paths` |
| TC-036 | ResourceWarning을 error로 승격한 상태에서도 경고 없이 종료 | 픽스처(encrypted.pdf) | `warnings.simplefilter("error", ResourceWarning)` 하에 실패 경로 실행 + `gc.collect()` | 경고로 인한 예외 없음 | 없음 | Pass | AC-3-9 보완 / `test_no_stream_leak_on_failure_path_resource_warning_free` |
| TC-037 | `pip install -e ".[dev]"`가 오류 없이 성공(재실행 포함) | venv 설치 완료 | `subprocess`로 재실행, returncode 확인 | 0 | 0 | Pass | AC-4-1 / `tests/test_packaging.py::test_editable_install_succeeds` |
| TC-038 | `import pdf_to_hwpx; pdf_to_hwpx.__version__ == "0.1.0"` | - | import 후 버전 문자열 비교 | "0.1.0" | "0.1.0" | Pass | AC-4-2 / `test_package_version_is_0_1_0` |
| TC-039 | unit-0 대상 파일 11개 전부 `py_compile` 통과 | - | `py_compile.compile(..., doraise=True)`(11개 파라미터화) | 전부 예외 없음 | 전부 통과 | Pass | AC-4-3 / `test_py_compile_succeeds` |
| TC-040 | 7개 서브패키지(`common`, `pdf_reader`, `hwpx_kernel`, `hwpx_writer`, `core`, `cli`, `gui`) `__init__.py` 존재 + import 가능 | - | 파일 존재 확인 + `importlib.import_module`(7종 파라미터화) | 전부 존재/import 성공 | 전부 성공 | Pass | AC-4-4 / `test_subpackage_init_exists_and_importable` |

## 5. 커버리지
- 인수조건(AC) 커버리지: **25/25 (100%)** — AC-1(5) + AC-2(7) + AC-3(9) + AC-4(4) = 25개 전 항목이 위 표의 TC-001~TC-005, TC-007~TC-012/TC-015/TC-017/TC-018, TC-022~TC-027/TC-030/TC-032/TC-033/TC-035, TC-037~TC-040에 1:1로 매핑되어 전부 PASS. 매핑 근거는 4절 "비고" 열의 AC-ID.
- 라인 커버리지(`coverage.py`, unit-0 대상 3개 소스 파일 기준):

  | 파일 | 문장 수 | 미실행 | 커버리지 |
  |---|---|---|---|
  | `pdf_to_hwpx/common/exceptions.py` | 11 | 0 | 100% |
  | `pdf_to_hwpx/common/logging_setup.py` | 53 | 0 | 100% |
  | `pdf_to_hwpx/pdf_reader/loader.py` | 49 | 2 | 96% |
  | **합계** | **113** | **2** | **98%** |

- 커버되지 않은 부분과 사유: `pdf_reader/loader.py` 105~106행(`pdfplumber.open()` 실패를 `CorruptedPdfError`로 변환하는 방어 분기). pypdf가 이미 페이지 트리를 성공적으로 읽어낸 PDF는 pdfplumber(pdfminer.six 기반)의 `open()`도 lazy 파싱 특성상 거의 항상 성공하므로, 헤더 손상/트렁케이션/페이지 트리 손상 등 여러 방식으로 재현을 시도했으나(2절 참고) 이 분기만 독립적으로 트리거하는 실제 PDF를 만들지 못했다. 인위적으로 `monkeypatch`해서 강제로 예외를 던지게 할 수도 있었으나, "실제 산출물로 증명한 것만 PASS로 적는다"는 06단계 원칙에 따라 그런 인위적 mock 검증을 PASS 근거로 쓰지 않고 정직하게 리스크로 남겼다(8절). 이 분기 자체는 03 §4-2가 요구하는 "파일을 열 수 없음 → CorruptedPdfError" 정책과 논리적으로 일관되며, 코드 구조상 명백한 방어적 중복 안전장치로 판단된다(결함 아님).

## 6. 결함(Defect) 목록

| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| (해당 없음) | | | | | |

- **결함 없음.** 근거: 4절의 77개(파라미터화 포함) 테스트 케이스가 AC-1~AC-4 25개 인수조건을 100% 커버하며 전부 PASS했고, 5절의 라인 커버리지가 98%(미커버 2줄은 결함이 아닌 재현 곤란한 방어 분기로 8절에 리스크로 별도 기록)이다. 실행 중 소스 코드(`exceptions.py`/`logging_setup.py`/`loader.py`)를 단 1바이트도 수정하지 않았다 — 테스트 작성 과정에서 발견된 문제는 모두 **테스트 코드 자체의 초안 오류**였고(내부검증 1차에서 발견·수정, `docs/harness/verify-log_unit-0-test.md` 참고), unit-0 산출물(제품 코드)의 결함은 발견되지 않았다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K

- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit0/`(격리 venv, `pip install -e ".[dev]"` + `reportlab` + `coverage`)
  - `.harness-tmp/pdf_fixtures_06_unit0/`(세션 스코프 pytest 픽스처가 생성한 PDF 8종 — `pdf_fixtures` 세션 종료 시 자동 삭제되도록 구현되어 있고, 실제로 자동 삭제됨을 확인)
  - `.harness-tmp/.coverage_06_unit0`(coverage.py 측정 데이터 파일, `--data-file` 옵션으로 위치를 명시적으로 `.harness-tmp/` 하위로 지정)
  - 사전 조사용 1회성 스크립트(`.harness-tmp/probe*.py`, `.harness-tmp/scratch2/` 등) — 픽스처/코드 동작을 미리 확인하기 위한 것으로, 정식 테스트 코드에는 포함하지 않았고 작업 도중 즉시 삭제했다.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): **[x] 아니오** — 최초 `coverage run` 실행 시 `coverage.py`의 기본 동작으로 리포지토리 루트에 `.coverage` 파일이 1회 생성된 것을 발견했다. 발견 즉시 삭제했고, 재측정부터는 `--data-file=".harness-tmp/.coverage_06_unit0"`을 명시해 같은 문제가 재발하지 않게 했다. 또한 `.harness-tmp/`에 06 실행 이전부터 남아있던 `venv-unit0/`(unit-0-note.md 5절이 언급한 05단계의 로컬 동작 확인용 잔여 venv, 06단계가 만든 것은 아님)를 발견해 함께 정리했다(하네스 위생 차원의 부수 조치이며, 이 리포지토리는 병렬 실행 중이 아니므로 "자기가 만든 것만 정리" 제약이 적용되지 않음).
- 정리(삭제) 완료 여부: **예.** `.harness-tmp/` 디렉터리 전체와 루트의 `.coverage` 파일, 그리고 `tests/`·`pdf_to_hwpx/` 하위에 생성된 `__pycache__/`(gitignore로 이미 무시되지만 위생상 함께 삭제)를 모두 제거했다.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
  ```
  $ git status --short
  ?? .claude/
  ?? .gitignore
  ?? CLAUDE.MD
  ?? HARNESS-README.md
  ?? ORCHESTRATOR.md
  ?? USAGE-GUIDE.md
  ?? automation/
  ?? docs/
  ?? pdf_to_hwpx/
  ?? pyproject.toml
  ?? templates/
  ?? tests/
  ?? "추가개선사항정리.md"
  ```
  이 결과는 세션 시작 시점의 `git status` 스냅샷과 정확히 동일하다 — 즉 이번 06단계 실행이 남긴 미추적 잔여물이 전혀 없다(`tests/`는 unit-0의 정식 산출물로서 원래도 신규 미추적 디렉터리였고, 그 안의 테스트 코드/`__init__.py`가 06단계가 의도적으로 추가한 정식 파일이다 — 삭제 대상 임시 아티팩트가 아님).
- 병렬 실행이었다면: 해당 없음(단독 실행).
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: **[x] 없음.**

## 8. 리스크 및 잔존 이슈
- **`pdf_reader/loader.py` 105~106행(pdfplumber.open() 실패 분기) 미커버**: 5절에서 설명한 대로 실제 PDF로 독립 재현이 어려운 방어적 이중 안전장치다. 향후 필드에서 이 분기가 실제로 발생하는 PDF 샘플을 확보하면 회귀 테스트로 추가할 것을 권고한다(결함이 아니라 커버리지 공백으로만 기록).
- **`HWPX_MIN_SUPPORTED_VERSION` 정확한 버전 미확정**: 03 §8-3이 이미 "확인 필요"로 이관한 별도 이슈이며 unit-0 파일 범위 밖. 이 테스트는 해당 상수를 직접 검증하지 않았다(loader.py/exceptions.py/logging_setup.py 어디에도 해당 상수가 없음을 확인).
- **후속 조치 필요 항목**:
  1. 07단계(통합테스트)는 이번 호출 지시에 따라 **여기서 이어서 수행하지 않는다** — unit-0은 "공통 선행" feature의 단독 작업 단위이며, 06·07 병합 조건(Low 등급 전용)도 적용 대상이 아니다(이 프로젝트는 Standard Tier). Feature A/B의 05→06이 모두 끝난 뒤 별도로 통합테스트가 진행되어야 한다. 이 사실을 `traceability.md` REQ-001/REQ-019 행에 명시했다(7절 별도 갱신).
  2. `pdf_reader/loader.py`가 소비되는 unit-1/2/3가 `PdfDocument.plumber_pdf`/`pypdf_reader`를 실제로 어떻게 다루는지는 그 단위들의 06/07 단계에서 별도로 검증되어야 한다(unit-0은 "연결만" 보장, 실제 소비 로직은 범위 밖).

## 9. 결론 및 판정
- [x] **PASS** — 다음 단계 진행 가능(7절 Teardown 확인 완료 전제조건 충족)

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 인수조건 커버리지 100% 확인 도중, `corrupted_page_tree` 픽스처가 reportlab이 매기는 PDF 객체 번호를 하드코딩한 패턴(`/Kids [ 3 0 R ]`)에 의존해 실제 생성물과 불일치하는 결함을 발견 → 정규식 기반 패턴 매칭으로 수정(`tests/conftest.py`)하여 조치 완료. 그 외 커버리지·명세 근거는 이상 없음.
- 2차 검증 결과 요약: "이 테스트 통과 후 다음 단계에 넘겨도 되는가" 관점에서 재검토한 결과, "0페이지 PDF"(구조 유효, AC-3-4)와 "0바이트 파일"(구조 자체 없음)이 서로 다른 경계값인데 후자가 누락되어 있음을 발견 → `zero_byte.pdf` 픽스처와 테스트를 추가하고 전체 재실행(77 passed)으로 조치 완료.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-0-test.md`
