# unit-9 구현 노트 — REQ-011(부분) 아웃바운드 화이트리스트(`core/net_guard.py`)

## 0. 속도 트랙

**표기 없음 → L3**(오케스트레이터 호출 프롬프트에 트랙 명시가 없었음). 6단계는 L3 기준 절차를 적용할 것.

## 1. 병렬 실행 여부

이번 호출은 **병렬 웨이브**로 진행됨 — 동시에 **unit-22**가 별도 호출로 구현 중이었다(오케스트레이터 지시사항에 명시). 이 unit은 프롬프트로 확정된 파일 범위(`webapp/core/net_guard.py` 신규, `webapp/config/wsgi.py` 1줄 호출)만 수정했다.

**관찰 사항(참고용, 조치 불필요)**: 작업 중 `git status`를 보면 unit-20/21/22/24/25가 동시에 만든 다른 파일들(`converter/executor.py`, `converter/cleanup.py`, `core/middleware.py`, `legal/` 등)이 워킹트리에 함께 존재했으나, 내가 건드린 파일(`core/net_guard.py`, `config/wsgi.py`)과는 전혀 겹치지 않았다. `config/wsgi.py`의 기존 내용에는 이미 unit-19가 남겨둔 "unit-9가 완료되면 여기서 net_guard.install()을 호출" placeholder 주석이 정확히 이 자리에 있어, 파일범위·삽입지점에 대한 모호함이 전혀 없었다(규칙A 질문 불필요).

## 2. 배경 요약 (역할 반전, DEC-033)

v4가 상정한 "아웃바운드 소켓 전면 차단"은 폐기되고, "승인되지 않은 제3자 서비스(클라우드 LLM/OCR SaaS 등) 호출을 화이트리스트 방식으로 기술적 차단"하는 디펜스-인-뎁스로 반전됐다(03 §6-3, §1-3 unit-9 행). unit-9는 애초에 Not Started였으므로 재작업 비용은 0이다 — 이번 구현은 v4 코드의 수정이 아니라 완전 신규 작성이다.

## 3. 구현 범위

### 3-1. `webapp/core/net_guard.py` (신규)

- `install(enforce=True)`: 기동 시 1회 호출되는 공개 함수.
  - `enforce=False`(dev)면 화이트리스트를 적용하지 않고 즉시 반환 — 로컬 개발이 net_guard 때문에 막히지 않아야 한다는 오케스트레이터 지시사항을 반영(unit-19가 확립한 dev/production 분리 패턴 재사용, unit-24의 미들웨어 분기와 동일한 원칙).
  - `enforce=True`(production)면:
    1. `DATABASE_URL`, `R2_ENDPOINT_URL` 두 환경변수를 `urllib.parse.urlsplit()`으로 파싱해 호스트명만 추출 → 허용목록(set) 구성. **하드코딩 없음** — 03 §6-3 요구사항 그대로.
    2. `socket.create_connection`을 몽키패치해, 접속 대상 호스트가 허용목록에 없으면 `NetworkAccessBlockedError`를 발생시키고, 있으면 원본 함수로 통과시킨다.
    3. 차단 시도는 `logging.getLogger("core.net_guard").warning(...)`으로 반드시 로그에 남긴다(조용히 차단만 하지 않음 — 프롬프트 필수 요구사항).
    4. 모듈 전역 `_installed` 플래그로 중복 설치를 방지(멱등성).
- `NetworkAccessBlockedError(Exception)`: 차단 시 발생하는 전용 예외.
- **Render 플랫폼 필수 트래픽(헬스체크/DNS 등) 관련**: 03 §6-3 원문이 이를 허용목록 후보로 언급하지만 구체적 식별 방법이 없어 배포 후 실측이 필요한 항목이다. 이번 구현은 이를 "허용목록에 넣지 않는" 대신 "production에서 dev만큼은 아니지만 여전히 강제 적용"으로 두고, 실제 배포 후(10~12단계) 헬스체크 등이 이 화이트리스트 때문에 실패하면 그때 구체적 호스트를 허용목록에 추가하는 방식으로 대응하는 것을 전제로 했다 — **인바운드 헬스체크(Render→앱)는 이 모듈의 방어 대상이 아니다**(이 모듈은 앱 프로세스가 만드는 아웃바운드 접속만 가로챈다). 앱이 스스로 아웃바운드로 Render API 등을 호출하는 경로는 현재 코드베이스에 없으므로 실질적 충돌 가능성은 낮다고 판단했다.

### 3-2. `webapp/config/wsgi.py` (기존 파일, 1줄 호출 추가)

```python
from core.net_guard import install as install_net_guard
...
install_net_guard(
    enforce=os.environ["DJANGO_SETTINGS_MODULE"].endswith(".production")
)
application = get_wsgi_application()
```

- `enforce` 판별 근거: `DJANGO_SETTINGS_MODULE` 값이 `config.settings.production`으로 끝나는지 여부. `os.environ.setdefault(...)` 직후이므로 이 시점에 값이 항상 존재함이 보장된다(dev 기본값 포함). `django.conf.settings.DEBUG`를 기준으로 판별하는 대안도 고려했으나, `get_wsgi_application()` 호출 전에 settings가 완전히 로드되어 있다는 보장이 약해(지연 로딩) `DJANGO_SETTINGS_MODULE` 문자열 판별이 더 단순하고 확실하다고 판단(가역적 구현 세부사항, 규칙A 대상 아님).
- unit-19가 남겨둔 placeholder 주석을 정확히 이 위치에서 교체했다.

## 4. 설계서 대비 편차 및 알려진 한계 (있는 그대로 기록)

1. **알려진 한계(이미 REQ-011에 문서화됨)** — `psycopg[binary]`는 libpq(C 확장)가 자체적으로 소켓 syscall을 수행하므로 이 순수 파이썬 `socket.create_connection` 몽키패치를 우회한다. Neon은 애초에 허용 대상이므로 우회되어도 보안 저하는 아니다. 이 모듈이 실제로 방어하는 것은 `urllib3`/`requests`/`boto3`(botocore가 내부적으로 `http.client`→`socket`을 쓰므로 R2 접근은 방어 범위 안) 등 파이썬 `socket` 모듈 경유 호출뿐이다. **다시 발견하려 시도하지 않고 note에 그대로 기록**(호출 프롬프트 지시사항).
2. **미문서화 위험(수동 확인 필요, 이번 unit의 파일범위 밖이라 조치하지 않음)**: `config/settings/production.py`는 장애 알림 메일 발송을 위해 SMTP(`EMAIL_HOST`)를 사용한다(03 §7-2). 그러나 03 §6-3 원문은 허용목록에 Neon `DATABASE_URL` 호스트와 R2 `R2_ENDPOINT_URL` 호스트만 명시하고 SMTP 호스트는 언급하지 않는다. 이번 구현은 **설계서 원문 그대로** 두 환경변수만 허용목록에 반영했으므로, `EMAIL_HOST`가 설정된 배포 환경에서는 net_guard가 SMTP 연결도 차단할 가능성이 있다. 이는 설계서 자체의 갭이지 이번 unit의 임의 축소가 아니다 — **6단계 테스터와 09단계 보안검증이 반드시 인지해야 할 항목**으로 남긴다(오케스트레이터가 이후 웨이브에서 03 문서 보정 또는 별도 unit으로 SMTP 호스트 허용 여부를 결정해야 함).
3. **Render 플랫폼 필수 트래픽 허용목록화는 보류** — §3-1에서 상술한 대로 배포 후 실측 필요 항목으로 남김(프롬프트가 허용한 판단).

## 5. 게이트 1 — 정적 분석/린트

리포지토리 전체(루트 `pyproject.toml`, `webapp/` 하위)에 ruff/flake8/black/mypy/pylint 설정이 **없음을 재확인**(unit-19/24-note.md와 동일 결론 — 있는데 건너뛴 것이 아니라 애초에 설정 자체가 없음).

대신 `python -m py_compile webapp/core/net_guard.py webapp/config/wsgi.py` 실행 → 컴파일 성공. `manage.py check`(dev 설정) 실행 → `System check identified no issues (0 silenced).`

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — §6-3의 몽키패치 대상(`socket.create_connection`), 허용목록 동적 구성(환경변수 파싱), 차단 시 예외(`NetworkAccessBlockedError`), 로깅 요구사항 모두 반영.
- [x] 에러 처리가 누락된 경로가 없는가 — `DATABASE_URL`/`R2_ENDPOINT_URL`이 없거나 파싱 실패해도(호스트명 없음) 예외를 던지지 않고 경고 로그만 남기고 계속 진행(허용목록이 비어있는 상태로 production이 시작되는 것 자체는 이 모듈의 책임 밖 — `production.py`의 `_require_env`가 이미 두 값을 필수로 강제하므로 실제로는 항상 값이 존재).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 모듈 자체는 사용자 입력이 아니라 환경변수(배포 설정)를 다루는 인프라 계층이라 "사용자 입력 검증" 대상은 아니다. 대신 접속 시도마다 목적지 호스트를 검사하는 것이 이 모듈의 핵심 책임이며 이를 빠짐없이 수행한다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음. 테스트에 사용한 `postgres://user:pass@...` 등은 로컬 검증용 가짜 값이며 코드에는 포함되지 않음(터미널 명령 인자로만 사용, 커밋 대상 아님).
- [x] 새로 추가한 외부 의존성이 있다면 실제 레지스트리 존재 확인 — **신규 의존성 없음**(표준 라이브러리 `socket`, `os`, `logging`, `urllib.parse`만 사용). `requirements.txt` 변경 없음.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `core/net_guard.py`(신규) 1개 파일과 `config/wsgi.py`의 지정된 1개 지점(placeholder 주석 → import + `install_net_guard(...)` 호출)만 수정. 그 외 파일 변경 없음(`git status`/`git diff`로 확인).

## 7. 로컬 동작 확인 (`.harness-tmp/venv_05_unit9/`, 확인 후 삭제 완료)

1. `python -m venv .harness-tmp/venv_05_unit9` 생성 후 `pip install -r webapp/requirements.txt` + `pip install -e .`(pdf_to_hwpx editable).
2. `manage.py check`(dev 설정) → `System check identified no issues (0 silenced).`
3. **직접 단위 검증**(`core.net_guard.install()` 직접 호출, `DATABASE_URL="postgres://user:pass@allowed-db.example:5432/dbname"`, `R2_ENDPOINT_URL="https://allowed-r2.example.com"` 가짜 값 설정):
   - `enforce=True` 상태에서 `socket.create_connection(("blocked-host.example", 80))` → **`NetworkAccessBlockedError` 발생 확인**(PASS).
   - `enforce=True` 상태에서 `socket.create_connection(("allowed-db.example", 5432))`(DATABASE_URL에서 파싱된 호스트) → `NetworkAccessBlockedError`가 아니라 `socket.gaierror`(가짜 도메인이라 DNS 실패) 발생 → 가드를 통과해 원본 `create_connection`까지 도달했음을 확인(PASS, 실제 연결 성공 여부는 검증 대상이 아니라 "차단되지 않고 통과"가 검증 대상).
   - `enforce=True` 상태에서 `socket.create_connection(("allowed-r2.example.com", 443))`(R2_ENDPOINT_URL에서 파싱된 호스트) → 동일하게 통과 확인(PASS).
   - `enforce=False` 상태에서 `socket.create_connection(("blocked-host.example", 80))` → 차단되지 않고 통과(가짜 도메인이라 `gaierror`) 확인(PASS, dev에서는 강제 자체가 비활성화됨을 검증).
4. **엔드투엔드(`config/wsgi.py` 실제 import) 검증**:
   - `DJANGO_SETTINGS_MODULE=config.settings.dev`로 `import config.wsgi` → 정상 로드(`application` 객체 생성 확인), `core.net_guard._installed == True`이며 화이트리스트 미적용(dev) 확인.
   - `DJANGO_SETTINGS_MODULE=config.settings.production` + 가짜 `SECRET_KEY`/`DATABASE_URL`/`R2_*`/`DJANGO_ALLOWED_HOSTS` 환경변수로 `import config.wsgi` → 정상 로드된 뒤, 곧바로 `socket.create_connection(("example.com", 80))` 시도 → **`NetworkAccessBlockedError` 발생 확인**(실제 production 부팅 경로에서 화이트리스트가 강제 적용됨을 종단간 검증).
5. 확인 후 `.harness-tmp/venv_05_unit9/`를 삭제해 정리 완료(규칙 K). 임시 테스트 스크립트는 세션 스크래치패드(`/tmp/test_net_guard*.py`)에 작성했다가 검증 후 함께 삭제했다(리포지토리에 남기지 않음).

## 8. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

1. **차단 동작**: `enforce=True`(production 설정)로 `core.net_guard.install()`을 호출한 프로세스에서, `DATABASE_URL`/`R2_ENDPOINT_URL`에서 파싱되지 않은 임의의 호스트(예: `example.com:80`)로 `socket.create_connection`을 호출하면 `core.net_guard.NetworkAccessBlockedError`가 발생해야 한다.
2. **허용 동작**: 같은 조건에서 `DATABASE_URL`의 호스트(예: `postgres://u:p@HOST:5432/db`의 `HOST` 부분) 또는 `R2_ENDPOINT_URL`의 호스트로 접속을 시도하면 차단되지 않고(즉 `NetworkAccessBlockedError`가 발생하지 않고) 원래의 `socket.create_connection` 동작(성공 또는 다른 종류의 네트워크 예외)으로 이어져야 한다.
3. **dev 비활성화**: `DJANGO_SETTINGS_MODULE=config.settings.dev`로 `config.wsgi`를 import한 프로세스에서는 임의의 호스트로의 접속 시도가 `NetworkAccessBlockedError`로 차단되지 않아야 한다(로컬 개발 방해 금지).
4. **로그 기록**: 차단된 접속 시도는 `core.net_guard` 로거에 `WARNING` 레벨로 남아야 한다(`caplog`나 로그 캡처로 확인 가능 — 조용히 예외만 던지고 로그가 없으면 실패로 간주).
5. **진입점 통합**: `webapp/config/wsgi.py`를 `DJANGO_SETTINGS_MODULE=config.settings.production`(필수 환경변수 모두 채운 상태)으로 import하는 것만으로 화이트리스트가 자동 적용되어야 한다(수동으로 `install()`을 별도 호출할 필요 없음). `DJANGO_SETTINGS_MODULE=config.settings.dev`로 import할 때는 적용되지 않아야 한다.
6. **알려진 한계 확인(실패로 취급하지 말 것)**: `psycopg`(libpq) 경유 DB 연결은 이 가드를 우회한다 — 09단계 보안검증이 이 사실을 알고 있어야 하며, 6단계에서 이를 "버그"로 재보고할 필요는 없다(이미 traceability.md REQ-011에 문서화됨).
7. **SMTP 미허용 위험 확인(수동 확인 항목)**: `EMAIL_HOST`가 설정된 배포 환경에서 장애 알림 메일 발송이 이 화이트리스트에 의해 차단되는지 여부를 09단계 또는 실제 배포 검증(10~12단계) 시 반드시 확인할 것 — 이번 unit은 설계서(§6-3) 원문 범위(Neon+R2)만 구현했으므로 이 항목은 버그가 아니라 설계서 자체의 알려진 갭으로 분류해야 한다.

## 9. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

### traceability.md 갱신 요청

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-011 | 작업 단위 (unit-n) | `unit-9`(변경 없음, 표기 그대로 유지) |
| REQ-011 | 구현 상태 | `구현 완료(unit-9, 부분 — 화이트리스트만. 인바운드 관련 서술은 03 §6-3에 따라 폐기) — 6단계 단위테스트 대기` |
| REQ-011 | 단위테스트 (unit-n-test) | 미정 유지(6단계가 채움) |

기존 REQ-011 행 "비고" 컬럼의 DEC-033/알려진 한계(psycopg 우회) 서술은 이번 구현과 내용이 일치하므로 별도 수정 요청 없음. 다만 아래 신규 항목을 "비고"에 **추가**해줄 것을 요청한다:

> **unit-9 구현 완료 시 신규 발견(수동 확인 필요)**: 03 §6-3 허용목록 원문(Neon+R2)에는 `config/settings/production.py`가 §7-2에서 이미 사용 중인 SMTP(`EMAIL_HOST`)가 포함되어 있지 않다. net_guard가 설계서 원문 그대로 구현되었으므로, 배포 환경에서 `EMAIL_HOST`가 채워지면 장애 알림 메일 발송이 이 화이트리스트에 의해 차단될 수 있다. 09단계 보안검증/10~12단계 실배포 검증 시 반드시 확인 필요(unit-9-note.md §4-2, §8-7 참고).

decisions.md에 남길 새로운 규칙 A 질문은 없음 — 설계서 명세(§6-3)와 unit-19가 미리 남겨둔 wsgi.py placeholder 덕분에 파일범위·삽입지점·역할반전 방향 모두 모호함 없이 진행 가능했다. 다만 위 SMTP 갭은 오케스트레이터가 "이번 설계서의 알려진 정보 갭"으로 decisions.md에 신규 항목(예: DEC-040 후보)으로 남길지 여부를 판단해야 할 사안으로 참고 보고한다(이 unit이 임의로 결정하지 않음).

---

## 10. 재작업 이력 (규칙 F, 06 FAIL: DEF-001 Critical) — 2026-09-29

> 이 절이 §3-1(패치 대상 `socket.create_connection`), §3-2(`endswith(".production")`), §4-1("botocore는 http.client 경유" 서술), §7(로컬 확인 방식)과 충돌하는 부분은 **이 절이 우선**한다(해당 절은 v1 이력으로 보존). 속도 트랙: L3 유지. 병렬 여부: 단독 재작업(다른 에이전트가 traceability.md/decisions.md를 동시 편집 중이나 이 unit은 건드리지 않음).

### 10-1. 변경 내역
1. `webapp/core/net_guard.py`: 패치 지점을 `socket.create_connection` 단일 -> **`socket.socket.connect`/`connect_ex`(권위 있는 차단) + `socket.getaddrinfo`(호스트명 게이트 + 허용 IP 기록)**로 교체. `create_connection` 패치는 제거(getaddrinfo/connect가 이미 포괄).
2. `webapp/config/wsgi.py`: 판정식을 `endswith(".production")`(fail-open) -> `os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.dev"`(**fail-closed**)로 변경.
3. 그 외 파일 변경 없음(converter/*, settings, requirements 무변경).

### 10-2. 설계 근거
- urllib3(botocore/boto3, requests 기반)는 `create_connection`을 거치지 않고 `getaddrinfo`+`socket()`+`connect()`를 직접 조합한다. 모든 TCP 클라이언트(http.client, urllib.request, urllib3, asyncio `sock_connect`, SSLSocket 포함)가 반드시 지나는 공통 지점은 `socket.socket.connect/connect_ex`이므로 여기를 차단 지점으로 선택. 06의 대안 2(`urllib3.util.connection.create_connection` 패치)는 전이 의존성의 내부 구현에 결합되어 버전에 취약하고 urllib3를 거치지 않는 경로를 못 막아 기각.
- connect 시점 목적지는 이미 IP라 호스트명 허용목록과 직접 비교할 수 없다. 그래서 `getaddrinfo`를 감싸 (a) 허용목록에 없는 호스트명 조회는 즉시 `NetworkAccessBlockedError`(로그에 호스트명이 남고 DNS 질의도 나가지 않음), (b) 허용 호스트명이 풀린 IP를 허용 IP 집합에 기록 -> connect가 그 IP만 통과. IP 리터럴 직접 접속은 허용 IP 집합에 없으면 connect에서 차단(DNS 우회 봉쇄). IPv6 4-tuple, IPv4-mapped IPv6(::ffff:a.b.c.d -> IPv4로 환원), zone id(%eth0), 호스트명 대소문자/후행 점 정규화를 처리한다. 주소 형태를 판정할 수 없으면 fail-closed.
- 멱등성: `_installed` 플래그 유지 + 원본 함수를 `_net_guard_original` 속성으로 unwrap해 reload 시 이중 래핑 방지.
- 회귀 방지: DB/R2 호스트(대소문자 무관)는 기존처럼 통과. `enforce=False`(dev)는 아무것도 패치하지 않음(AC-3 유지). 차단 시 WARNING 로그(AC-4) 유지.

### 10-3. 편차 및 판단 사항 (리뷰/확인 요청 포함)
1. **루프백(127.0.0.0/8, ::1, `localhost`)과 AF_UNIX는 통과**시킨다. v1은 `create_connection`만 막아 raw `socket.connect`는 원래 막지 않았으므로, connect 레벨로 내리면 새로 깨질 수 있는 로컬 IPC를 회귀 방지 차원에서 열어 둔 것이다. 외부로 데이터가 나가지 않는다. 엄격 차단으로 바꾸려면 알려 달라(에이전트 판단, 가역).
2. 그 결과 v1에서 차단되던 `create_connection(("127.0.0.1",...))`은 이제 통과(의도된 변경).
3. `getaddrinfo` 차단은 호스트명만 대상(None/빈 값/IP 리터럴/`localhost`는 통과). 설계서 §6-3에 없던 강화이며, 없으면 오프라인/미해석 환경에서 차단 여부가 `gaierror`에 가려지고 DNS 질의가 새는 문제가 있어 채택.
4. **알려진 한계(추가 문서화)**: psycopg(libpq C 확장) 우회는 v1 그대로 유지(구조적 한계, 변경 없음). 추가로 UDP `sendto/sendmsg` 비연결 전송과 C 확장이 여는 소켓은 범위 밖. 허용 호스트와 **IP를 공유하는 다른 호스트로의 IP 리터럴 접속**은 통과(IP 수준 검사의 본질적 한계). 허용 IP 집합은 DNS 재해석마다 누적되나 허용 호스트가 2개뿐이라 규모는 미미.
5. **DEC-040(EMAIL_HOST 허용 여부): 미결 유지.** 허용목록에 추가하지 않았고 관련 코드 변경 없음. EMAIL_HOST 설정 시 SMTP 접속은 차단될 수 있다(09/10단계 정책 결정 대기).

### 10-4. TC-013 fail-closed 상세
- dev 모듈명은 `webapp/config/settings/dev.py` 실물로 확인(`config.settings.dev`). `manage.py`(기본값 dev), `.env.example`(dev), `runserver`(config.wsgi import 경유)가 모두 정확히 이 문자열을 쓰므로 dev 실행은 회귀 없음(`manage.py check` 통과).
- 실측(10-6): `config.settings.dev`와 미설정(setdefault -> dev)만 enforce=False. 빈 값, `config.settings`, `config.settings.Dev`, `Config.Settings.DEV`, 후행 공백, `devv`, `production`, `production_backup`은 전부 enforce=True(패치 적용 + 차단 확인).
- 부작용: 빈 값/오탈자는 net_guard가 켜진 채 Django import 단계에서 ImproperlyConfigured/ModuleNotFoundError로 기동 실패한다(기존에도 기동 불가였고 보안 관점에서만 달라짐).

### 10-5. 게이트
- 게이트 1: 프로젝트에 lint/type-check/formatter 설정 없음(루트 pyproject.toml에 ruff/flake8/black/mypy 항목 없고 별도 설정 파일도 없음을 재확인). 대체로 `py_compile`(net_guard.py, wsgi.py) 성공, dev 설정 `manage.py check` -> `System check identified no issues (0 silenced).`
- 게이트 2:
  - [x] 설계/DEF-001 권고 및 사용자 확정 범위와 일치 (편차는 10-3에 명시)
  - [x] 에러 처리: 판정 불가 주소/비문자 host는 예외를 삼키지 않고 차단(fail-closed), 원본 예외는 그대로 전파
  - [x] 시스템 경계 검증: 소켓 주소/호스트명을 매 호출 검사, 환경변수 파싱 실패는 경고 로그(기존 유지)
  - [x] 하드코딩 시크릿/호스트 없음 (허용목록은 환경변수 파싱)
  - [x] 신규 의존성 없음(표준 라이브러리 `ipaddress`만 추가). 검증용 venv에만 `requests`를 설치(PyPI 실재, 설치 성공 2.34.2) - requirements.txt 무변경
  - [x] 범위 외 변경 없음 (수정 파일: net_guard.py, wsgi.py, 본 note, 신규 verify-log)

### 10-6. 로컬 동작 확인 (`.harness-tmp/venv_05_unit9/`, 종료 후 삭제)
방법: 실제 외부망 전송을 막기 위해 net_guard가 호출하는 "원본" getaddrinfo/connect를 스텁으로 교체(허용 호스트는 TEST-NET-3 203.0.113.x로 해석, connect는 호출 기록 후 ConnectionRefusedError). 차단 대상은 원본 connect가 **호출되지 않았음**을 함께 단언. 45개 단언 전부 PASS(`ALL OK`), 재설치 idempotent 확인.
- 차단 확인: 대상 {호스트명 `blocked-host.example`, IPv4 리터럴 `93.184.216.34`, IPv6 리터럴 `2606:2800:220:1:248:1893:25c8:1946`, IPv4-mapped `::ffff:93.184.216.34`} x 경로 {boto3 `list_buckets`, requests, urllib3 PoolManager, urllib.request, http.client, socket.create_connection, raw `connect`, raw `connect_ex`} 전부 `NetworkAccessBlockedError`(boto3는 `HTTPClientError`로 감싸지며 원인 체인에 포함) + 원본 connect 미호출. AF_INET6 4-tuple raw connect도 차단. 허용 IP와 인접한 `203.0.113.6`도 차단.
- 허용 확인(원본 connect까지 도달, 차단 예외 아님): boto3/requests/urllib3 -> `allowed-r2.example.com`, urllib.request -> `ALLOWED-R2.example.com.`(대소문자+후행 점), http.client/create_connection -> `allowed-db.example:5432`, 허용 호스트가 풀린 IP 직접 connect, 그 IPv4-mapped IPv6, 루프백 127.0.0.1 / ::1 / `localhost`, AF_UNIX.
- 진입점 e2e(`import config.wsgi`, 케이스별 서브프로세스): `config.settings.dev`/미설정 -> `patched=False`; `config.settings.production`(가짜 필수 env), 빈 값, `config.settings`, `.Dev`, `Config.Settings.DEV`, `dev `(후행 공백), `devv`, `production_backup` -> `patched=True` + 비허용 IP `203.0.113.9` connect가 `blocked`.
- 외부망 전송 없음: 차단 대상은 스텁 뒤에서 미도달, 허용 대상은 스텁이 응답. 고지 사항: 테스트 스크립트 초기 버전에서 스텁이 대문자+후행 점 호스트(`ALLOWED-R2.example.com.`)를 매칭하지 못해 예약 도메인 `.example`에 대한 실제 DNS 질의가 1회 나갔다(전송 데이터 없음, 스텁 정규화 수정 후 재실행). 테스트 스크립트는 세션 스크래치패드에만 있고 리포지토리에 남기지 않았다.

### 10-7. 6단계 재테스트 인수 조건 (보강)
06은 AC-1~AC-7 전체 + 아래를 재실행한다: (a) DEF-001 재현 절차(boto3 IP 리터럴 엔드포인트)가 이제 `NetworkAccessBlockedError` 체인으로 차단, (b) requests(TC-011)는 검증 venv에 설치해 스킵하지 말고 실행, (c) TC-013 경계 문자열이 10-4대로 판정, (d) TC-008 멱등성은 `socket.getaddrinfo`/`socket.socket.connect`/`connect_ex` 참조 동일성으로 확인(`socket.create_connection` 참조 전제는 폐기), (e) TC-006 허용목록 공집합에서 루프백 외 모든 접속 차단, (f) TC-018 psycopg 한계 문구 유지, (g) 루프백 통과는 10-3-1의 의도된 편차임을 인지.

### 10-8. 공유 문서 갱신 요청 (오케스트레이터 반영)
| 대상 | REQ-ID / DEC | 컬럼 | 값 |
|---|---|---|---|
| traceability.md | REQ-011 | 구현 상태 | `재작업 완료(unit-9 v2, DEF-001 해소: socket.socket.connect/connect_ex + getaddrinfo 가드) - 06단계 재테스트 대기` |
| traceability.md | REQ-011 | 비고 | "botocore가 http.client 경유" 서술 정정: botocore/requests는 urllib3 경유이며 v2는 socket.socket.connect 레벨에서 차단. 추가 한계: UDP sendto/C 확장 소켓/허용 IP 공유 호스트의 IP 리터럴. 루프백/AF_UNIX 통과. DEC-040(EMAIL_HOST) 미결 유지. |
| decisions.md | 신규 DEC(규칙 F 재작업 결과) | 결정 | 패치 지점을 socket.socket.connect/connect_ex + getaddrinfo로 변경(근거 10-2). 사용자 승인: TC-013 fail-open -> fail-closed(`DJANGO_SETTINGS_MODULE != "config.settings.dev"`이면 enforce). 루프백/AF_UNIX 통과는 에이전트 판단(가역, 10-3-1, 사용자 확인 요청). |
| decisions.md | DEC-040 | 상태 | 미결 유지(허용목록 무변경) |

### 10-9. 임시 아티팩트 정리 및 git status (규칙 K)
`.harness-tmp/venv_05_unit9/`, `.harness-tmp/_05_unit9_wsgi.py` 삭제 완료(`ls .harness-tmp` 결과 비어 있음). 정리 후 `git status` 원문:
```
On branch PROD_SCH
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   docs/harness/units/unit-9-note.md
	modified:   webapp/config/wsgi.py
	modified:   webapp/core/net_guard.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/harness/verify-log_unit-9-note.md

no changes added to commit (use "git add" and/or "git commit -a")
```

---

## 11. 재작업 이력 2 (규칙 F, 06 재검증 DEF-002 Low, DEC-045) — 2026-09-29

속도 트랙: L3 유지. 병렬 여부: 단독(오케스트레이터가 dev 서버를 별도 구동 중, 서버/런타임 파일 무접촉).

### 11-1. 변경 내역
`webapp/core/net_guard.py` `check_address()`의 호스트명 분기 1줄: `if norm in allowed_hosts:` -> `if norm == "localhost" or norm in allowed_hosts:`. `norm`은 기존 `_normalize_host`(strip, lower, rstrip("."))를 그대로 사용(`check_host_for_lookup`의 기존 localhost 판정과 동일 방식). 다른 로직·파일 무변경. 설계서 §6-3 v5.1(DEC-043)/§10-3-1 `localhost 통과`와 이제 일치.

### 11-2. 실측 (스텁 기반, 외부 DNS/TCP 없음, 검증용 venv `.harness-tmp/venv_05_unit9b`에 requests 2.34.2, boto3 1.43.104 설치 후 종료 시 삭제)
원본 getaddrinfo/connect/connect_ex를 스텁으로 교체(차단 대상은 "원본 connect 미호출"을 함께 단언, 미허용 호스트명은 스텁 getaddrinfo에 도달하면 leak으로 기록). 총 107개 단언, 2회 실행 모두 `ALL OK`, DNS leak 0.
- DEF-002 재현 해소: raw `connect`/`connect_ex` x `localhost`, `LOCALHOST`, `Localhost.`, `localhost.` 통과(원본 connect 도달). `getaddrinfo`/`create_connection("localhost")` 기존대로 통과.
- 접미사/유사 문자 차단(정확 일치만): `localhost.evil.com`, `evil.localhost`, `sub.localhost.`, `xlocalhost`, `localhostx`, `localhost x`, `local host`, `localhost:80`, `localhost%eth0`, `localdomain`, `localhost\nINJECT`, `localhost\x00.evil.com`, 키릴 `lоcalhost`/`localhosт`, 전각 `ｌｏｃａｌｈｏｓｔ`, 로마숫자 `ⅼlocalhost`, 유니코드 마침표 `localhost。` 전부 raw connect/connect_ex/getaddrinfo에서 `NetworkAccessBlockedError`, 원본 connect 미호출.
- localhost가 비루프백 IP(203.0.113.50)로 풀리는 환경: `create_connection`, `urllib.request`, `http.client`, `requests`는 connect 단계 IP 검사에서 차단(원본 connect 미호출). 루프백으로 풀리면 통과. 이름만 믿고 통과시키는 신규 경로는 getaddrinfo 경유 경로에는 없음.
- 회귀 없음: {`blocked-host.example`, IPv4 `93.184.216.34`, IPv6 `2606:2800:220:1:248:1893:25c8:1946`, mapped `::ffff:93.184.216.34`, 허용 IP 인접 `203.0.113.6`} x {raw connect, raw connect_ex, urllib.request, urllib3, requests, create_connection, boto3} 전부 차단, http.client 비허용 호스트 차단. 허용 R2/DB 호스트(대소문자·후행 점 포함)와 허용 IP raw connect는 통과.

### 11-3. 관찰 사항 (변경하지 않음, 범위 밖 - 미결 질문)
1. 잔여 한계(신규 아님, 문서화 대상): raw `sock.connect(("localhost", port))`처럼 호스트명이 그대로 C 레벨 connect로 들어오면 이름을 파이썬에서 IP로 풀 수 없어 이름만으로 통과한다. `/etc/hosts` 등이 localhost를 비루프백 IP로 매핑한 환경에서는 그 IP로 나갈 수 있다(실측: 스텁에서 도달). 허용 호스트명의 raw connect도 동일한 성질이며, 이 경로를 쓰는 표준 클라이언트는 없고 DEC-043이 localhost 통과를 확정했다. 엄격히 막으려면 check_address에서 localhost를 루프백 IP로 고정 해석하는 별도 설계가 필요하다(질문 Q1).
2. 기존 정규화 특성: `_normalize_host`가 `strip()`과 `rstrip(".")`(다중 점)를 하므로 `" localhost "`, `"localhost.."`도 localhost로 판정된다. C 레벨에서는 해석 실패(gaierror)로 끝나 외부로 나가지 않는다. 정규화 함수 변경은 범위 밖이라 유지(Q2: `localhost..`를 비허용으로 볼지).
3. 로그 인젝션: `_block()`이 host를 `%s`로 그대로 로깅해 개행 포함 호스트가 로그에 실제 개행으로 출력된다(실측 True). 기존 동작이며 본 수정과 무관, 변경하지 않음(Q3: `%r` 사용 등 별도 소작업 여부).

### 11-4. 게이트
- 게이트 1: lint/type-check/formatter 설정 없음(재확인: pyproject.toml에 ruff/flake8/black/mypy 항목 없음, ruff.toml/.flake8/setup.cfg 없음). 대체로 `py_compile` 성공.
- 게이트 2: [x] 설계 v5.1 및 DEC-045 일치 [x] 판정 불가 주소 fail-closed 유지, 예외 삼킴 없음 [x] 경계 입력 검증 유지 [x] 시크릿 없음 [x] 신규 의존성 없음(검증 venv에만 requests/boto3 설치, PyPI 실재 확인, requirements.txt 무변경) [x] 범위 외 변경 없음(net_guard.py 1줄 + 본 note + verify-log)

### 11-5. 6단계 재테스트 인수 조건 (DEF-002)
(a) `install(enforce=True)` 후 raw `connect`/`connect_ex(("localhost", port))`가 차단되지 않고 원본 connect에 도달 (b) `localhost.evil.com` 등 접미사/유사 문자열은 차단 (c) 비허용 호스트명/IPv4/IPv6/mapped 리터럴 차단 회귀 없음 (d) 11-3의 세 항목은 알려진 한계로 인지하고 결함으로 재판정하지 않음(사용자 결정 전).

### 11-6. 공유 문서 갱신 요청
| 대상 | REQ-ID / DEC | 컬럼 | 값 |
|---|---|---|---|
| traceability.md | REQ-011 | 구현 상태 | `재작업 완료(unit-9 v2.1, DEF-002 해소: check_address localhost 정확 일치 통과) - 06단계 재검증 대기` |
| traceability.md | REQ-011 | 비고 | raw connect 호스트명 직접 전달 시 이름만으로 통과하는 잔여 한계(11-3-1) 추가 |
| decisions.md | DEC-045 | 상태/결과 | 구현 완료(net_guard.py check_address 1줄, 11절) |

### 11-7. 임시 아티팩트 및 git status (규칙 K)
`.harness-tmp/venv_05_unit9b/` 삭제 완료(테스트 스크립트는 세션 scratchpad에만 존재). `.harness-tmp/run_local.log`, `venv_run_local`은 오케스트레이터 소유로 무접촉. `git status` 원문:
```
On branch PROD_SCH
Changes not staged for commit:
	modified:   docs/harness/03-system-design.md          (오케스트레이터/설계 갱신)
	modified:   docs/harness/decisions.md                 (오케스트레이터)
	modified:   docs/harness/traceability.md              (오케스트레이터)
	modified:   docs/harness/units/unit-23-note.md        (unit-23 소유)
	modified:   docs/harness/units/unit-9-note.md         (본 단위: 11절 추가)
	modified:   docs/harness/units/unit-9-test.md         (06 unit-9)
	modified:   docs/harness/verify-log_03-system-design.md (03단계)
	modified:   docs/harness/verify-log_unit-9-test.md    (06 unit-9)
	modified:   webapp/config/wsgi.py                     (unit-9 v2 이전 회차 변경, 미커밋)
	modified:   webapp/converter/ratelimit.py             (unit-23 소유)
	modified:   webapp/core/net_guard.py                  (본 단위: v2 + 이번 1줄)
Untracked files:
	docs/harness/units/unit-23-test.md                    (unit-23 06)
	docs/harness/verify-log_unit-23-note.md               (unit-23)
	docs/harness/verify-log_unit-23-test.md               (unit-23)
	docs/harness/verify-log_unit-9-note.md                (본 단위)
```

---

## 12. 재작업 이력 3 (규칙 F, DEC-045 연장: Q2 정규화, Q3 로그 인젝션) — 2026-09-29

속도 트랙: L3 유지. 단독 실행. 사용자 승인: 11-3의 Q2, Q3 둘 다 수정. Q1은 09단계 이관(변경 없음).

### 12-1. 변경 내역 (`webapp/core/net_guard.py`만)
1. **Q2**: `_is_localhost(host)` 신규(대소문자 + **단일** 후행 점만 정규화, `strip()` 없음, 다중 점 불가, bytes는 ascii 디코드). `check_host_for_lookup`, `check_address` 두 곳의 localhost 판정을 이 함수로 교체. **`_normalize_host`는 변경하지 않음**(허용 호스트 비교와 `allowed_hosts` 구축에 쓰이므로 회귀 위험 회피; localhost 분기에서만 엄격 비교 = 지시의 "좁히기" 방식).
2. **Q3**: `_block()`이 로그와 예외 메시지 모두 host를 `%r`/`!r`로 출력(개행·널·제어문자 이스케이프). 비문자 host/비튜플 주소 경로의 `_block(repr(x))`는 이중 repr을 피하려 `_block(x)`로 정리. 메시지 구조는 `허용되지 않은 목적지: <repr>`로 동일하며 허용목록·환경변수 값은 포함하지 않는다.

### 12-2. 실측 (스텁 기반, 외부 DNS/TCP 없음, 검증용 venv `.harness-tmp/venv_05_unit9b` 후 삭제) — 268 단언, 2회 실행 모두 `ALL OK`, DNS leak 0
- 이전 107개 단언 회귀 전부 통과(localhost 통과 4변형 x raw connect/connect_ex, 접미사/유니코드/개행/널 차단, 비루프백 매핑 시 IP 검사 차단, 차단 매트릭스, 허용 호스트 통과).
- 신규: `" localhost "`, `"localhost.."`, `"localhost "`, `" localhost"`, 탭/개행/CRLF 포함, `"localhost. "`, `"localhost..."`는 raw connect/connect_ex/getaddrinfo 모두 차단되고 DNS 미도달. `b"localhost"`(bytes), `localhost.`(단일 점)는 통과.
- 허용 호스트 무회귀: `ALLOWED-R2.example.com.`, `allowed-r2.example.com`, `Allowed-DB.EXAMPLE.`는 raw connect와 getaddrinfo 통과. `_normalize_host` 미변경이므로 허용 호스트의 `host..`(다중 점)와 앞뒤 공백 변형도 종전대로 통과(관찰, 12-3 참조).
- 로그: 개행/널이 든 호스트가 로그에 실제 개행 없이 `host='localhost\nINJECT'` 형태로 출력, 모든 로그 라인이 `net_guard:` 접두 한 줄. 예외 메시지 실측: `허용되지 않은 목적지: 'evil\nFORGED LOG LINE\x00'`(한 줄, 허용목록/환경변수 값 미노출).
- 게이트 1: lint 설정 없음(변동 없음), `py_compile` 성공. 게이트 2: 설계/DEC-045/승인 범위 일치, 예외 삼킴 없음(fail-closed 유지), 시크릿 없음, 신규 의존성 없음(검증 venv에만 requests/boto3), 범위 외 변경 없음.

### 12-3. 관찰(변경 안 함, 질문)
Q4: 허용 호스트(R2/DB)의 다중 후행 점 및 앞뒤 공백 변형(`host..`, ` host `)은 `_normalize_host` 유지로 여전히 통과한다. 지시가 "허용 호스트 동작 무회귀"를 요구해 유지했다. C 레벨 해석 실패로 외부 도달은 불가하고 IP 리터럴 경로는 영향 없다. 함께 엄격화할지는 사용자 결정 필요(낮은 우선순위).

### 12-4. 6단계 인수 조건 (추가)
(a) localhost 변형(공백/다중 점/탭/개행) 차단, 정확 일치(대소문자, 단일 후행 점, bytes)만 통과 (b) 차단 로그/예외 메시지에 실제 개행·널 없음, repr 형태 (c) 허용 호스트 대소문자/단일 점 통과 회귀 없음 (d) 11-5 조건 유지. Q1은 알려진 한계로 유지(09단계 이관).

### 12-5. 공유 문서 갱신 요청
| 대상 | REQ-ID / DEC | 컬럼 | 값 |
|---|---|---|---|
| traceability.md | REQ-011 | 구현 상태 | `재작업 완료(unit-9 v2.2: localhost 정확 일치, 차단 로그/예외 repr 이스케이프) - 06 재검증 대기` |
| decisions.md | DEC-045 연장 | 결과 | Q2(localhost 엄격 비교, `_normalize_host` 미변경), Q3(`%r`) 구현. Q1 09단계 이관. Q4(허용 호스트 다중 점/공백)는 미결 |

### 12-6. 임시 아티팩트 및 git status (규칙 K)
`.harness-tmp/venv_05_unit9b/` 삭제(자기 것만). 남은 `.harness-tmp/run_local.log`, `venv_run_local`은 오케스트레이터 소유. `git status --short` 원문은 11-7과 동일 구성(변경 파일: 03-system-design.md, decisions.md, traceability.md, unit-23-note.md[unit-23], unit-9-note.md[본 단위], unit-9-test.md[06], verify-log_03-system-design.md, verify-log_unit-9-test.md, wsgi.py[unit-9 이전 회차], converter/ratelimit.py[unit-23], net_guard.py[본 단위]; 미추적: unit-23-test.md, verify-log_unit-23-note.md, verify-log_unit-23-test.md, verify-log_unit-9-note.md).
