# unit-2 구현 노트 — Feature A, 이미지 추출 (05-unit-developer)

- 커버 REQ-ID: REQ-003(원본 이미지 바이트를 재인코딩 없이 그대로 추출)
- 소속: Feature A (PDF 판독 계열)
- 선행 단위: unit-0 (완료, PASS)
- 속도 트랙: **L3(일반)**
- **병렬 웨이브 호출**: 이 호출은 unit-1/unit-3/unit-4와 동시에 실행된 05-unit-developer 병렬 웨이브의 일부다. 확정 파일 범위(`pdf_to_hwpx/pdf_reader/image_extractor.py`) 밖 파일(`ir.py`, `loader.py`, `pyproject.toml` 등)은 전혀 수정하지 않았다.
- 선행 문서: `docs/harness/03-system-design.md`(§1-3 unit-2 행, §2-1 "PDF 파싱(이미지 원본 바이트 추출): pypdf" 선정 근거, §3-1 IR 정의), `docs/harness/02-planning.md`(REQ-003), `pdf_to_hwpx/pdf_reader/ir.py`(공용 IR), `pdf_to_hwpx/pdf_reader/loader.py`(unit-0, `PdfDocument.pypdf_reader`)

---

## 1. 구현 범위

### 1-1. 만든 함수/시그니처

`pdf_to_hwpx/pdf_reader/image_extractor.py` (신규 파일, 이 파일만 수정):

```python
def extract_image_blocks(pypdf_page: pypdf.PageObject) -> list[ImageBlockIR]:
    """페이지 하나에서 실제로 배치된 이미지를 원본 바이트 그대로 추출한다."""
```

- 입력: `PdfDocument.pypdf_reader.pages[i]` (unit-0의 `PdfDocument`가 소유한 `pypdf.PageObject`). unit-1의 `extract_text_blocks(plumber_page)`와 동일한 "페이지 1개 -> IR 목록" 호출 패턴을 따랐다(호출자는 orchestrator/unit-8로 가정, 설계서에 호출자 쪽 코드가 아직 없어 이 가정을 명시).
- 출력: 그 페이지의 `ImageBlockIR` 목록(`pdf_to_hwpx.pdf_reader.ir`에서 import, 수정 없이 그대로 사용).
- 내부 헬퍼(비공개): `_detect_image_format`.

### 1-2. REQ-003 핵심 — 원본 바이트 재인코딩 없음 (검증 완료)

`pypdf_page.images`가 반환하는 `ImageFile.data`를 그대로 `ImageBlockIR.raw_bytes`에 담는다 — 이 모듈에서 픽셀을 다시 디코드/인코딩하는 코드는 전혀 없다. **로컬 동작 확인에서 원본 JPEG 파일과 추출된 `raw_bytes`가 바이트 단위로 완전히 동일함을 직접 확인했다**(4절 참고). `image_format`은 `ImageFile.name`에 pypdf가 붙인 확장자(`.jpg`/`.png`/`.tiff`/`.jp2`)를 `_detect_image_format`으로 정규화("jpg"→"jpeg" 등)해 채운다 — 이 확장자는 `raw_bytes`를 만들어낸 것과 동일한 pypdf 내부 판별 로직의 산출물이라 바이트와 포맷 표기가 서로 어긋나지 않는다.

### 1-3. bbox 획득 방식과 pypdf API 한계 (지시문 요청 사항 — 지어내지 않고 명시)

**결론: pypdf의 `Page.images` 편의 API는 이미지의 페이지 내 배치 위치/크기를 전혀 제공하지 않는다.** pypdf 6.19.0 소스(`pypdf/_page.py`, `ImageFile` 클래스)를 직접 확인한 결과, `ImageFile`은 `name`/`data`/`image`(PIL)/`indirect_reference`/`is_inline`/`is_displayed` 필드만 가지고 있으며 좌표/변환행렬 필드가 없다. 실제 배치 위치는 PDF 콘텐츠 스트림의 `cm`(좌표 변환) + `Do`(XObject 그리기) 연산자 조합으로 결정되는데, pypdf는 이 정보를 `images` API 바깥으로 노출하지 않는다. 이를 신뢰성 있게 얻으려면 콘텐츠 스트림 연산자를 직접 파싱하는 별도 로직을 새로 구현해야 하며, 이는 REQ-003(원본 바이트 보존)의 범위를 벗어나는 별도 기능이라 이번 unit에서 임의로 구현하지 않았다.

**적용한 대안(지시문이 제시한 폴백과 동일)**: 모든 `ImageBlockIR.bbox`를 해당 페이지의 `MediaBox` 전체 크기 `(0.0, 0.0, width_pt, height_pt)`로 폴백한다(`pypdf_page.mediabox.width/height`에서 계산). `ir.py`는 이 unit의 파일 범위 밖 공유 계약이라 "폴백 여부"를 나타내는 별도 필드를 추가하지 않았다 — 대신 **"이 함수가 반환하는 bbox는 항상 페이지 전체 크기 폴백값"이라는 사실 자체가 계약**이다. 6단계 테스터와 후속 unit(특히 unit-7 이미지 임베딩, unit-8 오케스트레이터, unit-14 품질 리포트)이 이 사실을 알아야 하므로 아래 "공유 문서 갱신 요청"에도 남겼다.

**부가 한계**: `pypdf_page.images`는 리소스(XObject) 단위로 이미지를 반환하므로, 같은 이미지 리소스가 페이지 내 여러 위치에 반복 배치돼도 `ImageBlockIR`은 1개만 생성된다 — 위와 동일한 "위치 정보 자체를 pypdf가 노출하지 않는다"는 근본 한계에서 비롯된 것이라 별도로 보정하지 않았다.

### 1-4. "실제로 그려지는 이미지만 추출" (설계서 대비 편차 — 합리적 결정, 명시)

03 §1-3/§3-1은 "REQ-003: 원본 이미지 바이트를 재인코딩 없이 그대로 추출"이라고만 하고, 리소스로 선언만 되고 실제 콘텐츠 스트림에서 그려지지 않는 이미지까지 포함해야 하는지는 명시하지 않았다. `pypdf_page.images`는 기본적으로 리소스 딕셔너리에 있는 모든 이미지(화면에 그려지지 않는 미사용 리소스 포함)를 반환하므로, 두 가지 구현이 갈리는 지점이었다. 규칙 A 질문 대상이라기보다 합리적으로 정하고 note에 명시할 범위로 판단해, `ImageFile.is_inline or ImageFile.is_displayed`가 참인 경우만 채택했다 — 눈에 보이지 않는 리소스까지 HWPX에 끼워 넣는 것은 REQ-005(보존 우선순위)/사용자 기대와 맞지 않는 과잉 삽입이라고 판단했다. pypdf 소스 확인 결과 `is_displayed`는 콘텐츠 스트림 파싱 결과를 반영하도록 구현되어 있어(내부적으로 `_parse_images_from_content_stream` 결과와 대조), 신뢰할 수 있는 판별 기준이다.

### 1-5. 발견한 숨은 의존성 — Pillow (공유 문서 갱신 요청 대상, 중요)

`pypdf.PageObject.images`를 실제로 순회하면 내부적으로 `pypdf.generic._image_xobject`가 지연 임포트(lazy import)되는데, 이 모듈 최상단에 `from PIL import Image, UnidentifiedImageError`가 **무조건(try/except 없이)** 있다(pypdf 6.19.0 소스 직접 확인). 즉 **Pillow가 설치되어 있지 않으면 이미지가 1개라도 있는 PDF에서 `page.images`에 접근하는 순간 `ModuleNotFoundError`가 발생한다.** 그러나 현재 `pyproject.toml`(unit-0이 확정한 의존성 목록, 03 §2-1)에는 `pypdf`만 있고 `Pillow`(또는 `pypdf[image]` extra)가 없다 — 이 환경에도 원래 Pillow가 설치돼 있지 않아 로컬 동작 확인 전에 직접 재현했다(4절 참고). `pyproject.toml`은 이 unit의 파일 범위 밖(공유 매니페스트)이라 직접 수정하지 않았다 — 아래 "공유 문서 갱신 요청"에 필요한 변경을 남긴다.

---

## 2. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정이 없음을 재확인했다(`pyproject.toml`, 리포지토리 루트에 `ruff`/`flake8`/`black`/`mypy`/`pylint` 설정 없음 — 직접 검색으로 재확인, 있는데 건너뛴 것 아님. unit-0/unit-1과 동일 결론).
- `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` 실행 — **컴파일 성공**.
- 병렬 웨이브 중 다른 unit(unit-1/3/4)의 코드로 인한 전체 실행 실패는 이 unit의 범위(`image_extractor.py` 단일 파일 컴파일)에 영향을 주지 않았다 — 별도로 격리해 보고할 실패 없음.

## 3. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — REQ-003(재인코딩 없는 원본 바이트, `image_format` 원본 포맷)을 만족한다. bbox는 설계서가 요구한 필드를 채우되, pypdf API 한계로 페이지 전체 크기 폴백임을 1-3절/docstring에 명시했다(임의로 정밀한 값을 지어내지 않음).
- [x] 에러 처리가 누락된 경로가 없는가 — 이 모듈에 예외를 삼키거나 무시하는 코드가 없다(try/except 자체가 없음). `pypdf_page.images` 순회 중 pypdf가 던지는 예외(손상된 이미지 스트림, 지원하지 않는 필터 등)는 그대로 전파한다 — 03 §5 "페이지 단위 격리(벌크헤드)"는 이 함수를 호출하는 orchestrator(unit-8)의 책임이라고 판단해, 이 unit에서 임의로 흡수하지 않았다(흡수하면 REQ-009 "부분 실패 안내" 설계 의도를 어기게 됨).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 모듈의 입력(`pypdf_page`)은 사용자가 지정한 원본 PDF 바이트가 아니라, unit-0(`loader.py`)이 이미 암호화/손상/0페이지 여부를 검증한 `PdfDocument`에서 파생된 페이지 객체다. 시스템 경계 검증 자체는 loader.py 책임이라는 unit-1과 동일한 전제를 따랐다. 이 함수 내부에서는 `mediabox.width/height`를 `float()`로 강제 변환해 pypdf의 숫자형(FloatObject/NumberObject 등) 차이에 방어적으로 대응했다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 바이너리/포맷 처리 로직).
- [x] 새로 추가한 외부 의존성이 있다면 실존 패키지인지 확인했는가 — 이 파일 자체는 `pypdf`(unit-0이 이미 `pyproject.toml`에 등록)만 import하므로 신규 의존성을 추가하지 않았다. 다만 **동작에 실질적으로 필요한 `Pillow`가 현재 매니페스트에 빠져 있음을 발견**했다(1-5절) — PyPI에 실존하는 패키지(`Pillow`, https://pypi.org/project/Pillow/)이며 임의로 지어낸 이름이 아니다. 매니페스트 자체는 공유 자원이라 직접 추가하지 않고 "공유 문서 갱신 요청"에 남긴다.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 신규 생성했다. `ir.py`, `loader.py`, `pyproject.toml` 등 어떤 파일도 수정하지 않았다.

## 4. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

세션 스크래치 디렉터리(`.../scratchpad/`, 리포지토리 밖)에서 확인 후 스크립트/생성 파일은 리포지토리에 남기지 않았다. 이 환경에는 `pypdf`/`pdfplumber`/`lxml`/`Pillow`가 원래 설치돼 있지 않아(전부 `pip show` 결과 "not found"였음 — 1-5절에서 언급한 Pillow 부재를 이 시점에 직접 재현·확인함), `pyproject.toml`이 이미 선언한 버전 제약(`pypdf>=6.0.0,<7.0`, `pdfplumber>=0.11.0,<1.0`, `lxml>=5.0.0,<7.0`) 그대로와 검증용 `Pillow`를 로컬 환경에 설치해 확인했다(매니페스트 파일 자체는 수정하지 않음 — 공유 자원 규칙 준수).

1. **JPEG 이미지 1개를 포함한 최소 PDF**(직접 저수준으로 구성 — 40x30 Pillow로 생성한 JPEG을 `/DCTDecode` XObject로 임베딩한 1페이지 PDF, `MediaBox [0 0 200 200]`) → `load_pdf()` + `extract_image_blocks(page)` 호출 결과:
   - `len(blocks) == 1`
   - `blocks[0].bbox == (0.0, 0.0, 200.0, 200.0)` (MediaBox 전체 폴백, 1-3절과 일치)
   - `blocks[0].image_format == "jpeg"`
   - `blocks[0].raw_bytes`가 소스 JPEG 파일 바이트와 **완전히 동일**(`==` 비교로 확인) — REQ-003 핵심 요건(재인코딩 없음) 실증.
2. **이미지가 없는 빈 페이지**(`pypdf.PdfWriter().add_blank_page(100, 100)`) → `extract_image_blocks(page) == []`.
3. **Pillow 부재 상태에서 `pypdf_page.images` 접근 시 실패 여부**는 소스 코드 정적 확인(1-5절, `pypdf/generic/_image_xobject.py` 최상단 무조건 `from PIL import ...`)으로 결론 내렸다 — 실제로 이 세션에서 Pillow를 설치하기 전에는 `pypdf`/`pdfplumber` 자체도 설치돼 있지 않아 "설치 안 된 상태"를 그대로 재현할 기회가 있었고, 코드 경로상 이미지가 있는 PDF에서 `page.images`를 순회하면 반드시 이 임포트를 타게 되어 있음을 확인했다(간접 검증 — 직접 ModuleNotFoundError 트레이스백까지 재현하지는 않았으나 소스 코드 경로가 예외적 분기 없이 단일하므로 결론에 불확실성 없음).

## 5. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 추출 (REQ-003)
1. 이미지가 화면에 표시되는 페이지에 대해 `extract_image_blocks(page)`가 그 이미지 개수만큼의 `ImageBlockIR`을 반환한다.
2. 각 `ImageBlockIR.raw_bytes`는 PDF에 임베딩된 원본 이미지 스트림 바이트와 **바이트 단위로 완전히 동일**해야 한다(재인코딩 없음 — 원본 이미지 파일을 별도로 추출해 `==` 비교하는 방식으로 검증 가능).
3. `ImageBlockIR.image_format`은 원본 포맷을 소문자 문자열로 담는다(`"jpeg"`/`"png"`/`"tiff"`/`"jp2"` 중 하나, 그 외 알 수 없는 확장자는 원문 그대로 소문자 또는 `"unknown"`).

### AC-2. bbox (알려진 근사치 — 결함으로 오판하지 말 것)
4. **모든 `ImageBlockIR.bbox`는 `(0.0, 0.0, 페이지폭_pt, 페이지높이_pt)`, 즉 페이지 전체 크기다.** 이미지가 페이지의 일부 영역에만 작게 배치돼 있어도 bbox는 페이지 전체로 나온다 — 이는 1-3절에 기록한 pypdf API 한계에 따른 의도된 폴백이지 버그가 아니다. 6단계는 이 동작을 REQ-003 결함으로 보고하지 말고, 대신 이미지 배치 위치 정밀도 개선이 필요하면 "공유 문서 갱신 요청"(6절)의 후속 조치 여부를 오케스트레이터에게 확인할 것.

### AC-3. 미표시 리소스 제외
5. 리소스로 선언되어 있지만 실제로는 콘텐츠 스트림에서 그려지지 않는(눈에 보이지 않는) 이미지는 결과에 포함되지 않는다.

### AC-4. 빈 페이지
6. 이미지가 전혀 없는 페이지에 대해 `extract_image_blocks(page)`는 예외 없이 정확히 `[]`를 반환한다.

### AC-5. 의존성 전제 조건 (중요 — 테스트 환경 설정 시 확인)
7. 이 함수를 실제 이미지가 있는 PDF에 대해 호출하려면 **Pillow가 설치되어 있어야 한다**(1-5절). 6단계 테스트 환경에 Pillow가 없으면 `ModuleNotFoundError`가 발생할 수 있는데, 이는 `image_extractor.py`의 결함이 아니라 매니페스트 누락 때문이므로, 테스트 실행 전 `pip install Pillow`(또는 공유 문서 갱신 반영 후 `pip install -e .`)로 해소할 것.

### AC-6. 안정성
8. 이 함수는 입력 `pypdf_page`를 읽기 전용으로만 사용하며 어떤 상태도 변경하지 않는다(같은 페이지에 대해 여러 번 호출해도 결과가 동일).
9. `pdf_to_hwpx.pdf_reader.ir.ImageBlockIR`, `pdf_to_hwpx.pdf_reader.loader.PdfDocument`를 수정 없이 그대로 import해서 쓰고 있음을 코드 리뷰로 확인 가능(범위 외 파일 미접촉).

---

## 6. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 일괄 반영)

`docs/harness/traceability.md`에 아래 갱신을 요청한다 (직접 수정하지 않음, 병렬 호출 규칙):

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-003 | 작업 단위 | unit-2 |
| REQ-003 | 구현 상태 | Implemented — 단, bbox는 pypdf API 한계로 "페이지 전체 크기 폴백"이라는 알려진 근사치 한정(1-3절/AC-2 참고). 05단계 완료, 06단계 단위테스트 대기 |

추가로 아래 두 건은 REQ-003과 별개로 **오케스트레이터 판단이 필요한 항목**이라 함께 남긴다(어느 항목도 이 unit이 임의로 처리하지 않음):

1. **매니페스트 갱신 필요(중요)**: `pyproject.toml`의 `dependencies`에 `Pillow`(또는 `pypdf[image]` extra)를 추가해야 한다 — 그렇지 않으면 이미지가 있는 PDF에서 `image_extractor.extract_image_blocks`가 `ModuleNotFoundError`로 실패한다(1-5절/AC-5 근거). 이 파일은 이 unit의 범위 밖(공유 매니페스트)이라 직접 수정하지 않았다. 버전 제약은 근거 없이 지어내지 않기 위해 구체적 하한/상한을 제안하지 않으며, 오케스트레이터/다음 담당 unit이 03 §2-1과 동일한 방식(라이선스 확인 등, Pillow는 HPND/MIT 계열 허용적 라이선스)으로 확정하는 것을 권장한다.
2. **`ir.py`/`hwpx_kernel/schema.py`(unit-4) 검토 요청**: `ImageBlockIR.bbox`가 지금은 항상 페이지 전체 크기 폴백값이라는 사실을, unit-7(이미지 임베딩)·unit-8(오케스트레이터)·unit-14(품질 리포트)가 알고 있어야 한다. 특히 unit-14가 다루는 `ConversionWarning`에 이미지 배치 위치가 근사값임을 알리는 경고 코드(예: `IMAGE_BBOX_APPROXIMATED`)를 추가하는 것을 제안한다(03 §4-1 `ConversionWarning.code` 예시 목록에는 아직 없음). 이 unit은 `ir.py`/`hwpx_kernel/schema.py`가 파일 범위 밖이라 직접 반영하지 않았다.

추가로 `decisions.md` 갱신 요청은 없음(이번 unit에서 규칙 A 질문을 발동한 사례 없음 — 1-3절/1-4절/1-5절의 판단은 "합리적으로 정하고 note에 명시"/"한계로 명시하고 대안 제시"라는 이번 호출 지시문 범위 안에서 자체 결정 및 사실 기록).

---

## 7. 재작업(2026-09-28) — 06단계 DEF-001/DEF-002(Critical) 반려에 따른 재설계

- 트리거: 06-unit-tester가 `docs/harness/units/unit-2-test.md`(FAIL 판정)와 `tests/pdf_reader/test_image_extractor.py`로 실제 PDF에서 재현한 결함 2건(DEF-001, DEF-002, 둘 다 Critical). 이 절이 그 재작업 산출물이다.
- 속도 트랙: **L3(변경 없음)** — 이번 재작업 호출 지시문에 트랙 재지정이 없어 1절에 기록된 기존 L3를 그대로 유지한다. 05~07단계 절차 자체는 트랙과 무관하게 동일(ORCHESTRATOR.md 1장)하므로 이번 재작업도 게이트 1·2를 정식으로 다시 통과한다(아래 7-5/7-6).
- 병렬 실행 정보: 이 호출과 동시에 unit-1 재작업(06 반려에 따른 별도 재작업, `pdf_to_hwpx/pdf_reader/text_extractor.py`)이 진행 중이었다. 파일 범위가 겹치지 않아(이 재작업은 `pdf_to_hwpx/pdf_reader/image_extractor.py` 단일 파일만 수정) 충돌 없음.
- 수정 파일: `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일 전면 재작성(bbox 폴백·`is_inline`/`is_displayed` 제외 로직 등 결함과 무관한 부분은 지시문대로 그대로 유지). `ir.py`/`pyproject.toml`/테스트 파일은 건드리지 않음.

### 7-1. 근본 원인 재확인 (pypdf 6.19.0 소스 직접 확인, 추측 없음)

- `StreamObject._data`(`pypdf/generic/_data_structures.py`)는 PDF에 물리적으로 저장된 스트림 바이트를 **어떤 필터도 적용하지 않은 채** 그대로 들고 있다(`initialize_from_dictionary`가 `__streamdata__`를 그대로 대입, 필터 해석은 이 시점에 전혀 일어나지 않음).
- `EncodedStreamObject.get_data()`(`pypdf_page.images`가 내부적으로 호출하는 경로)만 `pypdf/filters.py::decode_stream_data`를 통해 필터를 해석한다. 이 함수를 직접 읽은 결과:
  - `DCTDecode.decode()`/`JPXDecode.decode()`는 **항등함수**(`return data`) — 즉 DCT/JPX는 `get_data()` 단계에서는 전혀 변형되지 않는다. "재인코딩"은 그 *이후* `pypdf/generic/_image_xobject.py::_xobj_to_image()`가 Pillow `img.save(..., quality="keep" 등)`으로 다시 저장하는 마지막 단계에서만 발생한다(DEF-002의 정확한 발생 지점).
  - `CCITTFaxDecode.decode()`는 pypdf가 직접 합성한 TIFF 헤더를 원본 데이터 앞에 덧붙인다(Pillow가 아니라 pypdf 자신의 코드이지만, 이 역시 "원본 스트림 그대로"는 아니다).
  - `JBIG2Decode.decode()`는 외부 `jbig2dec` 바이너리를 서브프로세스로 호출해 PNG로 변환한다(설치 안 되어 있으면 `DependencyError`).
  - `FlateDecode`/`LZWDecode`로 디코드된 결과(원시 픽셀 샘플)는 `_xobj_to_image()`의 마지막 분기에서 Pillow로 새 PNG/TIFF 파일로 재인코딩된다(DEF-001의 정확한 발생 지점).

### 7-2. 새 구현 — `/Resources/XObject` 직접 순회, 필터 무해석

`extract_image_blocks`는 이제 두 경로로 나뉜다:

1. **`_extract_resource_xobject_images`** (Do-참조 이미지, DEF-001/002가 재현된 경로, 이번 재작업의 핵심): `pypdf_page["/Resources"]["/XObject"]`를 직접 순회하며, 각 이미지 XObject의 `._data`(위 7-1의 원본 그대로 필드)를 **어떤 필터 디코딩도, Pillow도 거치지 않고** 그대로 `raw_bytes`에 담는다. "실제로 그려지는지"(`is_displayed`) 판정은 pypdf가 이미 만들어 둔 `page._content_stream_images` 캐시(`page._parse_images_from_content_stream()`, `pypdf/_page.py` 6.19.0 소스로 직접 확인 — `PageObject._get_image()`가 `is_displayed`를 판정하는 것과 동일한 방식)를 재사용해 그대로 유지했다 — 지시문이 요청한 대로 이 로직 자체는 건드리지 않았다.
2. **`_extract_inline_images`** (BI/ID/EI 인라인 이미지): `/Resources/XObject`에 선언되지 않아 위 방식으로는 찾을 수 없다. DEF-001/002 둘 다 Do-참조 XObject로 재현되었고 인라인 경로는 이번 결함 재현 범위 밖이라, 기존 pypdf 콘텐츠 스트림 파서가 만든 `ImageFile` 캐시(Pillow 경유, 재인코딩 위험 그대로 남음)를 계속 사용한다 — **알려진 한계**로 아래 7-4에 명시.

`image_format`은 `/Filter`(마지막 필터, 배열이면 배열의 마지막 항목)의 **이름만으로** 결정한다(`_raw_bytes_and_format`) — 필터를 실제로 해석하지 않으므로 pypdf 자신의 디코더조차 거치지 않는다.

### 7-3. 필터별 분류 (모듈 docstring/코드 상단 표와 동일, 근거 요약)

| 필터 | 분류 | `image_format` | raw_bytes 보장 |
|---|---|---|---|
| `/DCTDecode` | 완결된 이미지 코덱 | `jpeg` | 원본 스트림과 바이트 단위로 항상 동일 (모호함 없음) |
| `/JPXDecode` | 완결된 이미지 코덱 | `jp2` | 동일 |
| `/CCITTFaxDecode` | 완결된 이미지 코덱(지시문 기준) | `ccitt` | 동일 — 단, 이 원본 비트스트림 자체는 너비/행수 등 외부 파라미터 없이는 단독으로 뷰어가 열 수 있는 파일이 아님(하단 7-4 잔여 위험) |
| `/JBIG2Decode` | 완결된 이미지 코덱(지시문 기준) | `jbig2` | 동일 — CCITT와 같은 잔여 위험 |
| `/FlateDecode`, `/LZWDecode`, `/RunLengthDecode`, 필터 없음 | 원시 픽셀 샘플(원래 "이미지 파일"이 존재한 적 없음) | `raw-flate`/`raw-lzw`/`raw-runlength`/`raw-samples` | PDF에 저장된 스트림 그대로(압축 해제도, 재인코딩도 하지 않음) — **단, 이것이 REQ-003이 의도한 "정답"인지는 7-6 질문 목록 참고** |

**로컬 검증(6단계 재검증 전 자체 확인, `.harness-tmp/scratch_05_unit2_rework/`에서 수행 후 삭제 완료)**: 06단계 테스트 파일의 픽스처 생성 로직과 동일한 패턴(pypdf 저수준 API)으로 독립적으로 재구성해 직접 실행한 결과 —
  - DEF-002 재현 이미지(10x10 그라디언트 JPEG, `/DCTDecode`): `raw_bytes`가 원본 JPEG 파일과 **바이트 단위로 완전히 동일**, `image_format == "jpeg"`. **DEF-002 해소 확인.**
  - DEF-001 재현 이미지(4x3 원시 픽셀을 zlib 압축한 `/FlateDecode`): `raw_bytes`가 PDF에 실제로 저장돼 있던 **압축 스트림 바이트와 완전히 동일**(더 이상 합성 PNG 아님, PNG 시그니처로 시작하지 않음 확인). 단, 압축 해제된 원시 픽셀 바이트와는 당연히 다르다(compressed != decompressed는 논리적으로 동시에 성립 불가) — 기존 `test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`가 "and"로 두 조건을 모두 요구하고 있어, 이 설계 선택(스트림 그대로 보존)을 반영하려면 06단계가 그 두 assert를 "or"로(또는 이번 설계 선택에 맞춰 압축 스트림 쪽만 남기도록) 조정해야 한다 — 코드 결함이 아니라 06 테스트 자체가 특정 설계(압축 해제 후 픽셀 보존)를 전제로 작성돼 있었기 때문(테스트 파일은 이 unit의 파일 범위 밖이라 직접 수정하지 않음).
  - 기존 통과 케이스(TC-001/002/004/005/010/011/012/013/014, idempotency, `_detect_image_format` 화이트박스 10종) 전부 동일하게 통과 재확인.
  - **행동 변화(회귀 아님, 설계상 의도된 결과) — 06단계에 반드시 전달**: `test_extract_image_blocks_propagates_exception_for_corrupted_image_stream`(TC-021, 기존 PASS)이 이제는 예외를 던지지 않는다. 이전 구현은 Pillow가 손상된 JPEG를 열려다 `UnidentifiedImageError`를 던지는 것을 "우연히" 전파했을 뿐인데, 새 구현은 Do-참조 이미지 경로에서 Pillow/필터 디코딩 자체를 전혀 수행하지 않으므로(=REQ-003 "재인코딩 없이 그대로") 손상 여부와 무관하게 저장된 바이트를 그대로 반환한다. 이는 코드 결함이 아니라 "원본 바이트를 검증 없이 그대로 추출한다"는 이번 재설계의 핵심 취지와 정확히 일치하는 의도된 변화다 — 이미지 유효성 검증이 필요하다면 그것은 이 함수가 아니라 이 데이터를 실제로 사용하는 후속 단계(unit-7 등)의 책임으로 넘어간다고 판단했다. 06단계가 이 테스트를 그대로 재실행하면 FAIL로 보일 것이므로, "코드 반려 사유"가 아니라 "테스트 기대값 갱신 필요"로 처리해야 한다.

### 7-4. 알려진 한계 (지어내지 않고 명시)

1. **인라인 이미지는 여전히 Pillow 재인코딩 경로를 탄다** — DEF-001/002와 동일한 성격의 바이트 불일치 위험이 인라인 이미지에는 남아 있다. 인라인 이미지를 저수준으로 추출하려면 콘텐츠 스트림의 BI/ID/EI 토큰을 직접 재파싱하는 별도 파서가 필요한데, pypdf는 파싱 도중 이미 `_xobj_to_image()`를 호출해 원본 스트림 객체(디코드 전 raw 바이트)를 함수 스코프 밖으로 노출하지 않는다(소스 확인, `pypdf/_page.py::_parse_images_from_content_stream`) — 이번 재작업 지시문의 파일 범위(`image_extractor.py` 1개 파일)와 우선순위(DEF-001/002는 둘 다 Do-참조 XObject로 재현됨)를 감안해 이번에는 다루지 않았다. 07/08단계 이전에 재검토가 필요하면 별도 unit/재작업으로 분리해야 한다.
2. **CCITTFaxDecode/JBIG2Decode의 원본 비트스트림은 그 자체로 완결된 "파일"이 아니다** — 지시문이 이 둘을 "완결된 이미지 코덱"으로 분류해 원본 스트림 보존을 명확한 방향으로 지시했으므로 그대로 따랐지만, 실제로는 너비/행수(CCITT) 또는 페이지 연관 정보(JBIG2)가 없으면 범용 뷰어가 단독으로 열 수 없다. `ImageBlockIR`에는 이런 보조 메타데이터 필드가 없어(공유 계약, 파일 범위 밖) 이번 unit에서 보강하지 않았다 — unit-7(HWPX 이미지 임베딩) 착수 전에 이 문제를 인지해야 한다(7-6 질문 목록에도 포함).
3. **필터가 여러 개 연쇄된 경우(예: `[/ASCII85Decode, /DCTDecode]`, 실무에서 극히 드묾)**: `raw_bytes`는 항상 가공 없는 원본 스트림 전체이고 `image_format`은 배열의 마지막 필터만 본다 — 즉 이 드문 경우 `raw_bytes`가 아직 전송용 필터(ASCII85 등)로 감싸인 상태일 수 있다. 실제 재현 테스트가 없어 추측성 처리 로직을 추가하지 않았다(과설계 방지) — 실제 PDF에서 이 패턴이 보고되면 그때 좁혀서 대응하는 것이 낫다고 판단했다.
4. Pillow 의존성(1-5절)은 인라인 이미지 경로에서만 실제로 필요해졌다(Do-참조 경로는 이제 Pillow를 전혀 호출하지 않는다) — 그렇다고 `pyproject.toml`의 `Pillow` 의존성을 제거하자는 것은 아니다(인라인 경로가 여전히 필요로 함, 매니페스트는 공유 자원이라 이번에도 직접 수정하지 않음).

### 7-5. 게이트 1 — 정적 분석/린트 (재확인)

- 프로젝트에 lint/type-check/formatter 설정 없음을 재확인(루트에 `ruff`/`flake8`/`mypy`/`pylint`/`.pre-commit-config.yaml` 없음).
- `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` — 컴파일 성공.
- 병렬 실행 중인 unit-1 재작업의 코드로 인한 실행 실패 없음(이 unit의 파일만 컴파일 확인, 별도 실패 없어 격리 보고 대상 없음).

### 7-6. 게이트 2 — 자체 코드 리뷰 체크리스트 (재작업 기준)

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — REQ-003(재인코딩 없는 원본 바이트)을 DCT/JPX/CCITT/JBIG2에 대해 명확히 만족(모호함 없음, 지시문 근거). FlateDecode류는 "원본 스트림 그대로 보존"으로 REQ-003의 문자적 요구는 만족시켰으나, 그 결과물이 "이미지로 재구성 가능한가"는 별도 문제라 7-6-질문 목록으로 남김(임의 확정 안 함).
- [x] 에러 처리가 누락된 경로가 없는가 — `_raw_bytes_and_format`이 `_data` 속성 자체가 없는 비정상 스트림 구조를 만나면 `PdfReadError`를 명시적으로 발생시켜 삼키지 않는다. PDF 구조 자체가 깨진 경우(`.get_object()` 해석 실패 등)의 pypdf 예외도 그대로 전파된다(변경 없음). 다만 7-3에서 밝힌 대로 "이미지 내용 자체의 유효성"(손상된 JPEG 등)은 더 이상 이 함수 책임이 아니게 됐다 — 의도된 설계 변경이며 삼킨 예외가 아니다(애초에 검증을 시도하지 않음).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 변경 없음(unit-0 `loader.py`가 PDF 구조 자체는 이미 검증한 상태로 전달, 1-3절/1-5절과 동일 전제).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성이 있다면 실존 패키지인지 확인했는가 — 신규 의존성 추가 없음(기존 `pypdf`만 사용, `pathlib`는 표준 라이브러리). Pillow는 이번에도 새로 추가하지 않았고(이미 매니페스트에 있음), 오히려 Do-참조 경로에서는 더 이상 사용하지 않게 됨(7-4-4).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 재작성. `ir.py`/`loader.py`/`pyproject.toml`/테스트 파일 어느 것도 수정하지 않았다. 지시문이 그대로 두라고 명시한 bbox 폴백 계산식과 `is_displayed`/`is_inline` 판정 자체의 의미(무엇을 포함/제외하는가)는 그대로 보존했다(구현 경로만 Pillow를 우회하도록 바꿈).

### 7-7. 질문 목록 (규칙 A-3 — 오케스트레이터 결정 필요, 임의로 확정하지 않음)

**Q1. FlateDecode/LZWDecode/RunLengthDecode/필터 없음(원시 픽셀 샘플) 이미지에서 REQ-003 "재인코딩 없이 그대로 추출"의 의미**는 다음 중 무엇인가?

- (a) **이번 재작업이 채택한 안**: PDF에 저장된 스트림 바이트를 압축 해제조차 하지 않고 그대로 보존(`image_format="raw-flate"` 등). 장점: REQ-003의 문자적 요구(바이트 보존)를 가장 엄격하게 만족, Pillow 의존 없음. 단점: 결과물이 그 자체로는 뷰어가 열 수 있는 "이미지 파일"이 아니다 — 너비/높이/색공간/BitsPerComponent(모두 PDF XObject 딕셔너리에는 있지만 `ImageBlockIR`에는 없음)가 있어야 unit-7이 나중에 실제 이미지로 재구성할 수 있다.
- (b) PDF 자체의 제네릭 필터(Flate/LZW/RunLength — Pillow 아님)만 풀어 원시 픽셀 샘플을 얻고, 표준 이미지 컨테이너(PNG 등)로 감싸는 것은 이 unit이 아니라 후속 unit(예: unit-7, 또는 ir.py 확장 후 별도 변환 단계)의 책임으로 명시적으로 넘긴다 — 이 경우도 (a)와 마찬가지로 `ImageBlockIR`에 너비/높이/색공간 메타데이터가 필요하다.
- (c) 이전처럼 Pillow로 표준 이미지 파일을 합성하되, 06단계가 지적한 "재인코딩"이라는 사실을 quality_report 경고(예: `IMAGE_RAW_SAMPLES_REENCODED`)로 사용자에게 투명하게 알리는 방식으로 REQ-003의 "정신"(사용자가 인지하지 못한 채 원본이 훼손되지 않아야 한다)만 지키고 "문자"(바이트 보존)는 이 필터 계열에 한해 예외로 허용한다 — 단, 이 경우 DEF-001이 사실상 "결함"에서 "합의된 예외"로 재분류돼야 하므로 decisions.md 기록이 필요하다.

이 판단은 (1) `ir.py`(공유 계약) 확장 필요 여부를 좌우하고, (2) unit-7(HWPX 이미지 임베딩)의 설계 방향을 결정하며, (3) 실무에서 이 필터 계열이 "JPEG가 아닌 대다수 래스터 이미지"에 해당한다는 06단계의 지적(영향 범위가 넓음)까지 고려하면 되돌리기 어려운 결정이라 판단해, 임의로 (a)를 최종안으로 확정하지 않고 여기 남긴다(현재 코드는 잠정적으로 (a)를 구현한 상태 — 즉시 동작은 하되, (b)/(c)로 바뀌면 재수정 필요).

**Q2.** Q1이 (a) 또는 (b)로 결정될 경우, `ImageBlockIR`에 `width`/`height`/`color_space`/`bits_per_component` 같은 필드를 추가해야 하는가(ir.py 변경, 공유 계약 — unit-1/3/4와 조율 필요)?

### 7-8. 6단계 테스터를 위한 갱신된 인수 조건 (기존 5절 AC-1/AC-2를 아래로 대체, AC-3~AC-6은 변경 없음)

**AC-1(개정). 기본 추출 (REQ-003)**
1. Do-참조(비인라인) 이미지에 대해 `extract_image_blocks(page)`가 그 이미지 개수만큼의 `ImageBlockIR`을 반환한다.
2. `/DCTDecode`/`/JPXDecode`/`/CCITTFaxDecode`/`/JBIG2Decode` 필터로 인코딩된 이미지는 `raw_bytes`가 PDF에 저장된 원본 스트림과 **항상, 예외 없이** 바이트 단위로 완전히 동일해야 한다(더 이상 "특정 이미지 내용에서만" 같은 단서가 붙지 않음 — DEF-002 재발 여부의 직접 판정 기준).
3. `/FlateDecode`/`/LZWDecode`/`/RunLengthDecode`/필터 없음 이미지는 `raw_bytes`가 PDF에 저장된 스트림 바이트(압축된 상태 그대로, 또는 필터가 없으면 원시 그대로)와 완전히 동일해야 한다 — **압축 해제된 픽셀이나 Pillow가 합성한 PNG와 같아야 한다는 뜻이 아니다**(DEF-001 재발 여부의 직접 판정 기준, 단 이 의미 자체가 7-7 Q1 미결 상태임을 6단계도 인지할 것).
4. `image_format`은 실제 `/Filter` 이름에서 결정한 소문자 문자열이다: `"jpeg"`/`"jp2"`/`"ccitt"`/`"jbig2"`(완결 코덱), `"raw-flate"`/`"raw-lzw"`/`"raw-runlength"`/`"raw-samples"`(원시 픽셀 계열), 그 외/미해석 시 `"unknown"`.
5. 인라인 이미지는 이전과 동일하게 pypdf/Pillow 경유 경로를 그대로 사용한다(7-4-1) — `raw_bytes` 바이트 동일성을 인라인 이미지에는 요구하지 말 것(알려진 한계, 결함 아님).

**AC-2. bbox** — 변경 없음(기존 5절 그대로, 페이지 전체 크기 폴백).

**추가 확인 사항(6단계 회귀 시 필수)**
6. 기존 `test_extract_image_blocks_propagates_exception_for_corrupted_image_stream`(TC-021)은 이제 예외를 던지지 않는다(7-3 "행동 변화" 참고) — 이를 "회귀"로 보고하지 말고, 테스트 기대값 자체를 갱신해야 하는 항목으로 분류할 것.
7. 기존 `test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`의 두 assert(압축 스트림과의 동일성, 압축 해제된 픽셀과의 동일성)는 동시에 참일 수 없다(논리적으로 상호 배타) — 이번 설계 선택(7-2/7-3)에서는 첫 번째(압축 스트림과 동일)만 참이 된다. 06단계가 이 테스트를 어떻게 재작성할지는 7-7 Q1의 최종 결정에 따라 달라질 수 있다.

---

## 8. 인계 우선순위 (06단계 재검증용)

1. **최우선**: DEF-001/DEF-002 재현 테스트를 새 구현으로 재실행해 실제로 해소되는지 직접 확인(이 note 7-3의 자체 확인은 참고용이며, 06단계의 공식 재검증을 대체하지 않음).
2. 전체 회귀(기존 28 PASS 케이스) 재실행 — 단, TC-021은 7-8-6, DEF-001 테스트 자체는 7-8-7에 따라 기대값 조정이 필요할 수 있음을 감안.
3. 7-7의 질문 목록(Q1/Q2)을 오케스트레이터에게 전달 — unit-7 착수 전에 결정 필요.
4. 인라인 이미지 경로(7-4-1)의 잔존 위험을 unit-7/8/14에 알릴 것(기존 5절 "공유 문서 갱신 요청"의 취지와 동일한 결을 유지).

## 공유 문서 갱신 요청 (재작업분 — 병렬 웨이브 규칙, 직접 수정하지 않음)

`docs/harness/traceability.md` REQ-003 행 갱신 요청:

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-003 | 단위테스트(unit-2-test) | 06단계 재검증 대기 — 05단계 재작업 완료(`pdf_to_hwpx/pdf_reader/image_extractor.py` 전면 재작성, 이 note 7절), DEF-001/DEF-002 자체 확인상 해소됨(7-3). 공식 재검증은 06단계 책임. |
| REQ-003 | 구현 상태 | 재작업 필요 → **05단계 재작업 완료, 06단계 재검증 대기**로 갱신. 단, 7-7 Q1(FlateDecode류 원시 픽셀 샘플의 REQ-003 해석)이 미결이라 "완전 Implemented"로는 표기하지 말 것 — 오케스트레이터가 Q1을 결정한 뒤에만 최종 Implemented로 전환 권고. |
| REQ-003 | 비고 | 추가: "**05단계 재작업(2026-09-28)**: DEF-001/002는 `/Resources/XObject` 저수준 순회 + Pillow/필터디코더 완전 우회로 해소(DCT/JPX/CCITT/JBIG2는 원본 스트림과 바이트 단위 동일 보장). 단, FlateDecode류(원시 픽셀 샘플) 처리 방향과 인라인 이미지 잔존 위험은 unit-2-note.md §7-7/§7-4-1 질문/한계 참고, unit-7 착수 전 결정 필요." |

추가로 `decisions.md` 갱신 요청 (신규, 이번 재작업에서 규칙 A-3 질문 발동):

| 질문 | 배경 | 후보안 | 영향 |
|---|---|---|---|
| FlateDecode/LZWDecode/RunLengthDecode/무필터 이미지에서 REQ-003 "재인코딩 없이 추출"의 의미 확정(unit-2-note.md §7-7 Q1 원문 참고) | 06단계 DEF-001 반려, PDF 안에 "원본 이미지 파일"이 존재한 적 없는 필터 계열이라 03 §1-3/§3-1이 명시하지 않은 영역 | (a) 스트림 그대로 보존(현재 잠정 구현, `ImageBlockIR` 메타데이터 부족) / (b) 픽셀까지 풀고 컨테이너화는 후속 unit 책임으로 위임 / (c) 기존처럼 Pillow 재인코딩 허용 + quality_report 경고로 투명화 | unit-7 설계 방향, `ir.py` 확장 필요 여부, 실무 영향 범위(비-JPEG 래스터 이미지 대다수) |

이 표의 결정이 나오면 `docs/harness/decisions.md`에 DEC 번호를 부여해 정식 기록해 줄 것을 요청한다(이 unit은 직접 기록하지 않음, 병렬 호출 규칙).

---

## 9. 재작업 2차(2026-09-28, DEC-028 반영)

- 트리거: §7-7 Q1(FlateDecode/LZWDecode/RunLengthDecode/필터 없음 -- "원시 픽셀 샘플" 계열 이미지에서 REQ-003을 어떻게 해석할지)을 오케스트레이터가 **DEC-028**로 결정(`docs/harness/decisions.md` DEC-028 참고). 이 절이 그 재작업 산출물이다.
- 속도 트랙: **L3(변경 없음)** -- 이번 호출 지시문에도 트랙 재지정이 없어 기존 L3를 유지한다.
- 병렬 실행 여부: 이번 호출은 병렬 웨이브가 아니라 **단독(순차) 호출**이었다(호출 프롬프트에 "병렬 웨이브" 명시 없음). 파일 범위도 단일 파일(`pdf_to_hwpx/pdf_reader/image_extractor.py`)로 한정.
- 수정 파일: `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 수정(신규 함수/상수/예외 클래스 추가, `_raw_bytes_and_format` 시그니처에 `resources` 매개변수 추가 -- 내부 전용 헬퍼라 공개 계약 `extract_image_blocks(pypdf_page)` 시그니처는 변경 없음). `ir.py`/`pyproject.toml`/테스트 파일은 지시문대로 손대지 않았다. DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode 경로(1차 재작업 §7)는 이번에 전혀 수정하지 않았다(코드 리뷰로 확인 가능 -- `_SELF_CONTAINED_CODEC_FILTER_TO_FORMAT` 딕셔너리와 그 분기 로직은 문자 그대로 그대로임).

### 9-1. 구현 방식 요약

`_raw_bytes_and_format(xobj, resources)`가 이제 3갈래로 분기한다:
1. **완결된 이미지 코덱**(DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode): 기존 그대로 `xobj._data`(가공 없는 원본 스트림)를 반환. 변경 없음.
2. **원시 픽셀 샘플**(FlateDecode/LZWDecode/RunLengthDecode/필터 없음): `_synthesize_lossless_png(xobj, resources)`를 호출해 무손실 PNG를 합성하고, `image_format="png"`로 반환. **이번 재작업의 핵심.**
3. **그 외 인식 못하는 필터**: 기존과 동일하게 원본 `_data`를 그대로 반환하고 `image_format="unknown"`(추측성 처리 없음, 안전한 기본값 유지).

`_synthesize_lossless_png`의 처리 순서(지시문 1~4단계 그대로 구현):
1. `xobj.get_data()`로 표준 필터(Flate/LZW/RunLength, Predictor 포함)를 해제해 원시 픽셀 바이트를 얻는다 -- pypdf 표준 디코더만 쓰고 Pillow는 이 단계에서 전혀 관여하지 않는다(손실 없는 표준 압축 해제, pypdf 소스 확인 완료, `EncodedStreamObject.get_data()`가 `decode_stream_data()`를 호출).
2. `/Width`/`/Height`/`/BitsPerComponent`/`/ColorSpace`(`/Indexed` 팔레트 포함, 리소스 이름으로 간접 참조된 ColorSpace도 `resources["/ColorSpace"]`에서 조회)를 읽어 Pillow `Image.frombytes()`에 필요한 `(mode, rawmode, palette)`를 결정한다(`_resolve_pixel_layout`/`_resolve_indexed_layout`). `/Decode` 배열은 기본값 또는 전 채널 완전반전만 해석해 반영한다(`_maybe_apply_inverted_decode`).
3. `image.save(buffer, format="PNG")`로 무손실 PNG를 합성한다(품질 옵션 등 손실 파라미터를 전혀 쓰지 않음 -- PNG 포맷 자체가 무손실).
4. `_verify_png_round_trip_or_raise(png_bytes, image)`가 방금 만든 PNG를 `Image.open()`으로 다시 열어 크기/모드/픽셀 바이트(`tobytes()`)/(인덱스 컬러면 팔레트까지)를 원본으로 구성한 `image` 객체와 비교한다. 하나라도 다르면 **조용히 반환하지 않고** `_PngRoundTripVerificationError`(정의 위치: 이 파일 내부, `PdfReadError` 하위 클래스)를 던진다.

### 9-2. 지원 범위(과설계 방지, 근거)

의도적으로 다음으로 한정했다(전체 PDF ColorSpace 스펙을 다 구현하지 않음 -- REQ-003/DEC-028이 요구하는 "올바르게 해석"의 실무적으로 흔한 범위만 다룸):

| 항목 | 지원 | 미지원 시 처리 |
|---|---|---|
| ColorSpace | `/DeviceGray`/`/CalGray`(1채널), `/DeviceRGB`/`/CalRGB`(3채널), `/ICCBased`(`/N`으로 채널수 판별), `/Indexed`(base가 위 둘 중 하나), 리소스 이름 간접참조(`/CS0` 등) | `_UnsupportedRawImageEncodingError` |
| `/DeviceCMYK` | **의도적으로 미지원**(직접이든 Indexed의 base든) | `_UnsupportedRawImageEncodingError` |
| BitsPerComponent | Gray/Indexed: 1/2/4/8, RGB: 8 | `_UnsupportedRawImageEncodingError` |
| `/Decode` | 기본값(항등) 또는 전 채널 완전반전(`[1 0]` 반복) | `_UnsupportedRawImageEncodingError`(인덱스 컬러의 사용자정의 Decode 포함) |

**DeviceCMYK을 지원하지 않은 이유(중요, 규칙 A-3 자체판단 근거)**: PNG 포맷 자체가 CMYK 색공간을 표현할 수 없다는 것을 Pillow로 직접 확인했다(`Image.new("CMYK", ...).save(format="PNG")` -> `OSError: cannot write mode CMYK as PNG`). CMYK 원시 픽셀을 PNG로 담으려면 RGB로 색 변환해야 하는데, 이 변환 자체가 근사치를 만드는 손실 있는 색 변환이라(단순 비트 재배치가 아님) "무손실 PNG" 요건(지시문 3번)과 정면으로 상충한다. 억지로 근사 변환해 조용히 반환하기보다, 이 경우를 명시적으로 실패시키는 쪽이 DEC-028의 "증명되지 않은 손실 재발 방지" 취지에 맞다고 판단했다 -- 실무에서 CMYK 원시(비-JPEG) 래스터 이미지는 드물기도 하다(대다수 CMYK 이미지는 DCTDecode/JPEG로 저장되며, 그 경로는 이미 완결 코덱으로 원본 그대로 보존됨, 이번 재작업 대상 아님).

BitsPerComponent 관련: RGB/CMYK 16비트, Indexed 외 다채널 저비트심도 등은 실무에서 이 필터 계열(비-JPEG 임베디드 래스터) 안에서도 드물어 지원 범위에서 제외했다 -- 필요해지면 `_GRAY_RGB_MODE_TABLE`/`_INDEXED_BPC_TO_RAWMODE`에 항목을 추가하는 방식으로 점진적으로 넓힐 수 있게 설계했다(과설계 방지, YAGNI).

**`/Decode` 반전 지원이 BitsPerComponent와 무관하게 적용되는 이유**: `Image.frombytes(mode, size, data, "raw", rawmode)` 시점에 Pillow가 이미 원시 샘플 값을 0..255 범위로 선형 스케일링해 둔다는 것을 로컬로 직접 확인했다(예: 2bpc 샘플 0/1/2/3 -> 0/85/170/255, 4bpc 샘플 0/15 -> 0/255, 1/8 -> 17/136 -- 전부 `255/maxval` 배율의 정확한 선형 관계). 이 정확한 선형성 덕분에, 스케일링 이후의 0..255 도메인에서 `ImageOps.invert()`(단순 `255-x`)를 적용하는 것이 PDF Decode `[1 0]`이 원래 의도하는 "정규화된 샘플 값(`v/maxval`)의 반전"과 수학적으로 완전히 등가임을 확인했다(2/4/8bpc Gray, 1bpc Gray(모드 `"1"`, 내부적으로 비트 자체를 반전하는 것과 동치) 각각 실제 픽셀 단위 비교로 로컬 검증 완료, 10절 참고).

### 9-3. 팔레트(인덱스 컬러) 변환

`/Indexed [base hival lookup]`에서 `lookup`은 스트림(자체 필터 가능, `get_data()`로 표준 해석)일 수도, PDF 문자열 리터럴(`get_original_bytes()`로 원본 바이트 추출 -- pypdf가 파싱 시 내용에 따라 `TextStringObject`/`ByteStringObject` 중 어느 쪽으로 판별할지 달라짐을 로컬로 직접 확인, `bytes(x)`만으로는 `TextStringObject`에서 "encoding 없는 문자열" 오류가 남을 재현·수정했다)일 수도 있다. base가 `/DeviceRGB`면 lookup 바이트를 그대로 RGB 삼중항으로, `/DeviceGray`면 각 바이트를 `(g,g,g)`로 확장해 Pillow 팔레트로 사용한다. 인덱스 값(픽셀당 실제 저장되는 값) 자체는 원본 그대로 완전 보존되며(왕복 검증이 `getpalette()`까지 비교), 팔레트가 CMYK 기반인 경우는 9-2절과 같은 이유로 미지원 처리한다.

### 9-4. 왕복 검증 실패 처리 방식 -- 지시문 필수 요건에 대한 결정과 근거

지시문이 요구한 "왕복 검증 실패 시 조용히 반환하지 않고 명시적으로 실패를 알린다"에 대해, **예외를 던져 호출자에게 전파하는 방식**을 택했다(이미지를 결과 목록에서 조용히 빼고 로그만 남기는 방식은 채택하지 않음). 근거:
1. 이 모듈은 처음부터(1차 재작업 이전부터) "예외를 삼키지 않는다"는 계약을 갖고 있다(모듈 docstring 최상단 `extract_image_blocks`의 `Raises:` 절, `_raw_bytes_and_format`이 `_data` 속성 부재 시 이미 `PdfReadError`를 던지는 기존 패턴). 새 실패 모드만 조용히 예외로 처리하면 이 파일 안에서 일관성이 깨진다.
2. `ImageBlockIR`(공유 계약, `ir.py`)에는 "이 이미지가 실패했다"는 것을 알릴 필드가 없고, `extract_image_blocks`의 반환 타입은 `list[ImageBlockIR]`뿐이라 그 안에 경고를 실어 보낼 통로 자체가 없다(필드 추가는 이 unit의 파일 범위 밖). 조용히 제외만 하면 "이미지가 원래 없었는지, 있었는데 실패해서 빠졌는지"를 호출자가 구분할 방법이 사라져 REQ-005/REQ-009(부분 실패 안내) 정신에 오히려 어긋난다.
3. 03 §4-2/§5의 "페이지 단위 격리(벌크헤드)는 orchestrator(unit-8)의 책임"이라는 기존 설계 전제와 일관된다 -- 예외가 이 함수 밖으로 전파되면, 향후 unit-8이 페이지 단위로 잡아 `PAGE_SKIPPED` 경고로 전환하거나(현재 이미 동일하게 동작하는 기존 케이스: `_raw_bytes_and_format`의 `_data` 부재, TC-021 이전의 손상 스트림 등), 더 세밀하게는 `_UnsupportedRawImageEncodingError`/`_PngRoundTripVerificationError`를 구분해서 잡아 "이미지 1개만 제외 + 이미지 단위 경고"로 좁혀 처리할 수도 있다.

**알려진 트레이드오프(솔직히 명시)**: unit-8(orchestrator)이 아직 존재하지 않아, 현재 시점에는 이 예외가 페이지 전체를 스킵시키는 결과로 이어질 것이다(이미지 1개 실패가 페이지 전체 텍스트/표까지 함께 누락시킴 -- 과도하게 넓은 실패 반경). 이는 이 unit의 파일 범위(`image_extractor.py` 1개 파일)로는 개선할 수 없는 구조적 한계이며, unit-8 착수 시 `_UnsupportedRawImageEncodingError`/`_PngRoundTripVerificationError`를 개별적으로 잡아 "해당 이미지만 제외 + `ConversionWarning`"으로 좁히는 것을 강력히 권장한다(11절 "공유 문서 갱신 요청"에 반영).

### 9-5. 게이트 1 -- 정적 분석/린트 (재확인)

- 프로젝트에 lint/type-check/formatter 설정 없음을 재확인(루트에 `ruff`/`flake8`/`mypy`/`pylint`/`.pre-commit-config.yaml` 없음 -- 1차 재작업과 동일 결론).
- `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` -- 컴파일 성공.
- 이번 호출은 병렬 웨이브가 아니라 단독 호출이었다(호출 프롬프트에 병렬 웨이브 명시 없음) -- 다른 unit과의 파일 충돌/격리 이슈 없음.

### 9-6. 게이트 2 -- 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 -- DEC-028의 4단계 지시(압축 해제 -> 메타데이터 해석 -> 무손실 PNG 합성 -> 왕복 검증) 그대로 구현했다. 지원 범위 한정(9-2절)은 DEC-028 원문의 "필요 시"라는 표현에 부합하는 합리적 축소로 판단(과설계 방지 원칙, 03 전반의 YAGNI 기조와 일관).
- [x] 에러 처리가 누락된 경로가 없는가 -- 지원 범위 밖 조합은 전부 `_UnsupportedRawImageEncodingError`로 명시적으로 실패하고(9-2절 표), 왕복 검증 실패는 `_PngRoundTripVerificationError`로 명시적으로 실패한다(9-4절). 삼키는 `except`가 이 파일에 전혀 없다(`try/except`는 `Image.frombytes`의 `ValueError`를 잡아 더 명확한 메시지로 재변환(`raise ... from exc`)하는 지점 1곳뿐 -- 예외를 삼키지 않고 원인 체인을 보존한 채 다른 예외로 변환).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 -- 변경 없음(unit-0 `loader.py`가 PDF 구조 자체는 이미 검증한 상태로 전달). 이 함수가 새로 받는 `xobj`의 `/Width`/`/Height`/`/ColorSpace` 등은 PDF 내부 구조체 값이라 "사용자 입력"이 아니라 "신뢰할 수 없는 외부 파일 구조"에 해당하며, 없거나 해석 불가능한 경우 전부 명시적 예외로 처리했다(9-2절 표, 추측성 기본값을 채우지 않음).
- [x] 하드코딩된 시크릿/자격증명이 없는가 -- 없음(순수 이미지 처리 로직).
- [x] 새로 추가한 외부 의존성이 있다면 실존 패키지인지 확인했는가 -- 신규 의존성 추가 없음. `PIL.ImageOps`는 이미 매니페스트에 있는 `Pillow`(1차 재작업 때 이미 등록됨) 패키지의 표준 서브모듈이라 추가 등록 불필요(직접 `import PIL.ImageOps`로 로컬 확인 완료).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 -- `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 수정. DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode 분기, `_extract_inline_images`, bbox 폴백 로직, `_detect_image_format` 등 지시문이 건드리지 말라고 명시한 부분은 문자 그대로 유지했다(코드 리뷰로 확인 가능). `_raw_bytes_and_format`에 `resources` 매개변수를 추가한 것은 같은 파일 내부의 비공개 헬퍼 시그니처 변경이라 공개 계약(`extract_image_blocks(pypdf_page) -> list[ImageBlockIR]`)에는 영향 없다.

### 9-7. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

세션 스크래치 디렉터리(리포지토리 밖)에서 확인 후 스크립트/생성 파일은 리포지토리에 남기지 않았다(`git status --porcelain` 재확인 완료, 신규 파일은 `image_extractor.py` 1개뿐).

1. **왕복검증 통과 사례(필수 요청사항)**:
   - FlateDecode, `/DeviceRGB`, 8bpc, 5x4 임의 그라디언트 픽셀 -> `image_format=="png"`, PNG 시그니처로 시작, 디코드한 픽셀이 원본 원시 픽셀 샘플과 **완전히 동일**함을 직접 비교로 확인.
   - FlateDecode, `/DeviceGray`, 1bpc, `/Decode [1 0]`(반전), 9x3 바둑판 패턴 -> 결과 PNG를 픽셀 단위(`getpixel`)로 검증해 반전이 올바르게 반영됨을 확인.
   - FlateDecode, `/Indexed [/DeviceRGB 4 lookup]`, 4bpc, 6x2 -> 인덱스 값이 원본과 완전히 동일하게 보존됨을 확인.
   - 필터 없음(무필터), `/DeviceRGB`, 8bpc, 3x2 -> 동일하게 왕복검증 통과 확인.
   - 리소스 이름으로 간접 참조된 ColorSpace(`/ColorSpace /CS0`, `resources["/ColorSpace"]["/CS0"] == /DeviceGray`) -> 정상 해석·왕복검증 통과 확인.
2. **명시적 실패 경로가 실제로 동작하는지(필수 요청사항)**:
   - `/DeviceCMYK` 원시 픽셀 이미지(FlateDecode) -> `_UnsupportedRawImageEncodingError`가 실제로 발생함을 확인(조용히 변환/반환되지 않음).
   - `_verify_png_round_trip_or_raise`를 몽키패치로 강제 실패시켜 `extract_image_blocks` 호출 시 `_PngRoundTripVerificationError`가 그대로 전파됨을 확인(왕복검증 실패 경로가 실제로 예외를 던지는 코드 경로임을 실행으로 증명, 인위적으로 재현).
3. **회귀 확인**: DCTDecode(JPEG) 경로는 이번 재작업 전후로 `raw_bytes`/`image_format`이 완전히 동일함을 재확인(회귀 없음). `two_images`(다중 이미지 카운트), `undisplayed`(미표시 제외), `blank_page`(빈 목록), `small_placement`/`inline_image`(bbox 폴백)의 기존 06 테스트 픽스처 빌더 함수를 그대로 재사용해 재실행한 결과 전부 이전과 동일한 결과를 반환함을 확인(로직 변경 없는 경로).
4. **기존 06 테스트 파일(`tests/pdf_reader/test_image_extractor.py`, 1차 재작업 시점 이미 일부 기대값이 낡아 있었음)의 관련 테스트를 직접 재실행(pytest 없이 픽스처 빌더 함수만 재사용)한 결과**:
   - `test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`가 검증하는 픽스처(4x3 `/DeviceRGB` FlateDecode)는 이제 `image_format=="png"`이고, `raw_bytes`가 압축 스트림과도 원시 픽셀과도 **다르다**(PNG 컨테이너이므로 당연) -- 그러나 PNG를 디코드하면 원시 픽셀과 완전히 동일하다. 즉 이 테스트의 두 assert(`raw_bytes == 압축스트림`, `raw_bytes == 원시픽셀`)는 **여전히 둘 다 실패**하지만, 실패의 의미가 1차 재작업 때와 다르다 -- 이번에는 "결함"이 아니라 "PNG 컨테이너로 감싸여 있어 raw 비교가 성립하지 않음"이 원인이다. 10절에 06을 위한 개정된 인수 조건을 남긴다.
   - `test_flate_encoded_raster_image_is_a_freshly_synthesized_png_not_original`(PNG 시그니처로 시작하는지 확인)는 **그대로 통과**한다(우연히도 이번 설계의 최종 산출물도 PNG이기 때문 -- 단, "새로 합성됨" 자체는 이제 결함이 아니라 의도된 기능).
   - `test_dctdecode_jpeg_raw_bytes_can_silently_diverge_from_original_DEF002`(정확히는 이 테스트가 검증하는 픽스처가 이제는 원본과 동일하게 나옴)는 **여전히 해소 상태 유지**(DCT 경로 미변경, 회귀 없음).
   - `test_extract_image_blocks_propagates_exception_for_corrupted_image_stream`(TC-021)은 1차 재작업 때와 동일하게 **예외를 던지지 않는다**(DCT 경로 미변경이므로 동일한 이유로 동일한 상태 유지 -- 새로운 변화 아님).

### 9-8. 6단계 테스터를 위한 갱신된 인수 조건 (AC-1을 아래로 대체, 기존 AC-2~AC-6은 변경 없음)

**AC-1(2차 개정). 기본 추출 (REQ-003, DEC-028)**
1. `/DCTDecode`/`/JPXDecode`/`/CCITTFaxDecode`/`/JBIG2Decode` 이미지: 기존 AC-1(개정, 8절 7-8)과 동일 -- `raw_bytes`가 원본 스트림과 항상 바이트 단위로 완전히 동일.
2. `/FlateDecode`/`/LZWDecode`/`/RunLengthDecode`/필터 없음 이미지(9-2절 지원 범위 내 ColorSpace/BitsPerComponent/Decode 조합): `image_format == "png"`이고 `raw_bytes`는 유효한 PNG 바이트 스트림(PNG 시그니처로 시작)이다. **바이트 비교는 압축 스트림이나 압축 해제된 원시 픽셀과의 직접 비교(`==`)로 하지 말 것** -- 대신 `raw_bytes`를 PNG로 디코드한 뒤(`PIL.Image.open`), 그 픽셀 데이터(`.tobytes()`, 필요 시 `.getpalette()`)가 PDF XObject의 `/Width`/`/Height`/`/BitsPerComponent`/`/ColorSpace`/`/Decode`를 올바르게 해석한 원시 픽셀 값과 일치하는지로 검증할 것(9-7-1절이 이 방법으로 로컬 검증 완료).
3. 위 9-2절 지원 범위를 벗어난 조합(`/DeviceCMYK`, 미지원 BitsPerComponent, 임의의 `/Decode`, ColorSpace 해석 불가)은 `extract_image_blocks` 호출 시 예외(`_UnsupportedRawImageEncodingError`, `PdfReadError`의 하위 클래스)가 발생해야 한다 -- 결과 목록에 조용히 누락되어서는 안 된다.
4. 픽셀 데이터를 올바르게 합성했음에도 왕복 검증이 실패하는 상황(정상 흐름에서는 발생하지 않아야 함, 버그 회귀 테스트용)은 `_PngRoundTripVerificationError`가 발생해야 한다 -- `image_extractor_module._verify_png_round_trip_or_raise`를 몽키패치해 강제로 불일치를 유발하는 화이트박스 테스트로 이 경로 자체를 검증할 것을 권장(9-7-2절 참고).
5. `image_format`은 `"jpeg"`/`"jp2"`/`"ccitt"`/`"jbig2"`(완결 코덱, 변경 없음), `"png"`(원시 픽셀 계열, 신규), `"unknown"`(그 외 인식 못하는 필터, 변경 없음) 중 하나다. 1차 재작업이 썼던 `"raw-flate"`/`"raw-lzw"`/`"raw-runlength"`/`"raw-samples"` 표기는 **더 이상 나타나지 않는다**(DEC-028로 대체됨) -- 06단계가 이 표기를 기대하는 테스트를 작성했다면 갱신 필요.
6. 인라인 이미지는 변경 없음(기존 AC-1-5, 7-8절과 동일 -- 여전히 pypdf/Pillow 경유 경로, `raw_bytes` 바이트 동일성 요구하지 않음).

**추가 확인 사항(6단계 회귀 시 필수)**
7. `test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`은 이번 재작업 이후에도 두 assert가 실패한다(9-7-4절) -- 이는 "결함 재발"이 아니라 "테스트가 여전히 1차 재작업 이전의 설계(압축 스트림 그대로 보존)를 전제로 작성돼 있기 때문"이다. 06단계가 이 테스트를 위 AC-1-2 방식(PNG 디코드 후 픽셀 비교)으로 재작성해야 한다.
8. `test_flate_encoded_raster_image_is_a_freshly_synthesized_png_not_original`은 그대로 통과하지만, 테스트 이름/문서화 취지("결함 증거")는 더 이상 유효하지 않다 -- "PNG로 합성됨"은 이제 결함이 아니라 DEC-028이 의도한 정상 동작이므로, 06단계가 이 테스트의 이름/docstring을 갱신하거나 유지 여부를 판단할 것.
9. TC-021, DEF-002 관련 항목은 8절(1차 재작업)과 동일하게 유지(변경 없음) -- 8절 인수 조건 6/7번 그대로 유효.

---

## 10. 인계 우선순위 (06단계 재검증용, 갱신)

1. **최우선**: 9-8절 AC-1(2차 개정) 1~4번 -- 특히 2번(PNG 왕복 디코드 방식 검증)과 4번(왕복검증 실패 경로의 화이트박스 테스트)을 실제 pytest로 재검증.
2. 9-2절 지원 범위 표에 나열된 각 "미지원" 항목이 실제로 `_UnsupportedRawImageEncodingError`를 던지는지 각각 별도 테스트로 확인(DeviceCMYK은 9-7-2절에서 자체 확인 완료, 나머지 -- 미지원 BitsPerComponent, 임의 Decode 배열, ColorSpace 없음/해석불가 -- 는 06단계가 추가로 검증 권장).
3. 전체 회귀(8절 목록 그대로 유효, 이번에 추가로 9-8-7/8/9 반영).
4. §9-4 "알려진 트레이드오프"(현재는 이미지 1개 실패가 페이지 전체를 스킵시킴)를 unit-8(오케스트레이터, 아직 미착수) 설계자에게 전달 -- 11절 공유 문서 갱신 요청에도 반영.

---

## 11. 공유 문서 갱신 요청 (2차 재작업분 -- 직접 수정하지 않음)

`docs/harness/traceability.md` REQ-003 행 갱신 요청:

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-003 | 단위테스트(unit-2-test) | 06단계 재검증 대기 -- 05단계 2차 재작업 완료(`pdf_to_hwpx/pdf_reader/image_extractor.py`, 이 note 9절), DEC-028(FlateDecode류 무손실 PNG 합성+왕복검증) 반영, 로컬 자체 확인상 왕복검증 통과/실패 경로 둘 다 실제로 동작함을 확인(9-7절). 공식 재검증은 06단계 책임. |
| REQ-003 | 구현 상태 | **05단계 2차 재작업 완료, 06단계 재검증 대기**로 갱신 -- 8절에서 "완전 Implemented 보류" 사유였던 §7-7 Q1이 DEC-028로 해소되었으므로, 06단계 재검증 통과 시 "완전 Implemented"로 전환 가능. |
| REQ-003 | 비고 | 추가: "**05단계 2차 재작업(2026-09-28, DEC-028)**: FlateDecode/LZWDecode/RunLengthDecode/무필터 이미지를 표준 필터로 압축 해제 후 Width/Height/BitsPerComponent/ColorSpace(Indexed 포함)/Decode로 해석해 무손실 PNG로 합성, 합성 직후 왕복 디코드 검증을 통과해야만 반환(`image_format='png'`). DeviceCMYK/미지원 BitsPerComponent/임의 Decode는 명시적 예외(`_UnsupportedRawImageEncodingError`)로 실패, 왕복검증 실패는 `_PngRoundTripVerificationError`로 실패 -- 둘 다 조용히 누락되지 않음(unit-2-note.md §9 참고). 단, 현재 unit-8(오케스트레이터)이 미착수라 이 예외가 페이지 전체 스킵으로 이어지는 알려진 한계 있음(§9-4)." |

`decisions.md` 갱신 요청: **신규 요청 없음** -- DEC-028은 오케스트레이터가 이미 기록 완료했고(호출 지시문 근거), 이번 재작업은 그 결정을 구현으로 해소 확인하는 절차였다. 다만 unit-8 착수 전 참고용으로, §9-4의 "이미지 실패 예외 처리 세분화(개별 이미지 제외 + 이미지 단위 경고)"는 `ir.py`/orchestrator 설계 시점에 규칙 A 질문으로 다시 제기될 가능성이 있다는 점만 여기 남긴다(지금 당장 결정이 필요한 사안은 아님, 정보 전달 목적).

---

## 12. 3차 재작업(2026-09-28) — 07단계 DEF-INT-001(High) 반려에 따른 수정

- 트리거: 06단계에서 unit-2는 Verified/PASS였으나(9절 2차 재작업까지 반영), **07단계(Feature A 통합테스트, `docs/harness/feature-A-integration-test.md`)**가 unit-0~8을 monkeypatch 없이 실제 구현으로 엮어 돌린 결과 **DEF-INT-001(High, Open)**을 발견해 05단계로 반려했다. 이 절이 그 재작업 산출물이다.
- 속도 트랙: **L3(변경 없음)** — 이번 호출 지시문에도 트랙 재지정이 없어 기존 L3를 유지한다(Tier=High, DEC-021, 완화 없음 — 지시문에 명시된 그대로).
- 병렬 실행 여부: **단독(순차) 호출**이었다(호출 프롬프트에 "병렬 웨이브" 명시 없음). 파일 범위도 `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일로 한정(지시문이 명시한 unit-2 확정 파일 범위, 03 §1-3 그대로).
- 수정 파일: `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 수정(신규 헬퍼 함수 3개 추가, `_raw_bytes_and_format` 로직 확장, 모듈 docstring에 "3차 재작업" 절 추가). `tests/integration/test_feature_a_pipeline.py`(07 소유, 지시문이 명시적으로 수정 금지)는 손대지 않았다. `tests/pdf_reader/test_image_extractor.py`(06 소유)도 손대지 않았다(아래 12-4절에 06을 위한 갱신 필요 사항을 남김). `ir.py`/`pyproject.toml`/`hwpx_writer/image_embedder.py`/`hwpx_kernel/container.py` 어느 것도 수정하지 않았다.

### 12-1. 근본 원인 재확인 (07 결함 리포트 + 코드 직접 확인, 추측 없음)

기존(2차 재작업까지의) `_raw_bytes_and_format`는 `/Filter`가 배열일 때 **마지막 항목만** 보고, 그것이 "완결된 이미지 코덱"(`_SELF_CONTAINED_CODEC_FILTER_TO_FORMAT`: DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode)이면 `xobj._data`(어떤 필터도 해석하지 않은 원본 스트림)를 곧바로 그 코덱의 원본 바이트로 반환했다. 필터가 1개뿐이면 이 가정이 정확하지만, 앞에 다른 필터(전형적으로 `/ASCII85Decode`, 전송 인코딩)가 있으면 `_data`는 여전히 그 앞단 필터로 인코딩된 상태인데도 `image_format="jpeg"`(또는 해당 코덱 이름)로 잘못 라벨링되어 반환됐다.

07단계가 이 조합을 **reportlab의 `canvas.drawImage()`만 호출한, 지극히 평범한 PDF**에서 실측으로 재현했다(`tests/integration/test_feature_a_pipeline.py::_build_reportlab_wrapped_image_pdf` — `/Filter [/ASCII85Decode /DCTDecode]`가 reportlab의 관측된 기본 동작). 이 조합은 하류(unit-7 `image_embedder.py`의 `SUPPORTED_IMAGE_FORMATS` 화이트리스트, unit-4 `container.py::add_bin_data()`)가 포맷 **이름**만 보고 바이트 유효성을 검증하지 않기 때문에 아무도 걸러내지 못하고 최종 `.hwpx`까지 그대로 흘러갔다(`convert()`가 `success=True`, `warnings=[]`로 이상을 전혀 보고하지 않음).

### 12-2. §7-4-3 판단 정정 (지시문 필수 요청 사항)

1차 재작업(§7-4-3)은 이 다중 필터 연쇄 조합을 "실무에서 극히 드묾"으로 판단해 재현 테스트 없이 "알려진 한계"로만 기록했다. **이 판단을 여기서 정정한다**: 07단계가 실측으로 보여준 대로, 이 조합은 결코 드문 예외가 아니라 **reportlab 같은 널리 쓰이는 PDF 생성 라이브러리의 기본 산출물**이다. "재현 테스트가 없다"는 사실이 "실무에서 드물다"는 근거가 될 수 없었다 — 당시 판단은 실제 PDF 생성기 산출물을 조사하지 않은 채 추측으로 내려진 것이었고, 이는 부적절한 근거였다. §7-4-3 원문 자체는 이력 보존을 위해 수정하지 않고 그대로 남겨 두며, 이 절이 그 정정 기록이다.

### 12-3. 수정 내용

`_raw_bytes_and_format`가 이제 필터 배열 **전체**를 해석한다(`_normalize_filter_names`가 단일 필터/배열/필터 없음을 항상 이름 리스트로 정규화). 마지막 필터가 완결 코덱이고 그 앞에 다른 필터가 있으면:

1. 앞선 필터들이 전부 `_LEADING_FILTER_DECODERS`(ASCII85Decode/ASCIIHexDecode/FlateDecode/LZWDecode/RunLengthDecode — pypdf 표준 순수 파이썬 정적 메서드, **Pillow 미경유**, 시그니처 `decode(data, decode_parms)`를 pypdf 6.19.0 소스로 직접 확인)에 있으면, `_decode_leading_transport_filters()`가 각 필터를 실제로 디코드해 벗겨내고 그 결과를 완결 코덱의 원본 바이트로 반환한다. `/DecodeParms`는 `_normalize_decode_parms()`가 pypdf `filters.py::decode_stream_data`와 동일한 정렬 규칙(필터 배열과 같은 길이로 맞추고, 없는 자리는 빈 `DictionaryObject`)으로 정규화해 각 필터에 맞게 넘긴다.
2. 앞선 필터 중 하나라도 이 표에 없거나(예: `/Crypt`, 알 수 없는 이름) 디코딩 자체가 예외를 던지면(손상/예상 밖 구조), **완결 코덱으로 잘못 라벨링해 반환하지 않고** `image_format="unknown"`으로 명시적으로 빠진다 — 이는 지시문이 요청한 "기존 미지원 포맷 처리 경로"로, `hwpx_writer/image_embedder.py`(unit-7, 이번에 수정하지 않음)의 `SUPPORTED_IMAGE_FORMATS` 화이트리스트가 `"unknown"`을 이미 "제외 + `IMAGE_FORMAT_UNSUPPORTED` 경고"로 처리하는 기존 배선을 그대로 재사용한다.

단일 필터 케이스(1차/2차 재작업의 핵심, 06 기존 PASS 대상)는 `leading_filter_names`가 빈 리스트가 되어 이번 변경 이전과 완전히 동일한 코드 경로(`_data` 그대로 반환)를 탄다 — 회귀 없음(12-5절 로컬 확인). FlateDecode/LZWDecode/RunLengthDecode/필터 없음(DEC-028, 원시 픽셀 샘플) 경로는 애초에 `xobj.get_data()`로 필터 배열 전체를 pypdf가 표준 해석하므로 다중 필터가 있어도 이번 결함과 무관했고, 전혀 건드리지 않았다.

**규칙 A 질문 발동 없음**: 이번 수정은 지시문이 제시한 두 방향(a) 실제 디코드 (b) 안전하지 않으면 기존 미지원 경로) 중 정확히 그 범위 안에서 구현했고, "어느 필터를 안전하게 해석 가능하다고 볼지"(pypdf 표준 필터 5종 화이트리스트)는 pypdf 소스로 명확히 확인 가능한 사실에 기반한 합리적 결정이라 판단해 임의 확정하고 여기 근거를 남겼다(두 갈래 설계가 갈리는 모호함이 아니었음).

### 12-4. 06단계에 전달할 기존 테스트 충돌 (수정 아님, 정보 전달)

`tests/pdf_reader/test_image_extractor.py::test_filter_array_last_entry_determines_format_dctdecode_case`(06 소유, 이번에 수정하지 않음)는 **2차 재작업 이전(사실상 DEF-INT-001의 버그가 있던 상태)의 동작을 "화이트박스 커버리지" 명목으로 그대로 고정한 테스트**다 — `arbitrary_bytes`(유효한 ASCII85도, JPEG도 아닌 임의 바이트)를 스트림에 넣고 `image_format == "jpeg"`, `raw_bytes == arbitrary_bytes`(전송 필터가 벗겨지지 않은 원본 그대로)를 기대한다. 이번 수정 이후 로컬로 재실행한 결과, 이 테스트는 **의도한 대로 실패한다**(`image_format == "unknown"`, arbitrary_bytes가 유효한 ASCII85가 아니라 `_decode_leading_transport_filters`가 디코드에 실패해 안전 경로로 빠짐 — 로그에도 `Ignoring missing Ascii85 end marker.` 경고가 남고 최종적으로 디코드 실패). **이는 회귀가 아니라 DEF-INT-001이 실제로 고쳐졌다는 증거**다 — 06단계가 이 테스트를 아래 12-6절 AC에 맞춰 갱신해야 한다(예: 유효한 ASCII85로 인코딩된 실제 JPEG를 써서 "정상적으로 디코드되어 `jpeg`/원본과 바이트 일치"를 검증하는 방향으로, 또는 "안전하게 디코드 불가능한 임의 바이트는 `unknown`으로 빠짐"을 검증하는 별도 화이트박스 테스트로 분리).

그 외 `tests/pdf_reader/test_image_extractor.py`의 나머지 모든 테스트(322개 중 이 1건 제외 전부)는 이번 수정 이후에도 로컬 pytest 재실행에서 **전부 PASS**(12-5절).

### 12-5. 게이트 1 — 정적 분석/린트 (재확인)

- 프로젝트에 lint/type-check/formatter 설정 없음을 재확인(루트에 `ruff`/`flake8`/`mypy`/`pylint`/`.pre-commit-config.yaml` 없음 — 1차/2차 재작업과 동일 결론).
- `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` — 컴파일 성공.
- **로컬 환경에 `pytest`/`reportlab`/`platformdirs`가 설치돼 있지 않아(2차 재작업 시점과 동일하게 재확인) 이번에는 실제로 `pip install`로 로컬 설치해 pytest를 직접 실행했다**(매니페스트 `pyproject.toml`은 수정하지 않음 — `platformdirs`/`reportlab`는 이미 `pyproject.toml`에 선언돼 있고 이 로컬 venv에만 없던 것이었음, `pytest`는 개발 전용 도구라 애초에 런타임 매니페스트 대상이 아님, 2차 재작업의 "로컬 확인용 설치" 선례와 동일한 성격). 이 설치로 다음을 실제로 실행해 확인할 수 있었다(2차 재작업까지는 pytest 없이 픽스처 빌더 함수만 재사용하는 간접 확인이었던 것과 달리, 이번에는 **실제 pytest 실행**):
  - `python -m pytest tests/pdf_reader/test_image_extractor.py -q` → **322 passed, 1 failed**(실패 1건은 12-4절에서 설명한, 회귀가 아니라 결함이 실제로 고쳐졌다는 증거).
  - `python -m pytest tests/pdf_reader tests/hwpx_writer tests/hwpx_kernel -q` → 동일하게 **322 passed, 1 failed**(다른 unit 디렉터리 회귀 없음).
  - `python -m pytest tests/integration/test_feature_a_pipeline.py -q` → **2 passed, 1 failed**(TC-INT-002/TC-INT-004 회귀 없이 PASS 유지, DEF-INT-001 재현 테스트는 12-6절 참고 — 의도된 "예상외 통과" 실패).
  - `tests/common/test_logging_setup.py`, `tests/core/test_orchestrator.py`는 이 로컬 venv에 `platformdirs`가 원래 없어 수집 자체가 실패했었는데(이 unit의 파일 범위와 무관한 기존 환경 문제), 로컬 확인을 위해 `pip install platformdirs`로 추가 설치한 뒤 재실행해 위 통합테스트 결과를 얻었다 — 매니페스트에는 이미 선언돼 있던 패키지라 공유 자원 변경 아님.
- 병렬 실행이 아니므로 다른 unit과의 파일 충돌/격리 이슈 없음.

### 12-6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — REQ-003(재인코딩 없는 원본 바이트)을 다중 필터 연쇄 케이스에서도 이제 정확히 만족한다(안전하게 벗겨낼 수 있으면 벗겨내고, 아니면 명시적으로 미지원 처리). 지시문이 제시한 두 방향(a)/(b) 모두 실제로 구현했다(12-3절).
- [x] 에러 처리가 누락된 경로가 없는가 — `_decode_leading_transport_filters`의 `except Exception: return None`은 예외를 조용히 무시하는 것이 아니라, 호출자가 그 결과(`None`)를 받아 **명시적으로 `image_format="unknown"`이라는 가시적인 실패 경로**로 라우팅하도록 설계된 의도적 흐름 제어다(기존에 이미 존재하던 "미지원 포맷" 경로와 동일한 성격 — 그 이미지는 unit-7에서 제외되고 `ImageEmbedWarning`으로 사용자에게 보고된다, 조용히 사라지지 않음). `_data` 속성 부재 등 기존 `PdfReadError` 발생 지점은 변경 없이 그대로 유지했다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 변경 없음(unit-0 `loader.py`가 PDF 구조 자체는 이미 검증한 상태로 전달, 기존 전제와 동일). `/DecodeParms` 정규화는 PDF 내부 구조체이지 사용자 입력이 아니며, 없거나 형식이 다른 경우 빈 `DictionaryObject`로 안전하게 기본값 처리한다(추측성 픽셀 처리가 아니라 "파라미터 없음"이라는 PDF 표준 자체의 기본 의미와 일치).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성이 있다면 실존 패키지인지 확인했는가 — 신규 의존성 추가 없음. `pypdf.filters`의 `ASCII85Decode`/`ASCIIHexDecode`/`FlateDecode`/`LZWDecode`/`RunLengthDecode`는 이미 매니페스트에 있는 `pypdf`(unit-0이 등록) 패키지의 기존 공개 서브모듈이며, `import pypdf.filters`로 로컬에서 직접 확인했다(신규 PyPI 패키지 아님).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/pdf_reader/image_extractor.py` 1개 파일만 수정. DEC-028(원시 픽셀 샘플 PNG 합성) 경로, `_extract_inline_images`, bbox 폴백 로직, `_detect_image_format` 등은 문자 그대로 유지했다(코드 리뷰로 확인 가능 — 이번 diff는 임포트 3줄 추가, 상수 1개 추가, 헬퍼 함수 3개 신설, `_raw_bytes_and_format` 본문 확장, 모듈 docstring에 "3차 재작업" 절 추가뿐). `tests/integration/test_feature_a_pipeline.py`(07 소유, 지시문이 명시적으로 수정 금지)와 `tests/pdf_reader/test_image_extractor.py`(06 소유)는 손대지 않았다.

### 12-7. 로컬 동작 확인 (자체 테스트 아님, 최소 확인 — 12-5절 pytest 실행과는 별개로 직접 재현)

세션 스크래치 디렉터리(리포지토리 밖)에서 직접 pypdf 저수준 API로 PDF를 구성해 확인 후 스크립트/생성 파일은 리포지토리에 남기지 않았다(`git status --porcelain`으로 신규 파일이 `image_extractor.py` 1개뿐임을 재확인).

1. **DEF-INT-001 재현 시나리오(핵심)**: 40x30 JPEG을 `base64.a85encode(..., adobe=True)`로 ASCII85 인코딩한 뒤 `/Filter [/ASCII85Decode /DCTDecode]`로 이미지 XObject를 구성 → `extract_image_blocks(page)[0]` 결과: `image_format == "jpeg"`, `raw_bytes == 원본 JPEG 바이트`(완전히 동일, `==` 비교로 확인), `PIL.Image.open(io.BytesIO(raw_bytes)).load()`가 예외 없이 성공(유효한 이미지로 열림) — **DEF-INT-001 해소를 직접 실증**.
2. **회귀 확인(단일 필터)**: `/Filter /DCTDecode`(배열 아님, 필터 1개) 케이스 → `image_format == "jpeg"`, `raw_bytes == 원본 JPEG`(완전 동일) — 1차/2차 재작업 핵심 계약 그대로 유지 확인.
3. **안전하지 않은 선행 필터 폴백 확인**: `/Filter [/Crypt /DCTDecode]`(가상의 미지원 선행 필터) 케이스 → `image_format == "unknown"`(완결 코덱으로 잘못 라벨링되지 않고 명시적으로 미지원 경로로 빠짐을 직접 확인).
4. **07단계 통합테스트로 종단간(end-to-end) 확인**: `python -m pytest tests/integration/test_feature_a_pipeline.py -q` 실행 결과, `test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001`가 **실패**했는데, 그 실패 지점은 테스트 자신의 마지막 assert(`assert is_valid_image is False, "DEF-INT-001이 수정된 것으로 보입니다 — BinData의 이미지가 이제 유효합니다. ..."`)로, 정확히 **이 테스트가 스스로 의도한 "결함이 고쳐지면 실패로 전환되는 회귀 가드"의 역할대로 동작한 것**이다 — `convert()`가 실제로 만든 `.hwpx`의 `BinData/binN.jpg`가 이제 `PIL.Image.open()`으로 정상적으로 열린다는 뜻이다(orchestrator→unit-2→unit-7→unit-4 전체 실제 파이프라인 경유, mock 없음). TC-INT-002/TC-INT-004는 그대로 PASS 유지(회귀 없음).
5. **발견한 사소한 불일치(수정하지 않음, 07/06에 정보로만 전달)**: 위 통합테스트 함수의 docstring은 "이 테스트는 `pytest.mark.xfail(strict=True)`로 표시한다"고 서술하지만, 실제 코드에는 `@pytest.mark.xfail` 데코레이터가 없다(`grep`으로 직접 확인). 그 결과 이번처럼 결함이 고쳐지면 pytest가 "xfail이 예상외로 통과"가 아니라 그냥 **일반 FAIL**로 보고한다(실질적으로는 동일한 신호 — "고쳐졌으니 갱신 필요" — 를 CI에 전달하지만, 테스트 자체의 문서화 의도와 실제 데코레이터가 어긋나 있다). 이 파일은 07 소유라 직접 고치지 않았다 — 07 재실행 시 이 어긋남도 함께 바로잡을 것을 권장(정보 전달 목적, 이번 반려 사유와는 무관).

### 12-8. 6단계 테스터를 위한 갱신된 인수 조건 (AC-1에 3-4번 항목 신설, 그 외 기존 AC 변경 없음)

**AC-1(3차 개정 추가분). 다중 필터 연쇄 (REQ-003, DEF-INT-001)**

1. `/DCTDecode`/`/JPXDecode`/`/CCITTFaxDecode`/`/JBIG2Decode`가 필터 배열의 **마지막**이고 그 앞에 `/ASCII85Decode`/`/ASCIIHexDecode`/`/FlateDecode`/`/LZWDecode`/`/RunLengthDecode` 중 하나 이상이 선행하는 경우, `extract_image_blocks`가 반환하는 `raw_bytes`는 **그 앞선 필터를 실제로 디코드한 뒤의 완결 코덱 원본 바이트와 바이트 단위로 완전히 동일**해야 한다(예: ASCII85로 인코딩된 JPEG는 디코드된 JPEG 원본과 동일 — `PIL.Image.open(io.BytesIO(raw_bytes)).load()`가 예외 없이 성공해야 함). `image_format`은 마지막 필터가 결정하는 값(`"jpeg"`/`"jp2"`/`"ccitt"`/`"jbig2"`) 그대로다.
2. 위 완결 코덱 앞에 `_LEADING_FILTER_DECODERS`에 없는 필터(예: `/Crypt`, 임의의 알 수 없는 이름)가 선행하거나, 선행 필터 디코딩 자체가 실패하는 경우(예: 선언된 필터와 실제 바이트가 맞지 않는 손상된 PDF), `image_format == "unknown"`이어야 한다 — 완결 코덱 이름으로 잘못 라벨링되면 결함이다.
3. 단일 필터(배열이 아니거나 배열 길이가 1)인 기존 케이스는 이번 변경으로 어떤 동작 변화도 없어야 한다(회귀 확인 대상, 12-7-2절).
4. `tests/pdf_reader/test_image_extractor.py::test_filter_array_last_entry_determines_format_dctdecode_case`는 이번 수정 이후 **의도적으로 실패**한다(12-4절) — 06단계는 이를 결함으로 보고하지 말고, 위 1/2번 AC에 맞춰 테스트를 갱신할 것(예: 유효한 ASCII85 인코딩된 실제 JPEG로 교체해 "정상 디코드 후 원본과 바이트 일치"를 검증하거나, "안전하게 디코드 불가능한 임의 바이트"는 별도 테스트로 분리해 `image_format == "unknown"`을 검증).
5. `tests/integration/test_feature_a_pipeline.py::test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001`도 이번 수정 이후 **의도적으로 실패**한다(12-7-4절, 테스트 자신의 메시지가 갱신 방법을 안내함) — 07단계가 이 테스트를 뒤집고(`is_valid_image is True`), `docs/harness/decisions.md`/`feature-A-integration-test.md`를 DEF-INT-001 Closed로 갱신해야 한다(이 unit이 직접 하지 않음, 07 책임).

기존 AC-1(2차 개정, 9-8절)/AC-2~AC-6은 변경 없이 그대로 유효하다.

### 12-9. 인계 우선순위 (06/07단계 재검증용)

1. **최우선**: 위 AC-1(3차 개정 추가분) 1~3번을 06단계가 공식 pytest로 재검증.
2. 12-4절/AC-1-4: `test_filter_array_last_entry_determines_format_dctdecode_case`를 06단계가 새 AC에 맞춰 갱신(이 unit은 07 소유 통합테스트뿐 아니라 06 소유 단위테스트도 직접 수정하지 않았음 — 06의 책임 영역이라 판단).
3. 06단계 재검증 통과 후, 07단계가 `tests/integration/test_feature_a_pipeline.py::test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001`을 공식 재실행해 DEF-INT-001을 Closed로 전환(AC-1-5, 12-7-4/5절).
4. **오케스트레이터에게 참고로만 전달(결정 요청 아님)**: unit-7(`image_embedder.py`)/unit-4(`container.py`)가 포맷 이름이 아니라 바이트 매직넘버(예: JPEG `FF D8 FF`)까지 검증하는 방어 계층을 추가하면 "unit-2가 놓친 새로운 필터 조합"에 대해서도 2중 방어가 되겠지만, 이번 DEF-INT-001의 근본 원인은 unit-2의 판정 로직 자체였고 이번 수정으로 이미 해소되므로 **지금 당장 필수는 아니라고 판단**했다(과설계 방지) — 이 판단에 동의하지 않으면 unit-7/4를 별도 작업 단위로 검토할 것을 제안한다(이 unit이 직접 그 파일들을 수정하지 않음, 범위 밖).
