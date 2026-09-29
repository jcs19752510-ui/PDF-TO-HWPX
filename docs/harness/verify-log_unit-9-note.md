# 내부 검증 로그 (Internal Verification Log)

## 대상 산출물
- 파일: `webapp/core/net_guard.py`, `webapp/config/wsgi.py`, `docs/harness/units/unit-9-note.md` (05단계 재작업, 규칙 F / DEF-001)
- 작성 에이전트: 05(구현)
- 적용 Tier: High
- 버전: v2 (재작업)

## 1차 검증 (작성자 관점 자가 재검토)
- 검증자(역할): 05단계 작성자 본인
- 일시: 2026-09-29
- 체크리스트
  - [x] 입력 계약 반영: 06 결과서 6절/9절 및 사용자 확정 3항목(DEF-001, TC-013 fail-closed, psycopg/DEC-040 유지) 전부 반영
  - [x] 출력 계약: note 10절(변경/근거/편차/게이트/실측/인수조건/공유문서 요청/git status) 작성
  - [x] 상위 산출물과 모순 없음: 03 §6-3(화이트리스트, 로깅), DEC-033 유지. v1 서술과 충돌하는 부분은 10절이 우선한다고 명시
  - [x] 추측 없음: dev 모듈명은 settings/dev.py 실물로 확인, boto3/requests/urllib3/urllib.request/http.client 전부 실측
  - [x] 구조적 결함 점검: 최초 실측에서 테스트 스크립트 결함 2건(스텁 호스트 정규화 누락, http.client IPv6 인자 형식)을 발견 -> 코드 결함이 아닌 테스트 문제로 판별, 수정 후 45/45 PASS
  - [x] 오탈자/형식 점검
- 발견된 결함 목록:
  1. 테스트 스크립트의 스텁 호스트 정규화 누락(코드 무관) -> 수정
  2. http.client 테스트의 IPv6 host 인자 형식 오류(코드 무관) -> 수정
- 조치 내용: 테스트 스크립트 수정 후 재실행 -> 결함 0건

## 2차 검증 (독립 심사자 관점 — 역할 전환 재검토)
- 검증자(역할): 독립 보안 심사자(우회 가능성 위주)
- 일시: 2026-09-29
- 체크리스트
  - [x] 1차 지적 반영 확인: 재실행 45/45 PASS, idempotent OK
  - [x] 엣지 케이스: IPv6 4-tuple, IPv4-mapped, zone id 정규화, 대소문자/후행 점, bytes host, 비튜플 주소(fail-closed), 허용 IP 인접 주소 차단, 재설치, SSLSocket 상속 경로(requests/boto3 HTTPS), connect_ex 경로
  - [x] 다음 단계 에이전트가 추가 질문 없이 착수 가능: note 10-7에 06 재테스트 인수 조건 명시
  - [x] 비가역 결정 근거: 패치 지점 선택 근거와 기각 대안(urllib3 내부 패치)을 10-2에 기록. 루프백 통과는 가역이며 사용자 확인 요청으로 표기
  - [x] 보안/운영 위험: 잔존 우회(psycopg C 확장, UDP sendto, IP 공유 호스트의 IP 리터럴)를 docstring과 note에 문서화. dev 판정 fail-closed는 9개 값으로 실측
- 발견된 결함 목록:
  1. 없음
- 조치 내용: 해당 없음

## [재작업 2 / DEF-002] 1차 검증 (작성자 관점)
- 일시: 2026-09-29
- [x] 입력 계약: 06 재검증 DEF-002, DEC-045, 설계 v5.1 localhost 통과와 일치
- [x] 변경 범위: check_address 1줄, 기존 정규화 재사용
- [x] 스텁 기반 107단언 ALL OK (raw connect/connect_ex localhost 통과, 접미사/유니코드/개행/널 문자 차단, 회귀 매트릭스)
- 발견: 최초 실행에서 20건 FAIL -> 원인은 테스트 스텁이 IP 리터럴 getaddrinfo를 거부한 것(코드 무관), 스텁 수정 후 0건
- 결함: 코드 결함 0건

## [재작업 2 / DEF-002] 2차 검증 (독립 보안 심사자 관점)
- 일시: 2026-09-29
- [x] 우회 관점: 정확 일치만 통과함을 접미사/접두사/키릴/전각/유니코드 마침표/공백/개행/널/zone id/포트 문자열로 확인, DNS leak 0
- [x] localhost가 203.0.113.50으로 풀리는 환경에서 create_connection/urllib.request/http.client/requests가 connect에서 차단
- [x] 재실행 107단언 ALL OK, py_compile 성공
- 잔여(기존/범위 밖, note 11-3에 질문으로 기록): raw connect 호스트명 직접 전달 시 이름 통과, strip/다중 점 정규화, 로그 개행 미이스케이프
- 결함: 0건, 조치 없음

## [재작업 3 / Q2, Q3] 1차 검증 (작성자 관점)
- 일시: 2026-09-29
- [x] 승인 범위 일치: Q2 localhost 엄격 비교, Q3 %r 이스케이프, Q1 미변경
- [x] `_normalize_host` 미변경(허용 호스트 무회귀), localhost 분기만 `_is_localhost`
- [x] 268 단언 ALL OK. 첫 시도에서 테스트 스크립트 문자열 이스케이프 오류로 FAIL 2건 발생 -> 코드 무관, 스크립트 수정
- 코드 결함 0건

## [재작업 3 / Q2, Q3] 2차 검증 (독립 보안 심사자 관점)
- 일시: 2026-09-29
- [x] 우회: 공백/탭/개행/CRLF/다중 점/키릴/전각 변형 차단, DNS leak 0, bytes와 단일 점만 통과
- [x] 로그 인젝션: 로그 전 라인 `net_guard:` 접두 단일 라인, 예외 메시지 단일 라인이며 허용목록/환경변수 값 미노출
- [x] 재실행 268 단언 ALL OK, py_compile 성공
- 잔여: Q4(허용 호스트 다중 점/공백 변형 통과, 사용자 결정 필요), Q1 09단계 이관
- 결함 0건

## [재작업 3] 최종 판정
- [x] PASS (최소 2회 검증 완료) - 06 재검증 handoff 가능

## [재작업 2] 최종 판정
- [x] PASS (최소 2회 검증 완료) - 06 재검증 handoff 가능

## 최종 판정
- [x] PASS (결함 0건, 최소 2회 검증 완료) — 다음 단계(06 재테스트)로 handoff 가능
