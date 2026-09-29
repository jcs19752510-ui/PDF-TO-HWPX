# 테스트 결과서 (Test Result Report)

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
