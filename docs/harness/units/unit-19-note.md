# unit-19 구현 노트 — 웹 서비스 인프라 공통 선행(Django 프로젝트 스캐폴딩 + ConversionJob 모델)

- 담당 REQ-ID: REQ-021
- 소속 Feature: **Feature B(공개 웹 서비스 계층)** — 이 unit은 Feature B의 "공통 선행 unit"으로, 병렬 없이 단독 호출됨
- **속도 트랙: L3**(오케스트레이터 호출 프롬프트에 명시적 트랙 표기 없음 → ORCHESTRATOR.md 1장 기본값 L3 적용. 06/07단계는 L3 표준 절차를 그대로 따를 것)
- 구현일: 2026-09-28
- 입력 문서: `docs/harness/03-system-design.md` §1-2/§1-3(96~141행)/§2-1/§2-3/§3-2/§4-1/§4-4/§6-2/§6-3/§6-4, `docs/harness/decisions.md` DEC-020~036, `C:\big21\vibe-coding\AI-AUTO-WORK\webapp\config\*`(settings/middleware/urls/wsgi 참고), `C:\big21\vibe-coding\AI-AUTO-WORK\webapp\core\*`(apps/views/urls 참고)

## 1. 구현 범위

03 §1-3 unit-19 확정 파일범위(122~124행) 그대로:

| 파일 | 내용 |
|---|---|
| `webapp/manage.py` | Django 관리 커맨드 진입점(AI-AUTO-WORK 패턴 그대로, `DJANGO_SETTINGS_MODULE` 기본값 `config.settings.dev`) |
| `webapp/config/settings/base.py` | 공통 설정(INSTALLED_APPS=`core`+`converter`만, MIDDLEWARE, TEMPLATES, DB/캐시 미지정, `STORAGES`/`MEDIA_ROOT` 골격, `CACHES`=LocMemCache) |
| `webapp/config/settings/dev.py` | `DEBUG=True`, `DATABASE_URL` 미설정 시 SQLite(`webapp/db.sqlite3`) 폴백, R2 미설정 시 base의 FileSystemStorage(`webapp/.dev-media/`) 그대로 사용 |
| `webapp/config/settings/production.py` | `SECRET_KEY`/`DATABASE_URL`/`R2_*` 필수(`_require_env`), `XForwardedForMiddleware` prepend, HTTPS 강제, `/healthz` HTTPS 리다이렉트 예외, `ADMINS`(DJANGO_ADMIN_EMAIL) 장애 메일 알림 설정 |
| `webapp/config/urls.py` | `admin/`, `healthz`만 연결(아래 "설계서 대비 편차" 참고) |
| `webapp/config/wsgi.py` | WSGI 진입점, ASGI 미사용(설계 §2-1) |
| `webapp/config/middleware.py` | `XForwardedForMiddleware` — AI-AUTO-WORK 원본 그대로(rightmost X-Forwarded-For→REMOTE_ADDR), production에서만 등록 |
| `webapp/core/apps.py` | `CoreConfig` 최소 AppConfig |
| `webapp/converter/models.py` | `ConversionJob` 모델 — 03 §3-2 코드 블록을 필드명/타입/주석까지 그대로 구현 |
| `webapp/converter/migrations/0001_initial.py` | 위 모델의 최초 마이그레이션(`makemigrations`로 생성, 수동 편집 없음) |

부가 산출물(범위 내 필요 파일):
- `webapp/requirements.txt` — 로컬 기동에 필요한 최소 의존성(Django, psycopg[binary], dj-database-url, django-storages[s3], boto3, gunicorn, whitenoise, python-dotenv). 전부 `pip index versions`로 PyPI 실재 버전 확인 완료(§4 게이트2 참고). unit-26이 최종본으로 다듬을 예정(03 §1-3 unit-26 행).
- `webapp/.env.example` — AI-AUTO-WORK 패턴 재사용, 로컬 실행에 필요한 값이 전부 비워둬도 되는 선택값임을 주석으로 명시.
- `.gitignore`에 `webapp/.env`, `webapp/.dev-media/`, `webapp/staticfiles/` 추가(기존 `.harness-tmp/`, `*.sqlite3` 항목은 이미 있었음).
- `webapp/config/__init__.py`, `config/settings/__init__.py`, `core/__init__.py`, `converter/__init__.py`, `converter/migrations/__init__.py` — 패키지 구조상 필요한 빈 파일(의미 있는 "파일 범위" 항목이 아니라 구조적 필수 boilerplate로 판단, 별도 논의 대상 아님).

## 2. 설계서 대비 편차 (사유 포함)

1. **`webapp/core/views.py` + `webapp/core/urls.py`(healthz 라우트) 신규 추가 — 확정 파일범위 표(03 §1-3 unit-19 행)에는 명시되어 있지 않음.**
   - 사유: 03 §1-3 패키지 레이아웃(96~120행)은 `core/` 앱 구성요소로 `views.py(healthz)`, `urls.py`를 일반 나열해뒀으나, unit-19~26 어느 확정 파일범위 행에도 이 두 파일이 명시적으로 배정되어 있지 않다(작은 설계 공백). 오케스트레이터가 이번 호출에서 "로컬에서 실제로 뜨는지 healthz로 직접 확인"을 명시적으로 지시했고, `/healthz`는 03 §4-4에 이미 확정된 라우트이며 향후 어떤 unit의 확정 파일범위에도 `core/views.py`/`core/urls.py`가 나오지 않으므로(unit-20/23/24/25 전부 다른 파일만 명시) 향후 파일 충돌 위험이 없다고 판단해 이번 unit이 최소 구현(healthz 1개 뷰)만 추가했다. `GET /`(업로드 폼) 라우트는 unit-20 소유이므로 연결하지 않았다 — `config/urls.py`는 `admin/`과 `healthz`만 연결하고, `/` 요청은 현재 404를 반환한다(정상, unit-20 완료 전까지 기대되는 동작).
   - 영향: 없음(파일 추가만, 기존 계약 변경 없음). 6단계 테스터는 이 편차를 "미승인 범위 확장"이 아니라 "로컬 기동 검증을 위한 최소 스캐폴딩"으로 이해하면 된다.

2. **`INSTALLED_APPS`에 `legal`을 아직 포함하지 않음.** 03 §1-3 패키지 레이아웃은 `legal/` 앱을 명시하지만 unit-25(Not Started)가 아직 그 패키지 자체를 만들지 않았다 — 존재하지 않는 Python 모듈을 `INSTALLED_APPS`에 넣으면 `manage.py` 자체가 `ModuleNotFoundError`로 즉시 깨진다. `core`/`converter`만 포함했다. unit-25가 `legal/` 앱을 만들 때 `INSTALLED_APPS`에 자신을 추가하는 것이 자연스럽다(공유 파일 `config/settings/base.py`를 다시 건드려야 함 — 오케스트레이터가 unit-25 착수 시 이 점을 인지해야 함, 아래 "공유 문서 갱신 요청" 대신 여기 직접 기록: **unit-25는 `webapp/config/settings/base.py`의 `INSTALLED_APPS`에 `"legal"` 1줄을 추가해야 한다**).

3. **`ASGI`(`config/asgi.py`) 파일을 만들지 않음.** 03 §1-3 패키지 레이아웃 원문이 "ASGI 미사용(§2-1 근거) — wsgi.py만 사용"이라고 명시했으므로 그대로 따랐다(편차 아님, 명시적 확인 차 기록).

4. **`config/wsgi.py`/`config/settings/production.py`에 net_guard 호출부를 넣지 않음.** 오케스트레이터의 명시적 지시사항 — unit-9(net_guard)가 아직 Not Started라 존재하지 않는 모듈을 import하면 기동이 깨진다. 두 파일 모두 "unit-9 완료 후 여기서 `net_guard.install()`을 호출한다"는 주석으로 자리만 남겨뒀다(03 §1-3 unit-9 행 "진입점(config/wsgi.py) 1줄 호출"과 정합).

5. **관리자 로그인 경로를 AI-AUTO-WORK처럼 `django-admin/`으로 바꾸지 않고 Django 기본값 `admin/`을 그대로 사용.** AI-AUTO-WORK의 경로 변경은 그 프로젝트 고유의 DEC-009(자동화 공격 노출 축소)에 근거한 결정이며, 이 프로젝트의 decisions.md/03-system-design.md 어디에도 admin 경로 변경을 요구하는 근거가 없다 — 불필요한 차이를 만들지 않기 위해 표준값을 유지했다(가역적 구현 세부사항, 필요시 unit-23/26 단계에서 쉽게 변경 가능).

## 3. 로컬 기동 확인 (실제 실행 결과)

임시 venv `.harness-tmp/venv_05_unit19/`에서 실행 후 규칙 K에 따라 삭제 완료(작업 종료 시 venv/로그/sqlite 파일 모두 정리, `webapp/` 트리에는 소스 파일만 남음).

```bash
cd webapp
python -m venv ../.harness-tmp/venv_05_unit19
../.harness-tmp/venv_05_unit19/Scripts/python.exe -m pip install -r requirements.txt
../.harness-tmp/venv_05_unit19/Scripts/python.exe manage.py check
# → System check identified no issues (0 silenced).

../.harness-tmp/venv_05_unit19/Scripts/python.exe manage.py makemigrations converter
# → Migrations for 'converter': converter/migrations/0001_initial.py + Create model ConversionJob

../.harness-tmp/venv_05_unit19/Scripts/python.exe manage.py migrate
# → 전부 OK (contenttypes/auth/admin/converter.0001_initial/sessions)

../.harness-tmp/venv_05_unit19/Scripts/python.exe manage.py runserver 127.0.0.1:8778 --noreload &
curl -s -o - -w "\nHTTP_STATUS:%{http_code}\n" http://127.0.0.1:8778/healthz
# → 본문 "ok", HTTP_STATUS:200

curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8778/
# → 404 (정상 — GET / 은 unit-20 소유, 아직 미연결)

curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8778/admin/
# → 302 (Django admin 로그인 리다이렉트, 정상)
```

**production 설정 자체 로드 검증**(실제 Neon/R2 계정 없이, 필수 env var 가드가 의도대로 동작하는지만 확인):
- env var 없이 `DJANGO_SETTINGS_MODULE=config.settings.production manage.py check` 실행 → `ImproperlyConfigured: SECRET_KEY environment variable is required in production.`로 **의도한 대로 조기 실패**함을 확인(즉, 배포 시 시크릿 누락을 기동 단계에서 바로 잡아낸다).
- 가짜 값(`SECRET_KEY`, `DATABASE_URL`, `R2_ACCESS_KEY_ID` 등, `DJANGO_ALLOWED_HOSTS=example.com`)을 전부 채운 상태로 `django.setup()`까지 실행 → 정상 로드, `MIDDLEWARE[0]=="config.middleware.XForwardedForMiddleware"`, `STORAGES["default"]["BACKEND"]=="storages.backends.s3.S3Storage"`, `ALLOWED_HOSTS==["example.com"]` 전부 기대값과 일치.

결론: **`python manage.py runserver`는 `DATABASE_URL`/R2 자격증명 등 실제 클라우드 계정 없이 SQLite+로컬 디스크만으로 정상 기동하며, `/healthz`가 200 "ok"를 반환한다.** production 설정도 정상적인 조건(필수 env var 존재)에서 문제없이 로드됨을 별도로 확인했다.

## 4. 게이트 1 — 정적 분석/린트

- `pyproject.toml`, 리포지토리 루트에서 ruff/flake8/black/mypy/pylint 관련 설정 파일·섹션을 검색했으나 **없음을 확인**(unit-0-note.md와 동일한 결론 — 있는데 건너뛴 것이 아니라 애초에 설정이 없다).
- 대신 `python -m py_compile`로 이번 unit이 만든 모든 `.py` 파일(11개: manage.py, config/{__init__,middleware,urls,wsgi}.py, config/settings/{__init__,base,dev,production}.py, core/{apps,views,urls}.py, converter/models.py, converter/migrations/0001_initial.py)에 대해 문법 검증 실행 → **전부 컴파일 성공**.
- `manage.py check`(Django 자체 시스템 체크, 위 §3)도 0 issues로 통과 — 이는 py_compile보다 강한 검증(설정 간 정합성까지 확인)이라 사실상 이 프로젝트의 게이트1 역할을 겸한다.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — `ConversionJob` 필드명/타입/주석 전부 03 §3-2 코드 블록과 100% 동일(복붙 수준으로 그대로 옮김, 임의 변경 없음). `XForwardedForMiddleware` 로직도 AI-AUTO-WORK 원본과 동일(rightmost 파싱). 라우트(`/healthz`)도 03 §4-4 표와 동일(trailing slash 없음). 편차는 §2에 전부 명시.
- [x] 에러 처리가 누락된 경로가 없는가 — `production.py`의 `_require_env`가 필수 시크릿 누락 시 명시적 `ImproperlyConfigured` 예외로 조기 실패(조용히 넘어가지 않음, §3에서 실측 확인). `XForwardedForMiddleware`는 헤더가 없거나 빈 문자열일 때 `REMOTE_ADDR`을 건드리지 않고 그대로 통과(원본 로직 그대로, 예외 삼킴 없음).
- [x] 입력값 검증이 시스템 경계(사용자 입력, 외부 API 응답)에서 이루어지는가 — 이번 unit은 사용자 입력을 직접 받는 뷰(업로드 등)를 구현하지 않음(unit-20/21 몫). `XForwardedForMiddleware`가 다루는 `X-Forwarded-For`(외부/프록시발 신뢰 불가 헤더)는 rightmost 값만 채택하고 빈 문자열은 무시하는 방어 로직이 이미 있음(AI-AUTO-WORK 원본 그대로 재사용, 03 §6-4 설계 의도와 일치).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — dev의 `SECRET_KEY` 기본값은 `"django-insecure-dev-only-do-not-use-in-production"`(AI-AUTO-WORK 관례, DEBUG=True에서만 쓰이는 자리표시자이며 실제 배포 시크릿이 아님). production은 전부 환경변수 필수(`_require_env`). R2/DB 자격증명 어디에도 실제 값 없음.
- [x] 새로 추가한 외부 의존성이 실제 PyPI에 존재하는지 확인했는가 — `pip index versions`로 Django/dj-database-url/django-storages/boto3/python-dotenv/gunicorn/whitenoise 7종, `pip index versions psycopg`로 psycopg 존재 확인(§3 실행 로그, 그리고 `pip install -r requirements.txt`가 실제로 전부 설치 성공함으로 최종 확인).
- [x] 범위를 벗어난 변경(곁다리 리팩터링 등)이 섞여 있지 않은가 — `pdf_to_hwpx/` 패키지, `pyproject.toml` 어디에도 손대지 않음(git 상태로 확인, 아래 "변경 파일" 참고). 유일한 범위 외 확장은 §2-1(healthz)이며 사유를 명시했다.

## 6. 6단계 테스터가 확인해야 할 인수 조건(Acceptance Criteria)

- **AC-1 (로컬 기동)**: `webapp/` 디렉터리에서 신규 venv를 만들고 `pip install -r requirements.txt` 후 `.env` 없이(또는 빈 `.env`로) `python manage.py migrate && python manage.py runserver`를 실행하면 에러 없이 기동해야 한다. 콘솔에 `DATABASE_URL`/`R2_*` 관련 에러가 나오면 FAIL(이번 unit의 핵심 목표 위반).
- **AC-2 (healthz)**: 서버 기동 후 `GET http://127.0.0.1:8000/healthz` 요청 시 HTTP 200, 본문 정확히 `ok`(공백/개행 없이).
- **AC-3 (모델 스키마 고정)**: `converter/models.py`의 `ConversionJob` 필드 목록·타입·`Status` choices 값(`pending/processing/done/failed/expired`)이 03-system-design.md §3-2 코드 블록과 정확히 일치하는지 diff 대조. 이후 unit(20/21/22/24)이 이 필드를 그대로 참조할 것이므로 여기서 어긋나면 연쇄 결함이 된다.
- **AC-4 (마이그레이션 재현성)**: `converter/migrations/0001_initial.py`가 존재하는 상태에서 `python manage.py makemigrations converter --check`(또는 동등하게 `makemigrations`를 다시 실행)했을 때 "No changes detected"가 나와야 한다(모델과 마이그레이션이 어긋나 있으면 안 됨).
- **AC-5 (production 가드)**: `DJANGO_SETTINGS_MODULE=config.settings.production`으로 `manage.py check`를 실행하되 `SECRET_KEY`를 비워두면 `ImproperlyConfigured` 예외로 즉시 실패해야 한다(조용히 넘어가면 FAIL). 반대로 `SECRET_KEY`/`DATABASE_URL`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME`/`R2_ENDPOINT_URL`/`DJANGO_ALLOWED_HOSTS`를 전부(가짜 값이라도) 채우면 정상 로드되어야 한다.
- **AC-6 (XForwardedForMiddleware 미등록 조건)**: `config.settings.dev`로 로드했을 때 `MIDDLEWARE`에 `config.middleware.XForwardedForMiddleware`가 **없어야** 한다(dev는 프록시 전제가 없으므로). `config.settings.production`으로 로드했을 때는 `MIDDLEWARE[0]`이 정확히 이 미들웨어여야 한다.
- **AC-7 (범위 확인)**: `pdf_to_hwpx/` 패키지 내부 파일, `pyproject.toml`이 이번 커밋으로 변경되지 않았어야 한다(`git diff --stat` 확인).
- **수동 확인 권고(자동화 어려움)**: 6단계가 실제로 Neon/R2 계정을 아직 보유하지 않을 가능성이 높으므로, production 경로의 "R2/Neon에 실제로 연결되는지"는 이번 unit의 검증 범위가 아니다(AC-5는 어디까지나 "필수 env var 가드가 작동하는지"만 확인하면 충분).

## 7. traceability.md 갱신

이번 호출은 병렬 웨이브가 아니라 단독 호출이므로 `docs/harness/traceability.md`의 REQ-021 행을 직접 갱신했다("작업 단위"는 기존값 유지, "구현 상태"를 unit-19 관점에서 Implemented로, "단위테스트"를 06단계 대기로 표시, "비고"에 구현 노트 링크 추가).

## 8. 다음 단계로 넘어가기 전 참고 (오케스트레이터용)

- unit-19는 Feature B의 공통 선행이므로, 이 unit의 06단계(단위테스트) 통과 확인 후에 unit-20/21/23/24/25를 병렬 웨이브로 배치할 수 있다(03 §1-3 "공유 파일/공통 선행 요약" 문단, unit-22는 계약 기반 병렬 후 통합검증 순차).
- unit-25 착수 시 `webapp/config/settings/base.py`의 `INSTALLED_APPS`에 `"legal"`을 추가해야 한다(§2-2 편차 항목 참고, 공유 파일이므로 unit-25가 직접 수정).
- unit-9(net_guard) 착수 시 `webapp/config/wsgi.py`(또는 `production.py`)에 `net_guard.install()` 호출 1줄을 추가해야 한다(§2-4 편차 항목, 자리표시 주석 이미 있음).
