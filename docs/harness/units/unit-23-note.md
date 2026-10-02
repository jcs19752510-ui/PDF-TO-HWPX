# unit-23 구현 노트 — `converter/ratelimit.py` (IP 기반 레이트리밋)

- 작성 에이전트: 05-unit-developer
- 커버 REQ-ID: REQ-026
- **속도 트랙: L3**(오케스트레이터로부터 별도 트랙 지정 없음 — ORCHESTRATOR.md 1장 기본값 적용)
- **병렬 실행 여부**: 착수 프롬프트 기준으로는 단독 호출(unit-20의 06이 PASS된 시점에 착수). 다만 구현 도중 `webapp/converter/views.py`를 편집하려던 시점에 파일이 세션 시작 시점 대비 이미 변경되어 있음을 발견했다 — `from . import limits, storage`가 `from . import cleanup, limits, storage`로, `index()`에 REQ-028 지연 스윕 트리거 호출이 추가되어 있었다(unit-22 산출물이 오케스트레이터에 의해 이미 병합된 상태로 추정). 이 unit은 그 변경분을 건드리지 않고 내가 필요한 두 지점(import 목록에 `ratelimit` 추가, `convert()` 위에 데코레이터 1줄)만 최소 적용했다 — 실제 diff는 아래 2절 참고.

## 1. 구현 범위

- `webapp/converter/ratelimit.py` 신규 작성.
- `webapp/converter/views.py` 2곳만 수정:
  - `from . import cleanup, limits, storage` → `from . import cleanup, limits, ratelimit, storage` (기존 공유 import 줄에 이름 하나 추가)
  - `convert()` 함수 정의 바로 위에 `@ratelimit.enforce_rate_limit` 데코레이터 1줄 삽입(`@require_http_methods(["POST"])` 아래, `def convert(request):` 위) — 그 외 `convert()`/`index()`/`job_status()`/`download()`의 로직은 1바이트도 건드리지 않았다.

### 1-1. 임계값(03 §6-4, DEC-032 그대로)

- IP당 시간당 업로드 시도 20회 초과 → 429.
- IP당 동시 진행중(PENDING+PROCESSING) job 2건 초과 → 429.
- 캡차(hCaptcha)는 v1 미구현(DEC-032 그대로, 이 unit이 구현 범위에 추가하지 않음).

### 1-2. "시간당 20회" 구현 — `admin_auth.py` 패턴 그대로 재사용

`AI-AUTO-WORK`(`C:\big21\vibe-coding\AI-AUTO-WORK\webapp\core\admin_auth.py`)의 `is_rate_limited(ip)`를 그대로 참고해 `is_upload_rate_limited(client_ip)`를 구현했다 — `cache.incr(key)` 실패(`ValueError`, 키가 아직 없음) 시 `cache.set(key, 1, timeout=3600)`으로 초기화하는 고정윈도우 카운터. `admin_auth.py`와 동일하게 **요청의 성공/실패(400 등)와 무관하게 `POST /convert` 시도 자체를 센다** — 로그인 시도 카운터가 자격증명 유효 여부와 무관하게 모든 시도를 세는 것과 같은 설계 판단이다(무효 파일을 반복 제출해 카운터를 우회하는 경로를 만들지 않기 위함). 03/04 문서가 "성공한 업로드만 셀지 시도 전체를 셀지"를 명시하지 않아 이 부분은 `admin_auth.py` 선례를 그대로 따르는 것으로 규칙 A 질문 없이 해소했다(기존 프로젝트 패턴 재사용 지시가 이미 DEC-032/03 §6-4에 있음).

### 1-3. "동시 진행중 2건" 구현 — DB에 IP가 없는 문제를 어떻게 풀었는가 (설계서에 없는 구현 세부)

03 §3-2/DEC-036이 `ConversionJob`에 `client_ip` 필드를 두지 않기로 이미 확정해뒀다(개인정보 최소수집). 따라서 "이 IP가 지금 PENDING/PROCESSING job을 몇 건 갖고 있는가"를 DB만으로는 조회할 수 없다. 이 unit은 다음 방식으로 해소했다:

1. `POST /convert`가 202로 새 `job_id`를 발급하면(데코레이터가 원래 뷰의 응답을 가로채 확인), 그 `job_id` 문자열을 **IP별 LocMemCache 리스트**(`converter:ratelimit:jobs:<ip>`, TTL 60분 — DEC-029 TTL과 동일 근거)에 추가한다. 이 리스트 자체는 DB에 전혀 쓰지 않으므로 DEC-036(client_ip DB 미저장) 위반이 아니다.
2. 다음 요청이 오면, 그 IP의 추적 리스트에 있는 job_id들을 `ConversionJob.objects.filter(job_id__in=..., status__in=[PENDING, PROCESSING]).count()`로 **지금 이 순간의 실제 DB 상태**를 조회해 판정한다. job이 이미 DONE/FAILED로 끝났으면 자동으로 카운트에서 빠진다 — executor.py(unit-21)나 views.py의 다른 부분을 전혀 건드리지 않고도 "진행중" 여부를 정확히 반영한다.
3. 추적 리스트 크기 자체가 무한정 커지는 것을 막기 위해 IP당 최근 50건만 유지한다(`_MAX_TRACKED_JOBS_PER_IP`) — 이 상한은 설계서에 없는 안전핀으로, 정상 사용 시나리오(시간당 20회 제한이 이미 있으므로 실제로 50건까지 쌓일 일이 거의 없음)에 영향이 없다.

이 설계 대신 "제출 시점에 매번 카운터를 +1, executor.py가 완료 시 -1" 같은 카운터 방식도 고려했으나, 그러면 `executor.py`(unit-21, 06 PASS 완료 파일)를 수정해야 해 이번 unit의 파일 범위(`ratelimit.py` + `views.py` 1줄)를 벗어난다 — 이번 방식은 다른 unit의 파일을 전혀 건드리지 않고도 동일한 정확도를 얻는 대안이다.

### 1-4. 429 응답 문구

04-ux-design.md §1-2/§7이 확정한 단일 일반 문구를 그대로 사용한다: "요청이 제한되었습니다. 시간당 업로드 횟수를 초과했거나 이미 진행 중인 작업이 있습니다. 잠시 후 다시 시도해주세요" — 두 사유(시간당 초과/동시처리 초과)를 구분하지 않고 항상 동일한 문구+상태코드 429만 반환한다(04가 명시적으로 "바디 파싱에 의존하지 않는 방어적 설계"를 요구했으므로, 바디 스키마를 임의로 확장하지 않았다).

### 1-5. IP 신뢰 지점

`ratelimit.py`는 `request.META["REMOTE_ADDR"]`을 읽기 전용으로만 사용한다. `config/middleware.py`(unit-19, `XForwardedForMiddleware`)가 이미 정규화해둔 값을 그대로 신뢰하며, 이 unit은 그 미들웨어를 수정하지 않았다(4절에서 정규화 동작 자체를 별도로 재확인).

## 2. 설계서 대비 편차 및 사유

- 편차 없음. 03 §1-3(unit-23 행)·§6-4, DEC-032, 04-ux-design.md §1-2/§7의 문구를 그대로 구현했다. 캐시 백엔드도 `webapp/config/settings/base.py`가 이미 준비해둔 `LocMemCache`(unit-19 산출물)를 그대로 사용했고 새 설정을 추가하지 않았다.
- 유일한 "설계서에 없는 구현 세부"는 위 1-3절의 "IP별 job_id 추적 리스트" 메커니즘이다 — 설계서는 "IP당 동시 2건"이라는 정책만 확정했고 구현 메커니즘은 위임했으므로 규칙 A 질문 대상이 아니라고 판단했다(DEC-036과 상충하지 않는 방식을 스스로 찾아 구현).

## 3. 게이트 1 — 정적 분석/린트

프로젝트 루트(`pyproject.toml`)와 `webapp/`에 ruff/flake8/black/mypy 등 설정이 **존재하지 않음을 재확인**(unit-19/20/21-note.md와 동일 결론, `.flake8`/`ruff.toml`/`mypy.ini` 등 파일 자체가 없음) — 있는데 건너뛴 것이 아니라 설정이 없다는 사실을 기록한다. 대체 확인으로 `python -m py_compile webapp/converter/ratelimit.py webapp/converter/views.py`를 실행해 통과했다.

## 4. 로컬 동작 확인 (`.harness-tmp/venv_05_unit23/`, 작업 완료 후 정리함)

`python -m venv` + `pip install -r webapp/requirements.txt` + `pip install -e .`(pdf_to_hwpx 편집설치) + `pip install reportlab`(테스트용 더미 PDF 생성) 후:

1. `python manage.py check` → `System check identified no issues (0 silenced)`.
2. `python manage.py migrate` → 정상.
3. `python manage.py runserver 127.0.0.1:8123 --noreload` 기동 후:
   - **시간당 20회 초과**: 같은 세션(쿠키+CSRF 토큰 고정, 동일 `REMOTE_ADDR`=127.0.0.1)으로 `POST /convert`를 curl로 21회 연속 호출 → **1~20번째 202, 21번째 정확히 429** + 확정 문구 그대로("요청이 제한되었습니다. 시간당 업로드 횟수를 초과했거나...") 확인.
   - **동시 진행중 2건 초과**: 더미 1페이지 PDF는 변환이 즉시 끝나버려 HTTP로는 "진행중" 상태를 자연 재현하기 어려워, Django shell로 `ConversionJob(status=PENDING/PROCESSING)` 2건을 만들고 `ratelimit._track_submitted_job(ip, job_id)`로 동일 IP에 추적 등록한 뒤, 그 IP로 실제 `Client().post('/convert', ...)`를 호출 → **429** 확인. 동시에 **다른 IP**로 동일 요청 → **202**(영향 없음) 확인. 또한 순수 함수 단위로 `is_concurrent_limit_exceeded(ip)`가 (a) PENDING 2건 존재 시 `True`, (b) 그중 1건을 `DONE`으로 바꾼 직후 `False`로 즉시 반영됨을 확인 — DB 상태를 실시간 반영한다는 설계 의도(1-3절)가 실제로 동작함을 검증.
   - **`XForwardedForMiddleware`의 정규화 자체 확인**: 미들웨어 인스턴스를 직접 호출해 `REMOTE_ADDR=10.0.0.1`(프록시 자신의 IP), `X-Forwarded-For: 9.9.9.9, 10.0.0.1`(클라이언트가 임의 조작 가능한 leftmost 값 + 신뢰 가능한 rightmost 값)인 요청을 넣었을 때, 최종 `REMOTE_ADDR`이 **rightmost 값(10.0.0.1)** 로 정규화됨을 확인 — 즉 클라이언트가 `X-Forwarded-For` 헤더의 leftmost 값을 조작해도(9.9.9.9로 스푸핑 시도) rightmost(신뢰 가능한 엣지 부가값)만 채택되므로 레이트리밋을 헤더 조작으로 우회할 수 없음을 실측으로 확인했다(dev 환경은 이 미들웨어를 `MIDDLEWARE`에 등록하지 않으므로, 미들웨어 인스턴스를 직접 생성해 별도로 검증 — production.py는 이미 이 미들웨어를 체인 최상단에 등록해둔 상태, 코드 확인 완료).
4. 작업 종료 후 `.harness-tmp/venv_05_unit23/`, `webapp/db.sqlite3`, `webapp/.dev-media/`, curl 테스트용 더미 PDF/쿠키 파일 전부 삭제(규칙 K). 서버 프로세스 종료 확인.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 §6-4/DEC-032(임계값 20회/2건, LocMemCache, `admin_auth.py` 패턴)와 04 §1-2/§7(429 단일 일반 문구, 바디 미파싱 전제)을 항목별로 대조. 편차 없음(2절).
- [x] 에러 처리가 누락된 경로가 없는가 — `is_upload_rate_limited`/`is_concurrent_limit_exceeded`는 빈 IP(`""`)를 방어적으로 `False`(제한 없음)로 처리(REMOTE_ADDR이 어떤 이유로든 비어있는 극단적 상황에서 서비스 자체를 막지 않기 위함, `admin_auth.py`와 동일 판단). `json.loads(response.content)` 파싱 실패(`ValueError`/`AttributeError`)는 `job_id=None`으로 처리해 추적을 건너뛸 뿐 예외를 전파하지 않는다 — 다만 이 경우도 로그를 남기지 않는 것이 유일한 아쉬운 지점인데, 202 응답이 `job_id`를 못 담는 상황은 unit-20 계약 위반(있을 수 없는 경우)이라 별도 로깅을 추가하지 않았다(과설계 방지). 조용히 전체 요청을 실패시키는 `except: pass`류 코드는 없다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 unit의 "입력"은 `request.META['REMOTE_ADDR']`(이미 unit-19 미들웨어가 정규화한 신뢰값)과 자기 자신이 만든 `job_id`뿐이라 별도 사용자 입력 검증 대상이 없다. 실제 사용자 입력(업로드 파일)의 경계 검증은 이미 unit-20/24가 담당(범위 밖).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(이 파일은 캐시 키 문자열과 임계값 상수만 다룬다).
- [x] 새로 추가한 외부 의존성이 있다면 실존 여부를 확인했는가 — **신규 패키지 없음**. `django.core.cache`(Django 표준)만 사용, `requirements.txt`/`pyproject.toml` 변경 없음.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `git status`/`git diff`로 확인: 신규 파일은 `webapp/converter/ratelimit.py` 1개뿐이고, `webapp/converter/views.py`는 정확히 2줄(import 목록에 이름 추가, 데코레이터 1줄)만 변경되었다. 다른 unit 소유 파일(`models.py`/`storage.py`/`executor.py`/`limits.py`/`cleanup.py`/`core/middleware.py`/`config/*`)은 전혀 건드리지 않았다.

## 6. 6단계 테스터를 위한 인수 조건(Acceptance Criteria)

- **AC-1(시간당 카운터)**: 동일 IP에서 60분 이내에 `POST /convert`를 21회 연속 호출하면(각 호출의 성공/실패 여부 무관), 21번째 호출부터 HTTP 429 + `{"error": "요청이 제한되었습니다. 시간당 업로드 횟수를 초과했거나 이미 진행 중인 작업이 있습니다. 잠시 후 다시 시도해주세요"}`가 반환된다. 1~20번째는 이 레이트리밋으로 인해 차단되지 않는다(다른 사유 400/503 등은 별개).
- **AC-2(카운터 윈도우 리셋)**: 캐시가 비워진 직후(또는 `UPLOAD_RATE_LIMIT_WINDOW_SECONDS`=3600초 경과 후) 같은 IP가 다시 21회까지 202를 받을 수 있어야 한다(고정 윈도우 방식이므로 정확히 시각 경과 후 리셋되는지는 시간을 앞당길 수 있는 테스트 환경에서 `cache.clear()`로 대체 확인 가능).
- **AC-3(IP 격리)**: IP A가 시간당 한도(또는 동시 2건 한도)에 걸려 429를 받는 동안, IP B(`REMOTE_ADDR` 다름)는 정상적으로 202를 받아야 한다(같은 프로세스, 같은 캐시 백엔드를 공유해도 IP별로 독립적으로 카운팅됨).
- **AC-4(동시 진행중 2건 한도)**: 특정 IP가 이미 `status in (PENDING, PROCESSING)`인 job을 2건 갖고 있는 상태에서(단, 그 두 job이 **이 unit의 데코레이터를 통해 202로 발급된 job**이어야 함 — 즉 이 IP로 실제 `POST /convert`를 2번 성공시켜 만들어진 job), 같은 IP로 3번째 `POST /convert`를 호출하면 즉시 429가 반환되고, 새로운 `ConversionJob` 행이나 업로드 파일이 생성되지 않아야 한다(뷰 함수 자체가 호출되지 않으므로 부수효과 없음).
- **AC-5(동시 진행중 한도 해제)**: AC-4 상황에서 두 job 중 하나가 `DONE` 또는 `FAILED`로 전이되면(자연 완료 또는 테스트에서 직접 `ConversionJob.objects.filter(...).update(status=...)`), 즉시 다음 요청부터는 동시 진행중 카운트가 1건으로 줄어 429가 해제되어야 한다(추적 리스트에 완료된 job_id가 남아있어도 DB 상태 조회로 필터링되므로 카운트에 포함되지 않음).
- **AC-6(정상 경로 무간섭)**: 한도 이내의 정상 요청(1~20번째, 동시 진행중 0~1건)은 데코레이터가 없을 때와 동일하게 200/202/400/503 등 원래 `convert()` 뷰의 응답을 그대로 받아야 한다(레이트리밋이 정상 흐름을 변형하지 않음).
- **AC-7(IP 스푸핑 방어, production 설정 한정)**: `config.settings.production`이 로드된 상태(또는 `XForwardedForMiddleware`를 직접 `MIDDLEWARE`에 추가한 테스트 환경)에서, 클라이언트가 `X-Forwarded-For` 헤더에 임의의 값을 여러 개 콤마로 연결해 보내도(leftmost 값 조작), 레이트리밋 카운팅은 항상 rightmost 값(신뢰 가능한 엣지가 부가한 값) 기준으로 이루어져야 한다 — 즉 동일한 실제 클라이언트가 leftmost 값만 바꿔가며 요청해도 카운터가 리셋되지 않아야 한다. **dev 환경(`config.settings.dev`)에는 이 미들웨어가 등록되어 있지 않으므로 이 AC는 production 설정에서만 검증 가능**하다(4절 참고, 이번 unit은 미들웨어 자체를 직접 인스턴스화해 우회 검증했음).
- **AC-8(캡차 미구현 확인)**: 이 unit 어디에도 hCaptcha 등 캡차 관련 코드/설정/환경변수가 없어야 한다(DEC-032, v1 범위 밖).

## 7. 수동으로 확인이 필요한 부분

1. **AC-7(프록시 스푸핑 방어)의 실제 프로덕션 환경(Render) 검증** — 이번 unit은 미들웨어 로직을 직접 호출해 정규화 동작만 확인했고, 실제 Render 엣지가 붙이는 `X-Forwarded-For` 형태·다중 프록시 홉 여부는 배포 후(10~12단계) 실측 필요.
2. **시간당 윈도우가 실제로 1시간 경과 후 자연 리셋되는지**(실시간 대기가 필요해 이번 세션에서는 `cache.clear()`로 대체 확인함, 6절 AC-2 참고) — 06단계가 시간을 앞당기는 방법(예: `freezegun` 또는 캐시 타임아웃 직접 조작)으로 재확인 권장.
3. **다중 워커/다중 프로세스 환경에서의 정확도 저하** — `LocMemCache`는 프로세스 로컬이라 gunicorn이 `--workers 1`(03 §2-1 확정)을 벗어나 여러 워커로 스케일되면 이 레이트리밋 정확도가 워커 수만큼 느슨해진다(각 워커가 독립된 카운터를 가짐). 이는 설계서가 이미 인지하고 감수한 트레이드오프(03 §2-1 "단일 워커 전제에서만 정확")이므로 이 unit의 결함이 아니나, 06/09단계가 이 한계를 재확인할 필요가 있다.

## 8. 공유 문서 갱신 (직접 반영 완료 — 단독 호출로 간주)

착수 프롬프트가 "views.py를 공유하는 다른 unit이 동시에 안 돌고 있음을 확인했으므로 단독 호출로 간주해 직접 갱신해도 됨"이라고 명시했으므로, `docs/harness/traceability.md`의 REQ-026 행(작업 단위/구현 상태/비고)을 직접 갱신했다(위 3절 내용 반영). 다만 2절에서 밝힌 대로 **`views.py`가 세션 시작 시점 이후 unit-22 산출물로 추정되는 변경(REQ-028 지연 스윕 트리거)을 이미 포함한 상태로 발견됐다** — 이 unit이 그 변경을 만든 것은 아니며, 손대지도 않았다. 오케스트레이터는 최종 `views.py`가 unit-20/22/23의 변경을 모두 포함해 정상 병합됐는지(특히 `from . import cleanup, limits, ratelimit, storage` 한 줄에 세 unit의 이름이 모두 들어있는지) 웨이브 종료 후 한 번 더 확인 권장.

---

# 재작업 이력 v2 — DEF-023-01 (규칙 F, DEC-044) — 05단계 재작업

- 작성 에이전트: 05-unit-developer / 일자 2026-09-29 / **속도 트랙: L3(변경 없음)** / 병렬 웨이브 아님(다만 타 에이전트가 `webapp/core/net_guard.py`·`wsgi.py`·문서를 동시에 수정 중 — 손대지 않음)
- 트리거: `unit-23-test.md` CONDITIONAL PASS(70/71), TC-903 FAIL. 같은 IP 4스레드 동시 최초 POST 10라운드 모두 202가 4건(기대 <=2).

## R-1. 변경 내역
- 수정 파일은 `webapp/converter/ratelimit.py` **1개뿐**. `views.py`는 변경 불필요(데코레이터 위치·시그니처 동일)라 **미수정**. executor/storage/models/settings/requirements/core/wsgi 미접촉.
- 원인: 조회(뷰 실행 전)와 등록(뷰 종료 후) 사이 구간이 길어 check-then-act 경쟁.
- 수정: 뷰 호출 **전에** 슬롯 예약, 뷰 종료 시 202면 예약을 job_id 추적으로 승계, 아니면 반환.
  - `_try_reserve_slot(ip)`: IP별 락 안에서 `(추적 job_id 중 DB상 PENDING/PROCESSING 수) + (유효 예약 수) >= 2`이면 None(429), 아니면 예약 토큰 발급 — 조회와 예약이 원자적.
  - `_release_slot(ip, token, job_id)`: 같은 락 안에서 (202면) 추적목록 등록 후 예약 제거. 승계 중간에 카운트 빈틈이 없다. 추적목록 `get->append->set`의 lost update(DEF 설명의 부수 위험)도 이 락으로 함께 해소됨.
  - `enforce_rate_limit`: `try/finally`로 뷰가 예외를 던져도 예약 반환. 시간당 카운터(`is_upload_rate_limited`)는 기존과 동일하게 먼저 호출(순서·의미 불변).
  - 예약 TTL 상한(`_TRACKED_JOBS_TTL_SECONDS`=60분, monotonic): 스레드가 매달려 finally에 도달 못 해도 영구 잠금 방지(기존 좀비 PENDING의 TTL 상한과 동일 정책).
  - `is_concurrent_limit_exceeded`는 공개 함수로 유지(읽기 전용, 예약도 합산).
  - `REMOTE_ADDR==""`이면 예약 없이 기존처럼 뷰 직행(fail-open 유지, 범위 외).

## R-2. 설계 근거 / 기각한 대안
- **락 종류**: 전역 락 1개 대신 IP 해시 기반 64개 스트라이프 락. 락 안에서 LocMemCache get/set과 job_id<=50개 IN 쿼리 1회만 수행하므로 짧지만, DB(Neon) 지연이 있어도 다른 IP를 막지 않도록 스트라이프로 분리. **뷰 본체(파일 저장·DB insert·submit_job)는 락 밖**이라 서비스 직렬화 없음.
- **데드락**: 한 번에 락 하나만 획득, 락 안에서 다른 락을 잡거나 뷰를 호출하지 않음(중첩 없음). 락 안 예외도 `with`가 해제. 해시 충돌 IP끼리는 단지 잠시 대기.
- **예약 저장소**: 프로세스 메모리 dict. 캐시(LocMemCache)와 같은 단일 프로세스 전제(03 §2-1, DEC-032). 캐시 `add/incr` 방식은 executor 완료 훅(수정 금지)이 없어 DB 재조회와 병행해야 하므로 기각.
- **DB 카운트를 락 밖에서 스냅샷하는 안**: 스냅샷 이후 다른 스레드의 승계가 끼면 과통과 가능 -> 기각(락 안 조회로 정확성 우선).

## R-3. 설계서 대비 편차
- 없음. 429 문구·상태코드·IP 판정·시간당 20회 로직 무변경. 03/04 문서 수정 요청도 없음.

## R-4. 게이트 1 (정적 분석)
- 레포에 ruff/flake8/mypy/black 설정 없음(원 note 3절과 동일, 재확인: pyproject.toml/webapp에 설정 파일 없음). 대체로 `python -m py_compile webapp/converter/ratelimit.py` 통과 + 아래 실측.

## R-5. 로컬 동작 확인 (격리 venv `.harness-tmp/venv_05_unit23`, 스크립트 `.harness-tmp/_05_unit23/t.py`, 종료 후 삭제)
Django `Client` 다중 스레드(Barrier 동시 출발), dev 설정, SQLite/MEDIA_ROOT는 `.harness-tmp` 경로, `submit_job`=no-op(job이 PENDING 유지, 06 TC-903 재현절차와 동일). 라운드마다 캐시·DB·예약 초기화.

**Before (HEAD의 ratelimit.py, 라운드 12회씩)**
| 스레드 | 라운드별 202 최댓값 | PENDING 행 |
|---|---|---|
| 4 | 4 (12/12 라운드) | 4 |
| 16 | 16 | 16 |
| 40 | 20 (시간당 한도가 상한) | 20 |

**After (수정본, 12라운드씩)**
| 스레드 | 202 | 429 | PENDING 행 | 기타 코드 |
|---|---|---|---|---|
| 4 | 정확히 2 (12/12) | 2 | 2 | 0 |
| 16 | 정확히 2 | 14 | 2 | 0 |
| 40 | 정확히 2 | 38 | 2 | 0 |

- 한 IP 8스레드 x5라운드에서도 추적목록 길이 == 202 수(2) 확인(lost update 없음).
- 슬롯 반환: 뷰 예외(저장 단계 RuntimeError 3회) 후 예약 잔량 0 / 400 x5 후 예약 0·이후 정상 / 503(QueueFull) x4 후 예약 0 / CSRF 403 x4·413은 시간당 카운터 미생성(카운터 None).
- 해제: 순차 202,202,429 -> 1건 DONE 후 202 -> 전부 FAILED 후 202,202,429. 예약 2건 만료(TTL 상한 시뮬레이션: monotonic 과거로 조작) 후 재예약 성공, 만료 전에는 3번째 거절.
- 경계: 즉시 완료 스텁으로 22회 POST -> 1~20 202, 21·22 429; 429 본문이 기존 확정 문구와 일치; IP A 소진과 무관하게 IP B 202; GET `/` 무영향; `REMOTE_ADDR=""` 5회 모두 202(기존 fail-open 유지, 예약 미생성).
- 결과: 위 실측 항목 전부 PASS, 스크립트 최종 `FAILS 0`. (중간에 스크립트 자체 결함 2건 — Status 문자열 대소문자, None 참조 — 을 발견해 코드 결함이 아님을 확인 후 스크립트 수정·재실행.)
- 이 실측은 05의 최소 동작 확인이며 06 결과서가 아니다. 정식 재검증(TC-903/904/905 재실행)은 06 책임.

## R-6. 게이트 2 체크
- [x] 명세 일치(03 §6-4/DEC-032, 04 문구 불변) - [x] 에러 경로: 예외는 삼키지 않고 finally로 반환 후 재전파, 파싱 실패는 기존과 동일하게 job_id=None
- [x] 경계 입력 검증: 신규 사용자 입력 없음(REMOTE_ADDR는 미들웨어 정규화값) - [x] 시크릿 없음 - [x] 신규 의존성 없음(표준 라이브러리 threading/time/uuid만)
- [x] 범위 외 변경 없음(ratelimit.py 1개, views.py 미수정)

## R-7. 06 재검증 인수 조건
- AC-9(신규): 같은 IP N스레드(4/16/40) 동시 최초 POST(submit_job=no-op) 반복 라운드에서 202는 항상 2건 이하, PENDING 행도 2건 이하, 나머지 429(문구 불변).
- AC-4/5, AC-1~3 기존 그대로 유지(무회귀). 예외·4xx·503 후 슬롯 미누수. 데드락/행 없음(스레드가 모두 join 됨).
- 수동 확인: 실제 gunicorn `--threads 4`와 실 executor 조합에서의 한도(실환경 스레드 스케줄링)는 배포 전 07/10단계에서 확인 권장.

## R-8. 범위 외 유지(코드 변경 안 함)
REMOTE_ADDR 빈 문자열 fail-open, IPv6 대소문자/주소 회전 정규화, 후행 콤마 rightmost 빈값 폴백, Retry-After 미제공, 동시한도 차단 시도의 시간당 카운터 소모(TC-605), 캐시 장애 시 500(fail-closed), 다중 워커 시 락·캐시 분산(단일 워커 전제 재확인: 예약 메모리와 락도 프로세스 로컬), 고정 윈도우 2배 버스트.

## R-9. 임시 아티팩트 정리(규칙 K)와 git status 원문
`.harness-tmp/venv_05_unit23`, `.harness-tmp/_05_unit23`(스크립트·sqlite·media), 빈 `venv_05_unit23_x`, `pip install -e .`가 만든 `pdf_to_hwpx.egg-info/` 모두 삭제. `.harness-tmp/`는 빈 디렉터리.
```
 M docs/harness/03-system-design.md        (타 에이전트/오케스트레이터 소유)
 M docs/harness/decisions.md               (오케스트레이터/unit-9)
 M docs/harness/traceability.md            (오케스트레이터/unit-9)
 M docs/harness/units/unit-9-note.md       (unit-9)
 M docs/harness/units/unit-9-test.md       (unit-9)
 M docs/harness/verify-log_03-system-design.md (타 에이전트)
 M docs/harness/verify-log_unit-9-test.md  (unit-9)
 M webapp/config/wsgi.py                   (unit-9)
 M webapp/converter/ratelimit.py           (** 이 재작업 **)
 M webapp/core/net_guard.py                (unit-9)
?? docs/harness/units/unit-23-test.md      (unit-23 06단계)
?? docs/harness/verify-log_unit-23-test.md (unit-23 06단계)
?? docs/harness/verify-log_unit-9-note.md  (unit-9)
```
(이 note 추가분 `unit-23-note.md`와 `verify-log_unit-23-note.md`(신규)는 이 명령 이후 작성/수정.)

## 공유 문서 갱신 요청 (오케스트레이터가 반영)
- `traceability.md` REQ-026 / 구현 상태: "구현 완료(unit-23 v2) — DEF-023-01 수정 반영(예약 슬롯+IP별 락), 06 재검증 대기"
- `traceability.md` REQ-026 / 작업 단위: 변경 없음(unit-23)
- `decisions.md`: DEC-044 이행 기록 — "DEF-023-01을 ratelimit.py 슬롯 예약(스트라이프 락, TTL 상한 예약)으로 수정, executor/views 무변경. 범위 외 리스크(fail-open, IPv6, Retry-After)는 유지."
- 규칙 A 미결 질문: 없음.
