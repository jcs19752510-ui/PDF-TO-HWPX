# 내부 검증 로그 (Internal Verification Log)

## 대상 산출물
- 파일: `pdf_to_hwpx/hwpx_kernel/{__init__,constants,context,styles,fonts,flow,schema,section,container}.py`, `pdf_to_hwpx/common/exceptions.py`(예외 1개 추가), `tests/hwpx_kernel/*`, `tools/hwpx_probe.py`, `docs/harness/units/unit-4R-note.md` (05단계, unit-4R, DEC-051/055~062)
- 작성 에이전트: 05(구현)
- 적용 Tier: High (한글 수용이 걸린 핵심 산출물 계층)
- 버전: v1

## 1차 검증 (작성자 관점 자가 재검토)
- 검증자(역할): 05단계 작성자 본인
- 일시: 2026-09-29
- 체크리스트
  - [x] 입력 계약 반영: 03 v5.2 §1-4/§2-4/§3-3/§3-4, 분석서 【관찰】 항목, DEC-051/055~062, 범위 표(unit-4R 행)의 파일만 수정
  - [x] 출력 계약: unit-4R-note.md에 범위/편차/수동 확인/AC/트랙/공유문서 요청/git status 포함
  - [x] 상위 산출물과 모순 없음: 발행 어휘가 분석서 관찰 어휘의 부분집합임을 로컬 구조 비교로 확인(프로브 P1a/P2/P3/P4b의 header/section/hpf/version/settings/container/manifest 전 파트에서 "R1에 없는 요소 경로 0건, R1에 없는 속성 0건")
  - [x] 추측 없음: 분석서에 값이 없던 구조 값(charPr 하위 속성 기본값, paraPr breakSetting, numbering paraHead, tabPr, typeInfo, settings 항목, secPr 자식 값, hpf date 형식)은 R1을 로컬에서 읽어 구조 값만 확인. 본문/제목/고유명사 미복사. 미관찰 요소(그림, italic, 가로 용지, pageNum, 바탕쪽)는 구현하지 않음
  - [x] 구조적 결함 점검: 최초 실행에서 테스트 작성 오류 3건 발견 -> 코드 결함 아님(xmlns 개수 계산이 URN 안의 `xmlns:` 문자열까지 센 것, 들여쓰기 양자화 기대값 계산 오류, 여백 클램프 기대 산식 오류). 소프트 한도 테스트 기대값도 산식 오류(코드 무관). 수정 후 132 PASS
  - [x] 오탈자/형식 점검, ruff(주변 설정) 통과
- 발견된 결함 목록:
  1. (코드) `HwpxPackage._entries`의 `assert`는 `python -O`에서 제거됨 -> 명시적 예외로 교체
  2. (코드) 빈 구역 폴백 문단에 linesegarray 없음(R1은 항상 존재) -> lineseg 1개 추가
  3. (테스트) 위 4건 기대값/계산 오류
- 조치 내용: 위 1, 2 코드 수정, 3 테스트 수정 후 재실행 132 PASS

## 2차 검증 (독립 심사자 관점 — 역할 전환 재검토)
- 검증자(역할): 독립 심사자(한글 수용 위험 + 범위 준수 + 기밀 관점)
- 일시: 2026-09-29
- 체크리스트
  - [x] 1차 지적 반영 확인: assert 제거, 빈 문단 lineseg 확인(test_build_section_xml_empty_makes_paragraph_with_lineseg)
  - [x] 엣지 케이스: 5000 문단 문서(0.29s, paraPr 200/charPr 40 interning), 이모지/서로게이트/NUL 문자 텍스트, 빈 텍스트 셀, 병합 셀 그리드 오류 6종, secCnt 불일치, 손상 header, 쓰기 실패(부모가 파일), 기존 파일 덮어쓰기, 결정성(고정 메타로 바이트 동일)
  - [x] 다음 단계 에이전트가 추가 질문 없이 착수 가능: 5R/6R이 쓸 API 계약(make_paragraph/make_run/make_lineseg/make_table/make_table_cell, StyleRegistry, FlowTracker, PageSetup, build_section_xml, HwpxPackage)이 note 3절에 시그니처와 함께 정리됨
  - [x] 비가역 결정 근거: create_system/external_attr, version 기본값, P2~P4의 version 고정은 모두 가역이며 【미확인】/실험 대기로 note에 표기
  - [x] 보안/운영 위험: 외부 입력이 XML로 들어가는 경로는 텍스트(sanitize_text로 XML 금지 문자 제거+lxml 이스케이프)와 열거형/정규식 검증된 속성뿐. zip 엔트리 이름은 상수. 하드코딩 시크릿 없음. 신규 의존성 없음(lxml 기존)
  - [x] 기밀: 코드/테스트/note/로그에 R1의 본문/제목/고유명사/수치 없음(테스트는 R1을 열지 않음). 임시 스크립트와 덤프는 `.harness-tmp/_05_unit4R/`에서 작성 후 삭제
  - [x] 범위 준수: hwpx_writer/core/webapp/pdf_reader/설계서/traceability/decisions/tests/conftest.py 미수정. unit-27 파일 미접촉·미 import
- 발견된 결함 목록:
  1. (프로세스) `git rm` 시도가 권한 정책으로 거부됨 -> 삭제 대신 `test_container_bin_data.py`를 새 내용으로 덮어써 "전면 교체"를 달성, 파일명 정리는 오케스트레이터에 요청
  2. (구조 위험, 코드로 해결 불가) 초집합이어도 한글 수용 여부는 자동 검증 불가 -> 정직하게 "G1 대기"로 표기(PASS 선언 금지)
- 조치 내용: 1은 note 6절에 기록, 2는 note의 AC-H1 대기 항목으로 명시

## 결론
- 결함 잔존: 코드 결함 0건 (게이트 1·2 통과), 단 AC-H1(사용자 한글 확인)은 미수행 상태로 **G1 대기**
