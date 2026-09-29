# unit-24 구현 노트 — REQ-029 (자원남용 방어 상한)

## 0. 속도 트랙

**표기 없음 → L3**(오케스트레이터 호출 프롬프트에 트랙 명시가 없었음). 6단계는 L3 기준 절차를 적용할 것.

## 1. 병렬 실행 여부

이번 호출은 **병렬 웨이브**로 진행됨 — 동시에 unit-20, unit-21, unit-25가 별도 호출로 구현 중이었다. 이 unit은 프롬프트로 지정된 파일 범위(`converter/limits.py`, `core/middleware.py`, `config/settings/base.py`의 MIDDLEWARE/MAX_IMAGE_PIXELS 예외 지점)만 수정했다.

**관찰 사항(참고용, 조치 불필요)**: 구현 도중 `webapp/config/settings/base.py`를 다시 읽었을 때 파일이 디스크에서 변경되어 있었다 — unit-25가 같은 파일의 `INSTALLED_APPS`(`"legal"` 추가)와 docstring 일부를 동시에 수정한 결과였다. 내가 건드린 라인(`MIDDLEWARE` 리스트, PIL import/설정 블록)과는 겹치지 않아 병합 후에도 두 변경이 모두 정상 반영됨을 `git status`/재실행(`manage.py check`)으로 확인했다. `config/urls.py`도 unit-20/25가 각각 1줄씩 추가한 상태였고(내 파일 범위 아님) 이 역시 정상 병합되어 있었다.

## 2. 구현 범위

### 2-1. `webapp/converter/limits.py` (신규)

03-system-design.md §5/§6-4에서 확정한 수치를 **상수로만** 정의:

- `MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024` (50MB, DEC-030)
- `CONVERSION_SOFT_TIMEOUT_SECONDS = 300` (5분 — 참고용, 실제 타임아웃 판정 로직은 unit-20 몫)
- `MAX_CONCURRENT_CONVERSIONS = 2` (참고용, 실제 ThreadPoolExecutor 생성은 unit-21 몫)
- `PENDING_QUEUE_LIMIT = 20` (참고용, 실제 카운팅/503 판정은 unit-21 몫)
- `MAX_IMAGE_PIXELS = 128_000_000` (1억 2,800만 픽셀)
- `is_content_length_too_large(content_length: int) -> bool` — 유일한 검증 함수. `ContentLengthLimitMiddleware`가 사용.

로직 흡수 금지 원칙에 따라 큐 카운팅/타임아웃 판정 코드는 넣지 않았다. unit-20/21이 이 상수들을 `from converter.limits import ...`로 참조하는 구조를 전제로 설계했다(단, 실제 import 코드 작성은 각 unit의 몫이며 이 unit이 대신 작성하지 않았다 — executor.py/views.py는 파일 범위 밖).

### 2-2. `webapp/core/middleware.py` (신규)

`ContentLengthLimitMiddleware` 1개 클래스만 정의. `Content-Length` 헤더값을 정수 파싱해 `limits.is_content_length_too_large()`로 검사하고, 초과 시 본문을 전혀 읽지 않고 즉시 `HttpResponse(status=413)`을 반환한다. 헤더가 없거나 정수로 파싱 불가능하면(외부 입력 신뢰 불가) 판단을 보류하고 다음 미들웨어로 통과시킨다(이 미들웨어의 책임은 크기 상한 판단만이며, 형식 오류 자체를 별도 에러로 취급하지 않음 — 뒤 단계가 처리).

### 2-3. `webapp/config/settings/base.py` (기존 파일 수정, 확정된 예외 지점만)

1. `MIDDLEWARE` 리스트 최상단(`SecurityMiddleware`보다 앞)에 `"core.middleware.ContentLengthLimitMiddleware"` 추가.
2. 모듈 최상단(다른 설정보다 먼저)에서 `from PIL import Image`, `from converter.limits import MAX_IMAGE_PIXELS` 후 `Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS`를 실행 — settings 모듈은 `manage.py`(dev)와 `wsgi.py`(gunicorn/production) 양쪽 진입점 모두에서 `django.setup()` 시점에 반드시 import되므로, 이 한 지점이 "Django 진입점에서 전역 1회 설정"이라는 설계서 요구를 만족하는 유일한 공통 지점이라고 판단했다. `pdf_to_hwpx/pdf_reader/image_extractor.py`는 손대지 않았다.

**설계서 대비 편차**: 없음. §5 표가 명시한 4개 수치(50MB/5분/최대2건·대기20건/1.28억 픽셀)를 모두 상수로 반영했고, §6-4가 요구한 미들웨어 순서(SecurityMiddleware보다 앞단)도 그대로 구현했다.

**CLI 진입점 관련 참고(범위 밖, 조치 안 함)**: 03 §5 원문은 "Django/CLI 진입점에서 전역 1회 설정"이라고 되어 있으나, 이번 unit의 확정 파일 범위는 `converter/limits.py`와 `core/middleware.py`(+ base.py 예외 지점)로 한정되어 CLI 쪽(`cli/__main__.py`, unit-11 소유) 진입점에는 `Image.MAX_IMAGE_PIXELS` 설정을 추가하지 않았다. 이는 이번 프롬프트의 명시적 파일 범위 제한을 따른 것이며, CLI 경로에서 동일 설정이 필요하다면 별도 unit(또는 오케스트레이터 판단)으로 처리되어야 한다.

## 3. 게이트 1 — 정적 분석/린트

리포지토리 전체(루트 `pyproject.toml`, `webapp/` 하위)에 ruff/flake8/black/mypy/pylint 관련 설정 파일이나 섹션이 **없음을 확인**(unit-0/unit-19-note.md와 동일한 결론 — 있는데 건너뛴 것이 아니라 애초에 설정 자체가 없음).

대신 `python -m py_compile`로 이번 unit이 만들거나 수정한 3개 파일(`converter/limits.py`, `core/middleware.py`, `config/settings/base.py`)에 대해 문법 검증 실행 → 전부 컴파일 성공. `manage.py check`(Django 시스템 체크, 전체 프로젝트 대상)도 통과 — 이 unit이 아니라 병렬로 함께 반영된 unit-20/21/25 코드까지 포함해 전체가 깨지지 않았음을 확인했다(단, 이는 내 책임 범위를 넘는 보너스 확인이며, 실패했더라도 내 파일 범위 결과와는 별도로 보고했을 것).

## 4. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — §5 수치 4종, §6-4 미들웨어 순서 모두 일치.
- [x] 에러 처리가 누락된 경로가 없는가 — `Content-Length` 헤더 파싱 실패(비정수 값)를 명시적으로 처리(예외를 삼키지 않고 "판단 보류"로 처리, 크래시 없음).
- [x] 입력값 검증이 시스템 경계(사용자 입력, 외부 API 응답)에서 이루어지는가 — `Content-Length`는 클라이언트가 보낸 HTTP 헤더(시스템 경계 입력)이며, 미들웨어가 본문을 읽기 전 이 경계에서 바로 검증한다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 상수/로직뿐).
- [x] 새로 추가한 외부 의존성이 있다면 실제 레지스트리 존재 확인 — **신규 의존성 없음**(Pillow는 이미 `pyproject.toml`의 `pdf_to_hwpx` 의존성으로 존재, `webapp/requirements.txt`에 별도 추가 안 함 — editable install(`pip install -e .`)로 전이 설치됨을 venv 재현으로 직접 확인). 패키지 매니페스트 변경 없음.
- [x] 범위를 벗어난 변경(곁다리 리팩터링 등)이 섞여 있지 않은가 — `converter/limits.py`, `core/middleware.py`(신규 파일)와 `config/settings/base.py`의 두 지점(MIDDLEWARE 추가 1줄, PIL 설정 블록)만 수정. 그 외 로직 변경 없음.

## 5. 로컬 동작 확인 (`.harness-tmp/venv_05_unit24/`, 확인 후 삭제 완료)

1. `python -m venv .harness-tmp/venv_05_unit24` 생성 후 `pip install -r webapp/requirements.txt` + `pip install -e .`(pdf_to_hwpx editable, Pillow 전이 설치 목적).
2. `manage.py check` → `System check identified no issues`.
3. `Image.MAX_IMAGE_PIXELS`가 settings 모듈 import 시점에 실제로 `128_000_000`으로 전역 설정됨을 `django.setup()` 후 `PIL.Image.MAX_IMAGE_PIXELS`를 직접 읽어 확인.
4. `ContentLengthLimitMiddleware`를 `RequestFactory`로 직접 호출해 경계값 테스트:
   - `Content-Length = 50MB + 1` → **413**, 그리고 다운스트림(`get_response`, 즉 뷰/본문 처리)이 **호출되지 않음**을 스파이 함수로 확인(본문을 실제로 읽기 전에 거절한다는 설계 요구 검증).
   - `Content-Length = 정확히 50MB`(경계값) → 200(허용, 상한 이하는 통과).
   - `Content-Length` 헤더 없음 → 200(통과).
   - `Content-Length` 값이 정수가 아닌 문자열 → 크래시 없이 200(판단 보류, 통과).
5. **엔드투엔드(전체 미들웨어 스택 + 실제 URL 라우팅)**: Django 테스트 `Client`로 `POST /convert`에 실제 본문(수 바이트)은 작게 보내되 `CONTENT_LENGTH` 헤더값만 `50MB+1`로 위조해 전송 → 실제 배포될 `MIDDLEWARE` 리스트(`SecurityMiddleware` 등 포함) 순서 그대로 통과시켜도 **413**이 반환됨을 확인(`config/urls.py`의 `/convert` 라우트는 병렬 진행 중이던 unit-20 산출물을 그대로 이용). `GET /healthz`는 계속 200으로 정상 응답해 미들웨어 추가가 다른 라우트를 막지 않음도 함께 확인.
6. 확인 후 `.harness-tmp/venv_05_unit24/`를 삭제해 정리 완료(규칙 K). `webapp/db.sqlite3`는 `.gitignore` 대상(dev 전용 SQLite 폴백 산출물)이라 그대로 두었다.

## 6. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

1. **413 즉시 거절**: `Content-Length` 헤더가 `52428801`(50MB+1바이트) 이상인 `POST` 요청은 서버가 본문을 끝까지 읽지 않고 HTTP **413**을 반환해야 한다. 응답 본문은 한글 안내 문구(`"업로드 파일이 너무 큽니다. 최대 50MB까지 허용됩니다."`)를 포함해야 한다.
2. **경계값 허용**: `Content-Length`가 정확히 `52428800`(50MB, 상한 포함)이면 이 미들웨어는 요청을 통과시켜야 한다(이후 단계의 뷰/폼 검증에서 별도로 거절될 수는 있으나, 이 미들웨어 단계에서는 거절하지 않아야 한다).
3. **미들웨어 순서**: `webapp/config/settings/base.py`의 `MIDDLEWARE` 리스트에서 `core.middleware.ContentLengthLimitMiddleware`가 `django.middleware.security.SecurityMiddleware`보다 앞(인덱스가 더 작음)에 있어야 한다. `production.py`가 `XForwardedForMiddleware`를 리스트 맨 앞에 추가로 prepend해도(`MIDDLEWARE = ["config.middleware.XForwardedForMiddleware", *MIDDLEWARE]`), `ContentLengthLimitMiddleware`는 여전히 `SecurityMiddleware`보다는 앞에 있어야 한다.
4. **헤더 없음/비정수 값 처리**: `Content-Length` 헤더가 없거나(GET 요청 등) 정수로 파싱 불가능한 값이면 이 미들웨어는 요청을 그대로 통과시켜야 하며, 서버 프로세스가 크래시하거나 500을 반환해서는 안 된다.
5. **이미지 디컴프레션 상한 전역 적용**: `config.settings.dev` 또는 `config.settings.production`으로 `django.setup()`을 실행한 프로세스 안에서 `PIL.Image.MAX_IMAGE_PIXELS`를 읽으면 정확히 `128000000`이어야 한다(직접 `python -c "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings.dev'; django.setup(); from PIL import Image; print(Image.MAX_IMAGE_PIXELS)"` 로 재현 가능).
6. **`limits.py`가 유일한 값의 출처**: `converter/limits.py`에 정의된 `MAX_UPLOAD_SIZE_BYTES`(52428800), `MAX_IMAGE_PIXELS`(128000000), `CONVERSION_SOFT_TIMEOUT_SECONDS`(300), `MAX_CONCURRENT_CONVERSIONS`(2), `PENDING_QUEUE_LIMIT`(20) 값이 unit-20/21이 구현한 실제 동작(413/타임아웃 안내/503 큐 포화 등, 6단계에서 unit-20/21 노트와 함께 교차 검증)과 일치하는지 통합 시점에 재확인할 것 — 이 unit은 상수 정의만 책임지므로, 값이 일치하지 않으면 unit-20/21 쪽 import 누락(하드코딩된 별도 값 사용) 가능성을 의심할 것.
7. **`pdf_to_hwpx` 라이브러리 코드 무변경**: `pdf_to_hwpx/pdf_reader/image_extractor.py`에 이 unit으로 인한 diff가 없어야 한다(git diff로 확인 가능).

## 7. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

### traceability.md 갱신 요청

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-029 | 작업 단위 (unit-n) | `unit-24` (기존 "unit-24(신규)"에서 "(신규)" 표기 제거) |
| REQ-029 | 구현 상태 | `구현 완료(unit-24) — 6단계 단위테스트 대기` |
| REQ-029 | 단위테스트 (unit-n-test) | 미정 유지(6단계가 채움) |

기존 REQ-029 행의 "비고" 컬럼(DEC-025/DEC-030 서술)은 이번 구현과 내용이 일치하므로 별도 수정 요청 없음.

decisions.md에 남길 새로운 규칙 A 질문이나 결정 사항은 없음(설계서 명세가 명확해 구현 방법 분기가 발생하지 않았음).
