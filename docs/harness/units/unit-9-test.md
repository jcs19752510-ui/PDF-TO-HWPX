# 테스트 결과서 (Test Result Report) — unit-9 (v1 FAIL 원문 + 11절 v2 재검증 + 12절 v2.2 재검증 3회차)

> **현재 유효 판정은 12절(재검증 3회차, 2026-09-29): PASS** (DEF-001·DEF-002 모두 Fixed, 신규 결함 0건, 잔존 리스크는 12-8절). 1~10절은 v1(FAIL, DEF-001) 원문, 11절은 재검증 2회차(CONDITIONAL PASS, DEF-002 Low Open) 보존본이며, 12절이 자기완결적으로 전체를 재검증한다.

## 1. 개요
- 테스트 대상: `webapp/core/net_guard.py`(신규), `webapp/config/wsgi.py`(1줄 호출 추가) — unit-9, REQ-011 부분(아웃바운드 화이트리스트)
- 테스트 유형: 단위
- 적용 Tier: High (DEC-021, Feature B)
- 적용 속도 트랙: L3 (표기 없음 → 05-note §0에서 L3로 확정)
- 병렬 실행 정보: 병렬 웨이브에서 실행(동시에 unit-22가 06 진행 중, 오케스트레이터 프롬프트 명시). 파일범위(`core/net_guard.py`, `config/wsgi.py`)는 unit-22와 전혀 겹치지 않음(`git status`로 재확인, 7절 참고)
- 테스트 목적: unit-9-note.md §8 인수조건(AC-1~AC-7) 검증 + 오케스트레이터가 이번 06에 반드시 확인하라고 지시한 4개 항목(허용목록 동적 파싱, 차단 로그, 다중 호출 경로 일관성, dev/production 판정 경계) 검증
- 관련 산출물: `docs/harness/units/unit-9-note.md`, `03-system-design.md §6-3`, `docs/harness/decisions.md DEC-033/DEC-040`, `docs/harness/traceability.md REQ-011`
- 테스트 수행자(에이전트): 06(단위테스터)
- 테스트 일시: 2026-09-29

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - `install(enforce=True/False)`의 차단/허용/dev비활성화 동작
  - 허용목록이 하드코딩 없이 환경변수에서 동적으로 구성되는지 소스 대조
  - 차단 시 WARNING 로그 기록 여부
  - `socket.create_connection`을 경유하는 표준 라이브러리 경로(`urllib.request`, `http.client`) 및 서드파티 라이브러리 경로(`boto3`/`botocore`, `requests`)에서 차단 동작의 일관성
  - `config/wsgi.py`를 통한 dev/production 양쪽 end-to-end 재확인(05가 이미 확인한 항목의 재확인 — 새 발견 목적 아님)
  - `DJANGO_SETTINGS_MODULE` 접미사 판정 로직의 경계 케이스
  - 예외 입력: 환경변수 미설정(허용목록 공집합), URL 형식이 깨진 경우
- 제외 범위 (Out-of-Scope) 및 사유:
  - `psycopg`(libpq) 우회 자체의 재검증 — 이미 traceability.md REQ-011에 문서화된 알려진 한계이며 05-note와 호출 프롬프트가 "재발견 불필요"로 명시. 다만 이번 06이 새로 발견한 urllib3 계열 우회(6절 DEF-001)와는 성격이 다른 별개 항목임을 확인차 재확인(코드 성격상 C 확장 syscall이라 Python 레벨 몽키패치로 근본 해결 불가 — 결함 아님, 그대로 유지)
  - `EMAIL_HOST`(SMTP) 허용목록 누락 위험(DEC-040) — 이미 오케스트레이터가 09/10단계로 이관 확정한 리스크. 이번 06은 소스 대조로 "정말 허용목록에 없다"는 사실만 재확인(4절 TC-017)하고 조치는 하지 않음(범위 밖)
  - Render 플랫폼 헬스체크 관련 아웃바운드 — 이 모듈은 앱이 만드는 아웃바운드만 방어 대상이며, note §3-1이 이미 "실측 필요, 이번 unit 책임 아님"으로 기록. 06도 동일하게 범위 밖으로 유지
  - 실제 Neon/R2 실계정을 이용한 연결 성공 여부 — 이 모듈의 책임은 "허용목록 여부 판정"이지 실제 네트워크 도달성이 아니므로 가짜 호스트에 대한 `gaierror`/연결실패로 "차단되지 않음(가드 통과)"만 확인하면 충분(05와 동일한 접근)

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.13(레포 기본 인터프리터), 격리 venv `.harness-tmp/venv_06_unit9/`(pip install -r `webapp/requirements.txt`)
- 테스트 데이터: 가짜 `DATABASE_URL=postgres://u:p@allowed-db.example:5432/dbname`, 가짜 `R2_ENDPOINT_URL=https://allowed-r2.example.com`(둘 다 DNS에 존재하지 않는 예시 도메인 — 05가 이미 사용한 값과 동일 패턴 재사용), production e2e 확인용 가짜 `SECRET_KEY`/`R2_ACCESS_KEY_ID` 등
- 전제 조건: 05단계 게이트 통과 확인(아래 참고) — `unit-9-note.md` §5(정적분석: `py_compile` 성공, `manage.py check` 무이슈), §6(자체 코드리뷰 체크리스트 6개 항목 전부 [x])을 note에서 직접 확인함. 별도 재실행으로도 `manage.py check`(dev)가 이번 06 환경에서 "System check identified no issues (0 silenced)."로 재확인됨(아래 4절 실행 로그와 동일 환경)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 차단 동작(AC-1) | `enforce=True`, `DATABASE_URL`/`R2_ENDPOINT_URL`에 허용 호스트 설정 | 허용목록에 없는 `example.com:80`에 `socket.create_connection` 호출 | `NetworkAccessBlockedError` 발생 | 발생함 | PASS | AC-1 |
| TC-002 | 허용 동작 — DATABASE_URL 호스트(AC-2) | 위와 동일 | `DATABASE_URL`에서 파싱된 호스트(`allowed-db.example:5432`)로 접속 시도 | 차단 안 됨(`NetworkAccessBlockedError` 아닌 다른 예외 또는 성공) | `socket.gaierror`(가짜 도메인이라 DNS 실패) — 가드를 통과해 원본 함수까지 도달 | PASS | AC-2 |
| TC-002b | 허용 동작 — R2_ENDPOINT_URL 호스트(AC-2) | 위와 동일 | `allowed-r2.example.com:443`으로 접속 시도 | 차단 안 됨 | `gaierror`로 가드 통과 확인 | PASS | AC-2 |
| TC-003 | 경계값 — 대소문자 무시 | 위와 동일 | 허용 호스트를 대문자(`ALLOWED-DB.EXAMPLE`)로 접속 시도 | 대소문자 무시하고 허용(차단 안 됨) | `gaierror`로 가드 통과 확인(소스 `_extract_host`가 `.lower()` 적용, `guarded_create_connection`도 `host.lower()`로 비교함을 재확인) | PASS | 오케스트레이터 지시 항목 1(동적 파싱) 관련 부가 확인 |
| TC-004 | 로그 기록(AC-4) | 위와 동일 | `core.net_guard` 로거에 핸들러를 붙이고 차단 시도 실행 | WARNING 레벨 로그가 남고 차단된 호스트명이 메시지에 포함됨 | WARNING 1건 캡처, 메시지에 `host=blocked-host.example` 포함 확인 | PASS | AC-4, 오케스트레이터 지시 항목 2 |
| TC-005 | dev 비활성화(AC-3) | `enforce=False`로 재설치 | 임의 호스트(`blocked-host.example`)로 접속 시도 | 차단 안 됨 | `gaierror`(가드 미적용, 원본 소켓 예외로 직행) — `NetworkAccessBlockedError` 아님 확인 | PASS | AC-3 |
| TC-006 | 예외 입력 — 허용목록 공집합(경계값) | `DATABASE_URL`/`R2_ENDPOINT_URL` 둘 다 미설정, `enforce=True` | `install()` 호출 후 임의 호스트 접속 시도 | 환경변수 파싱실패 WARNING 2건(각 env별 1건) + 모든 접속이 차단됨(허용목록이 비어있으므로) | 파싱실패 경고 2건 확인, 접속 시도 시 `NetworkAccessBlockedError` 발생 | PASS | 빈 입력에 대한 방어적 동작 확인(호출 프롬프트 "명백히 위험한 케이스는 범위 밖이어도 테스트" 원칙 적용) |
| TC-007 | 예외 입력 — DATABASE_URL 형식 파손 | `DATABASE_URL="not-a-valid-url-at-all"`(호스트 파싱 불가), `R2_ENDPOINT_URL`은 정상 | `install(enforce=True)` 호출 | `install()`이 예외로 죽지 않고 DATABASE_URL만 파싱실패 경고(1건), R2는 정상 반영(경고 없음) | DB파싱경고 1건, R2파싱경고 0건, `install()` 정상 완료 | PASS | 예외 입력에도 기동 자체가 깨지지 않음을 확인 |
| TC-008 | 멱등성 | `enforce=True`로 이미 설치된 상태 | `install(enforce=True)` 재호출 | `socket.create_connection`이 재패치되지 않음(참조 동일성 유지) | 재호출 전후 `socket.create_connection` 참조 동일 | PASS | `_installed` 플래그 방어 확인 |
| TC-009 | 다중 호출 경로 1 — `urllib.request`(AC 항목3) | `enforce=True`, 허용목록 설정 | `urllib.request.urlopen("http://example.com")` 호출 | `NetworkAccessBlockedError`(또는 그 원인으로 감싸진 예외) 발생 | `NetworkAccessBlockedError` 직접 발생(내부적으로 `http.client`→`socket.create_connection` 경유 확인) | PASS | 오케스트레이터 지시 항목 3 |
| TC-010 | 다중 호출 경로 2 — `http.client`(AC 항목3) | 위와 동일 | `http.client.HTTPConnection("example.com", 80).connect()` 호출 | `NetworkAccessBlockedError` 발생 | 발생함 | PASS | 오케스트레이터 지시 항목 3 |
| TC-011 | 다중 호출 경로 3 — `requests` | 위와 동일 | `requests` 설치 여부 확인 후 설치돼 있으면 `requests.get()` 호출 | (설치 시) 차단, (미설치 시) 스킵하고 사유 기록 | `requirements.txt`에 `requests`가 없어 미설치 — 스킵, 사유 기록. **단 TC-012(boto3)가 `requests`와 동일한 `urllib3` 기반이므로 사실상 이 경로의 대리검증** | PASS(스킵, 근거 기록) | requests는 프로젝트 의존성이 아니라 강제 설치하지 않음(불필요한 의존성 추가 금지 원칙) |
| TC-012 | 다중 호출 경로 4 — `boto3`/`botocore`(AC 항목3, 실제 R2 스토리지 백엔드가 쓰는 라이브러리) | `enforce=True`, 허용목록 설정. 허용되지 않은 IP 리터럴 엔드포인트(`https://93.184.216.34`, DNS 조회 우회용)로 `boto3.client("s3", ...).list_buckets()` 호출 | `NetworkAccessBlockedError`(직접 또는 원인 체인)가 발생해야 함 | **`botocore.exceptions.EndpointConnectionError`만 발생, 원인 체인(`__cause__`/`__context__`)에 `NetworkAccessBlockedError`가 전혀 없음 — 가드가 전혀 개입하지 않고 실제 TCP 연결 시도까지 진행됨** | **FAIL** | **DEF-001(6절) — urllib3 기반 라이브러리(boto3/botocore, 그리고 동일 메커니즘의 requests)가 `socket.create_connection`을 호출하지 않고 `socket.socket()+.connect()`를 직접 사용해 이 가드를 전면 우회함** |
| TC-013 | dev/production 판정 경계 케이스(오케스트레이터 지시 항목 4) | 없음(순수 로직 분석) | `wsgi.py`의 판정식 `DJANGO_SETTINGS_MODULE.endswith(".production")`을 다양한 문자열에 대입해 실측 | 실제 배포 설정(`config.settings.production`/`config.settings.dev`)에 대해서만 올바른 판정이면 충분 | `config.settings.production`→True(정상), `config.settings.dev`→False(정상). 그 외 가상 케이스(`config.settings.production_backup`→False, 대소문자 상이 시 False)는 **기능 결함은 아니나 "fail-open"(오탐 시 dev로 간주해 미강제) 설계라는 리스크로 8절에 기록** | PASS(현재 실사용 값 기준), 리스크는 8절 별도 기록 | 오케스트레이터 지시 항목 4 |
| TC-014 | AC-5 진입점 통합 재확인 — dev | `DJANGO_SETTINGS_MODULE=config.settings.dev` | `import config.wsgi` 실행 후 `core.net_guard._installed`/패치 여부 확인 | `_installed=True`, `socket.create_connection`은 원본 그대로(미패치) | 확인됨(`_installed=True`, `patched=False`) | PASS | AC-5, 05단계 확인 항목 재확인(신규 발견 목적 아님) |
| TC-015 | AC-5 진입점 통합 재확인 — production | `DJANGO_SETTINGS_MODULE=config.settings.production` + 필수 환경변수(SECRET_KEY/DATABASE_URL/R2_*/DJANGO_ALLOWED_HOSTS) 전부 채움 | `import config.wsgi` 실행 후 허용 안 된 호스트로 `socket.create_connection` 시도 | `NetworkAccessBlockedError` 발생 | 발생함(`_installed=True`, `patched=True`) | PASS | AC-5 재확인 |
| TC-016 | 소스 대조 — 하드코딩 금지(오케스트레이터 지시 항목 1) | 없음 | `core/net_guard.py` 전체를 `.example`/`.com`/실제 호스트명 패턴으로 grep | 허용목록을 구성하는 실행 코드에 하드코딩된 호스트 리터럴이 없어야 함(환경변수에서만 파싱) | grep 결과 0건(문서 주석에도 실제 도메인 리터럴 없음). `_build_allowed_hosts()`가 `os.environ.get(env_name)` + `urlsplit().hostname`으로만 구성함을 소스로 직접 확인 | PASS | 오케스트레이터 지시 항목 1 |
| TC-017 | 알려진 한계/리스크 소스 재확인 — SMTP(EMAIL_HOST) | 없음 | `production.py`(EMAIL_HOST 정의)와 `net_guard.py`(허용목록 대상 env 2개만 참조)를 대조 | `EMAIL_HOST`가 허용목록 구성 대상(`DATABASE_URL`, `R2_ENDPOINT_URL`)에 없음을 재확인(이미 DEC-040으로 기록된 리스크, 조치는 09/10단계 몫) | 재확인됨 — `_build_allowed_hosts()`가 참조하는 env는 `DATABASE_URL`, `R2_ENDPOINT_URL` 2개뿐, `EMAIL_HOST`는 어디서도 참조되지 않음 | PASS(리스크 재확인, 버그 아님) | AC-7. 8절에 재기록 |
| TC-018 | 알려진 한계 소스 재확인 — psycopg 우회 | 없음 | `net_guard.py` 몽키패치 대상이 `socket.create_connection`뿐임을 재확인, psycopg[binary]는 libpq C 확장이라 별개 경로임을 재확인 | 이미 문서화된 한계와 일치, 재발견 불필요 | 소스/모듈 docstring과 일치 확인. **TC-012에서 새로 발견한 urllib3 우회(DEF-001)는 psycopg 우회와 원인이 다른 별개 결함**(C 확장 syscall vs 순수 파이썬 라이브러리가 다른 소켓 생성 경로 사용)임을 재확인 | PASS(리스크 재확인, 버그 아님) | AC-6 |

> 정상 경로(TC-001~005, 008~010, 014~015) + 경계값(TC-003, 006, 013) + 예외 입력(TC-006, 007) + 다중 호출 경로 비교(TC-009~012)를 모두 포함.

## 5. 커버리지
- 커버리지 지표: `core/net_guard.py`의 전체 실행 가능 라인(`import`문 제외) 기준, `install()`의 두 분기(enforce True/False)·`_build_allowed_hosts()`의 두 분기(파싱 성공/실패)·`guarded_create_connection()`의 두 분기(허용/차단)·`_installed` 재설치 방어 분기까지 전부 최소 1회 이상 실행 경로에 포함됨(TC-001~TC-008, TC-016으로 100% 라인/브랜치 도달 확인). `config/wsgi.py`의 신규 1줄(`install_net_guard(...)`)은 TC-014/015로 dev/production 양쪽 분기 모두 실행됨.
- 커버되지 않은 부분과 사유: 없음(코드 자체의 라인/브랜치 커버리지는 100%). 다만 **런타임 커버리지가 100%라는 사실과 "가드가 모든 아웃바운드 경로를 실제로 방어한다"는 사실은 별개**임을 이번 06이 확인함 — TC-012가 보여주듯 `guarded_create_connection` 브랜치 자체는 100% 커버되어도, 애초에 그 함수가 호출되지 않는 호출 경로(urllib3 계열)가 존재해 기능적 커버리지(방어 목적 달성 여부)는 100%가 아니다(DEF-001, 6절 참고).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | `net_guard.install()`은 `socket.create_connection`만 몽키패치한다. 그러나 `urllib3`(및 이를 사용하는 `botocore`/`boto3`, 그리고 동일 메커니즘을 쓰는 `requests`)는 `socket.create_connection`을 호출하지 않고 `urllib3.util.connection.create_connection()` 내부에서 `socket.getaddrinfo()` + `socket.socket()` + `sock.connect()`를 직접 조합해 연결을 생성한다. 그 결과 `boto3`/`botocore`/`requests` 경유 아웃바운드 호출은 이 가드를 전혀 거치지 않고 완전히 우회한다. `net_guard.py` 모듈 docstring 자체가 "botocore가 내부적으로 http.client를 거쳐 socket을 쓰므로 R2 접근은 이 방어 범위 안에 있다"고 명시하는데, 이는 사실과 다르다(실측 결과 botocore는 http.client가 아니라 urllib3를 통해 소켓을 생성함). `boto3`는 이 코드베이스가 R2 스토리지 백엔드(`storages.backends.s3.S3Storage`)로 실제 사용 중인 라이브러리이며, REQ-011/DEC-033이 정의한 디펜스인뎁스의 핵심 위협 모델("실수로 추가된 제3자 API 호출")이 정확히 이런 라이브러리(requests/boto3류 HTTP 클라이언트)를 통해 이뤄질 가능성이 가장 높다는 점에서, 이 우회는 이 모듈의 존재 목적 자체를 무력화한다. | 1) 격리 venv에서 DATABASE_URL/R2_ENDPOINT_URL을 허용 호스트로 설정하고 core.net_guard.install(enforce=True) 호출. 2) boto3.client("s3", endpoint_url="https://93.184.216.34", ...).list_buckets() 호출(허용목록에 없는 IP 리터럴 엔드포인트, DNS 우회 목적). 3) 발생한 예외(botocore.exceptions.EndpointConnectionError)의 원인 체인(__cause__/__context__)을 끝까지 순회해도 NetworkAccessBlockedError가 전혀 나타나지 않음을 확인(TC-012). 4) 대조 실험: socket.socket.connect(인스턴스 메서드) 자체를 패치하면 동일한 boto3 호출이 정상적으로 가로채짐을 확인 — 즉 socket.create_connection이 아니라 socket.socket.connect(또는 최소한 urllib3.util.connection.create_connection)를 패치 대상으로 삼아야 이 우회가 해소됨을 재현 가능한 형태로 확인함. | Critical | Open | 06단계에서 직접 수정하지 않음(단순 오탈자 수준이 아니라 몽키패치 대상 함수/설계 자체를 바꿔야 하는 로직 변경) — 05단계로 반려 |

- 결함 1건(DEF-001, Critical) 발견. 그 외 명시적 결함은 없으나, TC-013(dev/production 판정 fail-open 설계)과 TC-017(EMAIL_HOST 미포함)은 결함이 아니라 8절 리스크로 별도 기록함(각각 실사용 값 기준으로는 AC를 위반하지 않음).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/venv_06_unit9/`(unit-9 전용 격리 venv, `webapp/requirements.txt` 설치)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예
- 정리(삭제) 완료 여부: 완료 (`rm -rf .harness-tmp/venv_06_unit9`)
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   webapp/.env.example
	modified:   webapp/config/settings/base.py
	modified:   webapp/config/urls.py
	modified:   webapp/config/wsgi.py          <- 이 unit(unit-9) 소유 변경
	modified:   webapp/requirements.txt

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/harness/units/unit-20-note.md          (unit-20 소유, 병렬)
	docs/harness/units/unit-20-test.md          (unit-20 소유, 병렬)
	docs/harness/units/unit-21-note.md          (unit-21 소유, 병렬)
	docs/harness/units/unit-21-test.md          (unit-21 소유, 병렬)
	docs/harness/units/unit-22-note.md          (unit-22 소유, 병렬 - 동시 진행 중)
	docs/harness/units/unit-24-note.md          (unit-24 소유, 병렬)
	docs/harness/units/unit-24-test.md          (unit-24 소유, 병렬)
	docs/harness/units/unit-25-note.md          (unit-25 소유, 병렬)
	docs/harness/units/unit-25-test.md          (unit-25 소유, 병렬)
	docs/harness/units/unit-9-note.md           <- 이 unit(unit-9) 소유(05가 이미 작성해둔 입력, 이번 06이 새로 만든 것 아님)
	docs/harness/verify-log_unit-20-test.md     (unit-20 소유, 병렬)
	docs/harness/verify-log_unit-21-test.md     (unit-21 소유, 병렬)
	docs/harness/verify-log_unit-24-test.md     (unit-24 소유, 병렬)
	docs/harness/verify-log_unit-25-test.md     (unit-25 소유, 병렬)
	webapp/converter/cleanup.py                 (unit-22 소유, 병렬)
	webapp/converter/executor.py                (unit-21 소유, 병렬)
	webapp/converter/limits.py                  (unit-24 소유, 병렬)
	webapp/converter/ratelimit.py               (unit-23 소유, 병렬)
	webapp/converter/static/                    (unit-20 소유, 병렬)
	webapp/converter/templates/                 (unit-20 소유, 병렬)
	webapp/converter/urls.py                    (unit-20/22 소유, 병렬)
	webapp/converter/views.py                   (unit-20/22 소유, 병렬)
	webapp/core/middleware.py                   (unit-24 소유, 병렬)
	webapp/core/net_guard.py                    <- 이 unit(unit-9) 소유(신규 파일)
	webapp/legal/                                (unit-25 소유, 병렬)
```
(`.harness-tmp/`는 gitignore 대상이라 위 목록에 나타나지 않음 — 별도로 `ls .harness-tmp/`를 실행해 unit-22가 만든 `unit22/`, `venv_06_unit22/`만 남아있고 `venv_06_unit9/`는 존재하지 않음을 확인함)
- 병렬 실행이었다면: 위 `git status`에 보이는 항목 중 이 unit(unit-9) 소유는 `webapp/config/wsgi.py`(수정)와 `webapp/core/net_guard.py`(신규)뿐이며, `docs/harness/units/unit-9-note.md`는 05단계가 이미 남겨둔 입력 산출물이다. 나머지는 전부 동시 진행 중인 다른 unit(20/21/22/23/24/25) 소유로 확인됨. `.harness-tmp/` 하위의 unit-22 아티팩트는 아직 진행 중일 수 있어 건드리지 않음(규칙: 자기가 만든 것만 정리) — 이 unit(unit-9)이 만든 임시 아티팩트·미추적 잔여물은 없음(venv_06_unit9 삭제 완료로 확인). 웨이브 종료 후 오케스트레이터의 전체 트리 점검(`harness-janitor.sh --check`) 별도 필요.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 충족: git status가 깨끗함(이 unit 소유 변경만 존재)을 확인함. 단, 8절/9절 참고 — DEF-001로 인해 이 결과서 자체는 FAIL 판정이며, 7절(Teardown)의 정리 완료 자체는 PASS/FAIL 판정과 별개로 규칙 K를 충족함(정리는 완료했으나 최종 판정은 결함으로 인해 FAIL).

## 8. 리스크 및 잔존 이슈
- DEF-001(6절)이 해소되기 전까지, 이 모듈은 `psycopg`(DB) 외에 `boto3`/`requests` 등 urllib3 기반 HTTP 클라이언트 경유 아웃바운드 호출 전체에 대해 실질적 방어력이 없다. 05단계 재작업 시 다음 대안 중 하나를 검토 권장(06이 결정하지 않음, 참고용 실측 근거만 제공):
  1. `socket.create_connection` 대신(또는 추가로) `socket.socket.connect`(인스턴스 메서드)를 패치 — 이번 06이 대조 실험으로 boto3 호출을 정상적으로 가로챈다는 것을 확인함(6절 DEF-001 재현절차 4번). `http.client`/`urllib.request`/`socket.create_connection` 모두 결국 `socket.socket().connect()`를 호출하므로 이 지점 패치가 더 포괄적임.
  2. 또는 `urllib3.util.connection.create_connection`을 별도로 패치(다만 `urllib3`가 신규 의존성으로 추가되는 것은 아니고 `django-storages[s3]`/`boto3`의 전이 의존성이라는 점에 유의 — 직접 의존성 선언 없이 내부 구현에 의존하는 방식이라 버전 변경에 취약할 수 있음).
  둘 다 psycopg(libpq C 확장)는 여전히 우회함(구조적으로 해결 불가, 결함 아님 — 유지).
- DEC-040(SMTP/EMAIL_HOST 미허용, TC-017로 재확인됨): 09단계 보안검증/10~12단계 실배포 검증 시 반드시 확인 필요 — 이번 06의 결함 목록에는 포함하지 않음(오케스트레이터가 이미 리스크로 이관 확정).
- TC-013 fail-open 리스크: `DJANGO_SETTINGS_MODULE`이 예상 밖 문자열(예: 오탈자, 대소문자 상이)일 경우 `enforce=False`(dev와 동일)로 조용히 판정되어, 실제로는 production인데 화이트리스트가 적용되지 않을 수 있다. 현재 실사용 값(`config.settings.production`/`config.settings.dev`)에서는 발생하지 않으므로 결함으로 분류하지 않았으나, "안전 기본값은 실패 시 더 개방적인 쪽(fail-open)이 아니라 더 보수적인 쪽(fail-closed)이어야 한다"는 보안 설계 원칙 관점에서 09단계가 참고할 잔존 리스크로 기록한다.
- DEF-001 발견 경로에 대한 소급 확인: 05-note §7의 로컬 동작 확인은 `socket.create_connection` 직접 호출과 `config.wsgi` e2e만 검증했고, boto3/urllib3 같은 실제 소비 라이브러리 경로는 검증하지 않았다(05단계의 누락은 아님 — 05-note에 boto3 검증을 하겠다는 약속 자체가 없었고, 05가 검증한 범위 내에서는 결함이 없었음이 사실). 이는 "05가 검증을 안 해서 생긴 결함"이 아니라 "설계/구현 자체가 몽키패치 대상을 잘못 선택한" 결함이므로 06→05 반려 사유가 명확하다.

## 9. 결론 및 판정
- [ ] PASS
- [ ] CONDITIONAL PASS
- [x] FAIL — 사유: DEF-001(Critical) — `net_guard.install()`의 몽키패치 대상(`socket.create_connection`)이 `boto3`/`botocore`(및 동일 메커니즘의 `requests`) 등 urllib3 기반 HTTP 클라이언트를 가로채지 못해, 이 모듈의 핵심 방어 목적(제3자 API 호출 화이트리스트)이 정확히 이 유형의 라이브러리에 대해 무력화됨. 05단계로 반려하여 몽키패치 대상을 `socket.socket.connect`(또는 최소한 `urllib3.util.connection.create_connection` 추가 패치)로 재설계할 것을 요청. 재작업 후 06단계 전체(4절 전 TC)를 재실행해야 함(TC-001~011/014~018은 이번 실행에서 PASS했으므로 재작업이 이 부분들의 동작을 깨뜨리지 않는지 회귀 확인 필요).

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: AC-1~AC-7 전 항목이 4절 표에 1:1로 대응됨을 확인(커버리지 100%). 다만 오케스트레이터가 명시한 "requests가 내부적으로 쓰는 소켓" 확인 항목을 검증하는 과정에서 boto3 대리검증(TC-012)이 FAIL로 나타남 — 예상 결과(차단됨)와 실제 결과(우회됨)가 명백히 다름을 원인 체인까지 추적해 확인. 결함 1건 발견.
- 2차 검증 결과 요약: "이 결과서를 그대로 07(통합테스트)에 넘겨도 되는가"를 의심하며 재검토 — REQ-011/DEC-033의 핵심 위협 모델(제3자 SaaS 클라이언트 호출)이 대부분 requests/httpx/boto3류 라이브러리로 구현된다는 점에서, TC-012 FAIL은 "주변부 결함"이 아니라 "이 모듈의 존재 이유 자체를 무력화하는 결함"이라고 재확인 → 07로 넘길 수 없음(FAIL 유지, 05로 반려). 추가로 TC-013(fail-open 설계)과 TC-017(EMAIL_HOST)은 결함이 아니라 리스크로 재분류하는 것이 맞는지 재검토(둘 다 현재 실사용 값 기준으로는 AC를 위반하지 않고, 이미 알려진/이관된 리스크이므로 결함 목록에 추가하지 않는 것이 타당하다고 재확인). 2차 검증에서 결함 목록에 변경 없음(DEF-001 그대로 유지).
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-9-test.md`


---

# 11. 재검증(2회차) — v2 재작업(DEF-001 해소 여부 + 규칙 F 전체 회귀)

> 위 1~10절은 **v1 결과서(FAIL, DEF-001)의 원문 보존본**이다. 11절은 05단계 재작업(`unit-9-note.md` §10, 패치 지점 = `socket.socket.connect`/`connect_ex` + `socket.getaddrinfo`, wsgi fail-closed 판정)을 06단계가 처음부터 다시 검증한 결과이며 **자기완결적**이다. v1 표의 TC 전체(TC-001~018)를 v2 기준으로 재실측했다. 11절의 판정이 이 unit의 **현재 유효 판정**이다.

## 11-1. 개요
- 테스트 대상: `webapp/core/net_guard.py`(v2), `webapp/config/wsgi.py`(v2) — unit-9, REQ-011 부분
- 테스트 유형: 단위(+ 진입점 e2e 재확인)
- 적용 Tier: High (DEC-021) / 속도 트랙 L3 / 재검증 사유: 규칙 F(DEF-001 재작업 후 06 전체 재실행)
- 병렬 정보: 동시에 unit-23 06이 진행 중. 이 unit 파일범위(`core/net_guard.py`, `config/wsgi.py`)와 무관한 파일은 건드리지 않음
- 테스트 목적: (1) DEF-001 재현 절차가 이제 차단되는가 (2) TC-001~018 회귀 (3) 경로 10종 x 대상 14종 매트릭스 (4) 보안담당자 관점 우회 시도 (5) wsgi 활성화 판정 fail-closed 실측
- 테스트 수행자: 06(단위테스터), 일시: 2026-09-29

## 11-2. 테스트 범위 및 제외 범위
- In-Scope: AC-1~AC-7 전부, v2 신규 동작(getaddrinfo 게이트, connect 게이트, 허용 IP 집합, 루프백/AF_UNIX 통과, IPv6/IPv4-mapped/zone id, fail-closed 활성화 판정), 우회 시도, 스레드 경쟁, 로그/예외 민감정보, dev runserver 회귀
- Out-of-Scope(결함이 아니라 8절 리스크로 기록): psycopg libpq 우회, UDP `sendto/sendmsg`, C 확장/`_socket` 직접 소켓, 허용 호스트와 IP 공유 호스트, DEC-040(EMAIL_HOST 정책 결정 대기)
- **외부망 비접속 원칙**: net_guard가 캡처하는 "원본" `getaddrinfo`/`connect`/`connect_ex`를 스텁으로 교체한 뒤 net_guard를 import했다. 허용 호스트는 문서화용 대역(TEST-NET-3 203.0.113.x, 198.51.100.x, 2001:db8::/32)으로만 해석된다. 스텁 getaddrinfo가 "허용 목록 밖 이름"을 받으면 `LEAK`에 기록하고 `gaierror`를 던진다(실제 질의 없음). 전 실행에서 `LEAK`은 비어 있었다(=차단 대상에 대해 원본 해석기가 호출된 적 없음). `netstat -an`에 테스트 대역/93.184.216.34 연결 없음 확인. psycopg는 `libpq`가 실제로 연결을 시작하지 않도록 차단 경로와 `conninfo_attempts`(해석만 수행)만 호출했다. UDP는 `connect()`만 호출(스텁이 응답), `sendto`는 호출하지 않았다. 스텁 버그로 실제 질의가 나간 사례: **없음**(05가 고지한 초기 스텁 버그와 무관하게 이번 스텁은 대소문자/후행 점을 정규화하고 공백은 정규화하지 않는 엄격 모드).

## 11-3. 테스트 환경
- Windows 10 Pro 10.0.19045, **Python 3.11.9**(이 PC 기본 인터프리터; v1 결과서의 "3.13" 표기와 다름 — 이번 실측 기준), 격리 venv `.harness-tmp/venv_06_unit9/`(`pip install -r webapp/requirements.txt` + **`requests` 2.34.2**, boto3 1.35.36, urllib3 2.8.0, psycopg 3.2.10, Django 5.2.17). 종료 후 삭제(11-7).
- 테스트 스크립트는 세션 스크래치패드(`.../scratchpad/ng/`: `ng_env.py`(스텁), `s1_matrix.py`, `s2_edges.py`, `s3_misc.py`, `s4_wsgi.py`, `s5_runserver.py`, `s6_extra.py`, `s7_log.py`, 뮤턴트 `mut/`)에만 있고 리포지토리에는 남기지 않았다(v1 관례 동일). 총 실행 케이스: 매트릭스 140 + 엣지 71 + 시나리오(idem 6, dev 3, empty 5, malformed 9) + wsgi 15 + e2e 5 + runserver 3 + log 3 + extra 5.
- 전제(5단계 게이트) 확인: `unit-9-note.md` §10-5 — lint/type 설정 없음(재확인), `py_compile` 성공, `manage.py check` 통과, 자체 리뷰 6항목 [x]. 이번 06이 독립 재실행: `py_compile net_guard.py wsgi.py` -> COMPILE_OK, `manage.py check` -> "System check identified no issues (0 silenced)". 확인됨.
- 한계 고지: Windows에는 `socket.AF_UNIX`가 없어 AF_UNIX는 가짜 소켓 객체(`family=1`)로 **시뮬레이션**했다(E06). Render(Linux) 실환경 미검증 -> 8절.

## 11-4. 테스트 케이스 및 결과

### A. v1 TC-001~018 회귀 매핑 (모두 v2로 실측 재실행)
| ID | 시나리오 | 예상 결과(v2 기준) | 실제 결과 | Pass/Fail | 근거 |
|----|----------|--------------------|-----------|-----------|------|
| TC-001 | 비허용 호스트 `create_connection` 차단(AC-1) | `NetworkAccessBlockedError`, 원본 connect/DNS 미도달 | 차단, connects=[], leak=[] | PASS | M[a\|socket.create_connection] |
| TC-002 | DATABASE_URL 호스트 허용(AC-2) | 차단 예외 아님, 원본 connect 도달 | `allowed-db.example` 전 경로 REACHED | PASS | M[e2\|*] 10경로 |
| TC-002b | R2 호스트 허용(AC-2) | 동일 | `ALLOWED-R2.example.com.` 전 경로 REACHED | PASS | M[e1\|*] 10경로 |
| TC-003 | 대소문자/후행 점 정규화 | 허용 | e1 대문자+후행 점, bytes 대문자+점(E02c), DB URL 대문자+후행 점 파싱(malformed:upper_db) 전부 허용. 접두/접미/@ 유사 호스트는 차단(E02k/l/m) | PASS | |
| TC-004 | 차단 로그(AC-4) | `core.net_guard` WARNING 1건, 호스트 포함, 허용/루프백은 무로그 | hostname 차단(urllib.request) 1 WARNING host 포함, IP 차단(raw connect) 1 WARNING, 허용+루프백 0건 | PASS | s7: TC-004a/b/c |
| TC-005 | dev 비활성(AC-3) | 아무것도 패치하지 않음 | 3개 함수 스텁과 동일 객체, 임의 호스트 조회/IP connect가 원본 도달, 이후 `install(True)`도 `_installed`로 무시 | PASS | s3 dev TC-005a/c/d + wsgi dev |
| TC-006 | 허용목록 공집합(경계) | 파싱 경고 2건, 루프백 외 전부 차단 | 경고 2건, 호스트명/IP 차단, 루프백 통과, localhost 조회 통과 | PASS | s3 empty TC-006a~e |
| TC-007 | DATABASE_URL 형식 파손 | 기동이 죽지 않고 해당 env만 경고 | `not-a-valid-url-at-all`: install OK, 경고 1건, R2만 허용. R2 스킴 없음: 경고 1건. IPv4/IPv6 리터럴 DB 호스트: 해당 IP 허용. userinfo에 `@` 포함: 정상 파싱. 빈 값/공백: 경고 2건+전면 차단. **`postgres://u:pw@[::1/db`: `install()`이 `ValueError: Invalid IPv6 URL`로 기동 실패**(fail-closed, 비밀번호 미노출) — 8절 리스크 R9 | PASS(리스크 기록) | s3 malformed 9종 |
| TC-008 | 멱등성 | `socket.getaddrinfo`/`socket.socket.connect`/`connect_ex` 참조 동일성 | 재호출·`install(False)` 후에도 3개 참조 동일. `create_connection`은 미패치(폐기된 전제). reload 후 `_original_*`가 스텁으로 unwrap되고 이중 래핑 없이 원본 connect 1회 호출, 차단 유지 | PASS | s3 idem TC-008a~f |
| TC-009 | urllib.request | 차단 | 차단(모든 비허용 대상) | PASS | M[*\|urllib.request] |
| TC-010 | http.client | 차단 | 차단 | PASS | M[*\|http.client] |
| TC-011 | requests (스킵 금지) | 설치·실행, 차단 | venv에 requests 2.34.2 설치, http/https 두 경로 실행, 비허용 대상 전부 차단·허용 대상 도달 | PASS | M[*\|requests(http/https)] |
| TC-012 | boto3 list_buckets (DEF-001 재현) | **이번엔 차단** | 비허용 호스트/IPv4/IPv6/mapped 전부 `HTTPClientError`의 원인 체인에 `NetworkAccessBlockedError`, connect 미도달. 허용 R2 호스트는 도달. 원 재현절차(`https://93.184.216.34`)는 production e2e에서도 차단(E2E-5) | PASS | M[*\|boto3.list_buckets], E2E-5 |
| TC-013 | dev/production 판정(fail-closed로 기대값 갱신) | 정확히 `config.settings.dev`/미설정만 비활성, 그 외 전부 활성 | 15개 값 실측(11-4-D) — 기대와 전부 일치 | PASS | s4 |
| TC-014 | 진입점 dev | `patched=False` | 미설정/`config.settings.dev` 모두 `installed=True patched=False`, 비허용 IP connect 도달 | PASS | s4 |
| TC-015 | 진입점 production | 자동 적용 | `patched=True`, 비허용 IP connect 차단, `/healthz` 200 | PASS | s4, E2E-1 |
| TC-016 | 하드코딩 금지 | 허용 호스트 리터럴 0건 | 도메인/URL 패턴 grep 0건, 허용목록은 `os.environ.get` + `urlsplit().hostname`으로만 구성 | PASS | grep |
| TC-017 | EMAIL_HOST 미허용(DEC-040) 재확인 | 리스크 재확인만 | net_guard가 참조하는 env는 `DATABASE_URL`/`R2_ENDPOINT_URL` 2개뿐. `smtplib.SMTP/SMTP_SSL`(비허용 SMTP 호스트)은 실제로 차단됨(E08a/b) | PASS(리스크 재확인, 결함 아님) | 8절 R10 |
| TC-018 | psycopg 한계 문구 유지 | 한계 유지 + 사실 확인 | `psycopg.pq.__impl__ == "binary"`(libpq C 확장, 우회 구조 그대로). **추가 실측**: psycopg 3.2.10은 호스트명 접속 시 파이썬에서 `socket.getaddrinfo`로 먼저 해석하므로 비허용 호스트명은 libpq 이전에 차단됨(E09b). 단 IP 리터럴 host는 해석을 건너뛰어 libpq가 무가드로 연결(E09d, 실행하지 않고 `conninfo_attempts` 반환값으로만 확인) | PASS(한계 유지, 사실 보정 8절 R1) | E09 |

### B. 경로 x 대상 매트릭스 (140케이스, 실측: B=차단, R=원본 connect 도달)
경로 10종: boto3.list_buckets / requests(http) / requests(https) / urllib3.PoolManager / urllib.request / http.client / socket.create_connection / raw connect / raw connect_ex / asyncio(SelectorEventLoop). 기대 = 표의 열 "기대", 예외는 표기.
| 대상 | 호스트 | 기대 | 결과(10경로) | Pass/Fail |
|------|--------|------|--------------|-----------|
| a | `blocked-host.example` (비허용 호스트명) | B | 10/10 B, DNS 미발생 | PASS |
| a2 | `other.example` (R2와 IP 공유하는 다른 호스트명) | B | 10/10 B | PASS |
| b | `93.184.216.34` (IPv4 리터럴) | B | 10/10 B | PASS |
| b2 | `203.0.113.21` (허용 IP 인접) | B | 10/10 B | PASS |
| c | `2606:2800:220:1:248:1893:25c8:1946` (IPv6 리터럴) | B | 10/10 B | PASS |
| d | `::ffff:93.184.216.34` (IPv4-mapped IPv6) | B | 10/10 B | PASS |
| e1 | `ALLOWED-R2.example.com.` (대소문자+후행 점) | R | 10/10 R | PASS |
| e2 | `allowed-db.example` | R | 10/10 R | PASS |
| f1 | `127.0.0.1` | R | 10/10 R | PASS |
| f2 | `::1` | R | 10/10 R | PASS |
| f3 | `localhost` | R | 8/10 R, **raw connect·raw connect_ex는 B** | **FAIL(2건) -> DEF-002** |
| g1 | `203.0.113.20` (R2가 풀린 IP, 사전 해석 후) | R | 10/10 R | PASS |
| g2 | `2001:db8::10` (DB가 풀린 IPv6) | R | 10/10 R | PASS |
| g3 | `::ffff:203.0.113.20` (허용 IP의 mapped 형) | R | 10/10 R | PASS |
- 집계: 140건 중 138 PASS / 2 FAIL(f3 x raw connect/connect_ex). 예외 체인은 `__cause__/__context__/args/reason/kwargs`를 모두 순회해 판정(boto3 `HTTPClientError.kwargs['error']`, requests `MaxRetryError.reason` 포함).
- AF_UNIX/루프백: 루프백은 위 f1~f3, AF_UNIX는 D-E06.

### C. 엣지/우회 시도 (71 + 시나리오, 전부 실측 PASS)
| ID | 시나리오 | 예상 | 실제 | P/F |
|----|----------|------|------|-----|
| E01a/b | 허용 R2 IP 리터럴을 **해석 전**/후에 connect | 해석 전 차단 / 해석 후 통과 | 그대로 | PASS |
| E02a-n | getaddrinfo 인자 형태: keyword host, bytes, None, `localhost`/`LocalHost.`, `foo.localhost`(차단), IP 리터럴(게이트 통과·집합 미기록), 접미/접두/`@` 유사 호스트, 앞 공백 허용 호스트 | 명세대로 | 전부 기대와 일치. IP 리터럴을 getaddrinfo에 넘겨도 허용 IP 집합이 오염되지 않음(E02i) | PASS |
| E03a/b | zone id: `fe80::1%eth0` 차단, `::1%lo` 통과 | 그대로 | 그대로 | PASS |
| E04a-n | 특이 IP 표기: `127.1`, `0x7f.1`, `2130706433`, `0.0.0.0`, 선행 0(`203.0.113.020`, `0177.0.0.1`) 차단, `127.255.255.254` 통과, `169.254.169.254`/10.x/192.168.x 차단, `::` 차단, `::ffff:127.0.0.1` 통과, 허용 IPv6 2-튜플 | 명세대로 | 전부 일치(비표준 표기는 IP로 파싱 불가 -> 호스트명으로 취급되어 차단=fail-closed) | PASS |
| E05a-i | 판정 불가 주소: AF_INET에 str 경로, int host, None, 빈 튜플, bytes/bytearray 호스트, NUL 삽입, 빈 문자열 host | 차단(fail-closed), bytes 허용 호스트는 통과 | 그대로 | PASS |
| E06a-d | **[시뮬레이션]** AF_UNIX str/abstract bytes 경로 통과, connect_ex 통과, 비-UNIX 패밀리 str 경로 차단 | 그대로 | 그대로 | PASS(시뮬레이션) |
| E07a/b | UDP `SOCK_DGRAM.connect` 비허용 IP 차단 / 허용 IP 통과 | 그대로 | 그대로(`sendto` 미호출) | PASS |
| E08a/b | `smtplib.SMTP`/`SMTP_SSL` 비허용 SMTP 호스트 | 차단(DEC-040 실측) | 차단 | PASS(리스크 확인) |
| E09a-d | psycopg 4건 (TC-018 참조) | | | PASS |
| E10 | `socket.gethostbyname("blocked-host.example")` | 미가드 -> 리졸버 도달(리스크) | 도달 확인 | PASS(리스크 R6 실증) |
| E11a-c | `_socket.socket.connect`가 미패치 객체, `socket.SocketType is _socket.socket`, net_guard 코드에 `sendto/sendmsg/gethostbyname` 없음(호출하지 않고 구조 증거만) | 우회 가능 구조 확인(리스크) | 확인 | PASS(리스크 R2/R3) |
| E12a/b | 공유 IP: `other.example`(같은 IP) 호스트명은 차단, **R2의 IP 리터럴로 접속 + 임의 Host 헤더는 통과** | 알려진 한계 실측 | 통과 확인 | PASS(리스크 R4) |
| E13a-d | DNS rebinding: 허용 호스트가 다른 IP로 재해석되면 신규 IP 허용, **기존 IP도 계속 허용(집합은 증가만)**, 무관 IP 차단, 링크로컬 메타데이터 IP로 풀리면 허용됨 | 설계상 동작 실측 | 확인 | PASS(리스크 R5) |
| E14a-c | 오염 시도: 비허용 이름의 조회는 원본 해석기 호출 전에 차단(허용 집합 오염 불가), 그 이름의 IP로 connect 차단, `allowed_ips/allowed_hosts`는 모듈 속성으로 노출되지 않음 | 차단 | 확인 | PASS |
| E15a-d | 예외 메시지: 시도한 호스트만 포함, 허용목록·env 값 없음. 로그: DATABASE_URL 비밀번호/사용자/경로 없음(비밀번호가 든 환경에서 전 로그 라인 검사). INFO 부팅 로그는 허용 **호스트명**만 나열. 호스트에 개행 포함 시 로그가 이스케이프 없이 기록(log injection, Low 리스크) | 민감정보 비노출 | a/b/c PASS, d는 리스크 R7 실증 | PASS |
| E16 | 스레드 경쟁: 12 리더가 비허용 IP를 계속 connect 시도, 1 라이터가 허용 호스트를 100회 재해석 | 비허용 IP 통과 0건, 해석된 IP 오차단 0건 | errors=0, resolved=100 | PASS |
| EXTRA | getaddrinfo에 int/list host -> 원본이면 `TypeError`인데 가드는 `AttributeError`(인자 오류는 여전히 예외, 차단 아님). 키릴 문자/켈빈 기호 유사 문자 호스트 차단. `AI_NUMERICHOST` 플래그와 비허용 이름도 차단 | 취약점 없음 | 확인(예외 타입만 상이 -> R9) | PASS |

### D. wsgi 활성화 판정 실측 (`import config.wsgi`, 케이스별 서브프로세스, 값은 `os.environ[...]`에 직접 대입해 빈 문자열 보존)
| `DJANGO_SETTINGS_MODULE` | 기대 | 실제(enforce/비허용 IP) | 이후 Django import |
|---|---|---|---|
| (미설정) | 비활성 | OFF / connect 도달 | 정상 |
| `config.settings.dev` | 비활성 | OFF / 도달 | 정상 |
| `config.settings.production`(가짜 필수 env) | 활성 | ON / 차단 | 정상 |
| `""`(빈 값) | 활성 | ON / 차단 | ImproperlyConfigured |
| `config.settings` | 활성 | ON / 차단 | 정상(패키지 존재) |
| `config.settings.Dev` / `Config.Settings.DEV` / `config.settings.dev `(후행 공백) / ` config.settings.dev`(선행 공백) / `config.settings.devv` / `config.settings.dev.py` / `config.settings.dev;x` | 활성 | 전부 ON / 차단 | ModuleNotFoundError |
| `production` / `config.settings.production_backup` / `CONFIG.SETTINGS.PRODUCTION` | 활성 | 전부 ON / 차단 | ModuleNotFoundError |
- 판정: 15/15 기대 일치 -> PASS. 오탈자/빈 값은 가드가 켜진 채 Django import 단계에서 기동 실패(부작용은 기동 불가로 안전 측).

### E. production/dev e2e 및 무회귀
| ID | 시나리오 | 결과 | P/F |
|----|----------|------|-----|
| E2E-1 | production wsgi 로드 후 `/healthz` WSGI 호출 | 200 "ok" | PASS |
| E2E-2 | production에서 django-storages `default_storage.exists()` -> boto3가 허용 R2 호스트(`203.0.113.20:443`)로 실제 도달(스텁이 거부) | 차단되지 않음, connect 도달 | PASS |
| E2E-3 | production 프로세스에서 `requests.get("https://api.thirdparty-saas.example/...")` | 차단, connect 0, DNS 0 | PASS |
| E2E-4 | production `requests.get("https://93.184.216.34/")` | 차단 | PASS |
| E2E-5 | DEF-001 원 재현절차(boto3 `list_buckets`, IP 리터럴 엔드포인트) | **차단(원인 체인에 NB)** | PASS |
| RUN-1 | `manage.py runserver 127.0.0.1:18937 --noreload`(dev, DATABASE_URL 미설정) `/healthz` | 200 "ok" | PASS |
| RUN-2 | 같은 서버 `/`, `/privacy/` | 200, 200 (`/`의 로그 트레이스백은 미마이그레이션 SQLite의 `converter_conversionjob` 테이블 부재로 net_guard와 무관, dev는 가드 비활성) | PASS |
| MUT | 테스트 유효성: 매트릭스를 뮤턴트에 적용 — M1=v1 원본(git HEAD): **63건 FAIL**(boto3 포함, DEF-001 재현), M2 connect의 IP 차단 제거: 42건, M3 IPv4-mapped 환원 제거: 12건, M4 getaddrinfo IP 기록 제거: 48건, M5 호스트명 게이트 제거: 18건 FAIL | 5/5 뮤턴트를 매트릭스가 검출(테스트가 결함을 놓치지 않는 것을 입증) | PASS |

## 11-5. 커버리지
- 소스 라인/브랜치 관점: `net_guard.py`의 모든 함수·분기(`install` enforce True/False/재설치, `_build_allowed_hosts` 성공/실패, `_extract_host`, `_parse_ip`(IPv4/IPv6/mapped/zone/비IP), `check_host_for_lookup` 5분기, `guarded_getaddrinfo` 기록 분기, `check_address` 6분기(AF_UNIX/비튜플/비문자/호스트명 허용·차단/IP 루프백·허용집합·허용호스트IP 리터럴/차단), `guarded_connect(_ex)`, `_unwrap`)가 위 케이스로 최소 1회 실행됨. `pytest-cov`는 스크립트 기반(비-pytest) 실행이라 수치 측정은 하지 않았고 케이스-분기 대응 검토로 갈음(정직 고지).
- AC 커버리지 100%: AC-1(TC-001, M[a]) / AC-2(TC-002,002b, M[e]) / AC-3(TC-005, TC-014) / AC-4(TC-004) / AC-5(TC-014, 015, D표, E2E-1) / AC-6(TC-018, E09) / AC-7(TC-017, E08). 10-7의 (a)~(g) 보강 조건 모두 수행: (a)=E2E-5, (b)=TC-011, (c)=D표, (d)=TC-008, (e)=TC-006, (f)=TC-018, (g)=f1/f2/E06(루프백 통과 확인).
- 미커버: 실제 Linux(AF_UNIX 실소켓, epoll 기반 asyncio, gunicorn gthread), 실제 Neon/R2 접속, libpq 실연결 — 8절.

## 11-6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 |
|----|------|-----------|--------|------|------|
| DEF-001 | (v1) `socket.create_connection`만 패치해 urllib3/boto3/requests 우회 | 위 v1 6절 | Critical | **Fixed(재작업으로 해소, 06이 독립 재현·검증)** | 패치 지점 교체 확인: 원 재현절차가 E2E-5/M[boto3]로 차단, 뮤턴트 M1(v1)은 63건 FAIL로 결함 재현됨 |
| DEF-002 | **`socket.socket.connect/connect_ex`에 호스트명 `"localhost"`를 직접 넘기면 차단된다.** `check_address()`의 호스트명 분기가 `allowed_hosts`만 보고 `localhost`를 통과시키지 않는다. 반면 `getaddrinfo("localhost")`는 통과한다(`check_host_for_lookup`). 03 §6-3 v5.1(DEC-043 "루프백(127.0.0.1, ::1, localhost) 통과")과 note §10-3-1/§10-6 서술("localhost 통과")과 불일치. `socket.create_connection`/urllib3/requests/http.client/asyncio는 먼저 getaddrinfo로 IP를 얻어 IP로 connect하므로 영향이 없고, **raw `sock.connect(("localhost", port))`(예: `multiprocessing.connection`류, 직접 소켓 코드)만** 영향. 현재 webapp 코드에 해당 사용처 없음(grep 확인). 방향은 fail-closed(보안 저하 아님, 가용성 이슈). | (1) `install(enforce=True)` 후 `s=socket.socket(); s.connect(("localhost",80))` -> `NetworkAccessBlockedError: 허용되지 않은 목적지: localhost`. 매트릭스 M[f3\|raw connect], M[f3\|raw connect_ex]. (2) 대조: 같은 프로세스에서 `socket.getaddrinfo("localhost",80)`은 통과, `create_connection(("localhost",80))`은 통과. | **Low** | **Open** | 로직 변경(`check_address` 호스트명 분기에 `norm == "localhost"` 통과 추가, 1줄)이라 "사소한 오탈자 수준" 기준을 넘어 06이 직접 수정하지 않음. 05 반려 또는 오케스트레이터가 Deferred로 수용(아래 11-9) |
- 이번 재검증 중 발견한 **테스트 설계 측 문제**(코드 결함 아님, 수정 후 재실행 완료): (1) 스텁 connect가 Windows `socketpair` 에뮬레이션(루프백 connect)까지 거부해 asyncio 루프 생성이 실패 -> 루프를 스텁 설치 전에 생성하도록 수정, (2) 뮤턴트 실행 경로가 msys 형식(`/c/...`)이라 뮤턴트가 로드되지 않아 "전 뮤턴트 2 FAIL"의 허위 결과가 나옴 -> Windows 경로로 수정 후 재실행(63/42/12/48/18).

## 11-7. 테스트 환경 정리(Teardown) — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/venv_06_unit9/`(venv). `webapp/db.sqlite3`(runserver dev가 만든 0바이트 파일, `.gitignore` 대상) — 내가 만든 것이라 삭제함. 테스트 스크립트는 세션 스크래치패드(리포지토리 밖). runserver(포트 18937)는 종료 확인. 리포지토리 `__pycache__`는 `.gitignore` 대상(정리 대상 아님).
- 전부 `.harness-tmp/` 하위(venv) 또는 스크래치패드에서만 생성 [x] / 정리 완료 [x] (`rm -rf .harness-tmp/venv_06_unit9`, `ls .harness-tmp` 결과 빈 디렉터리)
- 강제 중단 없음 [x]
- 정리 후 `git status` 원문:
```
On branch PROD_SCH
Changes not staged for commit:
	modified:   docs/harness/03-system-design.md          <- 05/오케스트레이터(unit-9 설계 v5.1 정정), 이번 06은 미수정
	modified:   docs/harness/decisions.md                 <- 오케스트레이터 공유문서, 미수정
	modified:   docs/harness/traceability.md              <- 오케스트레이터 공유문서, 미수정
	modified:   docs/harness/units/unit-9-note.md         <- unit-9 05 재작업 산출물
	modified:   docs/harness/verify-log_03-system-design.md   <- 타 작업(설계문서 검증 로그) 소유
	modified:   webapp/config/wsgi.py                     <- unit-9 05 재작업
	modified:   webapp/core/net_guard.py                  <- unit-9 05 재작업
Untracked files:
	docs/harness/units/unit-23-test.md                    <- unit-23(타 에이전트) 소유
	docs/harness/verify-log_unit-23-test.md               <- unit-23 소유
	docs/harness/verify-log_unit-9-note.md                <- unit-9 05 재작업 산출물
```
  (이 unit-9 06이 갱신한 `docs/harness/units/unit-9-test.md`, `docs/harness/verify-log_unit-9-test.md`는 위 스냅샷 이후에 수정됨(기존 추적 대상 아님/변경 표시는 커밋 전 M로 보임).) 이 06이 만든 임시 아티팩트·미추적 잔여물 없음.
- 규칙 K 충족: 예.

## 11-8. 리스크 및 잔존 이슈 (결함 아님, 근거 포함)
- **R1 psycopg(libpq) 우회 — 알려진 한계(사실 보정)**: libpq가 C 레벨 소켓을 쓰므로 connect 가드는 우회(`pq.__impl__=="binary"`). 다만 psycopg 3.2.10은 호스트명 접속 시 `conninfo_attempts`에서 파이썬 `socket.getaddrinfo`를 먼저 호출하므로 **비허용 호스트명은 libpq 이전에 차단**된다(E09b). **IP 리터럴 host는 해석을 건너뛰어 무가드**(E09d). Neon은 허용 대상이라 정상 경로는 영향 없고, DATABASE_URL을 조작해야 하는 시나리오라 09단계 참고용. psycopg 버전 업그레이드 시 이 동작이 달라질 수 있음(내부 구현 의존).
- **R2 UDP `sendto/sendmsg`(비연결 전송)**: connect를 거치지 않아 우회. 구조적 한계(코드에 참조 없음 E11c). 실제 UDP 전송은 외부망 유출 방지 원칙상 실행하지 않음(정적 근거만).
- **R3 C 확장/`_socket` 직접 사용, Windows Proactor**: `_socket.socket`/`socket.SocketType`은 미패치 기반 클래스(E11a/b)라 고의적 우회가 가능(방어선은 "실수 방지" 수준). Windows asyncio 기본 Proactor 루프는 `ConnectEx`(overlapped)로 `sock.connect`를 거치지 않을 가능성이 있음 — **미실측(추론)**, 운영은 Linux(Selector)라 dev 한정 무관.
- **R4 허용 호스트와 IP 공유 호스트**: 실측(E12b) 통과. R2 엔드포인트는 Cloudflare 엣지 IP일 가능성이 높고 그 IP는 다른 Cloudflare 고객과 공유될 수 있다는 점은 **추론(미실측)**이며, 그렇다면 IP 리터럴+Host/SNI 조작으로 제3자 접속 여지가 있다. 호스트명 기반 실수 호출은 차단됨(a2).
- **R5 DNS rebinding/허용 IP 누적**: 허용 호스트의 DNS 응답은 신뢰된다. 재해석된 신규 IP는 허용되고 옛 IP도 계속 허용(집합 증가만, E13). 허용 호스트가 링크로컬(169.254.169.254) 등으로 풀리면 그 IP도 허용됨. 허용 호스트 2개라 규모는 미미하나 DNS 오염 시나리오는 방어하지 않는다.
- **R6 미가드 리졸버**: `gethostbyname/gethostbyname_ex/gethostbyaddr/getnameinfo`는 미패치(E10) — 호스트명이 DNS로 유출될 수 있음(이후 connect는 차단). DNS 터널링형 유출은 방어 밖.
- **R7 로그 인젝션(Low)**: 차단 호스트 문자열의 개행이 로그에 그대로 기록됨(E15d). 현재 앱에는 사용자 제공 URL 조회 기능이 없어 실현 가능성 낮음(REQ-020).
- **R8 INFO 로그**: 부팅 시 허용 호스트명(Neon/R2 호스트명)이 INFO로 기록됨. 비밀번호/자격증명은 기록되지 않음(E15b). Neon 엔드포인트 호스트명을 로그 비공개 수준으로 볼지는 운영 정책.
- **R9 견고성(Low)**: `DATABASE_URL`이 `[::1`처럼 urlsplit이 ValueError를 내는 형태면 `install()`이 기동을 중단(fail-closed, 비밀 미노출, 그러나 "파싱 실패는 경고" 계약과 다름). getaddrinfo에 비문자 host를 넘기면 원본의 `TypeError` 대신 `AttributeError`(cosmetic).
- **R10 DEC-040(EMAIL_HOST 미허용) — 사용자 정책 결정 대기**: 실측으로 `smtplib` 비허용 SMTP 호스트는 차단됨(E08). 결정 전까지 production에서 `EMAIL_HOST` 설정 시 장애 알림 메일이 나가지 않는다. 결함으로 올리지 않음.
- **R11 검증 환경 한계**: Windows/Python 3.11.9 단일 환경, AF_UNIX는 시뮬레이션, Linux(Render)·실 Neon/R2 미검증. 운영 Python 버전 미확인(ipaddress의 선행 0 IP 거부는 3.9.5+ 동작 — 3.11에서 확인). 10~12단계에서 실측 필요.
- **R12 stale 참조(가용성)**: net_guard 설치 전에 `from socket import getaddrinfo`로 원본을 잡은 모듈은 허용 IP 기록을 우회해 이후 허용 호스트 connect가 오차단될 수 있다. 의존성 스캔 결과 해당 패턴은 없음(psycopg는 속성 접근, ssl의 `create_connection`은 `socket` 모듈 전역 getaddrinfo를 조회) — 라이브러리 업데이트 시 재확인.

## 11-9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS** — DEF-001(Critical)은 해소를 독립 재현·검증(매트릭스 140건 중 138 PASS, 뮤턴트 5종 검출, DEF-001 원 재현절차 차단, TC-001~018 회귀 PASS, wsgi fail-closed 15/15). 남은 **DEF-002(Low, Open)**: raw `connect(("localhost",port))` 호스트명 분기의 명세(DEC-043 "localhost 통과") 불일치, 1줄 수정 성격이지만 로직 변경이라 06이 직접 고치지 않음. 완료 조건("모든 결함이 Fixed")을 엄격 적용하면 미충족이므로 오케스트레이터 결정 필요: (A) 05에 DEF-002 1줄 수정 반려 -> 재작업 후 M[f3\|raw] 2건 + 회귀 재실행 후 PASS, (B) DEF-002를 Deferred로 수용(현재 사용처 없음, fail-closed)하고 07 handoff.
- 07 handoff는 (A)/(B) 결정 후. 07이 알아야 할 점: 루프백/`localhost` getaddrinfo 통과, 허용 IP 집합은 해석 시점에 채워지므로 "허용 호스트를 먼저 해석하지 않고 그 IP 리터럴로 connect"는 차단(E01a).

## 11-10. 내부 검증
- 1차/2차/3차 요약: `docs/harness/verify-log_unit-9-test.md` 「v2 재검증」 절 참조. 1차에서 테스트 설계 결함 2건(TC-004 WARNING 레벨 명시 단언 누락, 스텁이 만든 asyncio 허위 실패), 2차에서 1건(뮤턴트 로딩 경로 오류로 인한 허위 검증 + AF_UNIX 시뮬레이션 고지 누락 가능성), 모두 수정 후 3차에서 0건.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-9-test.md`

## 11-11. 공유 문서 갱신 요청 (직접 수정하지 않음, 오케스트레이터 반영)
| 대상 | REQ-ID/DEC | 컬럼 | 값 |
|------|-----------|------|----|
| traceability.md | REQ-011 | 단위테스트(unit-n-test) | `unit-9-test.md v2 재검증 11절 — CONDITIONAL PASS (DEF-001 Fixed 검증완료, DEF-002 Low Open: raw connect("localhost") 차단, 05 1줄 수정 또는 Deferred 결정 대기)` |
| traceability.md | REQ-011 | 비고(추가) | psycopg 사실 보정: 호스트명 접속은 파이썬 getaddrinfo에서 선차단되나 IP 리터럴 host는 libpq 무가드. 추가 리스크: gethostbyname 등 미가드 리졸버, 허용 IP 집합 누적/DNS rebinding 신뢰, 로그 인젝션(Low), 부팅 시 malformed DATABASE_URL ValueError 중단. 09단계 참고 |
| decisions.md | DEF-002 처분(신규 DEC 후보) | 결정 | DEF-002를 (A) 05 수정 / (B) Deferred 중 택일하는 결정 기록 필요 |
| decisions.md | DEC-040 | 상태 | 미결 유지 — 06 재확인: SMTP 호스트 실제 차단됨(E08) |


---

# 12. 재검증(3회차) — v2.2 재작업(DEF-002 종결, Q2 localhost 정확 일치, Q3 로그/예외 repr) + 규칙 F 전체 회귀

> 12절은 05단계 재작업 2회(`unit-9-note.md` §11 DEF-002 = `check_address`의 localhost 정확 일치 통과, §12 = `_is_localhost` 엄격 비교 + `_block()` `%r`/`!r` 이스케이프; DEC-045/046)를 06단계가 처음부터 다시 검증한 결과이며 **자기완결적**이다. 12절의 판정이 이 unit의 **현재 유효 판정**이다. 소스·설계서·공유 문서는 수정하지 않았다.

## 12-1. 개요
- 테스트 대상: `webapp/core/net_guard.py`(v2.2: `_is_localhost` 신규, `check_host_for_lookup`/`check_address`의 localhost 분기, `_block()` `%r`), `webapp/config/wsgi.py`(fail-closed 판정) — unit-9, REQ-011 부분
- 테스트 유형: 단위(+ 진입점 e2e, 실소켓 루프백 검증) / 적용 Tier: High(DEC-021) / 속도 트랙 L3 / 재검증 사유: 규칙 F(05 재작업 2회 후 06 전체 재실행)
- 병렬 정보: 동시에 (1) 오케스트레이터 로컬 dev 서버(127.0.0.1:8000, `webapp/db.sqlite3`, `.harness-tmp/venv_run_local`, `run_local.log`)와 (2) unit-23 06(`webapp/converter/*`, `.harness-tmp/_06_unit23b`, `venv_06_unit23b`)이 진행 중. 이 06은 위 자원을 읽거나 수정하지 않았고 포트는 19461(dev runserver), 19463/19464(실소켓 루프백 서버/리스너)만 사용했다. dev runserver의 DB는 `DATABASE_URL=sqlite:///.harness-tmp/db_06_unit9c.sqlite3`로 우회해 오케스트레이터의 `webapp/db.sqlite3`(mtime 12:18, 이번 실행 이전)를 건드리지 않았다.
- 테스트 목적: (1) DEF-002 종결 (2) Q2 정확 일치 (3) Q3 로그 인젝션 차단 (4) 허용 호스트 무회귀 + Q4 리스크 실측 (5) 이전 회차 전체 회귀 (6) 이번 변경에 대한 뮤턴트 검출력 확인
- 테스트 수행자: 06(단위테스터), 일시: 2026-09-29

## 12-2. 테스트 범위 및 제외 범위
- In-Scope: AC-1~AC-7, 11절의 전 범위(TC-001~018, 경로 x 대상 매트릭스, 엣지/우회, wsgi 15값, e2e, runserver, 스레드 경쟁, 뮤턴트), 추가로 localhost 변형 전수, 로그 캡처 실측, 허용 호스트 변형(Q4), 실소켓 루프백.
- Out-of-Scope(결함이 아니라 12-8절 리스크): Q1(허용 호스트명·localhost의 raw connect 이름-only 통과), psycopg IP 리터럴 무가드, IP 공유 호스트, DNS rebinding, gethostbyname 미가드, UDP `sendto`, C 확장/`_socket` 직접 소켓, DEC-040(EMAIL_HOST 정책 미결).
- **외부망 비접속 원칙**: 11절과 동일하게 net_guard가 캡처하는 "원본" `getaddrinfo`/`connect`/`connect_ex`를 스텁으로 교체(TEST-NET-3 203.0.113.x, 198.51.100.x, 2001:db8::/32만 해석). 이번 스텁은 **엄격 모드**(`strip()` 없음, **단일** 후행 점만 정규화; 11절 스텁은 다중 점도 정규화했음 -> 이번에 더 엄격해져 Q4 다중 점 변형이 리졸버 스텁에서 실패하게 됨). 미등록 이름이 원본 getaddrinfo에 도달하면 `LEAK`에 기록. 차단 대상 케이스 전부에서 `LEAK`, `LOOKUPS`(원본 해석기 호출), `CONNECTS`(원본 connect 호출)가 비어 있음을 단언했다. Q4 변형(허용 호스트의 `..`/공백)만 의도적으로 원본 해석기 스텁에 도달하며(가드가 통과시키는 설계), 스텁이 `gaierror`를 던져 IP를 반환하지 않는다. **실제 외부 DNS/TCP 질의: 0건**(`netstat -an`에 203.0.113.x/93.184.216.34 연결 없음; 19463 서버는 127.0.0.1 루프백 TIME_WAIT만). 스텁 버그로 실제 질의가 나간 사례: **없음**. 실소켓 검증(12-4-F)은 `localhost`/`LOCALHOST`/`LocalHost`(hosts 파일 해석)와 가드가 해석 이전에 차단하는 이름만 사용했다(`localhost.` 같은 후행 점 변형은 실제 리졸버가 DNS를 물을 위험이 있어 실소켓에서는 **일부러 제외**, 스텁으로만 검증).

## 12-3. 테스트 환경
- Windows 10 Pro 10.0.19045, Python 3.11.9, 격리 venv `.harness-tmp/venv_06_unit9c/`(`requirements.txt` 전체 + **requests 2.34.2**; boto3 1.35.36, urllib3 2.8.0, psycopg 3.2.10, Django 5.2.17). 첫 설치 시도는 pip 24.0이 `requirements.txt`의 UTF-8 주석을 cp949로 디코드해 실패(무출력으로 오인할 뻔함, `pip list`로 발견) -> `PYTHONUTF8=1`로 재설치(환경 이슈, 소스 무관). 종료 후 삭제(12-7).
- 테스트 스크립트: 세션 스크래치패드 `.../scratchpad/ng3/`(`ng_env.py` 엄격 스텁, `s1_matrix.py`, `s2_edges.py`, `s3_misc.py`, `s4_wsgi.py`, `s5_runserver.py`, `s6_extra.py`, `s7_log.py`, 신규 `s8_localhost.py`, `s9_log_q4.py`, `s10_real_loopback.py`, `mk_mut.py`)에만 있고 리포지토리에는 남기지 않았다(v1/v2 관례).
- 전제(5단계 게이트) 확인: `unit-9-note.md` §11-4, §12-2 — lint/type/formatter 설정 없음(재확인), `py_compile` 성공, 자체 리뷰 체크리스트 [x]. 이번 06 독립 재실행: `py_compile net_guard.py wsgi.py` -> COMPILE_OK, `manage.py check` -> "System check identified no issues (0 silenced)". `git diff --stat`: `net_guard.py`, `wsgi.py` 2개 파일만(범위 외 소스 변경 없음). 확인됨.
- 한계: Windows에는 `socket.AF_UNIX`가 없어 AF_UNIX는 시뮬레이션(E06, 11절과 동일). Render(Linux) 실환경 미검증 -> 12-8 R11.

## 12-4. 테스트 케이스 및 결과 (전 실행 2회, 결과 동일)

### A. v1 TC-001~018 회귀 (v2.2로 재실측)
| ID | 시나리오 | 실제 결과 | P/F | 근거 |
|----|----------|-----------|-----|------|
| TC-001 | 비허용 호스트 차단(AC-1) | 10경로 전부 차단, 원본 connect/DNS 미도달 | PASS | 매트릭스 a |
| TC-002/002b | DATABASE_URL/R2 호스트 허용(AC-2) | 10경로 전부 원본 connect 도달 | PASS | 매트릭스 e1/e2 |
| TC-003 | 대소문자/단일 후행 점 허용 | `ALLOWED-R2.example.com.` 10/10 도달, 접두/접미/@ 유사 호스트 차단(E02k/l/m), DB URL 대문자+후행 점 파싱(malformed:upper_db) | PASS | 매트릭스 e1, s2, s3 |
| TC-004 | 차단 로그(AC-4) | `core.net_guard` WARNING 정확히 1건, 호스트 포함(**repr 형태**), 허용/루프백 0건 | PASS | s7 TC-004a/b/c |
| TC-005 | dev 비활성(AC-3) | 3개 함수 스텁과 동일 객체, 임의 호스트 원본 도달, 이후 `install(True)` 무시 | PASS | s3 dev |
| TC-006 | 허용목록 공집합 | 파싱 경고 2건, 루프백 외 전부 차단, 루프백/localhost 조회 통과 | PASS | s3 empty 5건 |
| TC-007 | DATABASE_URL 형식 파손 | 9종 시나리오 11절과 동일(`[::1` 만 ValueError로 기동 중단=fail-closed, 비밀번호 미노출, R9) | PASS(리스크 R9) | s3 malformed 9종 |
| TC-008 | 멱등성 | 3개 함수 참조 동일성, reload 후 unwrap, 이중 래핑 없음(원본 connect 1회) | PASS | s3 idem 6건 |
| TC-009/010/011 | urllib.request / http.client / **requests(스킵 없음, venv 설치)** | 비허용 전부 차단, 허용 도달 | PASS | 매트릭스 |
| TC-012 | boto3 list_buckets(DEF-001 재현) | 비허용 호스트/IPv4/IPv6/mapped 차단(원인 체인에 NetworkAccessBlockedError), 원 재현절차 production e2e에서도 차단 | PASS | 매트릭스, E2E-5 |
| TC-013 | wsgi 판정 | 15/15(12-4-D) | PASS | s4 |
| TC-014/015 | 진입점 dev/production | dev `patched=False`, production `patched=True` + `/healthz` 200 | PASS | s4, E2E-1 |
| TC-016 | 하드코딩 금지 | 허용목록은 `os.environ.get`+`urlsplit().hostname`으로만 구성. 소스에 허용 호스트 리터럴 없음(테스트 호스트 문자열은 `net_guard.py`에 0건) | PASS | 소스 대조 |
| TC-017 | EMAIL_HOST 미허용(DEC-040) | net_guard가 참조하는 env는 `DATABASE_URL`/`R2_ENDPOINT_URL` 2개뿐. `smtplib.SMTP/SMTP_SSL` 비허용 호스트 실제 차단(E08a/b). 미결 유지 | PASS(리스크 재확인) | s2 E08 |
| TC-018 | psycopg 한계 | `pq.__impl__=="binary"`, 호스트명 접속은 파이썬 getaddrinfo에서 선차단(E09b), IP 리터럴 host는 무가드(E09d, 실연결 미실행) | PASS(한계 유지) | s2 E09 |

### B. 경로 x 대상 매트릭스 (10경로 x 21대상 = 210건, 실측: B=차단, R=원본 connect 도달) — 2회 실행 모두 210/210 PASS
경로: boto3.list_buckets / requests(http) / requests(https) / urllib3.PoolManager / urllib.request / http.client / socket.create_connection / raw connect / raw connect_ex / asyncio(SelectorEventLoop).
| 대상 | 호스트 | 기대 | 결과 | P/F |
|------|--------|------|------|-----|
| a, a2 | `blocked-host.example`, `other.example`(R2와 IP 공유) | B | 10/10 B x2 | PASS |
| b, b2, c, d | `93.184.216.34`, `203.0.113.21`, IPv6 리터럴, IPv4-mapped | B | 10/10 B x4 | PASS |
| e1, e2 | `ALLOWED-R2.example.com.`, `allowed-db.example` | R | 10/10 R x2 (**허용 호스트 무회귀**) | PASS |
| f1, f2 | `127.0.0.1`, `::1` | R | 10/10 R x2 | PASS |
| **f3, f3b, f3c, f3d** | `localhost`, `LOCALHOST`, `Localhost.`, `localhost.` | R | **10/10 R x4 = 40건. raw connect / raw connect_ex 포함 -> DEF-002 종결** | PASS |
| **h1, h2, h3** | `localhost.evil.com`, `evil.localhost`, `xlocalhost` | B | 10/10 B x3 | PASS |
| **h4** | `localhost..` | B | 6경로 B(urllib.request, http.client, create_connection, raw connect, raw connect_ex, asyncio), **4경로(boto3, requests http/https, urllib3)는 클라이언트 URL 파서가 가드 이전에 거부**(`ValueError`/`LocationParseError`, 원본 lookup/connect 0건) -> `CLIENT_REJECTED`로 별도 분류해 통과 처리(가드가 막은 것이 아니라 클라이언트가 접속 자체를 시도하지 않은 것임을 명시). 동일 호스트는 아래 s8에서 5개 저수준 경로로 가드 차단 확인 | PASS(4건 CLIENT_REJECTED) | 
| g1, g2, g3 | 사전 해석된 허용 IP(IPv4/IPv6/mapped) | R | 10/10 R x3 | PASS |
- 원본 connect가 호출된 차단 대상: 0건, `LEAK`: 0건.

### C. localhost 정확 일치 전수 (DEF-002 종결 + Q2) — `s8_localhost.py`, 5경로(getaddrinfo / raw connect / raw connect_ex / create_connection / asyncio) x 변형, **368 단언 PASS**
| ID | 시나리오 | 기대 | 실제 | P/F |
|----|----------|------|------|-----|
| L-PASS | `localhost`, `LOCALHOST`, `Localhost.`, `localhost.`, `LocalHost`, `b"localhost"`, `b"LOCALHOST."`, `b"Localhost."` x 5경로(40건) | 원본 도달(차단 아님) | 40/40 도달. getaddrinfo·create_connection과 raw connect/connect_ex가 **일관** | PASS |
| L-BLOCK | 61종(str 51 + bytes 10) x 5경로(305건): `" localhost "`, `"localhost.."`, `"localhost..."`, 앞/뒤 공백, `\t`/`\n`/`\r`/`\r\n` 앞뒤, `"localhost. "`, `" localhost."`, `"localhost.\n"`, `"localhost.\t"`, `"localhost\x00"`, `"localhost\x00.evil.com"`, `"\x00localhost"`, `localhost.evil.com`, `evil.localhost`, `xlocalhost`, `localhostx`, `sub.localhost(.)`, `localhost.localdomain`, `localdomain`, 키릴 `о`/`т` 치환 3종, 전각 `ｌｏｃａｌｈｏｓｔ`, 유니코드 마침표 `。`/`．`, 제로폭 공백, NBSP, U+2028, U+0085, 로마숫자 `ⅰ`, `LOCALHOST..`, `localhost:80`, `localhost%lo`, `127.0.0.1.localhost`, `local host`, `loca1host`, `localhos`, `ocalhost`, `.localhost`, `.`, `..`, bytes 10종(`b" localhost"`, `b"localhost .."`, `b"localhost\x00"`, `b"localhost\n"`, `b"localhost\xff"`, `b"local\xc0host"` 등) | `NetworkAccessBlockedError`, 원본 lookup/connect 0건 | 298/305 차단. 나머지 7건은 asyncio 경로에서 asyncio 자체가 NUL·비ASCII bytes를 가드 이전에 `ValueError`/`UnicodeDecodeError`로 거부(원본 lookup/connect 0건, `CLIENT_REJECTED`); 같은 입력은 다른 4경로에서 가드가 차단 | PASS(7건 CLIENT_REJECTED 고지) |
| L-BA | `bytearray(b"localhost")` raw connect | 도달 | 도달 | PASS |
| L-BA | `bytearray(b" localhost")`, `bytearray(b"localhost..")` raw connect | 차단 | 차단 | PASS |
| L-NONSTR | raw connect의 host가 int/None/float/tuple/object | 차단(fail-closed) | 5/5 차단 | PASS |
| L-HC | http.client: `localhost`, `LOCALHOST.` 도달 / `localhost.evil.com`, `xlocalhost`, `localhost..` 차단 | 그대로 | 그대로 | PASS |
| L-REMAP | `localhost`가 비루프백(203.0.113.50)으로 풀리는 환경(스텁 TABLE 조작): create_connection, urllib.request, http.client, requests, urllib3, boto3, asyncio | connect 단계 IP 검사로 차단, 원본 connect 미도달 | 7/7 `blocked=True connects=[]` | PASS |
| L-REMAP | 다중 레코드 `[127.0.0.1, 203.0.113.50]` create_connection | 루프백 시도 후 비루프백에서 `NetworkAccessBlockedError`, 203.0.113.50은 원본 미도달 | `connects=[('127.0.0.1',80)]`, NB 발생 | PASS |
| L-POISON | `getaddrinfo("localhost")`가 비루프백 IP로 풀린 뒤 그 IP 직접 connect | 허용 IP 집합 오염 없음 -> 차단 | 차단 | PASS |
| L-REMAP(raw) | `raw connect(("localhost",80))`(비루프백 매핑 환경) | **이름만으로 통과(Q1, 알려진 한계)** | 도달 확인 -> 결함 아님, 12-8 R-Q1 | PASS(리스크 실증) |
- 직접 함수 단위 검증(`_is_localhost` 23케이스: 정확 일치/변형/None/int/float/list/tuple/bytearray/bytes): 불일치 0건. `_normalize_host`는 미변경(`"  a.B "`->`a.b`, `"a.b.."`->`a.b`, bytes 처리 유지) 확인.

### D. wsgi 활성화 판정 15값 (11절과 동일, 서브프로세스 실측) — 15/15 기대 일치, 2회 실행 동일
비활성은 미설정/`config.settings.dev` 2건만(비허용 IP connect 도달), 나머지 13건(`config.settings.production`, `""`, `config.settings`, `config.settings.Dev`, `Config.Settings.DEV`, 후행/선행 공백 dev, `devv`, `dev.py`, `dev;x`, `production`, `production_backup`, `CONFIG.SETTINGS.PRODUCTION`)은 전부 ON/차단. 오탈자/빈 값은 가드가 켜진 채 Django import 단계에서 기동 실패(안전 측). PASS.

### E. e2e 및 dev runserver
| ID | 시나리오 | 결과 | P/F |
|----|----------|------|-----|
| E2E-1 | production wsgi `/healthz` | 200 "ok" | PASS |
| E2E-2 | production `default_storage.exists()`(boto3)가 허용 R2 호스트 203.0.113.20:443에 도달 | 도달(차단 아님) | PASS |
| E2E-3 | production `requests.get("https://api.thirdparty-saas.example/...")` | 차단, connect 0, DNS 0 | PASS |
| E2E-4 | production `requests.get("https://93.184.216.34/")` | 차단 | PASS |
| E2E-5 | DEF-001 원 재현절차(boto3 IP 리터럴) | 차단(원인 체인에 NB) | PASS |
| RUN-1~3 | `manage.py runserver 127.0.0.1:19461 --noreload`(dev, 임시 sqlite) `/healthz`, `/`, `/privacy/` | 200 / 200 / 200 (`/`의 트레이스백은 미마이그레이션 SQLite의 `converter_conversionjob` 부재로 net_guard와 무관, dev는 가드 비활성) | PASS |

### F. 실소켓(비스텁) 루프백 검증 — `s10_real_loopback.py`, 28건 PASS (2회 실행)
가드를 실제 `socket` 위에 설치하고 127.0.0.1:19463(http.server)·19464(raw listener)만 사용. `raw connect`/`raw connect_ex`/`create_connection`/`urllib.request`로 `localhost`/`LOCALHOST`/`LocalHost`가 **실제 로컬 서버에 연결됨**(`connect_ex` rc=0, 응답 `b'pong'`) = DEF-002 종결의 실환경 증거. `" localhost "`, `"localhost.."`, `"localhost\n"`, `localhost.evil.com`, `evil.localhost`, `xlocalhost`, 키릴 치환은 connect/connect_ex/getaddrinfo 3방식 모두 해석 이전에 `NetworkAccessBlockedError`(21건), 비허용 IP 리터럴은 OS 도달 전 차단. 서버·소켓은 종료됨.

### G. Q3 — 로그/예외 이스케이프 (`s9_log_q4.py`, 실제 `StreamHandler` 출력 캡처) — 80 단언 중 Q3 계열 PASS
- 호스트 16종(개행 `\n`, `\r`, `\r\n`, NUL, ESC(`\x1b[31m`), 탭, BEL, U+2028, U+0085, VT/FF, 따옴표 혼합, 백슬래시, 한글, 50자, `"\n"`, `"\x00"`) x 3경로(getaddrinfo, raw connect(str), raw connect(bytes)) = 48건: 각 건에서 (a) `NetworkAccessBlockedError` (b) `core.net_guard` WARNING 정확히 1건 (c) **출력 줄 수 정확히 1**(`out.count("\n") == 1`, 실제 개행은 종결자 하나뿐) (d) 로그 본문에 `\r`,NUL,ESC,BEL,VT,FF,U+2028,U+0085 원문 문자 없음 (e) 예외 메시지에도 동일 제어문자 없음 (f) 원본 lookup/connect 0건. 예: `host='localhost\nINJECT'`, 예외 `허용되지 않은 목적지: 'a\nb\x00'`(한 줄). 모두 PASS. 위조 로그 줄(`FORGED LOG LINE level=CRITICAL`)이 별도 줄로 나타나지 않음을 확인.
- 비표준 주소 형태 5건(AF_INET에 개행 든 str 경로, None, int host, NUL 든 bytes host, 비ASCII bytes): 전부 차단, 로그 1줄, 메시지 단일 줄, NUL 미출력 — PASS.
- (고지) Q3d/Q3g는 정보 기록용 항목(항상 PASS)이라 실효 단언에서 제외하면 s9의 Q3 실효 단언은 56건이다. 예외 메시지 내용(Q3c/Q3e): 정확히 `허용되지 않은 목적지: 'blocked-host.example'` / `'93.184.216.34'` 형태이며 허용 호스트명 2종, `DATABASE_URL`/`R2_ENDPOINT_URL` 문자열, 비밀번호, 사용자명, `postgres`, 테이블 IP, 모듈명 어느 것도 없음. 로그에도 DB 비밀번호(`S3cretPw-XYZ`) 없음(Q3f). s2 E15a-d(기존)도 갱신 기대(이스케이프 확인)로 PASS.
- 부팅 INFO 로그는 허용 **호스트명** 리스트만 출력(자격증명 없음, R8 유지).

### H. Q4 — 허용 호스트의 다중 후행 점·공백 변형 (리스크 실측, `s9_log_q4.py` Q4 계열 PASS)
변형: `allowed-r2.example.com..`, `...`, 앞/뒤 공백, `\tallowed-r2.example.com\n`, `ALLOWED-R2.EXAMPLE.COM..`.
| ID | 실측 | 결론 |
|----|------|------|
| Q4a | `getaddrinfo(변형)`: 이름 게이트 통과(`_normalize_host` 미변경으로 허용 호스트와 동일 판정). 엄격 리졸버 스텁이 `gaierror` -> 결과 IP 없음 -> 허용 IP 집합에 **아무것도 기록되지 않음** | 통과하나 유출 경로 아님 |
| Q4b | 그 직후 허용 R2의 IP 리터럴(203.0.113.20)로 raw connect | **차단**(집합 오염 없음) |
| Q4c | `raw connect((변형, 443))`: 이름-only로 원본 connect에 도달(문자열 그대로, IP 아님) | Q1과 동일한 성질. 실제 C 레벨은 이 문자열을 해석해야 하며 해석 실패 시 `gaierror` |
| Q4d | `create_connection((변형, 443))`: 해석 실패로 connect 이전 종료(`connects=[]`) | 유출 없음 |
| Q4e | 허용 호스트의 접미/접두/NUL 유사 호스트 3종 | 차단 유지 |
- **실측 범위 정직 고지**: 실제 OS 리졸버가 `host..`/공백 포함 이름에서 DNS를 묻는지는 외부 질의 0건 원칙상 측정하지 않았다. 스텁 실측과 설계 추론(가장 관대한 리졸버가 이 이름을 정규화해 풀더라도 결과는 허용 호스트와 **동일한 IP**이며 신규 목적지가 아님)으로 "새로운 외부 목적지로의 유출 경로는 없다"고 판단한다. 결함으로 올리지 않고 12-8 R-Q4로 기록.

### I. 엣지/우회 재시도 (s2, 71건 PASS, 11절과 동일 범위 + 갱신) 및 기타
E01(해석 전/후 허용 IP), E02(getaddrinfo 인자 형태 a-n), E03(zone id), E04(특이 IP 표기 14종: `127.1`, `0x7f.1`, `2130706433`, `0.0.0.0`, 선행 0, `::`, mapped 루프백 등), E05(판정 불가 주소 9종 fail-closed), E06(AF_UNIX 시뮬레이션 4), E07(UDP connect), E08(SMTP), E09(psycopg), E10(gethostbyname 미가드=리스크), E11(구조적 우회 증거), E12(공유 IP=리스크), E13(rebinding=리스크), E14(허용 집합 오염 시도 3건: 비허용 이름은 해석기 호출 전 차단, 그 IP connect 차단, 집합은 모듈 속성으로 비노출), E15(a-d, d는 이제 이스케이프 확인으로 갱신), **E16 스레드 경쟁**(리더 12 vs 라이터 100회 재해석: 비허용 IP 통과 0건, 해석된 IP 오차단 0건, errors=0) 전부 PASS. 추가: s6 EXTRA(int/list host는 `AttributeError`로 예외 유지=차단 아님/취약점 아님, 키릴·켈빈 유사 호스트 차단, `AI_NUMERICHOST`+비허용 이름 차단) 5건, s3 시나리오(idem 6, dev 3, empty 5, malformed 9종) PASS.

### J. 뮤턴트(테스트 유효성) — 18종 전부 검출 (`mk_mut.py`로 현재 소스에서 생성, 치환 1회 일치 단언, 로드 경로 검증 후 실행)
| 뮤턴트 | 내용 | s1 매트릭스 FAIL | s8 localhost FAIL | s9 로그/Q4 FAIL | s2 엣지 FAIL | 검출 |
|--------|------|------|------|------|------|------|
| M1 | v1 원본(git HEAD) | 96 | 259 | 53 | 36 | O |
| M2 | connect IP 검사 제거 | 40 | 9 | 0 | 13 | O |
| M3 | IPv4-mapped 환원 제거 | 10 | 0 | 0 | 1 | O |
| M4 | getaddrinfo IP 기록 제거 | 46 | 0 | 0 | 8 | O |
| M5 | 호스트명 게이트 제거 | 44 | 179 | 16 | 13 | O |
| **M6a** | **`_is_localhost`를 `strip()` 허용으로 되돌리기(Q2)** | 0 | **106** | 0 | 0 | O(s8만 검출) |
| **M6b** | `_is_localhost` 다중 후행 점 허용 | 6 | 22 | 0 | 0 | O |
| **M6c** | `endswith("localhost")` | 20 | 81 | 0 | 1 | O |
| **M6d** | `startswith("localhost")` | 16 | 149 | 0 | 0 | O |
| **M6e** | `_normalize_host`로 비교(strip+다중 점) | 6 | 128 | 0 | 0 | O |
| **M7a** | **`_block` 로그를 `%s`로 되돌리기(Q3)** | 0 | 0 | **34** | 1 | O(s9 검출) |
| **M7b** | 예외 메시지 repr 제거 | 0 | 0 | **36** | 0 | O |
| **M7c** | 로그+예외 모두 평문 | 0 | 0 | 36 | 1 | O |
| **M8** | **check_address의 localhost 분기 제거(DEF-002 되돌리기)** | 8 | 18 | 0 | 0 | O |
| **M9** | check_host_for_lookup의 localhost 분기 제거 | 32 | 26 | 0 | 2 | O |
| M10 | connect가 무조건 통과(M2와 동치, 라벨만 다름) | 40 | 9 | 0 | 13 | O |
| M11 | 모든 조회 IP를 허용 집합에 기록(오염) | 40 | 9 | 0 | 3 | O |
| **M12** | `_is_localhost`의 bytes 디코드 제거 | 0 | 9 | 0 | 0 | O |
- **정직 고지(테스트 유효성 자기 오류)**: 최초 뮤턴트 루프는 `NG_MUT` 경로를 백슬래시 문자열로 넘겨 뮤턴트가 로드되지 않았고(모듈 경로가 여전히 `webapp/core`) **18종 전부 0 FAIL**이 나왔다. 이는 "뮤턴트가 통과했다"가 아니라 "뮤턴트를 아예 로드하지 못한" 허위 결과(11절의 msys 경로 사건과 같은 유형)였다. `loaded=` 경로 출력으로 발견해 슬래시 경로로 고치고, 이후 러너가 로드 경로에 `mut/<이름>`이 포함되지 않으면 중단(`NOT_LOADED_ABORT`)하도록 강제한 뒤 재실행한 결과가 위 표다. M6a·M12는 매트릭스(s1)만으로는 놓치고 s8이 필요했으며, M7a/b/c는 s9(실제 로그 출력 캡처)로만 확실히 검출됨 -> 신규 s8/s9가 이번 변경의 회귀 방지에 실질적으로 기여함을 입증.

## 12-5. 커버리지
- 분기 관점(스크립트 기반, `pytest-cov` 수치 미측정 — 11절과 동일한 정직 고지): `_is_localhost`(bytes/bytearray 디코드, 비-str `False`(직접 호출 23케이스로 도달; 실제 호출 지점에서는 앞단이 먼저 걸러 도달 불가한 방어 분기), 소문자화, 단일 점 제거, 정확 일치), `check_host_for_lookup`(빈 host/IP 리터럴/localhost/허용/차단), `check_address`(AF_UNIX/비튜플/비문자/호스트명 localhost·허용·차단/IP 루프백·허용집합·허용호스트 IP/차단), `_block`(str/비str/repr 이스케이프), `install` 전 분기, `guarded_getaddrinfo` 기록 분기가 최소 1회 실행됨.
- AC 커버리지 100%: AC-1(TC-001) / AC-2(TC-002, 002b) / AC-3(TC-005, 014) / AC-4(TC-004, Q3 G절) / AC-5(TC-014, 015, D, E2E-1) / AC-6(TC-018) / AC-7(TC-017). 05 재작업 인수 조건 §11-5 (a)~(d)와 §12-4 (a)~(d) 전부 수행: §11-5(a)=C/F절, (b)=C절 접미사, (c)=매트릭스 a~d, (d)=12-8; §12-4(a)=C절, (b)=G절, (c)=매트릭스 e1/e2, (d)=§11-5 유지.
- 미커버: Linux(AF_UNIX 실소켓, epoll asyncio, gunicorn gthread), 실제 Neon/R2, libpq 실연결, 실제 OS 리졸버의 이상 이름 처리 — 12-8.

## 12-6. 결함(Defect) 목록
| ID | 설명 | 상태 | 조치/근거 |
|----|------|------|-----------|
| DEF-001 | (v1, Critical) `socket.create_connection`만 패치해 urllib3/boto3/requests 우회 | **Fixed**(11절에서 검증, 12절 회귀로 재확인) | 매트릭스 boto3/requests/urllib3 전 대상, E2E-5, M1 뮤턴트가 96/259건 FAIL로 결함 재현 |
| DEF-002 | (v2, Low) raw `connect/connect_ex(("localhost", port))` 차단(03 §6-3 v5.1/DEC-043 "localhost 통과"와 불일치) | **Fixed**(06이 독립 검증) | 스텁 40건(f3~f3d x 10경로) + s8 L-PASS 40건 + 실소켓 F절(실제 로컬 서버 연결) + M8 뮤턴트 검출(8/18 FAIL)로 종결 확인. getaddrinfo·create_connection과 일관 |
- **신규 결함: 0건.** 05가 남긴 Q1·Q4와 이번에 재확인한 항목은 결함이 아니라 12-8 리스크로만 기록한다(사유: Q1은 DEC-043이 localhost 통과를 확정, DEC-046이 09단계 이관을 확정; Q4는 외부 유출 경로가 없음을 위 H절로 확인).
- 테스트 설계 측 문제(코드 결함 아님, 수정 후 재실행 완료): (1) 뮤턴트 로딩 경로 오류로 인한 허위 무검출(위 12-4-J), (2) s2 E15d 기대값 갱신 중 문자열 치환 실수로 SyntaxError 발생 및 약한 단언(개행 유무만 확인) -> `chr(92)`를 이용해 "이스케이프된 `\n`이 로그에 있고 줄 수 1" 조건으로 강화, (3) h4/asyncio 일부가 클라이언트 자체 파서 거부(`CLIENT_REJECTED`)로 판정되는 것을 코드 결함이 아니라 별도 분류로 처리하고 결과서에 건수(매트릭스 4, s8 7) 고지, (4) pip cp949 디코드 실패(환경).

## 12-7. 테스트 환경 정리(Teardown) — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/venv_06_unit9c/`(venv), `.harness-tmp/db_06_unit9c.sqlite3`(dev runserver용 임시 SQLite). 서버 프로세스(runserver 19461, http.server 19463, listener 19464)는 모두 종료됨(`netstat`에 LISTEN 없음, 19463은 루프백 TIME_WAIT 잔여만 — OS가 자동 소멸). 스크립트는 스크래치패드(리포지토리 밖).
- 전부 `.harness-tmp/` 하위(또는 스크래치패드)에서만 생성 [x] / 자기가 만든 것만 정리 [x] (`rm -rf .harness-tmp/venv_06_unit9c .harness-tmp/db_06_unit9c.sqlite3`). 정리 후 `.harness-tmp/` = `_06_unit23b`, `venv_06_unit23b`(unit-23 소유, 무접촉), `run_local.log`, `venv_run_local`(오케스트레이터 소유, 무접촉). `webapp/db.sqlite3`(오케스트레이터 소유, mtime 이번 실행 이전) 무접촉, 포트 8000 서버 종료하지 않음.
- 강제 중단 없음 [x]
- 정리 후 `git status --short` 원문:
```
 M docs/harness/03-system-design.md          <- 03/오케스트레이터(설계 v5.1 정정), 이번 06 미수정
 M docs/harness/decisions.md                 <- 오케스트레이터 공유문서, 미수정
 M docs/harness/traceability.md              <- 오케스트레이터 공유문서, 미수정
 M docs/harness/units/unit-23-note.md        <- unit-23 소유
 M docs/harness/units/unit-9-note.md         <- unit-9 05 재작업 산출물
 M docs/harness/units/unit-9-test.md         <- 이 06(12절 추가, 배너 갱신)
 M docs/harness/verify-log_03-system-design.md <- 03단계 소유
 M docs/harness/verify-log_unit-9-test.md    <- 이 06(v2.2 회차 추가)
 M webapp/config/wsgi.py                     <- unit-9 이전 회차 변경(05), 이번 06 미수정
 M webapp/converter/ratelimit.py             <- unit-23 소유
 M webapp/core/net_guard.py                  <- unit-9 05 재작업(v2.2), 이번 06 미수정
?? docs/harness/units/unit-23-test.md        <- unit-23 소유
?? docs/harness/verify-log_unit-23-note.md   <- unit-23 소유
?? docs/harness/verify-log_unit-23-test.md   <- unit-23 소유
?? docs/harness/verify-log_unit-9-note.md    <- unit-9 05 산출물
```
  (주: 위 스냅샷은 이 결과서·검증 로그 최종 저장 직전의 원문이다. unit-9-test.md/verify-log는 이미 수정 표시 상태.) 이 06이 만든 임시 아티팩트·미추적 잔여물 없음. `__pycache__`는 `.gitignore` 대상.
- 규칙 K 충족: 예.

## 12-8. 리스크 및 잔존 이슈 (결함 아님, 근거 포함)
11절 R1~R12는 그대로 유효하며(R7 로그 인젝션은 **해소됨**: 아래 표), 이번 회차에서 확인·추가한 항목:
| ID | 내용 | 근거/성격 | 이관 |
|----|------|-----------|------|
| R7(갱신) | 로그 인젝션 **해소** — 개행/CR/NUL/ESC/유니코드 줄 구분자가 든 호스트가 `%r`로 이스케이프돼 단일 로그 줄, 예외 메시지도 동일 | G절 48+5건, 뮤턴트 M7a/b/c 검출 | 종결(09 참고 불필요) |
| R-Q1 | 허용 호스트명·`localhost`를 raw `sock.connect((name, port))`에 직접 넘기면 이름만으로 통과(파이썬에서 IP로 풀 수 없음). `/etc/hosts` 등이 `localhost`를 비루프백으로 매핑한 환경에서는 그 IP로 나갈 수 있음 | L-REMAP(raw) **스텁 실측**, getaddrinfo를 거치는 모든 표준 클라이언트 경로는 connect 단계 IP 검사로 차단됨(L-REMAP 7/7). 이 경로를 쓰는 표준 클라이언트 없음, DEC-043이 localhost 통과 확정 | DEC-046: **09단계** 사용자 질문 |
| R-Q4 | 허용 호스트(R2/DB)의 다중 후행 점·앞뒤 공백·탭/개행 변형은 `_normalize_host` 미변경으로 이름 게이트 통과. 엄격 리졸버 스텁에서 해석 실패 -> IP 미기록·IP 리터럴 connect 차단(Q4a/b/d), raw connect는 이름-only 통과(Q4c, R-Q1과 동일 성질). 신규 외부 목적지 없음(허용 호스트와 동일 IP로만 풀릴 수 있음). **실제 OS 리졸버 동작은 미측정** | H절. localhost는 엄격화됐고 허용 호스트는 무회귀 조건상 유지된 비대칭이 남음 | 05 Q4: 사용자 결정 필요(낮은 우선순위). 09 참고 |
| R-N1 | `getaddrinfo`에 비-str/bytes host(int, list, bytearray)를 넘기면 원본의 `TypeError` 대신 `AttributeError`/`TypeError`(가드 예외, 차단 아님). 기능상 취약점 없음(cosmetic) | s6 EXTRA, s8 INFO | R9와 병합, 09 참고 |
| R-N2 | asyncio·boto3·requests는 NUL/비ASCII bytes/이상 문자열을 가드 이전에 클라이언트가 거부(`CLIENT_REJECTED`, 매트릭스 4·s8 7건). 가드 유효성의 증거는 아니지만 접속 시도가 발생하지 않으므로 우회 아님 | 12-4-B/C | 참고 |
| R-N3 | 빈 문자열 host의 `getaddrinfo("")`는 `check_host_for_lookup`의 `if not host: return`으로 게이트를 통과한다(기존 동작, 이번 변경 아님). 이후 connect 단계 IP 검사가 결과 주소에 적용되므로 비루프백은 차단됨 — **빈 host의 실제 OS 해석 결과는 이번에 측정하지 않았음(미실측)** | 소스 대조(추론), connect(("",80))는 E05i에서 차단 확인 | 09 참고(낮음) |
| 유지 | R1(psycopg IP 리터럴 무가드), R2(UDP `sendto`), R3(C 확장/`_socket`, Windows Proactor 추론), R4(IP 공유 호스트), R5(DNS rebinding/IP 누적), R6(gethostbyname 등 미가드 리졸버), R8(INFO 로그 호스트명), R9(`[::1` ValueError 기동 중단), R11(Windows 단일 환경, AF_UNIX 시뮬레이션), R12(stale 참조) | 11절 근거 유지, 이번 회차 s2 E01~E14/E16, s3 malformed로 재확인 | 09/10~12단계 |
| DEC-040 | EMAIL_HOST 미허용 — **미결 유지 재확인**: net_guard가 참조하는 env 2개뿐, `smtplib` 비허용 호스트 실제 차단(E08). 허용목록 무변경 | s2 E08a/b | 09/10 착수 전 사용자 결정 |

## 12-9. 결론 및 판정
- [x] **PASS** — DEF-001·DEF-002 모두 Fixed(06이 독립 재현·검증), 신규 결함 0건. 근거: 매트릭스 210/210, localhost 정확 일치 368/368, Q3 로그/예외 이스케이프 실측 PASS, 실소켓 루프백 28/28, 엣지 71/71, wsgi 15/15, e2e 5/5, runserver 3/3, TC-001~018 회귀 PASS, 이번 변경 포함 뮤턴트 18/18 검출, 전 실행 2회 재현 동일, 실제 외부망 질의 0건. 의도된 검증 한계(Windows 단일 환경, AF_UNIX 시뮬레이션, 실제 리졸버 이상 이름 처리, Linux/Render 미검증)와 Q1·Q4·기타 리스크는 12-8에 명시.
- [ ] CONDITIONAL PASS / [ ] FAIL
- 07(통합) handoff 가능. 07이 알아야 할 점: 루프백/`localhost`는 getaddrinfo·connect 모두 정확 일치(대소문자·단일 후행 점·bytes)만 통과, 허용 IP 집합은 해석 시점에 채워지므로 "허용 호스트를 먼저 해석하지 않고 그 IP 리터럴로 connect"는 차단(E01a), 차단 로그/예외 메시지의 host는 repr 형태(`'...'`), 허용 호스트 정규화는 종전대로(Q4).

## 12-10. 내부 검증
- 1차/2차/3차 요약: `docs/harness/verify-log_unit-9-test.md` 「v2.2 재검증(3회차)」 절 참조. 검증 로그 파일 경로 동일.

## 12-11. 공유 문서 갱신 요청 (직접 수정하지 않음, 오케스트레이터 반영)
| 대상 | REQ-ID/DEC | 컬럼 | 값 |
|------|-----------|------|----|
| traceability.md | REQ-011 | 단위테스트(unit-n-test) | `unit-9-test.md 12절(v2.2 재검증 3회차) — PASS (DEF-001·DEF-002 Fixed, 신규 결함 0건, 매트릭스 210/210·localhost 368/368·실소켓 28/28·뮤턴트 18/18 검출; 잔존 리스크 Q1·Q4·DEC-040은 09단계/사용자 결정)` |
| traceability.md | REQ-011 | 비고(추가/갱신) | 로그 인젝션(구 R7) 해소(`%r`). 잔존: 허용 호스트명·localhost의 raw connect 이름-only 통과(Q1, 09), 허용 호스트 다중 후행 점·공백 변형 이름 게이트 통과(Q4, 사용자 결정 대기·외부 유출 없음 스텁 실측, 실제 리졸버 미측정), `getaddrinfo("")` 게이트 통과(미실측) |
| decisions.md | DEC-045 | 상태/결과 | 종결: DEF-002 Fixed(06 12절 검증) |
| decisions.md | DEC-046 | 상태/결과 | Q2·Q3 구현 검증 완료(06 12절). Q1은 09 이관 유지, Q4(허용 호스트 정규화 엄격화 여부)는 신규 사용자 결정 후보 |
| decisions.md | DEC-040 | 상태 | 미결 유지(재확인) |
