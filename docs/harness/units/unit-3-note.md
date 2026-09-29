# unit-3 구현 노트 — PDF 표 구조 인식 (05-unit-developer)

- 커버 REQ-ID: REQ-004 (표 구조 인식 → HWPX 표 객체 변환, 셀 병합은 best-effort)
- 소속: Feature A
- 속도 트랙: **L3(일반)** — 오케스트레이터로부터 별도 트랙 지정을 전달받지 않아 기본값 적용. 06/07단계는 기본 절차대로 검증하면 된다.
- 선행 단위: unit-0(완료, PASS) — `pdf_to_hwpx/pdf_reader/loader.py`의 `PdfDocument.plumber_pdf`를 읽기 전용으로 소비.
- **병렬 웨이브 호출임**: 이 호출과 동시에 unit-1(`pdf_reader/text_extractor.py`), unit-2(`pdf_reader/image_extractor.py`), unit-4(`hwpx_kernel/schema.py`, `hwpx_kernel/container.py`)가 각각 별도의 05-unit-developer 호출로 동시 실행 중이었다.
- 확정 파일 범위: **`pdf_to_hwpx/pdf_reader/table_recognizer.py` 단일 파일만** 수정함(범위 밖 파일 접촉 없음).
- 선행 문서: `docs/harness/03-system-design.md`(v3, PASS) §1-3 unit-3 행, §2-1 pdfplumber 선정 근거, §3-1 IR 정의 / `docs/harness/02-planning.md`(v3, PASS) REQ-004 / `pdf_to_hwpx/pdf_reader/ir.py`(공용 IR 계약) / `pdf_to_hwpx/pdf_reader/loader.py`(unit-0 산출물)

---

## 1. 구현 범위

### 1-1. 함수 시그니처

```python
def extract_table_blocks(
    plumber_page: pdfplumber.page.Page,
    table_settings: dict[str, Any] | None = None,
) -> list[TableBlockIR]:
```

- 입력: `PdfDocument.plumber_pdf.pages[i]`로 얻는 pdfplumber 페이지 객체(unit-0이 만든 `PdfDocument`를 소비하는 쪽은 호출자 — 이 함수 자체는 `PdfDocument`가 아니라 페이지 단위 pdfplumber 객체를 받도록 설계했다. 이유: 03 §3-1 `PageIR`가 페이지 단위 엔티티이고, `PageIR.table_blocks`를 채우는 호출자(§1-2 다이어그램상 `LOADER -> TBL`)가 페이지를 순회하며 페이지별로 이 함수를 호출하는 구조가 자연스럽기 때문. `PdfDocument` 전체를 받게 하면 이 함수가 페이지 순회 책임까지 떠안게 되어 단일 책임 원칙에서 벗어난다).
- `table_settings`: pdfplumber `Page.find_tables()`에 그대로 전달하는 선택적 표 감지 설정. 설계서(§2-1)가 확정한 것은 "pdfplumber 채택"과 "`extract_tables()` 계열이 REQ-004 요구를 충족"이라는 결론까지이고, 구체적 `table_settings` 튜닝 값(선 감지 전략 등)은 설계서에 명시가 없어 임의로 특정 값을 고정하지 않고 `None`(pdfplumber 기본값)을 기본으로 하되 호출자가 필요 시 오버라이드할 수 있게 열어뒀다. 이는 설계 모호성에 대한 임의 선택이 아니라, 설계서가 이미 확정한 "기본 동작으로 충분"이라는 판단을 그대로 따르면서 확장 여지만 남긴 것이다.
- 출력: 페이지 내 감지된 표 개수만큼의 `TableBlockIR` 리스트(표 없으면 빈 리스트, 예외 없이 정상 반환).

### 1-2. 병합 셀(REQ-004) 감지 휴리스틱 — best-effort

**pdfplumber의 한계**: `Table.rows[i].cells`는 감지된 실제 선(rule line) 사각형이 없는 격자 칸을 `None`으로 표시할 뿐, "이 칸이 병합되어 없다"는 사실을 직접 알려주지 않는다(pdfplumber 0.11.10 소스(`pdfplumber/table.py`의 `Table._get_rows_or_cols`/`Table.extract`)를 직접 읽어 확인함).

**휴리스틱**(코드/모듈 docstring에도 동일 내용 기술):
1. 격자를 좌상단→우하단 순으로 훑으며 실제 사각형이 있는 칸은 자기 자신을 소유자(owner)로 기록.
2. `None` 칸을 만나면:
   - a. 왼쪽 칸 소유자의 사각형 오른쪽 끝(x1)이 이 칸이 속한 열의 시작 x좌표(다른 행에서 관측된 실제 셀 x0 기준선)를 넘어서면 **가로 병합**으로 판정, 왼쪽 소유자에 흡수.
   - b. 가로 병합이 아니면, 위쪽 칸 소유자의 사각형 아래쪽 끝(bottom)이 이 행의 시작 y좌표(top)를 넘어서면 **세로 병합**으로 판정, 위쪽 소유자에 흡수.
   - c. 둘 다 기하학적으로 확인 안 되면 병합으로 단정하지 않고 **내용 없는 독립 1x1 빈 셀**로 남김.
3. 같은 소유자를 공유하는 칸들을 묶어 `TableCellIR(row_span, col_span, text)`로 변환(`row_span`/`col_span`은 소유자 그룹의 행/열 범위로 계산).
4. (a) 또는 (b)로 **확정된 병합이 하나라도 있을 때만** `TableBlockIR.has_merged_cells = True`. 확정 병합이 전혀 없으면(2-c만 발생했거나 애초에 병합이 없으면) `False`.

**한계(지어내지 않고 명시, 모듈 docstring에도 동일 내용)**:
- 병합된 셀이 표의 첫 행/첫 열에 걸쳐 있어 비교 기준이 될 실제 사각형을 전혀 얻을 수 없는 극단적 배치(예: 표 전체 한 열이 병합만으로 구성)는 2-c 경로로 빠져 병합이 아닌 빈 셀로 남을 수 있다 — 이 경우 `has_merged_cells`가 `False`로 남아 실제로는 병합이 있는데 감지하지 못하는 미탐(false negative) 가능성이 있다.
- 3개 이상 칸이 얽힌 비직사각형(L자형 등) 복합 병합은 pdfplumber의 격자 모델 자체가 표현하지 못하므로 이 모듈도 표현하지 못한다.
- pdfplumber가 애초에 표로 인식하지 못하는 경우(테두리선이 전혀 없는 표 등)는 `find_tables()` 단계에서 걸러지므로 이 모듈 책임 밖이다.
- 위 한계는 모두 REQ-004가 명시한 "병합 셀은 best-effort" 범위 안에 있으며, `TableBlockIR.has_merged_cells`가 `True`인 경우는 실제로 기하학적으로 확정된 병합이 최소 1건 있다는 뜻(오탐 없음을 지향)이지만, `False`라고 해서 병합이 전혀 없다는 보장은 아니다(위 미탐 가능성).

### 1-3. bbox

`TableBlockIR.bbox`는 지시대로 `pdfplumber`의 `find_tables()`가 반환한 `Table.bbox`(감지된 셀 사각형들의 min/max로 pdfplumber가 계산)를 그대로 사용했다. 별도 계산을 하지 않음.

### 1-4. rows/cols

`TableBlockIR.rows`/`cols`는 격자(grid) 차원(= `len(table.rows)` / 각 행의 `cells` 길이)이며, 병합으로 합쳐진 "논리적" 행/열 수가 아니다. `cells` 리스트의 항목 수는 병합이 있으면 `rows * cols`보다 적을 수 있다(각 항목이 이미 `row_span`/`col_span`을 담고 있으므로 소비자(unit-6)가 격자를 복원할 수 있다).

---

## 2. 설계서 대비 편차

없음. `pdf_reader/table_recognizer.py` 단일 파일 범위, `TableBlockIR`/`TableCellIR`는 `ir.py`에서 import만 하고 재정의하지 않았으며, `hwpx_kernel/schema.py`(unit-4 소관)는 전혀 건드리지 않았다.

---

## 3. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`)이 **없음을 재확인**했다(`pyproject.toml` 및 리포지토리 루트 검색, unit-0-note.md의 동일 확인과 일치). 있는데 건너뛴 것이 아니라 애초에 없다.
- 대신 `python -m py_compile pdf_to_hwpx/pdf_reader/table_recognizer.py` 실행 — **컴파일 성공**.
- **병렬 웨이브 관련 기록**: 이 호출이 수정한 파일은 `table_recognizer.py` 1개뿐이며, 이 파일 단독으로 컴파일 검증했다. 동시 실행 중이던 unit-1/2/4가 아직 파일을 완성하지 못한 상태에서 프로젝트 전체를 대상으로 한 검증(예: 전체 패키지 import)을 시도하면 그쪽 단위의 미완성 코드 때문에 실패할 수 있으므로, 이 note의 게이트1 판정은 **이 단위가 수정한 파일 기준**으로만 내렸다(05-unit-developer.md "병렬 호출 시 추가 규칙" 준수). 실제로 전체 패키지 동시 import 테스트는 시도하지 않았다(무의미하다고 판단).

## 4. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 §3-1의 `TableBlockIR`/`TableCellIR` 필드를 그대로 채움(재정의 없음, import만). §1-3 unit-3 확정 파일 범위(`pdf_reader/table_recognizer.py`)와 정확히 일치. §2-1 "pdfplumber `extract_tables()`가 REQ-004 요구 수준을 충족" 판단에 따라 `find_tables()`+`extract()` 조합만 사용(추가 서드파티 라이브러리 도입 없음).
- [x] 에러 처리가 누락된 경로가 없는가 — 이 함수는 사용자 입력을 직접 받지 않고(이미 unit-0이 검증한 `PdfDocument`에서 나온 페이지 객체만 받음), pdfplumber 호출 자체가 실패할 상황(페이지가 아예 파싱 불가)은 호출 이전 단계(`load_pdf`)에서 이미 `CorruptedPdfError`로 걸러진다. 함수 내부에서 발생 가능한 유일한 비정상 케이스(빈 행/빈 열의 표 감지 결과)는 조용히 삼키지 않고 `continue`로 해당 표만 건너뛰며, 예외를 삼키는 `except: pass` 류 코드는 전혀 없다(애초에 이 함수는 어떤 예외도 잡지 않는다 — 잡을 필요가 있는 pdfplumber 예외가 없었다).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 함수의 입력(`plumber_page`)은 사용자 입력이 아니라 unit-0이 이미 검증을 마친 내부 객체이므로 이 계층에서 추가 경계 검증은 필요 없다고 판단했다(시스템 경계는 `loader.load_pdf`이며 이미 처리됨).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성이 있는가 — **없음**. `pdfplumber`는 unit-0이 이미 `pyproject.toml`에 등록해 둔 기존 의존성을 import만 했다(신규 패키지 추가 아님, `pyproject.toml` 미수정).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `table_recognizer.py` 1개 파일만 신규 생성, 다른 파일 수정 없음.

---

## 5. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

`.harness-tmp/venv-unit3` 가상환경(unit-0과 동일 방식으로 `pip install -e ".[dev]"` + 테스트용 `reportlab` 추가 설치, `reportlab`은 이 임시 검증에만 쓰고 `pyproject.toml`에는 추가하지 않음)에서, 스크래치패드 스크립트로 표 포함 PDF 3종을 즉석 생성해 `load_pdf()` -> `extract_table_blocks()`를 실제로 호출했다(스크립트는 리포지토리에 남기지 않음):

1. **병합 없는 3x3 표** (`plain_table.pdf`, 실제 사각형 9칸 전부 존재): `rows=3, cols=3, has_merged_cells=False`, `cells` 9개 전부 `row_span=1, col_span=1`, 텍스트 A~I 정확히 추출됨.
2. **가로 병합 표** (`merged_table.pdf`, 1행의 0/1열 사이 세로선만 의도적으로 생략): `has_merged_cells=True`, 병합 셀 텍스트 `"A"`가 `col_span=2, row_span=1`로 정확히 추출됨(나머지 8칸 정상 1x1). pdfplumber가 실제로 해당 위치를 `None`으로 반환하는 것을 직접 확인 후 검증(`Table.rows[0].cells == [(...), None, (...)]`).
3. **세로 병합 표** (`vmerged_table.pdf`, 1~2행의 1열 사이 가로선만 의도적으로 생략): `has_merged_cells=True`, 병합 셀 텍스트 `"E"`가 `row_span=2, col_span=1`로 정확히 추출됨.
4. **표 없는 페이지** (`no_table.pdf`, 텍스트만 있는 페이지): `extract_table_blocks()`가 예외 없이 빈 리스트 `[]` 반환.

4가지 모두 기대한 결과와 일치함을 확인했다. (참고: pdfplumber 0.11.10의 `Table.rows[i].cells`가 병합 위치에서 `None`을 반환한다는 사실은 pdfplumber 소스코드(`Table.extract`, `Table._get_rows_or_cols`)를 직접 읽어 사전에 확인한 뒤 테스트 PDF를 설계했다 — 추측이 아니라 실제 라이브러리 동작 확인 기반.)

---

## 6. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 동작
1. 병합 없는 표(예: 3x3, 테두리선 전부 존재)에 대해 `extract_table_blocks(page)`가 `TableBlockIR` 1개를 반환하고, `rows`/`cols`가 실제 격자 크기와 일치하며, `cells` 개수가 `rows * cols`와 같고 전부 `row_span == 1 and col_span == 1`이다.
2. `has_merged_cells`가 병합 없는 표에서는 `False`다.
3. 각 `TableCellIR.text`가 해당 셀의 실제 텍스트와 일치한다(빈 셀은 `""`이며 `None`이 아니다 — dataclass 필드 타입이 `str`이므로 `None`을 담지 않는다).

### AC-2. 가로 병합
1. 특정 행에서 인접한 두 열 사이 경계선이 없는 표(가로 병합)에 대해, 해당 병합 영역이 `TableCellIR` 1개로 합쳐지고 `col_span >= 2`, `row_span == 1`이다.
2. `has_merged_cells`가 `True`다.
3. `cells` 개수가 `rows * cols`보다 적다(병합된 만큼).

### AC-3. 세로 병합
1. 특정 열에서 인접한 두 행 사이 경계선이 없는 표(세로 병합)에 대해, 해당 병합 영역이 `TableCellIR` 1개로 합쳐지고 `row_span >= 2`, `col_span == 1`이다.
2. `has_merged_cells`가 `True`다.

### AC-4. 경계/예외 상황
1. 표가 전혀 없는 페이지에 대해 `extract_table_blocks(page)`가 예외 없이 빈 리스트 `[]`를 반환한다.
2. 한 페이지에 표가 2개 이상 있으면 `TableBlockIR`도 그만큼 반환된다(각 표의 `bbox`가 서로 겹치지 않고 `find_tables()` 순서를 따름).
3. `TableBlockIR.bbox`가 pdfplumber `Table.bbox`와 동일한 4-튜플이다(x0, top, x1, bottom 좌표계, 별도 변환 없음).

### AC-5. 알려진 미탐 한계(회귀 검증용, "실패"가 아니라 "설계된 한계"임을 06단계가 인지해야 함)
1. 표 전체의 한 열이 통째로 병합되어 그 열에 대해 어느 행에서도 실제 사각형을 얻을 수 없는 극단적 배치에서는, 해당 병합이 감지되지 않고 `has_merged_cells=False`로 남을 수 있다 — 이는 버그가 아니라 1-2절/모듈 docstring에 명시된 알려진 한계이므로, 06단계가 이 케이스를 "결함"으로 보고하기 전에 이 note와 코드 docstring의 한계 설명을 먼저 참고할 것.

---

## 7. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

`docs/harness/traceability.md` REQ-004 행 갱신 요청:

| 컬럼 | 현재값 | 요청값 |
|---|---|---|
| 구현 상태 | `Not Started` | `Implemented (unit-3, 05단계 완료 — pdf_to_hwpx/pdf_reader/table_recognizer.py, 06단계 단위테스트 대기)` |
| 비고 | `셀 병합은 best-effort(01보고서 6-4)` | `셀 병합은 best-effort(01보고서 6-4). 구현 상세/인수조건: docs/harness/units/unit-3-note.md — 휴리스틱은 인접 셀 기하 정보(왼쪽/위쪽 소유 셀의 사각형 범위)로 병합 판정, 확정 못한 경우는 has_merged_cells=False로 보수적 처리(미탐 가능성 있음, note §1-2/AC-5 참고)` |

(unit-6은 이 REQ의 다른 작업 단위이므로 "작업 단위" 컬럼은 변경 요청하지 않음 — 이미 `unit-3, unit-6`로 정확함.)

규칙 A 질문·결정 기록 요청: 없음(이번 구현에서 설계 모호성으로 인한 질문 발생하지 않음, 1-1절의 `table_settings` 파라미터 추가는 설계서가 이미 확정한 판단의 연장이라 질문 대상 아니라고 판단).
