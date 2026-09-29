# unit-1 구현 노트 — Feature A, 텍스트 추출 (05-unit-developer)

- 커버 REQ-ID: REQ-002(텍스트 추출), REQ-006(적용대상만 — 실제 NFC 정규화는 unit-15 소관), REQ-007(ToUnicode 매핑 누락 대응)
- 소속: Feature A (PDF 판독 계열)
- 선행 단위: unit-0 (완료, PASS)
- 속도 트랙: **L3(일반)**
- **병렬 웨이브 호출**: 이 호출은 unit-2/unit-3/unit-4와 동시에 실행된 05-unit-developer 병렬 웨이브의 일부다. 확정 파일 범위(`pdf_to_hwpx/pdf_reader/text_extractor.py`) 밖 파일(`ir.py`, `loader.py` 등)은 전혀 수정하지 않았다.
- 선행 문서: `docs/harness/03-system-design.md`(§1-3 unit-1 행, §3-1 IR 정의, §4-2 예외계층), `docs/harness/02-planning.md`(REQ-002/006/007)

---

## 1. 구현 범위

### 1-1. 만든 함수/시그니처

`pdf_to_hwpx/pdf_reader/text_extractor.py` (신규 파일, 이 파일만 수정):

```python
def extract_text_blocks(plumber_page: pdfplumber.page.Page) -> list[TextBlockIR]:
    """pdfplumber 페이지 객체 하나에서 TextBlockIR 목록을 만든다."""
```

- 입력: `PdfDocument.plumber_pdf.pages[i]` (unit-0의 `PdfDocument`가 소유한 pdfplumber 페이지 객체). `ir.py`(오케스트레이터가 이미 생성해 둔 공용 IR 계약)에서 `TextBlockIR`을 import해서 그대로 사용했고, `ir.py` 자체는 수정하지 않았다.
- 출력: 그 페이지의 `TextBlockIR` 목록. 호출자(orchestrator, unit-8로 추정)가 페이지를 순회하며 이 함수를 호출해 `PageIR.text_blocks`를 채우는 구조를 가정했다(설계서에 호출자 쪽 코드가 아직 없어 이 가정을 note에 명시함).
- 내부 헬퍼(모두 비공개, `_` 접두): `_group_words_into_lines`, `_line_words_to_blocks`, `_build_block`, `_sanitize_text`, `_is_missing_char`, `_is_bold`, `_is_italic`.

### 1-2. 블록 구성 방식 (설계서가 시그니처/그래뉼래러티를 명시하지 않아 합리적으로 결정)

03 §1-3 unit-1 행은 "pdfplumber의 문자/단어/라인 단위 정보를 최대한 활용"이라고만 하고 `TextBlockIR` 하나가 문자/단어/줄 중 어느 단위에 대응해야 하는지는 명시하지 않았다. 두 가지 이상의 구현 방법이 갈리는 지점이었지만, 규칙 A 질문 대상이라기보다는 "합리적으로 정하고 note에 명시하라"는 이번 호출 지시문 범위 안이라고 판단해 아래와 같이 정하고 여기 기록한다:

1. `plumber_page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=False)`로 word 목록을 얻는다. `extra_attrs`에 `fontname`/`size`를 지정하면 pdfplumber가 **word 내부에서 폰트명/크기가 바뀌는 지점을 자동으로 쪼개준다** — 즉 이 시점부터 이미 "한 word = 단일 폰트/크기"가 보장된다.
2. `top` 좌표를 기준으로 근접한 word를 같은 "줄"로 묶는다(허용 오차 2.5pt, `_LINE_TOLERANCE_PT`). pdfplumber가 줄 단위 그룹을 직접 제공하지 않아 직접 구현한 휴리스틱이다.
3. 같은 줄 안에서 `(fontname, size)`가 동일하게 이어지는 연속 word 구간을 하나의 `TextBlockIR`로 합친다(공백으로 join). 폰트가 바뀌면 새 블록을 시작한다.
4. bbox는 구간에 속한 word들의 bbox를 합집합(`min(x0)`, `min(top)`, `max(x1)`, `max(bottom)`)한 값이다. `TextBlockIR.bbox`의 좌표 순서는 pdfplumber 자체 관례(`x0, top, x1, bottom`, 페이지 상단 기준 y)를 그대로 따랐다 — 03 설계서가 순서를 명시하지 않아 pdfplumber 원본 관례를 유지하는 것이 가장 편차가 적다고 판단했다.

**한계(그대로 기록)**: 다단(멀티컬럼) 레이아웃에서 같은 top대에 있는 다른 컬럼의 word를 한 줄로 잘못 묶을 수 있고, 큰 가로 간격이 있어도 같은 스타일이면 하나의 블록으로 합쳐진다(컬럼 경계 인식은 하지 않음). 회전/기울어진 텍스트도 이 휴리스틱의 대상이 아니다.

### 1-3. REQ-007 — ToUnicode 매핑 누락 감지 방식과 한계

`_sanitize_text(text) -> (sanitized_text, missing: bool)`가 word 텍스트 단위로 아래 3가지 신호를 검사해 대체문자(□, U+25A1)로 치환한다:

1. **`(cid:123)` 패턴** — pdfminer.six(pdfplumber의 파싱 엔진)가 폰트에 ToUnicode CMap이 없어 문자 코드를 유니코드로 되돌릴 수 없을 때 기본 폴백으로 흘려보내는 것으로 알려진 리터럴 문자열. 정규식 `\(cid:\d+\)`로 감지.
2. **빈 문자열 글자 또는 U+FFFD(유니코드 표준 대체문자)**.
3. **사설 영역(PUA) 단일 코드포인트** — `U+E000-F8FF`, `U+F0000-FFFFD`, `U+100000-10FFFD`. 일부 서브셋 폰트가 매핑 실패 글리프를 이 영역에 두는 경우가 있다는 관찰에 근거.

**한계 (지어내지 않고 그대로 기록)**:
- 이 세 신호에 해당하지 않지만 실제로 의미가 잘못된 경우는 감지하지 못한다. **로컬 동작 확인 중 이 한계를 실제로 관찰했다** — reportlab로 한글 텍스트("안녕하세요 반갑습니다")를 Helvetica(한글 미지원) 폰트로 그린 샘플 PDF를 pdfplumber로 열어보니, 텍스트가 `(cid:...)`나 PUA 코드포인트가 아니라 **엉뚱하지만 멀쩡해 보이는 ASCII 문자('n')와 `ZapfDingbats` 폰트명**으로 잘못 디코딩되어 나타났다. 이런 "그럴듯하지만 틀린" 치환은 이 휴리스틱으로 절대 감지할 수 없다 — 이는 근본적으로 텍스트 레이어만 보고는 "원래 의도된 글리프가 무엇인지" 알 방법이 없기 때문이며, 완벽한 해결책은 없다고 판단해 한계로만 기록한다(6단계 테스터가 이 케이스로 실패 판정을 내리지 않도록 미리 공유).
- PUA 검사는 오탐 가능성이 있다 — 일부 정상적인 기호 폰트(Wingdings류)가 PUA를 실제 의미로 사용하는 경우 잘못 "누락"으로 표시될 수 있다.
- `(cid:N)` 패턴 감지는 **합성 문자열에 대해서만** 단위 검증했다(`_sanitize_text("a(cid:12)b")` 등, 아래 2절). pdfminer가 실제로 이 폴백을 발동시키는 "ToUnicode 없는 서브셋 폰트"를 가진 실제 PDF를 이번 호출 시간 안에 직접 제작해 end-to-end로 재현하지는 못했다(구조적으로 이런 PDF를 손으로 만드는 작업 자체가 non-trivial) — 이 사실을 숨기지 않고 명시한다.

### 1-4. 폰트 굵기/기울임(bold/italic) 추정

`_is_bold`/`_is_italic`은 pdfplumber가 word 단위로 제공하는 `fontname` 문자열의 관례적 표기(`Bold`, `Italic`, `Oblique` 부분 문자열)만으로 추정한다. pdfplumber는 char/word 레벨에서 폰트 디스크립터의 실제 weight 플래그를 노출하지 않으므로 이 이상의 정밀한 방법이 없었다. 커스텀 서브셋 폰트가 이런 명명 관례를 따르지 않으면 오탐/누락할 수 있다(한계 그대로 기록).

### 1-5. is_scanned / NFC 정규화에 대한 가정 (지시문대로 명시)

- 이 함수는 `PageIR.is_scanned`를 채우지 않는다. 페이지에 추출 가능한 텍스트가 없으면(word 목록이 비면) 그냥 빈 리스트 `[]`를 반환할 뿐이며, "이 페이지가 스캔본인지"에 대한 판단은 전혀 하지 않는다 — 그 판단은 orchestrator(unit-8)의 책임이라고 가정했다.
- `TextBlockIR.text`는 NFC 정규화를 거치지 않은 pdfplumber 원문 그대로다. 실제 NFC 정규화는 `pdf_reader/hangul_normalizer.py`(unit-15)가 이 출력을 입력받아 별도 후처리 단계로 수행한다(03 §1-3 unit-15 행)고 가정했다.

---

## 2. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정이 없다는 unit-0의 확인을 재확인했다(`pyproject.toml`, 리포지토리 루트에 `ruff`/`flake8`/`black`/`mypy`/`pylint` 설정 없음 — `grep`로 재확인, 있는데 건너뛴 것 아님).
- 대신 `python -m py_compile pdf_to_hwpx/pdf_reader/text_extractor.py` 실행 — **컴파일 성공**.
- 병렬 웨이브 중 다른 unit(unit-2/3/4)의 미완성 코드로 인한 전체 실행 실패는 이 unit의 범위(`text_extractor.py` 단일 파일 컴파일)에 영향을 주지 않았다 — 별도로 격리해 보고할 실패 없음.

## 3. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — REQ-002(폰트명/크기/굵기/기울임 best-effort), REQ-007(대체문자 치환 + `to_unicode_missing` 플래그)을 `TextBlockIR` 필드 그대로 채웠다. REQ-006은 "정규화 파이프라인 입력을 만드는 것까지"로 범위를 한정한 지시문대로, NFC 정규화 자체는 수행하지 않았다.
- [x] 에러 처리가 누락된 경로가 없는가 — 이 모듈에 예외를 삼키거나 무시하는 코드가 없다. `extract_words`가 예외를 던지는 경우(예: 파싱 손상)는 이 함수가 별도로 잡지 않고 그대로 전파한다 — loader.py(unit-0)가 이미 로드 단계에서 손상 PDF를 `CorruptedPdfError`로 걸러내므로, 이 함수에 도달한 page 객체는 이미 유효성이 확인된 상태라고 가정했다(이 가정을 여기 명시). 페이지 내용 자체가 비정상적이어서 `extract_words`가 예외를 던지는 극단적 케이스까지 이 unit이 새 예외로 감싸는 것은 설계서(03 §4-2)에 근거가 없어 임의로 추가하지 않았다 — 필요하다면 orchestrator(unit-8) 레벨의 `except Exception` 최상위 방어선(03 §4-2)이 이를 `INTERNAL_ERROR`로 흡수한다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 모듈의 입력은 사용자 파일이 아니라 unit-0이 이미 검증한 `PdfDocument`에서 파생된 pdfplumber 페이지 객체이므로, 시스템 경계 검증은 이미 loader.py에서 수행됐다는 전제다. 이 모듈 내부에서는 `word.get("text", "")`처럼 필드 부재에 대한 방어적 접근만 추가했다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 텍스트 처리 로직).
- [x] 새로 추가한 외부 의존성 — **없음**. `pdfplumber`는 unit-0이 이미 `pyproject.toml`에 등록한 기존 의존성을 그대로 import했을 뿐이다(`import pdfplumber`, `from pdf_to_hwpx.pdf_reader.ir import TextBlockIR`). 새 패키지를 설치하거나 매니페스트를 건드리지 않았다(병렬 웨이브 규칙 — 공유 자원인 매니페스트는 범위 밖).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/pdf_reader/text_extractor.py` 1개 파일만 신규 생성했다. `ir.py`, `loader.py`, `pyproject.toml` 등 어떤 파일도 수정하지 않았다.

## 4. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

`.harness-tmp/venv-unit1`(신규 생성, 병렬 실행 중인 unit-3의 `venv-unit3`와 충돌하지 않도록 별도 디렉터리 사용)에 `pip install -e ".[dev]"` + 로컬 검증용 `reportlab`(스크래치 전용, 프로젝트 의존성에 추가하지 않음)을 설치해 스크래치패드에서 확인 후 스크립트/생성 PDF 전부 폐기했다:

1. **일반 텍스트 + 굵게 + 기울임 + 한글 혼재 PDF** (reportlab로 즉석 생성) → `extract_text_blocks`가 5개 블록 반환, 각각 `font_name`/`font_size`/`bold`/`italic`이 의도한 값과 일치함을 확인(`Helvetica-Bold` → bold=True, `Helvetica-Oblique` → italic=True).
2. **빈 페이지 PDF**(콘텐츠 없이 `showPage()`만 호출) → `extract_text_blocks`가 정확히 `[]`를 반환함을 확인(1-5절 가정과 일치).
3. **`_sanitize_text` 단위 확인**(합성 문자열): `"hello"` → 변경 없음/`missing=False`, `"a(cid:12)b"` → `(cid:12)`가 □로 치환되고 `missing=True`, `""` → `missing=False`, `"�"` → □ 치환/`missing=True`, `chr(0xE001)`(PUA) → □ 치환/`missing=True`. 모두 기대대로 동작.
4. **실제 관찰된 한계 사례**(1-3절에 상술) — 한글을 지원하지 않는 폰트로 그린 텍스트가 `(cid:...)`/PUA가 아닌 "그럴듯한 오디코딩"(`ZapfDingbats` 폰트에 'n' 문자들)으로 나타나는 경우를 실제로 관찰했고, 이 경우 `to_unicode_missing`이 `False`로 남는다(감지 못함) — 한계로 정직하게 기록.

모든 항목 의도대로 동작 확인. 스크래치 스크립트(`make_test_pdf.py`, `make_blank_pdf.py`, `run_check.py`)와 생성된 PDF(`test_sample.pdf`, `blank.pdf`)는 확인 후 삭제했다(리포지토리에 남기지 않음).

---

## 5. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 추출
1. 추출 가능한 텍스트가 있는 페이지에 대해 `extract_text_blocks(page)`가 빈 리스트가 아닌 `list[TextBlockIR]`을 반환한다.
2. 각 `TextBlockIR.text`는 원본 페이지의 해당 구간 텍스트를 (word 사이 단일 공백으로 join한) 문자열로 담고 있다.
3. `TextBlockIR.bbox`는 `(x0, top, x1, bottom)` 순서이며, `x0 <= x1`, `top <= bottom`을 만족한다(페이지 상단 기준 pdfplumber 좌표계).

### AC-2. 폰트/스타일
4. 서로 다른 폰트명/크기가 섞인 줄에서, 폰트명/크기가 바뀌는 지점마다 별도의 `TextBlockIR`이 생성된다(같은 블록 안에서 `font_name`/`font_size`가 섞이지 않는다).
5. 폰트명에 `Bold`가 포함된 구간은 `bold=True`, `Italic`/`Oblique`가 포함된 구간은 `italic=True`로 표시된다(대소문자 무관).

### AC-3. REQ-007 (ToUnicode 매핑 누락)
6. 추출된 텍스트에 `(cid:숫자)` 패턴이 포함되어 있던 경우, 해당 부분이 대체문자 `□`(U+25A1)로 치환되고 그 블록의 `to_unicode_missing=True`다.
7. 추출된 텍스트에 U+FFFD, 또는 PUA 범위(U+E000-F8FF/U+F0000-FFFFD/U+100000-10FFFD) 단일 코드포인트 문자가 있던 경우도 6과 동일하게 처리된다.
8. **알려진 미탐 케이스(실패로 취급하지 말 것)**: 폰트 미스매치로 인해 "다른 정상 문자로 잘못 디코딩"된 경우(예: 한글을 지원 안 하는 폰트가 라틴 문자로 대체 렌더링)는 `to_unicode_missing=False`로 남을 수 있다 — 이는 알려진 설계상 한계이며 6단계에서 이 케이스를 REQ-007 결함으로 보고하지 않는 것을 권장한다(1-3절 근거 참고).

### AC-4. 빈 페이지 / 스캔본
9. 추출 가능한 텍스트가 전혀 없는 페이지(예: 완전히 빈 페이지, 또는 이미지만 있는 스캔본 페이지)에 대해 `extract_text_blocks(page)`는 예외 없이 정확히 `[]`를 반환한다.
10. 이 함수는 `PageIR.is_scanned`를 설정하지 않는다 — 6단계는 이 함수 자체를 "스캔본 판정" 기준으로 테스트하지 말 것(그 로직은 unit-8 소관).

### AC-5. 안정성
11. 이 함수는 입력 `plumber_page`를 읽기 전용으로만 사용하며 어떤 상태도 변경하지 않는다(같은 페이지에 대해 여러 번 호출해도 결과가 동일).
12. `pdf_to_hwpx.pdf_reader.ir.TextBlockIR`, `pdf_to_hwpx.pdf_reader.loader.PdfDocument`를 수정 없이 그대로 import해서 쓰고 있음을 코드 리뷰로 확인 가능(범위 외 파일 미접촉).

---

## 6. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 일괄 반영)

`docs/harness/traceability.md`에 아래 갱신을 요청한다 (직접 수정하지 않음, 병렬 호출 규칙):

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-002 | 작업 단위 | unit-1 |
| REQ-002 | 구현 상태 | Implemented (unit-1, 05단계 완료, 06단계 단위테스트 대기) |
| REQ-006 | 작업 단위 | unit-1(입력 생성만, 정규화 자체는 unit-15) |
| REQ-006 | 구현 상태 | Partially Implemented (unit-1이 정규화 파이프라인 입력측 텍스트 추출 완료 — 실제 NFC 정규화는 unit-15 별도 진행 필요, 05단계 완료/06단계 단위테스트 대기) |
| REQ-007 | 작업 단위 | unit-1 |
| REQ-007 | 구현 상태 | Implemented (unit-1, 05단계 완료, 06단계 단위테스트 대기 — 단 1-3절/AC-3의 휴리스틱 한계를 함께 기록해줄 것) |

추가로 `decisions.md` 갱신 요청은 없음(이번 unit에서 규칙 A 질문을 발동한 사례 없음 — 1-2절의 그래뉼래러티 판단은 "합리적으로 정하고 note에 명시"라는 지시문 범위 안에서 자체 결정).

---

## 재작업(2026-09-28) — DEF-001 수정 (06단계 FAIL 반려에 따른 재작업, 규칙 F)

### 배경(06단계가 발견한 결함)

`docs/harness/units/unit-1-test.md` 6절 DEF-001(High): `_group_words_into_lines`가 `(round(top,1), x0)` 오름차순 정렬 후 `top` 차이가 고정 허용오차 `_LINE_TOLERANCE_PT`(2.5pt)인지로만 "같은 줄"을 판정했다. pdfplumber의 `top`은 글자 상단(어센트 포함) 기준이라, 같은 베이스라인 위 단어라도 폰트 "크기"가 크게 다르면 어센트 차이만큼 `top` 값이 크게 벌어진다(재현 실측: size10 "Small" top=133.9598 vs size24 "BIGGER" top=122.8578, 차이 11.1pt > 2.5pt). 결과: (1) 정렬 시 `top`이 1차 키라 실제로는 오른쪽에 있는 큰 글자가 왼쪽 작은 글자보다 먼저 정렬되어 읽기 순서가 뒤바뀌고, (2) 큰 글자가 허용오차를 벗어나 별도 "줄"로 분리되면서 그 좌우에 있던 작은 글자들이 서로 인접한 것처럼 재배열되어 원래 떨어져 있던 단어끼리 하나의 블록 텍스트로 잘못 합쳐지는 내용 손상까지 발생했다(예외/경고 없이 조용히 발생). AC-2-4(폰트 크기 혼합 줄 분리), AC-1-2(텍스트 무결성) 위반.

### 무엇을 고쳤는가

1. **판정 기준 변경**: `top` 값 하나만 보는 고정 허용오차(`_LINE_TOLERANCE_PT`, 2.5pt) 대신, word의 세로 구간 `[top, bottom]`이 서로 얼마나 겹치는지(overlap 길이 / 두 word 중 더 작은 높이 비율)로 "같은 줄"을 판정하도록 `_group_words_into_lines`를 재작성했다. 새 상수 `_LINE_OVERLAP_RATIO = 0.5`(50% 이상 겹치면 같은 줄).
2. **책임 분리**: "같은 줄인지 판정"(세로 겹침 비율 기준, 스윕 방식으로 클러스터링)과 "줄 내부 읽기 순서 정렬"(x0 오름차순, 클러스터 확정 후 별도로 수행)을 분리했다. 이전 구현은 판정 전에 이미 `(top, x0)`으로 전역 정렬을 해버려서 클러스터 배정 자체가 틀어지는 구조적 문제가 있었다(06단계가 지적한 재검토 포인트 2번, 8절).
3. 알고리즘: word를 `top` 오름차순으로 스윕하면서, 이미 만들어진 각 줄 클러스터의 `max_bottom`과 비교해 겹칠 가능성이 있는 클러스터만 검사(빠른 스킵), 클러스터 내 아무 멤버와든 겹침 비율이 임계값 이상이면 그 클러스터에 편입(전이적 병합 — 예: A-B, B-C가 각각 겹치면 A-B-C가 한 줄로 묶임). 클러스터 확정 후 각 클러스터 내부를 `x0` 기준 정렬, 클러스터 간에는 `min(top)` 기준으로 정렬해 최종 줄 순서를 만든다.

### 왜 이 방식을 골랐는가 (근거)

- 실측 데이터 확인 결과, `top`(어센트 포함, 폰트 크기에 따라 변동폭이 큼)보다 `bottom`(디센트만큼만 베이스라인 아래로 내려감, 변동폭이 작음) 쪽이 폰트 크기가 달라도 상대적으로 안정적이었다(Small bottom=143.9598, BIGGER bottom=146.8578 — 차이 2.9pt, 같은 조건에서 top 차이는 11.1pt였음). 이는 일반적인 폰트의 어센트가 디센트보다 크기 때문이며(라틴 폰트 관례), 세로 구간 전체의 "겹침"을 보면 이 비대칭성에 흔들리지 않고 같은 베이스라인 판정이 가능하다.
- 대안으로 검토했으나 채택하지 않은 것: (a) 폰트 크기에 비례하는 허용오차(예: `max(size_a, size_b) * 0.5`) — word 쌍마다 어떤 size를 기준으로 삼을지 애매하고, 극단적으로 큰 폰트 하나가 섞이면 허용오차가 과도하게 커져 실제로 다른 줄인 단어까지 묶일 위험이 있어 기각. (b) union-find 기반 전수 쌍 비교 — 정확하지만 페이지당 word 수가 많을 때 O(n²) 상수가 커서, 스윕+`max_bottom` 조기 스킵 방식(사실상 같은 목적을 달성하면서 비교 대상을 줄임)을 택했다.
- 임계값 `_LINE_OVERLAP_RATIO = 0.5`는 03 설계서에 근거 수치가 없어 합리적으로 정한 값이다(재현 케이스에서는 실제 겹침 비율이 99.6~100%로 여유 있게 통과함 — 기존 `_LINE_TOLERANCE_PT`와 마찬가지로 "근거 있는 표준값은 아님"을 그대로 유지해 기록).

### 수정 범위 및 미변경 사항

- `pdf_to_hwpx/pdf_reader/text_extractor.py` 1개 파일만 수정(지시문 범위 준수). `ir.py`/`loader.py`/`pyproject.toml`/`tests/pdf_reader/test_text_extractor.py` 등 어떤 파일도 건드리지 않았다.
- `_LINE_TOLERANCE_PT` 상수는 제거하고 `_LINE_OVERLAP_RATIO`로 대체했다. 기존 공개 API(`extract_text_blocks` 시그니처), `_line_words_to_blocks`/`_build_block`/`_sanitize_text`/`_is_bold`/`_is_italic` 등 다른 함수는 변경하지 않았다(범위 외 리팩터링 금지 원칙 준수).
- 1-2절/8절에 이미 기록된 다단(멀티컬럼) 레이아웃 한계, 회전/기울어진 텍스트 한계는 이번 수정 대상이 아니며 여전히 동일하게 남아있다(06단계 지시문에서도 이번 수정 범위가 아님을 명시함).

### 남은 한계 (새 알고리즘 기준으로 다시 정직하게 기록)

- 겹침 비율 임계값(0.5)은 극단적인 경우 — 예: 위 첨자/아래 첨자처럼 세로로 일부러 어긋나게 배치된 텍스트 — 를 의도적으로 다른 줄로 분리할 수도, 같은 줄로 합칠 수도 있다. 이번 재작업은 "같은 베이스라인 위 폰트 크기 혼합" 케이스(DEF-001 재현 조건)를 정확히 고치는 데 집중했고, 위/아래 첨자처럼 베이스라인 자체가 다른 케이스에 대한 전용 처리는 여전히 하지 않는다(기존에도 없었던 기능이며 이번에 새로 만들지 않음).
- 여전히 다단 레이아웃에서 같은 세로 구간에 있는 다른 컬럼 word를 한 줄로 잘못 묶을 가능성은 남아있다(기존 한계 그대로, 06단계도 이번 수정 범위가 아니라고 명시).
- 클러스터 매칭이 "멤버 중 아무거나와 임계값 이상 겹치면 편입"이므로, 아주 드물게 사슬처럼 계속 이어지는 전이적 병합(A-B 겹침, B-C 겹침이지만 A-C는 안 겹침)이 발생하면 시각적으로 완전히 겹치지 않는 A와 C가 한 줄로 묶일 수 있다. 이는 통상적인 문서(같은 줄 안 폰트 크기가 몇 종류로 제한됨)에서는 발생 가능성이 낮다고 판단했으나, 06단계가 필요하다고 판단하면 추가 회귀 케이스로 확인해도 좋다.

### 게이트 1 재검증 (정적 분석/린트)

- 이전과 동일하게 프로젝트에 lint/type-check/formatter 설정이 없음을 재확인(`ruff`/`flake8`/`black`/`mypy`/`pylint` 설정 `pyproject.toml`에 없음 — 있는데 건너뛴 것 아님).
- `python -m py_compile pdf_to_hwpx/pdf_reader/text_extractor.py` — 컴파일 성공.

### 게이트 2 재검증 (자체 코드 리뷰 체크리스트)

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — REQ-002의 핵심 가치("원문 텍스트를 있는 그대로 보존", DEF-001이 침해했던 부분)를 복구했다. 03 설계서는 그룹핑 알고리즘의 구체적 수치를 규정하지 않으므로 이번 변경도 이전과 동일하게 "합리적으로 정한 휴리스틱"의 범주 안에 있다.
- [x] 에러 처리가 누락된 경로가 없는가 — 새로 추가한 `_has_vertical_overlap`을 포함해 예외를 삼키거나 무시하는 코드 없음. 0 높이(`top == bottom`) 방어를 위해 `max(height, 0.01)`로 0 나눗셈을 방지했다(단어 bbox가 이론상 항상 양의 높이를 가져야 하지만 방어적으로 처리).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 함수의 입력은 여전히 unit-0이 이미 검증한 pdfplumber word dict이며, 이번 변경으로 새로운 시스템 경계가 생기지 않았다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성 — 없음(순수 표준 라이브러리 로직 변경).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `_group_words_into_lines`와 그 직접 종속 헬퍼(`_has_vertical_overlap` 신규)만 변경했다. `_line_words_to_blocks` 이하 나머지 함수는 그대로다.

### 로컬 동작 확인 (재작업)

`.harness-tmp/venv_05_unit1_rework/`(신규 격리 venv, 확인 후 삭제)에 `pip install -e ".[dev]" reportlab`을 설치해:

1. `python -m py_compile` 컴파일 확인.
2. `pytest tests/pdf_reader/test_text_extractor.py -q` — **36 passed**(DEF-001 재현 테스트 2건 `test_font_size_switch_on_same_line_creates_separate_blocks`, `test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub` 포함 전부 통과).
3. `pytest tests/ -q`(전체 회귀) — **209 passed, 2 failed**. 실패 2건(`test_image_extractor.py::test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`, `::test_dctdecode_jpeg_raw_bytes_can_silently_diverge_from_original_DEF002`)은 병렬 진행 중인 **unit-2(`image_extractor.py`)의 자체 DEF-001/DEF-002 재작업 대상**이며 이 파일(`text_extractor.py`) 수정과 무관함을 확인했다(테스트 파일 경로/실패 내용 모두 unit-2 소유). `text_extractor.py` 관련 테스트는 전부 통과.
4. 임시 아티팩트(`.harness-tmp/venv_05_unit1_rework/`)는 확인 후 즉시 삭제, 재작업 종료 시점 `git status --short`로 이 unit이 건드린 파일이 `pdf_to_hwpx/pdf_reader/text_extractor.py` 1개뿐임을 확인했다.

### 재검증 우선순위 (06단계 인계)

**재검증 우선순위: DEF-001 재현 테스트 2건(`test_font_size_switch_on_same_line_creates_separate_blocks`, `test_extract_text_blocks_mixed_size_three_words_reading_order_via_stub`) + 전체 회귀(`tests/pdf_reader/test_text_extractor.py` 전량, 36개).** 위 로컬 확인에서 이 2건을 포함해 36개 전부 PASS를 확인했으나, 06단계 원칙(라인 커버리지 100%가 정확성을 보장하지 않음, 06-unit-tester 자체 재실행 필요)에 따라 06이 직접 재실행해 판정할 것을 권고한다. 5절 AC-1~AC-5(12개 조건)와 TC-001~TC-026(테스트 결과서 4절) 전체가 여전히 유효한 매핑인지도 함께 재확인 요청.

### 트랙 표기 재확인

- 이 unit(unit-1)이 속한 feature의 속도 트랙은 기존과 동일하게 **L3(일반)**이다(변경 없음). 06단계는 L3 기준(전 섹션 작성, 내부 검증 2회, 06·07 병합 대상 아님)을 그대로 적용할 것.

### 공유 문서 갱신 요청 (재작업분, 병렬 실행 규칙 — 직접 수정하지 않음)

이번 재작업은 병렬 웨이브(unit-2 재작업과 동시 진행) 중 호출되었으므로 `docs/harness/traceability.md`를 직접 수정하지 않는다. 오케스트레이터가 웨이브 종료 후 아래로 갱신해줄 것을 요청한다(현재 값은 06단계 FAIL 반영분, 재작업 완료로 갱신 필요):

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-002 | 구현 상태 | Implemented (unit-1, 05단계 재작업 완료 — DEF-001 수정, `pdf_reader/text_extractor.py`. `_group_words_into_lines`를 세로 겹침 비율(`_LINE_OVERLAP_RATIO`) 기반 판정으로 교체. 06단계 재검증 대기. unit-5는 Not Started, 변경 없음) |
| REQ-002 | 단위테스트 | 재작업 완료, **06단계 재검증 대기** — `docs/harness/units/unit-1-note.md` "재작업(2026-09-28)" 절 참고. 05단계 로컬 확인(`pytest tests/pdf_reader/test_text_extractor.py`)에서 DEF-001 재현 테스트 2건 포함 36개 전부 PASS 확인했으나 최종 판정은 06단계 재실행 필요 |
| REQ-006 | 구현 상태 | Partially Implemented (unit-1: 정규화 대상 원본 텍스트 생성 부분 DEF-001 수정 완료, 06단계 재검증 대기 — 정규화 자체는 여전히 unit-15 소관, Not Started) |
| REQ-007 | 구현 상태 | Implemented (unit-1, 05단계 완료 — REQ-007 자체 로직은 이번 재작업에서 변경하지 않음(수정 대상은 줄 그룹핑 로직뿐). 파일 전체 06단계 재검증 대기) |

추가로 이 결과는 06단계 재실행 전까지 07단계(통합테스트)로 handoff하지 않는다 — 06-unit-tester가 DEF-001 재현 테스트 2건 + 전체 회귀를 재검증한 뒤에만 07단계로 넘어갈 수 있다(위 "재검증 우선순위" 절 참고).
