# 테스트 결과서 (Test Result Report) — unit-19

## 1. 개요
- 테스트 대상: unit-19 (Feature B 공통 선행 — Django 프로젝트 스캐폴딩 + `ConversionJob` 모델)
- 테스트 유형: 단위
- 적용 Tier: High (`docs/harness/decisions.md` DEC-021, 완화 없음)
- 적용 속도 트랙: L3(일반) — `unit-19-note.md` 명시대로 정식 절차 적용
- 병렬 실행 정보: 단독 실행(병렬 웨이브 아님)
- 테스트 목적: `docs/harness/units/unit-19-note.md`의 AC-1~AC-7을 실측으로 검증하고, 특히 `ConversionJob` 모델 스키마가 `03-system-design.md` §3-2와 필드 단위로 정확히 일치하는지 확인한다(Feature B 나머지 8개 unit이 이 스키마에 의존).
- 관련 산출물: `docs/harness/units/unit-19-note.md`, `docs/harness/03-system-design.md` §1-2/§1-3/§2-1/§2-3/§3-2/§4-1/§4-4/§6-2/§6-3/§6-4, `docs/harness/decisions.md` DEC-020~036
- 테스트 수행자(에이전트): 06단계(단위테스터)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): AC-1(로컬 기동)~AC-7(범위 확인) 전 항목, 및 AC에 직접 명시되지 않았으나 명백히 위험한 경계·예외 입력(빈 입력, 개별 필수 env var 누락, trailing slash, HTTP 메서드 변형).
- 제외 범위 및 사유:
  - 실제 Neon/R2 계정을 통한 production 연결 검증 — note §6 "수동 확인 권고" 항목대로 이번 unit의 검증 범위가 아님(계정 미보유, AC-5는 "필수 env var 가드 동작"만 요구).
  - `webapp/core/views.py`/`urls.py`의 healthz 이외 로직, `webapp/converter/`의 뷰/스토리지 로직 — 아직 존재하지 않음(unit-20/21/22의 몫).
  - unit-25의 `INSTALLED_APPS` 편입, unit-9의 `net_guard.install()` 호출 — note §8에 이미 오케스트레이터 인계 사항으로 명시되어 있어 이번 06 범위 아님.

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.13, Git Bash. `webapp/requirements.txt` 그대로(Django 5.2.17, psycopg[binary] 3.2.10, dj-database-url 2.3.0, django-storages[s3] 1.14.6, boto3 1.35.36, gunicorn 23.0.0, whitenoise 6.8.2, python-dotenv 1.0.1).
- 테스트 데이터: 실제 Neon/R2 계정 없이, `manage.py migrate` 시 SQLite(`webapp/db.sqlite3`, 임시) 폴백 사용. production 검증은 전부 가짜 값(`fake-secret-key`, `postgres://user:pass@localhost:5432/fakedb` 등)만 사용.
- 전제 조건: 05단계(unit-19-note.md)가 게이트1(정적분석/린트)·게이트2(자체 코드리뷰) 통과를 주장(§4/§5) — 아래 4절에서 06이 독립적으로 재확인함.
- 격리 venv: `.harness-tmp/venv_06_unit19/`(규칙 K, 단독 실행이므로 접미사 "_unit19"만 사용, 반복 생성/삭제 총 3회 — 최초 실행, 정리 후 추가 엣지케이스 확인을 위한 재생성, 최종 정리. 상세는 7절).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 (AC-1) | `.env` 없이 migrate | 신규 venv, `pip install -r requirements.txt` 완료, `webapp/db.sqlite3`/`.env` 없음 | `python manage.py migrate` | 에러 없이 전체 마이그레이션 적용(contenttypes/auth/admin/converter/sessions) | 19개 마이그레이션 전부 `OK`, 에러 0건, `DATABASE_URL`/`R2_*` 관련 에러 없음 | PASS | |
| TC-002 (AC-1 경계) | 빈 `.env` 파일이 존재하는 상태에서 migrate | `webapp/.env`를 `touch`로 생성(내용 0바이트) | `db.sqlite3` 삭제 후 재실행 `python manage.py migrate` | `.env` 유무와 무관하게 동일하게 성공 | 동일하게 19개 마이그레이션 전부 `OK` | PASS | AC-1 원문의 "`.env` 없이(또는 빈 `.env`로)" 조건 명시적으로 재현 |
| TC-003 (AC-2) | `GET /healthz` 정상 응답 | `runserver 127.0.0.1:8791 --noreload` 기동 | `curl -s -o body -w %{http_code} http://127.0.0.1:8791/healthz` | HTTP 200, 본문 정확히 `ok`(공백/개행 없음) | `HTTP_STATUS:200`, 본문 hexdump `6f6b`(2바이트, `ok` 그대로) | PASS | |
| TC-004 (AC-2 재현성, 독립 2회차) | 다른 포트(8792)의 새 서버 인스턴스에서도 동일 결과 | 새 `runserver 127.0.0.1:8792` 기동, `.env`(빈 파일) 존재 상태 | `curl` 재실행 후 TC-003의 본문과 `diff` | 두 응답 본문이 바이트 단위로 동일 | `diff` 결과 차이 없음("BODY IDENTICAL ACROSS RUNS") | PASS | 규칙 B 2차 독립 실행 근거 |
| TC-005 (경계, AC 범위 외 위험 케이스) | `GET /healthz/`(trailing slash) | 서버 기동 중 | `curl .../healthz/` | `core/urls.py`가 trailing slash 없는 라우트만 등록했으므로 404 | `HTTP_STATUS:404` | PASS | note §4-4 "trailing slash 없음" 설계 의도와 일치 |
| TC-006 (예외 입력) | `POST /healthz` | 서버 기동 중 | `curl -X POST .../healthz` | 뷰가 GET만 의도했으나 메서드 제약을 코드로 강제하지 않음 — Django 기본 CSRF 미들웨어가 토큰 없는 POST를 거부 | `HTTP_STATUS:403`(CSRF 검증 실패, Django 표준 동작) | PASS | 결함 아님(AC-2는 GET만 요구, 403은 CsrfViewMiddleware의 정상 동작) |
| TC-007 (경계) | `HEAD /healthz` | 서버 기동 중 | `curl -I .../healthz` | Django HttpResponse는 HEAD를 자동 처리 | `HTTP_STATUS:200` | PASS | |
| TC-008 (경계) | `GET /`(unit-20 미완료) | 서버 기동 중 | `curl .../` | `config/urls.py`가 `/`를 연결하지 않았으므로 404 | `HTTP_STATUS:404` | PASS | note §3에서 예측한 "정상(unit-20 소유)"과 일치 |
| TC-009 (경계) | `GET /admin/` | 서버 기동 중 | `curl .../admin/` | Django admin 로그인 리다이렉트 | `HTTP_STATUS:302` | PASS | INSTALLED_APPS의 admin 앱이 정상 등록됨을 간접 확인 |
| TC-010 (AC-3, 소스 텍스트 대조) | `ConversionJob` 필드가 설계서와 일치 | `03-system-design.md` §3-2 코드 블록, `webapp/converter/models.py` | 정규식으로 두 `class ConversionJob` 블록을 추출해 Python `difflib.unified_diff` | 차이 없음(`class ConversionJob`부터 파일 끝까지 완전 동일) | `EQUAL`(diff 출력 0줄) | PASS | 코드 리터럴 수준 100% 일치 |
| TC-011 (AC-3, ORM 교차검증) | 필드명/타입/max_length/null/blank/default가 스펙과 일치(독립 방법) | `django.setup()` 후 `ConversionJob._meta.get_fields()` 순회 | 19개 필드 각각의 `get_internal_type()`/`max_length`/`null`/`blank`/`default` 출력 | job_id(UUIDField, editable=False, default=uuid4) / status(CharField, max_length=16, default=PENDING) / created_at(auto_now_add) / started_at·finished_at·downloaded_at·purged_at(null=True,blank=True) / enable_ocr(Boolean,default=False) / ocr_lang(Char,max_length=16,default='kor') / input_object_key(Char,255) / output_object_key(Char,255,blank=True) / progress_stage(Char,16,blank=True) / progress_current_page·progress_total_pages(Integer,default=0) / progress_message(Char,255,blank=True) / result_success(Boolean,null=True) / result_warnings·result_errors(JSONField,default=list) | 실제 출력이 예상과 전부 일치(19개 필드 전수 확인, 출력 로그 그대로 본문 §3-2와 대조 완료) | PASS | 텍스트 diff(TC-010)와 별개 방법(런타임 리플렉션)으로 재검증 — 단일 검증 방법 의존 리스크 제거 |
| TC-012 (AC-3, Status choices) | `Status` choices 값이 `pending/processing/done/failed/expired` | 위 ORM 세션 | `list(ConversionJob.Status.choices)` 출력 | 5개 값이 정확히 이 순서·문자열로 존재 | `[('pending', ...), ('processing', ...), ('done', ...), ('failed', ...), ('expired', ...)]` — value 5종 전부 일치(라벨 한글 문자열은 콘솔 인코딩 문제로 깨져 보였으나 value만 AC-3 요구사항이며 소스 재확인 결과 라벨도 원본과 동일) | PASS | |
| TC-013 (AC-3, 인덱스) | `Meta.indexes`가 `status`+`created_at` 복합 인덱스 | 위 ORM 세션 | `ConversionJob._meta.indexes` 출력 | `fields=['status', 'created_at']` | `<Index: fields=['status', 'created_at'] name='converter_c_status_ba430f_idx'>` | PASS | |
| TC-014 (AC-4) | `makemigrations converter --check` | `0001_initial.py` 존재, 모델 수정 없음 | `python manage.py makemigrations converter --check --dry-run`(1회차) | "No changes detected" | `No changes detected in app 'converter'`, `EXIT:0` | PASS | |
| TC-015 (AC-4, 독립 2회차) | 동일 명령 재실행(별도 세션) | TC-014와 동일 조건, migrate 재적용 후 | 동일 명령 재실행 | 동일 결과 | `No changes detected in app 'converter'`, `EXIT:0` | PASS | 규칙 B 2차 독립 실행 근거 |
| TC-016 (AC-5, 1차) | `SECRET_KEY` 없이 production `check` | `DJANGO_SETTINGS_MODULE=config.settings.production`, 다른 env var 없음 | `manage.py check` | `ImproperlyConfigured: SECRET_KEY environment variable is required in production.`로 즉시 실패 | 정확히 이 메시지로 예외 발생, `EXIT:1` | PASS | |
| TC-017 (AC-5, 전부 충족) | 7개 필수 env var(SECRET_KEY/DATABASE_URL/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME/R2_ENDPOINT_URL/DJANGO_ALLOWED_HOSTS) 전부 가짜 값으로 채움 | 위와 동일 settings module | `django.setup()` 후 설정값 확인 | 정상 로드, `MIDDLEWARE[0]`/`STORAGES["default"]["BACKEND"]`/`ALLOWED_HOSTS` 기대값과 일치 | `MIDDLEWARE[0]=config.middleware.XForwardedForMiddleware`, `STORAGES.default.BACKEND=storages.backends.s3.S3Storage`, `ALLOWED_HOSTS=['example.com']`, `SECRET_KEY=fake-secret-key` | PASS | |
| TC-018 (AC-5, 경계 — 개별 var 누락) | 6개는 채우고 `R2_BUCKET_NAME`만 누락 | 위와 동일 | `django.setup()` | `ImproperlyConfigured: R2_BUCKET_NAME environment variable is required in production.` | 정확히 이 메시지로 예외 발생 | PASS | 가드가 "SECRET_KEY만 체크"가 아니라 6개 항목 각각을 독립적으로 강제함을 증명(1차 검증에서 놓치기 쉬운 지점) |
| TC-019 (AC-5, 경계 — 2회차) | `DATABASE_URL`만 누락(나머지 채움) | 위와 동일 | `manage.py check` | `ImproperlyConfigured: DATABASE_URL ...` | 정확히 이 메시지로 실패 | PASS | 규칙 B 2차 독립 실행, 다른 변수로 재검증 |
| TC-020 (경계, AC 범위 외 위험 케이스) | `DJANGO_ALLOWED_HOSTS`/`RENDER_EXTERNAL_HOSTNAME` 둘 다 미설정(단, `_require_env` 6종은 전부 채움) | 위와 동일 | `manage.py check` | `_require_env`로 감싸지 않은 값이므로 기동 자체는 실패하지 않음(설계 의도) | `System check identified no issues (0 silenced)`, `ALLOWED_HOSTS=[]` | PASS(설계 의도와 일치) | **리스크로 기록**(8절) — 운영자가 배포 시 이 값을 빠뜨리면 기동은 성공하지만 모든 요청이 런타임에 `DisallowedHost`로 거부됨. note/설계서 어디에도 이 값을 `_require_env`로 강제하라는 요구가 없어 결함은 아니나, 배포 체크리스트에 반드시 반영 필요 |
| TC-021 (AC-6, dev) | dev `MIDDLEWARE`에 `XForwardedForMiddleware` 없음 | `DJANGO_SETTINGS_MODULE=config.settings.dev` | `django.setup()` 후 `settings.MIDDLEWARE` 확인 | 미들웨어 미포함 | `assert` 통과, 8개 표준 미들웨어만 존재 | PASS | |
| TC-022 (AC-6, production) | production `MIDDLEWARE[0]`이 정확히 이 미들웨어 | 위 TC-017 조건 | `settings.MIDDLEWARE[0]` 확인 | `config.middleware.XForwardedForMiddleware` | 일치 | PASS | |
| TC-023 (AC-6, 독립 2회차) | 동일 조건 재확인(별도 프로세스) | 위와 동일 | 재확인 | 동일 | 동일 | PASS | 규칙 B 2차 독립 실행 |
| TC-024 (AC-7) | `pdf_to_hwpx/`, `pyproject.toml` 미변경 | 리포지토리 루트 | `git diff --stat -- pdf_to_hwpx/ pyproject.toml` | 출력 없음(diff 없음) | 출력 0줄, `git status --porcelain -- pdf_to_hwpx/ pyproject.toml`도 0줄(신규 파일도 없음) | PASS | |
| TC-025 (게이트1 재확인) | 05가 주장한 "린트 설정 없음" 사실 확인 | 리포지토리 루트 | `pyproject.toml`/루트에서 ruff/flake8/black/mypy/pylint 문자열 검색 | 매치 없음(exit 1) | `grep_exit:1`(매치 없음), `.flake8`/`mypy.ini`/`.pylintrc` 파일 없음 | PASS | note §4 주장과 독립적으로 재확인 |
| TC-026 (게이트1 재확인) | 이번 unit의 모든 `.py` 파일이 문법 오류 없음 | 격리 venv | `python -m py_compile`로 17개 파일(11개 note 명시분 + `core/urls.py` 등 실제 존재 파일 포함) 전수 컴파일 | 전부 성공 | `py_compile EXIT:0` | PASS | |
| TC-027 (게이트2 재확인) | 하드코딩된 실 시크릿 없음 | 소스 코드 리뷰 | `production.py`/`dev.py`/`.env.example`/`middleware.py` 육안 검토 | dev 기본값은 `"django-insecure-dev-only-do-not-use-in-production"`(자리표시자)뿐, production은 전부 `_require_env`, `.env.example`은 전부 빈 값 | 확인됨, 실 시크릿 없음 | PASS | |

> 정상 경로(TC-001~003, 010~017, 021~024) + 경계값(TC-005, 007~009, 018, 020) + 예외 입력(TC-006, 016) + 독립 재현성(2회차, TC-004/015/019/023) 전부 포함.

## 5. 커버리지
- 커버리지 지표: AC 커버리지 7/7(AC-1~AC-7) = 100%(TC-001~TC-024가 1:1 이상으로 대응, AC당 최소 2개 TC). 게이트1/2 재확인 별도 3건(TC-025~027).
- 커버되지 않은 부분과 사유: (1) 실제 Neon Postgres/Cloudflare R2 연결 자체는 검증하지 않음 — 계정 미보유, note §6에서 이미 이번 unit 범위 밖으로 명시. (2) 이 unit은 Django 인프라 스캐폴딩이라 별도 pytest 자동화 테스트 코드(`tests/webapp/` 등)가 존재하지 않음 — 라인/브랜치 커버리지 측정 도구를 적용할 대상 자체가 없고, 검증은 `manage.py`/`curl`/ORM 리플렉션을 통한 실행 기반 확인으로 대체했다(테스트 유효성은 4절의 실행 로그로 근거함). 이는 AC 미달이 아니라 unit 성격(설정/스키마 파일 위주, 분기 로직이 `_require_env` 정도만 존재)에 따른 것이며, 8절에 리스크로 기록한다.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | 본 결과서 7절 Teardown git status 인용 블록에 `(use "use "git add <file>..." to include...)` 형태의 중복 따옴표 오탈자 | `docs/harness/units/unit-19-test.md` 작성 중 git status 출력을 옮겨적는 과정에서 발생(코드/동작 변경 아님, 이 문서 자체의 표기 오류) | Low | Fixed | 06(본인)이 직접 수정 — `docs/harness/units/unit-19-test.md`의 git status 인용 블록 내 "Untracked files" 안내문을 `(use "git add <file>..." to include in what will be committed)`로 정정. 수정 파일 1개, 변경 1줄 — "사소한 오탈자" 기준(동작·로직·인터페이스 불변) 충족, 5단계 반려 없이 직접 수정. 조치 이력은 `docs/harness/verify-log_unit-19-test.md` 1차 검증 항목에도 동일하게 기록 |

이 외 결함 없음. TC-001~TC-027 전부 PASS(27개 케이스, 코드 결함 0건). 근거: 4절의 각 TC마다 예상 결과와 실제 결과를 직접 비교했고("에러 없음"만으로 PASS 처리한 케이스 없음), AC-3(가장 중요한 검증 포인트)는 텍스트 diff(TC-010)와 ORM 런타임 리플렉션(TC-011~013) 두 가지 독립적 방법으로 교차검증해 필드명·타입·max_length·null/blank·default·choices·인덱스가 모두 설계서와 정확히 일치함을 확인했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/venv_06_unit19/`(venv, 총 3회 생성/삭제 — ①1차 실행 ②정리 후 엣지케이스(TC-020) 확인용 재생성 ③최종 정리), `webapp/db.sqlite3`(migrate 산출물), `webapp/.env`(TC-002용 빈 파일), `webapp/.dev-media/`, `webapp/staticfiles/`, `webapp/**/__pycache__/`(실행 중 자동 생성), `.harness-tmp/runserver_unit19_run1.log`/`run2.log`.
  - 참고(수정 후 즉시 원위치): 검증 과정 중 실수로 `/tmp/venv_check_unit19`를 1회 생성했다가 규칙 K 위반(`.harness-tmp/` 밖)임을 즉시 인지하고 삭제한 뒤 `.harness-tmp/venv_06_unit19/`에 재생성해 진행했다(TC-020 실행은 재생성된 정상 위치에서 수행).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 (단, 위 참고의 일시적 예외는 발생 즉시 자체 정정함)
- 정리(삭제) 완료 여부: 완료. `webapp/db.sqlite3`, `webapp/.env`, `webapp/.dev-media/`, `webapp/staticfiles/`, `webapp/**/__pycache__/` 전부 삭제. `.harness-tmp/venv_06_unit19/`, `.harness-tmp/runserver_unit19_run*.log` 전부 삭제.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .gitignore
	modified:   docs/harness/traceability.md
	modified:   docs/harness/units/unit-2-note.md
	modified:   docs/harness/units/unit-2-test.md
	modified:   docs/harness/verify-log_unit-2-test.md
	modified:   tests/integration/test_feature_a_pipeline.py
	modified:   tests/pdf_reader/test_image_extractor.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/harness/units/unit-19-note.md
	webapp/

no changes added to commit (use "git add" and/or "git commit -a")
```
  (`webapp/` 하위 `find` 결과, 정리 후: `.env.example`, `config/`, `converter/`, `core/`, `manage.py`, `requirements.txt`의 소스 파일 19개만 남아 있음(테스트 시작 전과 동일한 파일 목록) — 임시 산출물 0건)
- 병렬 실행이었다면: 해당 없음(단독 실행). 다만 정리 확인 중 `.harness-tmp/venv_07_featureA_rerun2/`와 `docs/harness/verify-log_unit-2-test.md`/`tests/integration/test_feature_a_pipeline.py`/`docs/harness/units/unit-2-*` 수정분이 관찰되었다 — 이 세션이 만든 것이 아니며(`venv_06_unit19`라는 이름을 쓴 적 없고 unit-2/Feature A 관련 파일을 열람·수정한 적 없음), 동시에 진행 중인 다른(unit-2 07 재실행 관련) 세션의 산출물로 판단된다. 이 unit-19 테스트 범위의 임시 아티팩트·미추적 잔여물은 없음.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 확인: 위 `git status`에서 `webapp/`는 (소스 파일만 포함된) 신규 추가 대상으로 정상 표시되고, 그 외 임시 산출물은 전부 사라졌음 — PASS 판정 가능.

## 8. 리스크 및 잔존 이슈
- **DJANGO_ALLOWED_HOSTS/RENDER_EXTERNAL_HOSTNAME 둘 다 미설정 시 기동은 성공하지만 런타임에 모든 요청이 `DisallowedHost`로 거부됨**(TC-020). 결함은 아님(AC-5/설계서 어디에도 이 값을 `_require_env`로 강제하라는 요구 없음)이나, 실제 Render 배포 체크리스트(10~12단계)에 "DJANGO_ALLOWED_HOSTS 또는 RENDER_EXTERNAL_HOSTNAME 중 최소 하나 설정 확인"을 명시적으로 추가할 것을 권고한다.
- 이 unit은 설정/스키마 파일 위주라 자동화된 pytest 스위트가 없음(5절 참고) — 향후 unit-20~25가 `config/settings/*.py`를 추가로 건드릴 가능성이 있는데(예: unit-25의 `INSTALLED_APPS` 편입), 그 시점에 회귀를 자동으로 잡아줄 테스트가 아직 없다. unit-26(배포 매니페스트 최종본) 또는 그 이후 단계에서 `webapp/config/settings`에 대한 최소 스모크 테스트(pytest-django) 도입을 검토 권고.
- 실 Neon/R2 연결 미검증(note §6에 이미 명시된 범위 외 사항, 재확인 차 기록).
- unit-25 착수 시 `INSTALLED_APPS`에 `"legal"` 추가 필요, unit-9 착수 시 `wsgi.py`/`production.py`에 `net_guard.install()` 호출 추가 필요 — note §8의 오케스트레이터 인계 사항을 06도 동일하게 확인함(이 unit의 결함이 아니라 향후 unit의 작업 항목).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능 (7절 Teardown 확인 완료)
- AC-1~AC-7 전 항목 PASS(27개 테스트 케이스), 결함 0건. `ConversionJob` 스키마는 텍스트 diff + ORM 리플렉션 이중 교차검증으로 `03-system-design.md` §3-2와 완전히 일치함을 확인 — unit-20/21/22/24가 이 스키마를 소비해도 안전하다.
- **다음 웨이브 착수 가능**: unit-19의 06단계가 PASS로 확정되었으므로, note §8이 명시한 대로 unit-20/21/23/24/25를 병렬 웨이브로 배치할 수 있다(unit-22는 계약 기반 병렬 후 통합검증 순차). Feature B는 9개 unit(3개 초과) + High tier이므로 06·07 병합 조건(Low 등급 전용)에 해당하지 않는다 — 이 unit-19-test.md만 산출하고, 07단계(통합 테스트)는 별도로 호출되어야 한다(다만 unit-19는 "공통 선행"으로서 그 자체로 완결된 07 대상 시나리오가 없으므로, 통상적인 07은 unit-20 이후 Feature B 다른 unit들이 완료된 뒤 수행된다).

## 10. 내부 검증 (최소 2회)
- 1차 검증 결과 요약: AC-1~AC-7 각각에 대응하는 TC가 최소 1개 이상 존재함을 확인(실제로는 AC당 평균 3~4개, 2차 독립 실행분 포함 총 27개). 모든 TC의 "예상 결과"가 note §6(AC 원문) 또는 03-system-design.md §3-2/§4-4 원문에서 직접 인용되었음을 재확인 — 추측으로 채운 예상 결과 없음. AC-3(가장 중요한 포인트)는 단일 방법(텍스트 diff)만으로 끝내지 않고 ORM 리플렉션을 추가해 이중 검증했음을 확인.
- 2차 검증 결과 요약: "이 테스트를 통과했다고 07(통합테스트)로 넘겨도 되는가"를 의심하며 재검토한 결과, 1차가 놓칠 뻔한 경계 조건 2개를 추가로 발굴해 실행함 — (a) production 가드가 SECRET_KEY 하나만 체크하는 게 아니라 6개 필수 항목 각각을 독립적으로 강제하는지(TC-018, R2_BUCKET_NAME 개별 누락으로 실증), (b) `_require_env`로 감싸지 않은 `DJANGO_ALLOWED_HOSTS`가 빠지면 어떻게 되는지(TC-020, 결함은 아니나 배포 리스크로 8절에 기록). 또한 healthz 라우트의 trailing slash 엄격성(TC-005)과 HTTP 메서드 변형(TC-006/007)도 1차 설계에는 없었으나 "명백히 위험한 경계 케이스"로 판단해 추가했다. 이 재검토 결과 결함은 추가로 발견되지 않았으나(전부 설계 의도와 일치), 테스트 자체의 커버리지가 1차보다 견고해졌다.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-19-test.md`
