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
