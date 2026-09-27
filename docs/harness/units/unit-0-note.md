# unit-0 구현 노트 — 공통 선행 단위 (05-unit-developer)

- 커버 REQ-ID: REQ-001(PDF 로드), REQ-019(로깅 정책 기반)
- 소속: 공통 선행(단독 실행, 병렬 웨이브 아님)
- 속도 트랙: **L3(일반, 기본값)** — 06/07단계는 기본 절차대로 검증하면 된다(별도 완화/강화 없음).
- 선행 문서: `docs/harness/03-system-design.md`(v3, PASS), `docs/harness/04-ux-design.md`(v2, PASS), `docs/harness/02-planning.md`(v3, PASS) REQ-001/REQ-019.

---

## 1. 구현 범위

### 1-1. 프로젝트 스캐폴딩 (unit-0이 최초 단위라 오케스트레이터 지시로 추가 수행)
- `pyproject.toml` 신규 생성 — 프로젝트명 `pdf-to-hwpx`, `requires-python = ">=3.11"`(03 §2-1), `license = {text = "MIT"}`(DEC-014).
- 런타임 의존성: `pdfplumber`, `pypdf`, `lxml`, `pytesseract`, **`platformdirs`**(아래 "설계서 대비 편차" 참고). 개발 의존성: `pytest`(`[project.optional-dependencies].dev`).
- 패키지 레이아웃: **flat layout** — `pdf_to_hwpx/` 패키지를 리포지토리 루트에 03 §1-3이 명시한 트리 그대로 배치(`src/` 접두어를 두는 src-layout을 쓰지 않음).
  - **근거**: 03단계 §1-3이 트리를 `pdf_to_hwpx/common/...` 형태로 이미 구체적으로 확정해 뒀고("패키지 레이아웃(확정)" 표), 05단계 필수 원칙("설계서 명세와 실제 구현이 일치")을 지키려면 그 트리를 문자 그대로 따르는 것이 가장 편차가 적다. src-layout이 주는 이점(테스트 시 미설치 패키지의 우발적 import 방지)은 `pyproject.toml` + `pip install -e .`로 이미 편집 가능 설치를 확인했으므로(2절 참고) 이 프로젝트 규모에서는 추가 이점이 크지 않다고 판단했다.
  - 서브패키지 `common/`, `pdf_reader/`, `hwpx_kernel/`, `hwpx_writer/`, `core/`, `cli/`, `gui/`에 모두 `__init__.py`를 생성했다. **unit-0의 확정 파일 범위는 `common/logging_setup.py`, `common/exceptions.py`, `pdf_reader/loader.py` 3개뿐**이지만, 나머지 5개 디렉터리(`hwpx_kernel/`, `hwpx_writer/`, `core/`, `cli/`, `gui/`)의 `__init__.py`는 "최초 단위로서 프로젝트 골격을 만들라"는 이번 호출의 명시적 추가 지시에 따른 것이며, 각 파일 docstring에 "unit-N 소관, 아직 생성되지 않음"이라고 명시해 이후 단위가 실제 로직을 채울 자리만 비워뒀다(로직 코드는 전혀 넣지 않음 — 05-unit-developer의 "범위 외 파일 건드리지 않기" 원칙과 "스캐폴딩 지시"가 충돌하지 않도록, 각 stub은 의미 있는 코드를 전혀 포함하지 않는 순수 placeholder로 한정했다).
  - `tests/` 디렉터리 골격: `tests/__init__.py`(빈 파일)만 생성. 실제 테스트 코드는 06단계가 추가한다.
  - `.gitignore` 확인 결과 `__pycache__/`, `*.pyc`, `*.egg-info/`는 이미 있었음. 파이썬 빌드 산출물 중 빠져 있던 `build/`, `dist/`, `.pytest_cache/` 3줄을 "파이썬 표준 캐시/빌드 산출물" 섹션에 추가했다(하네스 표준 항목인 `.harness-tmp/`, `.venv*/` 등은 건드리지 않음).

### 1-2. `common/exceptions.py`
03 §4-2 예외 계층을 원문 그대로 구현:
```
ConversionError
├── PdfLoadError
│   ├── EncryptedPdfError
│   ├── CorruptedPdfError
│   └── EmptyPdfError
├── HwpxWriteError
│   ├── ContainerBuildError
│   └── OutputPathError
└── OcrEngineError
    └── TesseractNotFoundError
```
총 9개 클래스(기반 3 + 리프 6). 03 §4-2가 "계층 밖 예외는 orchestrator 최상위 `except Exception`에서 `INTERNAL_ERROR`로 변환"이라고 명시했으므로, 그 catch-all 자체는 이 모듈에 구현하지 않았다(orchestrator/unit-8의 책임). 각 클래스 docstring에 04단계 UX 설계서(§2 G-4 표)의 사용자 노출 문구를 주석으로 남겨, 나중에 unit-8이 매핑표를 만들 때 근거를 바로 찾을 수 있게 했다.

### 1-3. `common/logging_setup.py`
03 §7-1(로깅) + §3-2(로컬 영속 파일) + §6-2(개인정보 처리 원칙)을 반영:
- `setup_logging(verbose=False, log_dir=None, also_log_to_console=False)`: `RotatingFileHandler(maxBytes=5MB, backupCount=5)`를 `platformdirs.user_log_dir("pdf-to-hwpx")` 위치(기본값)에 등록. 기본 레벨 INFO, `verbose=True`면 DEBUG(03 §7-1). 중복 호출 시 기존 핸들러를 정리해 중복 등록을 방지(GUI/CLI 진입점이 "앱 시작 시 1회"만 부르는 것이 원칙이지만, 방어적으로 idempotent하게 만들었다 — 03 §1-1 "횡단 관심사는 진입점 1곳에서만 초기화" 원칙을 실수로 어겨도 로그가 중복 기록되지 않게 함).
- 모든 로그 라인에 앱 버전(`pdf_to_hwpx.__version__`)·Python 버전·OS 정보를 `logging.Filter`로 부착해 포맷에 포함(03 §7-1 "재현성" 요구, GitHub Issue 첨부 시 그대로 유용하도록).
- **개인정보 미포함 규칙(§6-2) 구현** — `SessionFileRegistry` 클래스: 파일마다 `register(path)`를 호출하면 verbose=False일 때 `doc#1`, `doc#2`... 형태의 세션 내 일련번호만 반환하고, verbose=True일 때만 전체 경로를 반환한다(배치 변환처럼 여러 파일을 순서대로 처리하는 경우용). 단일 파일 케이스를 위한 저수준 헬퍼 `describe_input_for_log(path, sequence_label, verbose)`도 함께 제공.
- **PDF 본문 텍스트를 로그에 남기는 경로 자체가 없음** — 이 모듈은 그런 인자를 받는 함수를 제공하지 않는다(설계 자체로 원천 차단).

### 1-4. `pdf_reader/loader.py`
03 §1-3(unit-0 파일 범위) + §1-2(컴포넌트 다이어그램) + §4-2(엣지 케이스)를 반영:
- `load_pdf(path: Path) -> PdfDocument`: pypdf로 먼저 열어 `is_encrypted`를 확인하고(암호화 감지), 페이지 수를 확인한 뒤(0페이지 감지), pdfplumber로도 열어 텍스트/표 파싱에 쓸 핸들을 준비한다.
- `PdfDocument` 데이터클래스: `path`, `page_count`, `plumber_pdf`(unit-1/unit-3이 소비), `pypdf_reader`(unit-2가 소비), 내부 파일 스트림. `close()`와 컨텍스트 매니저(`with load_pdf(path) as doc:`)를 제공해 리소스 누수를 방지한다.
- **의도적으로 범위에 넣지 않은 것**: 실제 텍스트/이미지/표 파싱(unit-1/2/3), `hwpx_kernel/schema.py`의 IR 데이터클래스(`PageIR` 등, unit-4 소관 — 이번 호출에서 그 파일을 전혀 건드리지 않았음). loader의 반환 계약은 IR이 아니라 "PdfDocument"이며, 이는 03 §1-3 표에 명시된 unit-0의 실제 산출물과 일치한다.
- **엣지 케이스 매핑** (03 §4-2 그대로):
  | 상황 | 예외 |
  |---|---|
  | 비밀번호로 보호된 PDF | `EncryptedPdfError` |
  | 파일을 열 수 없음(존재하지 않는 경로, 권한 문제, pypdf/pdfplumber 파싱 실패 등) | `CorruptedPdfError` |
  | 0페이지 PDF | `EmptyPdfError` |

  "파일이 존재하지 않는 경우"는 03 §4-2가 별도 예외 리프로 정의하지 않았다(그 목록은 PDF *내용*에 대한 것). 시스템 경계 검증 원칙(게이트2 체크리스트)에 따라, 로더가 파일을 열 수 없는 모든 경우(부재/권한/손상 포함)를 `CorruptedPdfError`로 일괄 처리했다 — "PDF 파일을 읽을 수 없습니다"라는 04 §2 G-4 문구가 이 모든 경우에 의미적으로 부합한다고 판단했기 때문이다. 이 판단은 임의 확장이 아니라 03 §4-2에 이미 정의된 예외 클래스의 적용 범위를 시스템 경계까지 넓힌 것이며, 새 예외 클래스를 만들지는 않았다.

---

## 2. 설계서 대비 편차

1. **`platformdirs`를 런타임 의존성에 추가함** — 이번 호출의 지시문은 "의존성은 03단계에서 확정된 것만: pdfplumber, pypdf, lxml, pytesseract"라고 명시했지만, 03 §2-1 기술 스택 표는 "로컬 경로/설정" 항목에서 `platformdirs`(MIT)를 이미 명시적으로 확정해 뒀고, 03 §7-1(로깅)이 로그 저장 위치로 `platformdirs.user_log_dir("pdf-to-hwpx")`를 직접 지정했다. `common/logging_setup.py`는 unit-0 자신이 이번에 구현하는 파일이므로, 이 의존성 없이는 설계서 명세를 구현할 방법이 없었다. 지시문의 4개 패키지 나열은 03 문서를 요약 인용한 것으로 보이며 배타적 목록으로 해석하지 않았다 — 03 §2-1 원문(기술 스택 선정 및 근거 표)이 상위 근거다. 게이트2 체크리스트에 따라 `pip index versions platformdirs`로 PyPI 실존을 재확인했다(3절 참고). 규칙 A 질문 대상(설계 모호)이 아니라 지시문 요약 누락으로 판단해 별도 질문 없이 진행했으며, 이 판단 근거를 여기 명시한다.
2. **`[project.scripts]` 미포함** — 03 §4-3이 정의한 `pdftohwpx` CLI 진입점은 `cli/__main__.py`(unit-11 소관)가 아직 없어 pyproject.toml에 미리 선언하지 않았다. unit-11이 해당 파일을 만들 때 함께 추가해야 한다(공유 파일이므로 unit-11 note에도 이 사실을 남겨야 함 — 06단계 테스터가 아니라 unit-11 담당자를 위한 인수인계 메모).
3. **`requirements.txt`(정확한 버전 고정) 미생성** — 03 §6-4는 "requirements.txt에 정확한 버전을 고정한다. 가능하면 --require-hashes까지"라고 했으나, 이번 호출 지시문은 pyproject.toml만 요구했다. `pyproject.toml`의 `dependencies`는 최소 버전 하한(`>=`)과 다음 메이저 미만(`<`) 범위로만 선언했다(예: `pypdf>=6.0.0,<7.0`). 정확한 고정과 해시 검증은 09단계(보안검증) 또는 별도 lockfile 생성 단위에서 다루는 것이 적절하다고 판단해 이번 범위에는 포함하지 않았다.

---

## 3. 게이트 1 — 정적 분석/린트

- **프로젝트에 lint/type-check/formatter 설정이 없음을 확인했다** (`ruff`/`flake8`/`black`/`mypy`/`pylint` 관련 설정 파일/섹션을 `pyproject.toml`, 리포지토리 루트에서 검색했으나 없음 — 이 사실을 그대로 기록한다. 있는데 건너뛴 것이 아니다).
- 대신 지시에 따라 `python -m py_compile`로 문법 검증을 수행: unit-0이 생성한 모든 `.py` 파일(패키지 `__init__.py` 8개 + `common/exceptions.py` + `common/logging_setup.py` + `pdf_reader/loader.py` + `tests/__init__.py`) 전부 **컴파일 성공**.
- 추가로 `.harness-tmp/venv-unit0`에 가상환경을 만들어 `pip install -e ".[dev]"`로 실제 설치까지 성공시켰다(의존성 해석 오류 없음).

## 4. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 예외 계층(03 §4-2), 로깅 정책(03 §7-1/§6-2), 로더 엣지케이스(03 §4-2)를 원문 그대로 구현. 편차는 위 2절에 전부 명시.
- [x] 에러 처리가 누락된 경로가 없는가 — `load_pdf`의 모든 `try` 블록이 구체적 예외로 재던지며, 임의로 `except: pass`나 조용히 삼키는 코드 없음. 실패 시 열려 있던 파일 스트림도 `finally`/바깥 `except`에서 반드시 닫는다(리소스 누수 방지).
- [x] 입력값 검증이 시스템 경계(사용자 입력, 외부 API 응답)에서 이루어지는가 — `load_pdf`가 사용자가 지정한 임의의 PDF 경로(파일 부재/권한/암호화/손상/0페이지 전부)를 열기 직후 검증한다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(로컬 도구, 인증 개념 자체가 03 §6-1에서 "해당 없음"으로 확정됨).
- [x] 새로 추가한 외부 의존성이 실제 PyPI 레지스트리에 존재하는지 확인했는가 — `pip index versions <pkg>`로 5개 전부(`pdfplumber`, `pypdf`, `lxml`, `pytesseract`, `platformdirs`) 및 `pytest` 실존을 재확인했다(3절 "설계서 대비 편차" 1번 참고). 이번 호출에서 직접 재조회했으며 03단계 조사를 맹신하지 않았다.
- [x] 범위를 벗어난 변경(곁다리 리팩터링 등)이 섞여 있지 않은가 — `hwpx_kernel/schema.py`(unit-4 소관)는 건드리지 않았음. 나머지 unit 소관 디렉터리에는 로직 없는 순수 placeholder `__init__.py`만 두었고, 이는 오케스트레이터의 명시적 스캐폴딩 지시에 따른 것으로 편차 아님(1-1절 참고).

## 5. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

스크래치패드에 임시 스크립트를 작성해 `.harness-tmp/venv-unit0` 가상환경에서 실행, 아래를 모두 확인했다(스크립트는 06단계 정식 테스트 코드가 아니며 리포지토리에 남기지 않음):
- 정상 PDF(1페이지) 로드 성공, `page_count == 1`, `close()`/`with` 컨텍스트 매니저 정상 동작
- `pypdf`로 즉석 생성한 암호화 PDF -> `EncryptedPdfError`
- 0페이지 PDF -> `EmptyPdfError`
- 임의 바이트로 구성한 손상 PDF -> `CorruptedPdfError`
- 존재하지 않는 경로 -> `CorruptedPdfError`
- `setup_logging()`이 `RotatingFileHandler` 로그 파일을 생성하고, 로그 라인에 앱/Python/OS 컨텍스트가 포함됨을 확인
- `SessionFileRegistry`(verbose=False)가 파일명 대신 `doc#1`, `doc#2`로 마스킹하고, verbose=True일 때만 전체 경로를 노출함을 확인(§6-2 개인정보 미포함 규칙)

모든 항목 통과.

---

## 6. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. `common/exceptions.py`
1. `ConversionError`, `PdfLoadError`, `HwpxWriteError`, `OcrEngineError`가 모두 `ConversionError`(또는 그 하위)를 상속하는 클래스 계층으로 존재한다.
2. `EncryptedPdfError`, `CorruptedPdfError`, `EmptyPdfError`가 `PdfLoadError`의 하위 클래스다.
3. `ContainerBuildError`, `OutputPathError`가 `HwpxWriteError`의 하위 클래스다.
4. `TesseractNotFoundError`가 `OcrEngineError`의 하위 클래스다.
5. 모든 클래스가 `Exception`처럼 메시지 문자열 1개를 받아 생성 가능하다(`raise EncryptedPdfError("메시지")`).

### AC-2. `common/logging_setup.py`
1. `setup_logging(verbose=False, log_dir=<임시 디렉터리>)` 호출 후 `<임시 디렉터리>/pdf-to-hwpx.log` 파일이 생성된다.
2. `verbose=False`(기본)일 때 로거 레벨이 `INFO`이고, `verbose=True`일 때 `DEBUG`다.
3. 로그 파일에 기록된 각 줄에 앱 버전 문자열(`app=`), Python 버전(`python=`), OS 정보(`os=`)가 포함된다.
4. `SessionFileRegistry(verbose=False).register(path)`를 연속 호출하면 `doc#1`, `doc#2`, ... 순으로 반환하고 원본 경로 문자열을 포함하지 않는다.
5. `SessionFileRegistry(verbose=True).register(path)`는 `str(path)`와 동일한 문자열을 반환한다.
6. `setup_logging()`을 같은 프로세스에서 2회 호출해도 로그 한 줄당 중복 기록(핸들러 중복)이 발생하지 않는다.
7. `RotatingFileHandler`의 `maxBytes=5*1024*1024`, `backupCount=5` 설정값이 코드에 반영되어 있다(회전 자체를 실제로 5MB 채워 검증하는 것은 06단계에서 시간 대비 비용이 크므로, 설정값 검사 + 실제 rollover 동작(예: maxBytes를 테스트용으로 아주 작게 주입 가능한지)까지는 06단계 재량으로 판단 권장).

### AC-3. `pdf_reader/loader.py`
1. 정상적인 1페이지 이상 PDF에 대해 `load_pdf(path)`가 예외 없이 `PdfDocument`를 반환하고, `page_count`가 실제 페이지 수와 일치한다.
2. `PdfDocument.plumber_pdf`가 `pdfplumber.PDF` 인스턴스, `PdfDocument.pypdf_reader`가 `pypdf.PdfReader` 인스턴스다.
3. 사용자/소유자 비밀번호가 걸린 PDF에 대해 `load_pdf`가 `EncryptedPdfError`를 던진다.
4. 페이지가 0개인 PDF에 대해 `load_pdf`가 `EmptyPdfError`를 던진다.
5. 유효한 PDF 헤더가 없는(또는 구조가 완전히 깨진) 바이트로 구성된 파일에 대해 `load_pdf`가 `CorruptedPdfError`를 던진다.
6. 존재하지 않는 경로에 대해 `load_pdf`가 `CorruptedPdfError`를 던진다(파일 없음도 "읽을 수 없음"으로 취급 — 2절 편차/판단 근거 참고).
7. `PdfDocument.close()` 호출 후 내부 파일 스트림이 닫힌 상태(`_stream.closed is True`)가 된다.
8. `with load_pdf(path) as doc:` 구문이 정상 동작하고, 블록 종료 시 자동으로 리소스가 해제된다.
9. 예외가 발생해 `load_pdf`가 중간에 실패하는 경로(암호화/0페이지/손상)에서도 내부적으로 연 파일 스트림이 누수 없이 닫힌다(예: `ResourceWarning` 없이 종료되는지 06단계에서 `-W error::ResourceWarning` 등으로 확인 권장).

### AC-4. 패키지/스캐폴딩
1. 리포지토리 루트에서 `pip install -e ".[dev]"`가 오류 없이 성공한다.
2. `python -c "import pdf_to_hwpx; print(pdf_to_hwpx.__version__)"`가 `0.1.0`을 출력한다.
3. `python -m py_compile` 대상 파일 전부가 문법 오류 없이 통과한다(1절 파일 목록).
4. `pdf_to_hwpx/{common,pdf_reader,hwpx_kernel,hwpx_writer,core,cli,gui}/__init__.py`가 모두 존재하고 import 가능하다.

---

## 7. traceability.md 갱신 (단독 실행이므로 직접 반영함)

`docs/harness/traceability.md`의 REQ-001, REQ-019 행에서 "구현 상태" 컬럼을 `Not Started` -> `Implemented (unit-0, 05단계 완료, 06단계 단위테스트 대기)`로 갱신했다. "작업 단위" 컬럼은 기존에 이미 정확했으므로(REQ-001: unit-0, REQ-019: unit-0/unit-17) 변경하지 않았다. 상세는 파일 diff 참고.
