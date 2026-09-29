# 내부 검증 로그 (Internal Verification Log)

## 대상 산출물
- 파일: `webapp/converter/cleanup.py`, `docs/harness/units/unit-22-note.md`(R절, DEF-020c-01 / DEC-063)
- 작성 에이전트: 05(구현) / Tier: Standard / 버전: v2 (재작업)

## 1차 검증 (작성자 관점)
- 일시: 2026-09-29
  - [x] 계약 반영: EXPIRED + purged_at NULL + 생성 70분 경과만 대상, 삭제+purged_at, 멱등
  - [x] 수정 전(HEAD)/후 대조 실측: 전 FAIL 2(고아) -> 후 FAILS 0
  - [x] 방금 만든 예약(1분)·유예 구간(65분) 보존, 이미 purged 행 무변경, 삭제 실패 후 재시도, 배치 합계 20 확인
- 발견 결함: 검증 스크립트의 "로그 파일명 미포함" 항목이 `or True`로 실질 검증이 아니었음. 조치: note에는 근거를 "스토리지 키가 UUID 기반, 로그는 job_id만"으로 정정 기재하고 해당 항목을 실측 PASS 주장에서 제외.

## 2차 검증 (독립 심사자 관점)
- 일시: 2026-09-29
  - [x] 경쟁: 조회~UPDATE 사이 PENDING 승격 시 조건부 UPDATE가 무변경 (훅 주입으로 실측). 단 오브젝트 삭제는 UPDATE 이전이라 이 경쟁은 70분 이상 경과 행에서만 이론상 가능 -> 실사용 불가
  - [x] 기존 경로 회귀 없음: 일반 대상 UPDATE 로직 동일(90분 DONE 정리 PASS)
  - [x] 부하: 스윕당 쿼리 최대 2 + LIMIT 20, 쿨다운/락 무변경
  - [x] 범위: cleanup.py만 수정, views.py 등 금지 파일 미접촉, dev 서버 자원 미접촉, egg-info 없음, .harness-tmp/_05_unit22b 삭제
  - 잔여: 뷰에 예약 TTL 상수 부재(질문 Q-1), 일반 대상 상시 20건 초과 시 고아 이월
