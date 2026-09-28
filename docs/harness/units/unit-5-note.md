# unit-5 구현 노트 — Feature A, HWPX 문단/텍스트 빌더 (05-unit-developer)

- 커버 REQ-ID: REQ-002(텍스트 추출 → HWPX 문단 변환), REQ-006(적용대상만 — 실제 NFC 정규화는 unit-15 소관, 이번엔 unit-1 원문 그대로 소비), REQ-008(HWPX 출력 호환)
- 소속: Feature A(코어 변환 파이프라인)
- 선행 단위: unit-1(`pdf_reader/text_extractor.py`, 완료·PASS), unit-4(`hwpx_kernel/schema.py`, 완료·PASS)
- 속도 트랙: **L3(일반)**
- **병렬 웨이브 호출**: 이 호출은 unit-6(`hwpx_writer/table_builder.py`)·unit-7(`hwpx_writer/image_embedder.py`) 05-unit-developer 호출과 동시에 실행됐다. 확정 파일 범위(`pdf_to_hwpx/hwpx_writer/paragraph_builder.py` 신규 1개)만 수정했고, `pdf_reader/ir.py`, `pdf_reader/text_extractor.py`, `hwpx_kernel/schema.py`, `hwpx_kernel/container.py`, unit-6/7 소유 파일(`table_builder.py`, `image_embedder.py`)은 전혀 건드리지 않았다.
- 선행 문서: `docs/harness/03-system-design.md`(v4 §1-3 unit-5 행 — v5는 웹서비스 계층만 다루고 이 파일 영역은 "단 한 줄도 수정하지 않는다"는 전제, v5 §1-1/§0-3 재확인), `docs/harness/02-planning.md` REQ-002/006/008, `unit-1-note.md`, `unit-4-note.md`

---

## 1. 구현 범위

### 1-1. 만든 함수/시그니처

`pdf_to_hwpx/hwpx_writer/paragraph_builder.py` (신규 파일, 이 파일만 수정):

```python
def build_paragraph_fragments(
    blocks: list[TextBlockIR],
    *,
    char_shape_id: str = "0",
    para_shape_id: str = "0",
) -> list[etree._Element]:
    """페이지 1개 분량의 TextBlockIR 목록을 <hp:p> 목록으로 변환한다."""
```

- 입력: unit-1의 `extract_text_blocks(page)`가 반환한 **페이지 1개 분량**의 `TextBlockIR` 목록(줄 단위, 줄 내부 x0 오름차순으로 이미 정렬된 상태).
- 출력: 입력과 같은 읽기 순서를 유지하는 `<hp:p>` 프래그먼트 목록. `hwpx_kernel.schema`의 계약 함수(`text_block_to_paragraph_fragment`)만 사용해서 만들며, `schema.py`/`container.py`는 import만 하고 수정하지 않았다.
- 내부 헬퍼(모두 비공개, `_` 접두): `_same_line`, `_group_to_paragraph`, `_has_visual_gap`, `_prepend_space`.

### 1-2. 설계서가 정하지 않은 부분 — 판단과 근거 (지시문에서 "규칙 A 질문 대상이 아니라 합리적으로 정하고 기록할 범위"로 명시한 항목들)

**(A) 그래뉼래러티 — TextBlockIR 1개 = 문단 1개가 아니라 "같은 줄" 그룹 = 문단 1개**

- `schema.text_block_to_paragraph_fragment`는 계약상 블록 1개당 문단 1개(run 1개)만 만드는 저수준 함수다(unit-4-note.md 2-2절). 그런데 unit-1은 "폰트/크기가 바뀌면 새 블록"으로 쪼개므로, 같은 시각적 줄이 폰트 변화 때문에 여러 `TextBlockIR`로 나뉘어 있다.
- 이 모듈은 인접한 두 블록의 bbox 세로 구간([top, bottom]) 겹침 비율이 임계값(`_LINE_OVERLAP_RATIO = 0.5`) 이상이면 "같은 줄"로 판정해 묶는다(`_same_line`). 이 값과 방식은 unit-1의 `_has_vertical_overlap`/`_LINE_OVERLAP_RATIO`(DEF-001 재작업에서 실측 검증됨 — 어센트/디센트 비대칭 때문에 `top` 단독 비교보다 안정적)를 그대로 재사용했다. 다만 unit-1은 임의의 word 전체를 클러스터링해야 했지만, 이 모듈의 입력은 이미 줄 단위로 정렬돼 있으므로 **인접한 두 블록끼리만** 비교하는 더 단순한 버전으로 구현했다(전수 재클러스터링은 이미 끝난 일을 다시 하는 과설계로 판단).
- **근거**: TextBlockIR 1개=문단 1개로 그대로 매핑하면 원래 한 줄이던 텍스트가 폰트가 바뀔 때마다 별도 문단(줄바꿈)으로 쪼개져 과도한 줄바꿈이 생긴다(지시문이 지적한 문제 그대로). "같은 줄 = 문단 1개"로 복원하는 것이 REQ-002(서식 보존)와 REQ-008(정상적인 문서 구조) 양쪽에 더 부합한다고 판단했다.
- **하지 않은 것**: 여러 "줄"을 하나의 논리적 문단(단락)으로 합치는 것(줄바꿈 vs 문단 구분)은 시도하지 않았다 — 03 설계서가 요구하지 않고, 신뢰할 근거(줄 간격/들여쓰기 분석 등) 없이 시도하면 과설계라고 판단했다. 즉 이 모듈의 최종 결과는 "1 시각적 줄 = 1 `<hp:p>`"다.

**(B) `schema.py`가 "여러 run을 가진 문단 1개"를 만드는 함수를 제공하지 않는 문제 — 공유 자원 이슈로 보고 (schema.py 미수정)**

- 실제로 이 간극을 발견했다. `schema.py`를 고치지 않고, 대신 병합 대상 각 블록마다 `text_block_to_paragraph_fragment()`를 개별 호출해 만들어진 임시 `<hp:p>`에서 `<hp:run>` 자식만 꺼내(`extra[0]`) 첫 블록의 `<hp:p>`에 `append`로 이어 붙였다. lxml은 이미 다른 트리에 속한 엘리먼트를 `append`할 때 자동으로 원래 부모에서 떼어내 옮기므로, run 내부의 굵기/기울임/폰트명/크기/텍스트 조립 로직은 전부 `schema.py`가 그대로 수행한 결과를 재사용할 뿐, 이 모듈이 그 로직을 중복 구현하지 않는다.
- **이것은 임시방편이며, `schema.py` 확장이 필요한 공유 자원 이슈로 아래 "공유 문서 갱신 요청"에 남긴다** — 지시문이 명시한 대로 `schema.py`를 직접 고치지 않았다.

**(C) 배치 방식 — 절대 좌표 배치가 아니라 순차 흐름형(inline flow)**

- bbox(pt)를 HWPUNIT으로 변환해 고정 위치에 배치하는 방식은 채택하지 않았다. 대신 문단을 읽기 순서(입력 목록 순서) 그대로 흐름형으로 두고, bbox는 병합된 블록들의 합집합을 `bboxPt` 속성(디버깅/추후 정밀 배치용, schema.py가 이미 정의한 관례)으로만 남긴다.
- **근거**: (1) 03 §1-1(v4/v5 공통)이 `pdf_to_hwpx`를 "상태 없는 순수 변환 라이브러리"로 규정하고 있고, (2) `schema.py`(unit-4, 공용 계약)가 절대 위치 지정에 필요한 필드/속성을 애초에 정의하지 않았다(그런 속성을 이 unit이 임의로 새로 발명하면 계약 확장이 되어 schema.py 수정 없이는 불가능하거나, schema.py를 우회해 별도 XML 속성을 즉석으로 만드는 것이 되어 더 큰 임의 결정이 된다). (3) REQ-008이 다루는 "세로 위치 오차(6-6)"는 이미 schema.py 단계에서 "확정 안 된 리스크"로 명시돼 있다(unit-4-note.md 1절, DEC-017) — 이 unit이 그 불확실성을 추가로 해결할 근거나 도구가 없는 상태에서 임의로 좌표 고정 배치를 시도하면 오히려 검증되지 않은 가정을 하나 더 쌓는 것이 된다.
- **한계(그대로 기록)**: 페이지 레이아웃(다단, 정밀 세로 위치)은 이 방식으로 보존되지 않는다 — 텍스트는 순서대로 나열되지만 원본 PDF의 정확한 x/y 좌표는 문서에 반영되지 않는다. REQ-008 6-6(세로 위치 오차)에 대한 최종 검증/개선은 이후 unit(schema.py 확장 또는 별도 unit)의 몫으로 남는다.

**(D) 병합 시 텍스트 사이 공백 — bbox 가로 간격 기준으로 판단**

- unit-1은 같은 (폰트명, 크기) 구간의 word들만 공백으로 join하고, 폰트가 바뀌는 지점(=이 모듈이 다시 합치는 블록 경계)에서는 원래 있었을 공백 문자를 전혀 보존하지 않는다(word 자체가 공백을 포함하지 않으므로). 이 사실을 로컬 검증에서 실제로 확인했다(2절 참고) — 아무 처리도 안 하면 "Hello **World**"가 "HelloWorld"로 붙어버리는 텍스트 손상이 생긴다.
- 처리: 두 블록의 bbox 사이에 양(+)의 가로 간격이 있으면(`curr.bbox[0] - prev.bbox[2] > 0`) 원래 단어 경계였다고 보고 공백 1개를 삽입한다. 간격이 0 이하(맞닿거나 겹침)면 스타일 변화가 한 단어 내부에서 일어난 것으로 보고 공백을 넣지 않는다.
- **한계(그대로 기록)**: 실제 단어 사이 공백 폭과 무관하게 "간격이 있으면 공백 1개"로 단순화했다 — 03 설계서에 근거 수치가 없어 합리적으로 정한 값이다. 매우 드물게 스타일이 단어 중간에서 바뀌면서도 시각적으로 살짝 간격이 있는 폰트(커닝 등)라면 불필요한 공백이 삽입될 수 있다.

### 1-3. REQ-006 비적용 재확인

- `TextBlockIR.text`를 있는 그대로 소비한다. NFC 정규화는 수행하지 않는다 — unit-15(`hangul_normalizer`, 아직 Not Started)의 책임이며, 이 unit은 그 정규화 이전 단계의 원문을 받아 그대로 문단으로 옮기는 역할만 한다.

### 1-4. 호출 규약 — 페이지 경계 (unit-8에게 인계할 제약)

- 이 함수는 인접한 두 블록의 bbox 세로 겹침으로 "같은 줄"을 판정하므로 **같은 페이지 안에서만** 유효하다. 서로 다른 페이지의 블록을 한 호출에 섞으면 각 페이지가 독립 좌표계(0,0 기준)를 가져 다른 페이지의 줄을 같은 줄로 잘못 묶을 위험이 있다. 따라서 오케스트레이터(unit-8, 아직 Not Started)는 **페이지마다 이 함수를 한 번씩 호출**하고 반환된 목록들을 페이지 순서대로 이어 붙여야 한다(페이지 구분 표현 자체는 이 함수의 책임이 아니며, 모듈 docstring에도 명시했다).

---

## 2. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`)이 여전히 없음을 재확인했다(`pyproject.toml`에 grep — 없음, 있는데 건너뛴 것 아님).
- `python -m py_compile pdf_to_hwpx/hwpx_writer/paragraph_builder.py` — **컴파일 성공**.
- 병렬 웨이브 중 다른 unit(6/7)의 미완성 코드로 인한 실행 실패: 이 모듈은 `table_builder.py`/`image_embedder.py`를 import하지 않으므로 컴파일/실행에 영향 없음. `pdf_to_hwpx.hwpx_kernel.schema`, `pdf_to_hwpx.pdf_reader.ir`(둘 다 이미 완료·PASS 상태, 이번 웨이브 대상 아님)만 import했다.
- 신규 외부 의존성 없음. `lxml`은 unit-4가 이미 `pyproject.toml`에 등록해 둔 기존 의존성을 import만 했다(매니페스트 미접촉).

## 3. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 v4 §1-3 unit-5 행("HWPX 문단/텍스트 빌더", 선행 unit-1/unit-4)과 REQ-002/006/008을 그대로 따랐다. 설계서가 명시하지 않은 그래뉼래러티/배치방식/공백처리는 1-2절에 근거와 함께 기록했다.
- [x] 에러 처리가 누락된 경로가 없는가 — 이 모듈에 예외를 삼키거나 무시하는 코드가 없다. `blocks`가 빈 리스트면 즉시 `[]`를 반환(정상 경로, 예외 아님). `schema.text_block_to_paragraph_fragment` 호출이 실패(예: 잘못된 bbox 타입)하면 그대로 전파한다 — 이 unit이 별도로 감싸는 것은 설계서(03 §4-2 예외계층)에 근거가 없어 임의로 추가하지 않았다. orchestrator(unit-8) 레벨의 최상위 방어선이 이를 흡수하는 구조(unit-1-note.md와 동일한 패턴)를 그대로 따랐다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 모듈의 입력은 사용자 입력이 아니라 unit-1이 이미 만든 `TextBlockIR`(내부 계약 데이터)이므로, 시스템 경계 검증은 이미 상위 단계(PDF 로딩·추출)에서 수행됐다는 전제다. 이 모듈 내부에서는 빈 리스트/그룹 크기 1 같은 경계 케이스를 코드 흐름으로 자연스럽게 처리한다(방어적 분기 불필요).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 XML 조립 로직).
- [x] 새로 추가한 외부 의존성이 실제 존재하는지 확인 — 신규 의존성 추가 없음(위 2절 참고).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/hwpx_writer/paragraph_builder.py` 1개 파일만 신규 생성했다. `hwpx_writer/__init__.py`(unit-0이 만든 placeholder, "unit-5/6/7 소관, 아직 생성되지 않음"이라는 stale docstring이 있음)는 이번 unit의 확정 파일 범위 밖이라 수정하지 않았다(unit-4가 `hwpx_kernel/__init__.py`에 대해 취한 것과 동일한 판단 — 3절 참고, 후속 정리 제안만 남김). `ir.py`/`text_extractor.py`/`schema.py`/`container.py`/`table_builder.py`/`image_embedder.py` 어떤 파일도 건드리지 않았다.

## 4. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

프로젝트에 이미 설치돼 있는 `lxml`/의존성을 그대로 사용해(신규 설치 불필요, 별도 venv 생성 없음 — 병렬 규칙상 임시 아티팩트도 만들지 않았으므로 `unit5` 식별자 디렉터리 생성 자체가 필요 없었음) 스크래치패드에서 검증 스크립트를 실행한 뒤 즉시 삭제했다. 확인한 항목:

1. **같은 줄, 폰트 2종(굵게 아님 → 굵게) + 시각적 간격 있는 블록 2개** ("Hello"/"World", bbox가 가로로 떨어져 있음) → `build_paragraph_fragments`가 **문단 1개, run 2개**를 반환. 두 번째 run의 텍스트가 `" World"`(공백 삽입 확인)이고 `bold="1"` 속성이 유지됨을 확인. 병합된 문단의 `bboxPt`가 두 블록의 합집합(`"10.00,100.00,80.00,112.00"`)으로 정확히 계산됨을 확인.
2. **같은 목록에 다른 세로 위치(다른 줄)의 블록 1개**("다음 줄입니다", 한글 포함) 추가 → 별도 문단(총 2개 문단)으로 분리됨을 확인, run 1개.
3. 생성된 모든 프래그먼트를 `etree.tostring()` → `etree.fromstring()`으로 왕복시켜 **well-formed XML**임을 확인(파싱 에러 없음, 로컬 이름이 `p`로 완전한정됨).
4. `build_paragraph_fragments([])`가 예외 없이 `[]`를 반환함을 확인.

모든 항목 의도대로 동작 확인. 검증 스크립트(`unit5_verify.py`)는 스크래치패드에만 작성했고 확인 후 삭제했다(리포지토리에 남기지 않음). `git status --short` 결과 이 unit이 건드린 파일이 `pdf_to_hwpx/hwpx_writer/paragraph_builder.py` 1개뿐임을 확인했다.

---

## 5. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 변환
1. 비어있지 않은 `list[TextBlockIR]`을 넣으면 `build_paragraph_fragments`가 비어있지 않은 `list[etree._Element]`를 반환한다. 각 원소의 로컬 이름은 `p`이고 네임스페이스는 `{http://www.hancom.co.kr/hwpml/2011/paragraph}p`다.
2. 빈 리스트를 넣으면 예외 없이 정확히 `[]`를 반환한다.
3. 반환된 문단 목록의 순서는 입력 블록 목록의 순서(읽기 순서)를 그대로 보존한다.

### AC-2. 줄 병합(그래뉼래러티)
4. bbox의 세로 구간이 충분히 겹치는(겹침 비율 ≥ 0.5) 인접 블록 2개 이상을 넣으면, 결과는 **문단 1개**이며 그 문단의 `<hp:run>` 자식 개수는 입력 블록 개수와 같다.
5. 각 run은 자신이 유래한 블록의 `bold`/`italic`/`font_name`/`font_size`/`text` 속성을 그대로 반영한다(schema.py 계약과 동일한 방식 — `bold="1"`, `italic="1"`, `fontName`, `fontSizeHwpunit`, `<hp:t>` 텍스트).
6. bbox 세로 구간이 겹치지 않는 블록은 별도의 `<hp:p>`로 분리된다.
7. 병합된 문단의 `bboxPt` 속성은 `"x0,y0,x1,y1"`(소수점 2자리) 형식이며, 그 그룹에 속한 모든 블록 bbox의 합집합(`min(x0)`, `min(y0)`, `max(x1)`, `max(y1)`)과 일치한다.

### AC-3. 공백 보존 (텍스트 무결성)
8. 같은 줄로 병합되는 두 블록 사이에 bbox 가로 간격이 있으면(`다음 블록.bbox[0] > 이전 블록.bbox[2]`), 두 번째 이후 run의 텍스트 앞에 공백 1개(`" "`)가 삽입된다.
9. 두 블록의 bbox가 가로로 맞닿아 있거나 겹치면(간격 ≤ 0) 공백이 삽입되지 않는다.

### AC-4. REQ-006 비적용
10. 입력 `TextBlockIR.text`에 NFC/NFD가 섞여 있어도 이 함수는 정규화를 수행하지 않고 그대로(공백 삽입 로직 제외) 문단에 옮긴다 — 6단계는 이 함수 자체를 NFC 정규화 여부로 테스트하지 말 것(그 책임은 unit-15, 현재 Not Started).

### AC-5. XML 유효성 / 안정성
11. 반환된 모든 `<hp:p>` 프래그먼트는 `lxml.etree.tostring()` → `etree.fromstring()` 왕복이 예외 없이 성공한다(well-formed XML).
12. 이 함수는 입력 `blocks`(및 그 원소들)를 변경하지 않는다(같은 입력으로 여러 번 호출해도 결과가 동일) — 단, `schema.text_block_to_paragraph_fragment`가 만든 **임시 프래그먼트**(run을 꺼내고 남은 빈 `<hp:p>` 껍데기)는 버려지므로 그 부분까지 검사할 필요는 없다.
13. **호출 규약(6단계가 통합테스트에서 반드시 지켜야 함)**: 서로 다른 페이지의 `TextBlockIR`를 한 호출에 섞지 말 것 — 페이지마다 별도로 호출하고 결과 리스트를 이어 붙여야 한다(1-4절 근거). 여러 페이지를 한 호출에 섞어 테스트하면 페이지 경계에서 줄 오판정이 발생할 수 있으며, 이는 이 함수의 결함이 아니라 잘못된 호출 방식으로 취급해야 한다.

### AC-6. 알려진 한계 (실패로 취급하지 말 것)
14. 다단(멀티컬럼) 레이아웃에서 같은 세로 구간에 있는 다른 컬럼의 블록이 같은 줄로 잘못 병합될 수 있다(unit-1로부터 물려받은 한계, 1-2-A절).
15. 텍스트는 순차 흐름형으로만 배치되며 원본 PDF의 절대 x/y 좌표(정밀 세로 위치, REQ-008 6-6)는 문서에 반영되지 않는다(1-2-C절 근거) — `bboxPt` 속성으로만 참고 가능.
16. 스타일이 단어 중간에서 바뀌면서도 시각적으로 살짝 간격이 있는 폰트(커닝 등)의 경우 불필요한 공백이 삽입될 수 있다(1-2-D절).

---

## 6. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 일괄 반영)

### traceability.md

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-002 | 작업 단위 | unit-1, unit-5 |
| REQ-002 | 구현 상태 | Implemented (unit-5, `hwpx_writer/paragraph_builder.py` — `build_paragraph_fragments()`. 05단계 완료, 06단계 단위테스트 대기. unit-1이 만든 TextBlockIR을 소비해 같은 줄 블록을 문단 1개로 병합) |
| REQ-006 | 작업 단위 | unit-1(입력 생성만), unit-5(입력 그대로 소비, 정규화 미수행), unit-15(정규화 자체, Not Started) |
| REQ-006 | 구현 상태 | Partially Implemented (unit-5는 unit-1 원문을 재정규화 없이 그대로 문단화 완료, 05단계 완료/06단계 대기 — 실제 NFC 정규화는 여전히 unit-15 미착수) |
| REQ-008 | 작업 단위 | unit-4(컨테이너 골격/공용 계약), unit-5(문단 빌더) |
| REQ-008 | 구현 상태 | Implemented (unit-5, 문단 조립 부분. 05단계 완료, 06단계 단위테스트 대기 — 단, 세로 위치 정밀 배치(6-6)는 이번 unit이 흐름형 배치로 유보했고, 실제 한컴오피스 호환은 unit-4-note.md DEC-017 미검증 리스크가 여전히 유효함. unit-6/7 통합(unit-8) 이후 종합 검증 필요) |

### decisions.md

- 신규 DEC 추가는 오케스트레이터 판단에 맡기되, 아래 사실은 기록 후보로 제안한다: **"`hwpx_kernel/schema.py`는 현재 블록 1개당 run 1개짜리 문단만 만드는 저수준 계약이며, 여러 run을 가진 문단(같은 줄, 스타일 혼합)을 만드는 기능은 unit-5(`paragraph_builder.py`)가 schema.py 외부에서 run을 재조립하는 방식으로 임시 해결했다. `schema.py`가 이 기능을 1급 계약으로 흡수해야 하는지(즉 `SCHEMA_VERSION`을 올려 `text_blocks_to_paragraph_fragment(blocks: list[TextBlockIR]) -> etree._Element` 같은 다중-run 버전을 추가할지)는 unit-4 소유자(또는 unit-6/7이 유사한 패턴이 필요한지 확인 후)의 판단이 필요한 공유 자원 이슈다."**
- unit-6(표)도 "셀 내 여러 문단/여러 run" 필요성이 있는지(unit-4-note.md 2-2절 "현재는 셀당 문단 1개로 단순화") 함께 검토하면, `schema.py` 확장을 한 번에 처리할 수 있어 효율적일 것으로 보인다(강제 아님, 참고 제안).

### 기타 후속 조치 제안(강제 아님, 참고용)

- `pdf_to_hwpx/hwpx_writer/__init__.py`의 stale docstring("unit-5/6/7 소관, 아직 생성되지 않음")이 이제 사실과 다르다(unit-5/6/7이 모두 이번 웨이브에서 생성됨). 이 unit의 확정 파일 범위 밖이라 직접 수정하지 않았다 — 다음 정리 단위 또는 unit-8 착수 전에 갱신 권장.
