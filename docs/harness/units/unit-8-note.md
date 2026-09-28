# unit-8 구현 노트 — Feature A, 변환 오케스트레이션 통합 지점 (05-unit-developer)

- 커버 REQ-ID: REQ-005(보존 우선순위+미보존 요소 고지), REQ-009(변환 실패/부분 실패 안내), REQ-010(변환 결과 다운로드 제공 — 핵심 변환 로직 관점에서는 "HWPX 바이트 생성" 부분만 해당, 실제 다운로드 HTTP 응답은 unit-20 몫)
- 소속: Feature A(코어 변환 파이프라인). 선행 단위: unit-5(paragraph_builder), unit-6(table_builder), unit-7(image_embedder) — 모두 Verified(06단계 PASS).
- 속도 트랙: **L3(일반)** — 호출 프롬프트에 별도 트랙 지정 없어 기본값 적용.
- 이번 호출은 병렬 웨이브가 아니었다(단독 05 호출). 확정 파일 범위(`pdf_to_hwpx/core/orchestrator.py`, 신규 1개 파일)만 생성했다.
- 선행 문서: `docs/harness/03-system-design.md`(§1-2 컴포넌트 다이어그램, §1-3 unit-8 행/확정 파일 범위, §4-1 공개 API 계약, §4-2 예외 계층, §5 벌크헤드 원칙, 3-2 `ConversionJob` 상태 전이 주석), `docs/harness/04-ux-design.md`(§패널C 오류 메시지 매핑 표), `docs/harness/units/unit-{0..7}-note.md`(전부 재확인), `pdf_to_hwpx/pdf_reader/ir.py`, `pdf_to_hwpx/common/exceptions.py`, `pdf_to_hwpx/hwpx_kernel/container.py`/`schema.py`, `pdf_to_hwpx/hwpx_writer/*.py`.

---

## 1. 구현 범위

`pdf_to_hwpx/core/orchestrator.py` 1개 파일 신규 생성. 공개 API(`convert`/`ConversionOptions`/`ProgressEvent`/`ConversionResult`/`ConversionWarning`/`ConversionIssue`/`ConversionStats`)를 03 §4-1 그대로 구현했다. 상세 로직은 모듈 docstring에 이미 상술했으므로(코드만 읽어도 판단 근거가 드러나게 함, unit-4/7 선례와 동일한 문서화 방식), 이 note는 **왜 이렇게 결정했는지의 요약과 08/06단계가 알아야 할 것**에 집중한다.

### 1-1. 실제 동작 흐름
1. `_validate_output_path()`로 출력 경로를 PDF를 열기 **전에** 먼저 검증한다(`OutputPathError` 사전 검증, 지시문 필수 요건).
2. `load_pdf()`로 PDF를 연다(`with` 컨텍스트 매니저로 반드시 해제).
3. `hwpx_kernel.container.build_empty_container()`로 빈 컨테이너 골격을 만든다.
4. 페이지마다: `extract_text_blocks`/`extract_table_blocks`/`extract_image_blocks` 호출 → REQ-005 dedup(아래 2-1) → `build_paragraph_fragments`/`table_blocks_to_fragments`/`embed_image_blocks` 호출 → 프래그먼트 정렬(아래 2-2) → 전체 문서 프래그먼트 목록에 이어붙임. 이 전체를 페이지 단위 `try/except`로 감싼다(아래 2-5 벌크헤드).
5. 루프 종료 후 `hwpx_schema.build_reference_section_body()`로 섹션 XML을 만들고 `add_section_xml()`/`add_bin_data()`로 실제 파일에 반영한다.
6. `ConversionResult`를 반환한다. 실패 유형별 매핑은 아래 2-3/2-4.

---

## 2. 이번 unit이 직접 판단한 6가지 결정과 근거

### 2-1. REQ-005 dedup — 표 우선, 이미지는 dedup 대상에서 제외(중요, 반드시 읽을 것)

지시문은 "표 bbox와 유의미하게 겹치는 텍스트/이미지 블록을 표 쪽 우선으로 제외"하라고 요청했다. **텍스트는 그대로 구현했으나(`_exclude_text_overlapping_tables`, 2D bbox 겹침비 ≥ 0.5), 이미지는 의도적으로 dedup 대상에서 제외했다.**

**근거**: unit-2(`image_extractor.py`) 모듈 docstring이 명시한 대로, `ImageBlockIR.bbox`는 콘텐츠 스트림의 배치 행렬(`cm`/`Do` 연산자)을 해석하지 않고 **항상 페이지 전체 크기(`(0, 0, width_pt, height_pt)`)로 폴백**한다(unit-2의 확정된, 06단계 PASS로 검증된 계약). 이 상태에서 이미지 bbox와 표 bbox의 겹침비(교집합/더 작은 쪽 면적)를 계산하면, 표는 항상 페이지보다 작으므로 교집합=표 면적, 분모(더 작은 쪽)=표 면적이 되어 **겹침비가 사실상 항상 1.0**이 된다. 즉 순진하게 이미지에도 이 dedup을 적용하면 "표가 있는 페이지의 이미지는 전부 제외"라는, 명백히 잘못되고 유해한 동작이 나온다.

**실측 확인**: 스모크 테스트(4절)에서 표+이미지가 함께 있는 페이지를 실제로 변환해, 텍스트 dedup은 정확히 동작하고(표 셀 텍스트 "R0C0"이 표 안에만 1회 등장, 자유 텍스트로 중복되지 않음) 이미지는 정상적으로 BinData에 임베딩됨을 확인했다(4절 참고).

**결정**: 텍스트에만 dedup을 적용하고, 이미지는 항상 모두 포함시킨다(그 대신 이미지의 위치 정확도 자체가 이미 낮다는 리스크는 2-3절에서 별도로 다룬다). 이는 지시문이 요구한 "표>이미지>텍스트" 우선순위 정책의 문자 그대로의 구현이 아니라, **그 정책의 실질적 의도(중복 방지)를 현재 데이터 품질 안에서 구현 가능한 범위로 좁힌 것**이다 — 임의로 요구사항을 축소한 것이 아니라, 이미지 bbox가 위치 정보를 담고 있지 않다는 상위 unit(unit-2)의 이미 확정된 제약 때문에 기술적으로 불가능/유해하다는 것을 발견하고 대응한 것이다(A-3 가역적 기술 결정 — unit-2의 bbox 정확도가 개선되면(향후 콘텐츠 스트림 파서 추가) 이 dedup을 이미지에도 재적용할 수 있다).

**한계(그대로 명시)**: 텍스트 dedup 자체도 완벽하지 않다 — 겹침비 임계값 0.5는 unit-1/unit-5의 "같은 줄" 판정 선례(`_LINE_OVERLAP_RATIO = 0.5`)를 2D 면적으로 확장한 것일 뿐 근거 있는 표준값이 아니다. 표 경계선과 정확히 맞닿은 텍스트, 표 밖이지만 표 바로 옆에 있는 캡션 등은 오탐/누락 가능성이 있다.

### 2-2. 페이지 배치 순서

문단과 표는 각 프래그먼트의 `bboxPt` 속성(paragraph_builder/table_builder가 이미 부착)의 y0 값으로 정렬해 대략적인 읽기 순서를 근사한다(`_order_page_fragments`). 이미지는 (2-1과 동일한 이유로) 위치 정보가 신뢰할 수 없으므로 정렬 대상에서 빼고 각 페이지의 끝에 붙인다. 완벽한 z-order 재현은 REQ-008 범위 밖(YAGNI, 지시문이 명시적으로 허용)이다. 여러 페이지는 `container.add_section_xml`이 단일 섹션만 지원하므로 하나의 `section0.xml`에 순서대로 이어붙였다 — 명시적 페이지 구분자(페이지 브레이크)는 `schema.py`/`container.py` 계약에 없어 이번 unit이 추가하지 않았다(공유 자원 변경 없이는 불가능, 4절 "공유 문서 갱신 요청" 참고).

### 2-3. 알려진 미해결 리스크 — 다중 페이지 이미지 좌표 충돌 (고치지 않고 그대로 이관)

지시문이 사전에 경고한 리스크가 스모크 테스트에서 **실제로 재현되었다**: `image_block_to_picture_fragment`가 페이지 로컬 bbox를 그대로 HWPUNIT 절대좌표로 쓰기 때문에, 이미지가 있는 페이지가 여러 장이면 모든 이미지가 정확히 같은 절대좌표(`(0,0)`, 크기=페이지 전체 크기)에 배치된 `<hp:pic>`이 생성된다(4절 실측 확인 — `xHwpunit="0" yHwpunit="0"`, `widthHwpunit="59528" heightHwpunit="84189"`, 이는 실제 그려진 이미지 크기(40x30pt)가 아니라 A4 페이지 전체 크기다). 이는 unit-2의 bbox 폴백 한계와 unit-4의 "페이지 로컬=문서 절대좌표" 가정(DEC-017 미검증)이 겹쳐 나타나는 문제다.

**임의로 해결하지 않았다** — `schema.py`/`container.py`는 unit-4의 확정 파일 범위이고, 이 좌표를 실제 한글이 "페이지 기준 상대좌표"로 해석하는지 "문서 전체 절대좌표"로 해석하는지 자체가 DEC-017 미검증 영역이다. 08(전체시스템테스트)/실제 한글 뷰어 검증 단계로 명시적으로 이관한다. 06단계는 이 unit의 단위 테스트에서 "이미지가 실제로 올바른 화면 위치에 보이는지"를 검증 대상으로 삼지 말아야 한다(BinData에 올바른 바이트가 들어갔는지, 프래그먼트가 정확히 몇 개 생성됐는지까지만 검증 가능).

### 2-4. `ConversionStats` 집계 기준

- `tables_detected`: 페이지별 `len(table_blocks)`의 합.
- `tables_preserved_fully`: `has_merged_cells is False`인 표만 카운트. **병합 셀이 확정된 표는 "완전 보존"에서 제외**했다 — REQ-004가 병합 셀 처리를 "best-effort"로 명시하고, unit-3의 병합 감지 자체가 미탐(false negative) 가능성이 있는 휴리스틱이라는 점(unit-3-note.md)에 근거해, 병합이 있는 표는 실제로는 `table_builder`가 `row_span`/`col_span`으로 정확하게 배치하더라도(unit-6은 divmod 근사가 아니라 실제 span 기반 정밀 배치를 한다) **상류 인식 단계(unit-3)의 불확실성**을 반영해 보수적으로 "완전 보존 미보장"으로 분류했다. 이 판단 기준은 향후 unit-14(quality_report)가 그대로 재사용하거나 재검토할 수 있다.
- `images_embedded`: 실제 BinData에 등록된(=`embed_image_blocks`가 반환한 `embedded` 목록에 포함된) 이미지 수만 카운트. CCITT/JBIG2/미지원 포맷으로 경고 처리되어 제외된 이미지는 포함하지 않는다.
- `chars_extracted`: 페이지별 모든 `TextBlockIR.text` 길이의 합(REQ-005 dedup **이전** 값 — "추출"이라는 지표 이름에 맞춰, 표와 겹쳐 최종 출력에서 제외된 텍스트도 "PDF에서 추출은 됐다"는 사실 자체는 반영되도록 함).
- `chars_replaced_with_placeholder`: 지시문이 명시한 정의를 그대로 따름 — `to_unicode_missing=True`인 블록의 **`text` 길이 합**(□ 문자 개수가 아니라 그 블록 전체 글자 수).

### 2-5. 페이지 단위 격리(벌크헤드)와 `success` 판정 (03 §5 기존 원칙의 실제 구현)

unit-1/2/3 모듈 docstring은 한결같이 "이 함수는 예외를 삼키지 않고 전파하며, 페이지 단위 격리(벌크헤드)는 orchestrator(unit-8)의 책임"이라고 명시해 왔다. 이 unit에서 실제로 그 책임을 구현했다: 페이지별 처리를 `try/except Exception`으로 감싸, 한 페이지에서 예외가 나도 나머지 페이지 처리를 계속한다(`ConversionIssue(code="PAGE_PROCESSING_FAILED", page_index=...)`로 기록).

**단, 페이지 하나라도 실패하면 최종 `ConversionResult.success`는 `False`로 반환하고, 이미 만들어진 부분 컨테이너 파일은 삭제한다.** 이것이 "부분 성공(일부만 담긴 파일이라도 다운로드 제공)"과 다른 점인데, 근거는 03 §3-2 `ConversionJob` 상태 전이 주석이다: "DONE + result_success=False -> 다운로드 자체를 제공하지 않고 result_errors만 노출"이라고 이미 확정돼 있고, 03 §4-1 `ConversionResult`에는 "부분 성공" 상태를 표현할 별도 필드가 없다(성공/실패 이진 + errors/warnings 리스트뿐). 세 번째 상태를 억지로 만들기보다 기존 계약을 그대로 준수하는 쪽을 택했다.

**대안 후보(채택하지 않음, 참고용)**: "실패한 페이지만 건너뛰고 나머지로 만든 파일을 success=True + warnings로 제공"하는 방식도 가능했으나, 이는 `ConversionResult`/`ConversionJob` 계약에 없는 새로운 "부분 성공" 개념을 암묵적으로 도입하는 것이라 A-3 범위를 넘어선다고 판단했다(웹 레이어가 이미 "성공 여부"만으로 다운로드 가능 여부를 이진 판단하도록 설계돼 있어, 혼자 다른 의미를 부여하면 계약 불일치가 생김). 이 대안이 필요하다면 03 설계서 자체의 갱신(신규 필드 추가)이 선행되어야 하므로 공유 문서 갱신 요청(6절)에 후보로만 남긴다.

### 2-6. `HWPX_MIN_SUPPORTED_VERSION`/`ConversionIssue` 필드

- `HWPX_MIN_SUPPORTED_VERSION = hwpx_kernel.schema.SCHEMA_VERSION`("1.0") — 03 §4-2/§8-3이 "확인 필요"로 남긴 항목이라 임의 버전 문자열을 지어내지 않고, 현재 유일하게 존재하는 HWPX 계약 버전 상수를 그대로 재사용했다. 별도의 "파일 포맷 최소 지원 버전" 개념이 아직 없어 이것이 가장 안전한 선택이라고 판단했다.
- `ConversionIssue(code: str, message: str, page_index: int | None = None)` — 03 §4-1이 이름만 정의하고 필드를 정하지 않아 직접 정의했다. `ConversionWarning`과 최대한 대칭을 유지하되, 문서 전체 오류(예: `EncryptedPdfError`)는 특정 페이지에 속하지 않으므로 `page_index`만 선택적(`None` 허용)으로 뒀다.

---

## 3. OCR(REQ-014) 미구현 — 지시문 필수 명시 사항 재확인

`ConversionOptions.enable_ocr`/`ocr_lang`은 계약대로 받기만 하고 실질적인 동작 변화가 없다. `pdf_reader/ocr_engine.py`(unit-12)와 스캔본 판정 라우팅(unit-9, `PageIR.is_scanned`를 True로 설정하는 로직)이 모두 Not Started이기 때문이다. 이 unit은 `PageIR`을 아예 구성하지 않는다(각 추출 함수의 반환값을 바로 소비하고 `PageIR` 데이터클래스는 조립하지 않았다 — 이 시점에는 `PageIR`을 만들 실익이 없었고, `is_scanned` 필드를 채울 로직도 없어 만들어도 항상 기본값 `False`만 갖는 빈 껍데기가 되기 때문이다). `enable_ocr=True`로 호출해도 현재는 텍스트가 없는 페이지가 그대로 빈 텍스트로 처리될 뿐이다 — 이것은 결함이 아니라 명시적으로 이관된 범위 밖 항목이다.

---

## 4. 로컬 동작 확인 (테스트 아님, 최소 확인 — `.harness-tmp/venv-unit8`, 세션 종료 전 전부 삭제 완료)

`reportlab`(임시 설치, 프로젝트 의존성에는 추가하지 않음 — 스모크 검증 전용)으로 텍스트 2종(일반/볼드) + 2x2 표(선으로 그린 실제 표, pdfplumber `find_tables()`가 인식 가능) + JPEG 이미지 1개가 있는 페이지 1장과, 순수 텍스트만 있는 페이지 1장으로 구성된 PDF를 즉석 생성해 확인했다:

1. **정상 변환**: `convert()` 호출 결과 `success=True`, 생성된 `.hwpx`가 유효한 zip이며 `mimetype`/`Contents/section0.xml`/`BinData/bin0.jpg` 등 예상 엔트리를 모두 포함. `section0.xml`에 "Hello World"/"R0C0"/"Second page plain text"가 모두 포함됨을 바이트 단위로 확인.
2. **REQ-005 dedup 실제 동작**: `section0.xml`에서 "R0C0" 텍스트가 정확히 1회만 등장(표 셀 안에서만) — 표 영역과 겹치는 자유 텍스트 블록이 정확히 제외됨을 확인. 이미지(`<hp:pic>`)는 정상적으로 1개 포함됨(2-1절이 설명한 대로 dedup 미적용, 그대로 포함).
3. **다중 페이지 좌표 충돌 리스크 실측**: 이미지의 `<hp:pos xHwpunit="0" yHwpunit="0"/>`, `<hp:sz widthHwpunit="59528" heightHwpunit="84189"/>`(A4 페이지 전체 크기)로, 실제로 그려진 위치(72,400)/크기(40x30pt)와 무관하게 항상 페이지 원점+페이지 전체 크기로 나옴을 확인 — 2-3절 리스크가 이론이 아니라 실제 재현됨.
4. **`progress_callback` 스테이지 순서**: 실제 호출 순서가 `['loading', 'extracting', 'building', 'extracting', 'building', 'saving', 'done']`(2페이지 문서)로, 명시한 규약(loading 최초 1회 → 페이지마다 extracting/building 반복 → saving → done)과 정확히 일치함을 확인.
5. **`ConversionStats` 정확성**: `total_pages=2`, `tables_detected=1`, `tables_preserved_fully=1`(병합 없음), `images_embedded=1`, `chars_extracted=84`(2페이지 전체 텍스트 글자 수 합), `chars_replaced_with_placeholder=0`(ToUnicode 문제 없는 표준 PDF).
6. **`OutputPathError` 사전 검증**: 이미 존재하는 출력 파일에 `overwrite_existing=False`로 재호출 시 `success=False`, `errors[0].code == "OutputPathError"`, PDF를 열기도 전에 즉시 실패함을 확인(파일 열기 시점까지 도달하지 않음 — 코드상 `_validate_output_path`가 `load_pdf` 호출보다 먼저 실행됨을 재확인). `overwrite_existing=True`로는 정상 재변환됨을 확인.
7. **`CorruptedPdfError` 매핑 + 컨테이너 미생성**: 유효하지 않은 바이트로 만든 가짜 PDF에 대해 `success=False`, `errors[0].code == "CorruptedPdfError"`, 그리고 **출력 파일 자체가 생성되지 않음**을 확인(로드 실패는 `build_empty_container` 호출 전이라 `container_built=False` 경로 — cleanup 로직이 애초에 필요 없는 케이스도 정상 동작).
8. **페이지 단위 벌크헤드**: `extract_table_blocks`를 매 페이지 예외를 던지도록 몽키패치해 재현 — 두 페이지 모두 `ConversionIssue(code="PAGE_PROCESSING_FAILED", page_index=0)`/`page_index=1`로 개별 기록되고(한 페이지 실패가 다른 페이지 처리를 막지 않음, 실제로 2페이지 모두 각각 독립적으로 실패 기록됨), 최종 `success=False`이며 부분 산출물 파일이 정리(삭제)됨을 확인.

**명시적으로 하지 않은 것**: 실제 한글(한컴오피스)로 열어보는 검증(개발 환경에 한글 없음, DEC-017과 동일한 제약 — unit-4/5/6/7과 동일선상의 리스크). 06단계 정식 pytest 테스트 스위트 작성(다음 세션 몫, 지시문 명시).

---

## 5. 게이트 1 — 정적 분석/린트
- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`/`.pre-commit-config.yaml`)이 여전히 없음을 재확인했다(리포지토리 루트 검색, unit-0~7-note.md와 동일 결론).
- `python -m py_compile pdf_to_hwpx/core/orchestrator.py` — **컴파일 성공**.
- 단독 호출(병렬 웨이브 아님)이라 다른 unit의 미완성 코드로 인한 실행 실패 이슈 없음.

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트
- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 §4-1 공개 API 시그니처(함수/데이터클래스 필드)를 그대로 구현했고, §1-2("orchestrator가 유일한 통합점"), §5(페이지 단위 격리), §3-2(`ConversionJob` 상태 전이 주석의 success 의미)를 모두 반영했다. 지시문이 위임한 6가지 결정은 위 2절에 근거와 함께 기록했다.
- [x] 에러 처리가 누락된 경로가 없는가 — `ConversionError` 계층 전체(하위 subtype 포함, `isinstance` 매핑) + 최상위 `except Exception`(INTERNAL_ERROR)까지 이중으로 잡는다. 페이지 단위 `try/except`도 별도로 존재해 두 레이어 모두 예외를 삼키지 않고 `ConversionIssue`로 변환하거나 로그로 남긴다(`_cleanup_partial_output`의 `except OSError`만 조용히 넘어가되 `logger.warning(..., exc_info=True)`로 로그를 남겨 완전히 삼키지는 않음 — best-effort 정리 실패가 원래 실패 사유를 가리지 않게 하기 위한 의도적 설계, 6절 코드 주석에 명시).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — `output_path`(시스템 경계: 호출자가 지정하는 파일시스템 경로)는 `_validate_output_path`가 변환 시작 전에 검증한다(파일 존재+overwrite 플래그, 쓰기 권한). `input_path`(PDF 파일) 자체의 유효성 검증은 `load_pdf`(unit-0, 이미 06 PASS)가 담당하며 이 unit은 그 결과(예외)를 소비만 한다 — 경계 검증 책임이 이미 상류 unit에 있는 경우 중복 구현하지 않는 것이 03 §1-2 아키텍처와 일치한다(unit-4-note.md 선례와 동일한 판단).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 로컬 파일 변환 로직, 네트워크/인증 관련 코드 전혀 없음).
- [x] 새로 추가한 외부 의존성이 실제 존재하는지 확인했는가 — **신규 런타임 의존성 추가 없음**(`pyproject.toml` 미접촉, 이 unit은 이미 등록된 모듈만 import). 로컬 스모크 검증에만 쓴 `reportlab`은 `.harness-tmp` 전용 가상환경에 임시 설치했다가 검증 종료 후 그 가상환경째로 삭제했으며(4절/7절), 프로젝트 의존성 목록에는 추가하지 않았다(설치 자체는 PyPI 공식 패키지로 `pip install reportlab` 정상 설치됨을 이번 세션에서 직접 확인).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/core/orchestrator.py` 1개 신규 파일만 생성했다(`git status --porcelain` 재확인, 7절). `hwpx_kernel/`, `hwpx_writer/`, `pdf_reader/`, `pyproject.toml` 등 어떤 기존 파일도 수정하지 않았다.

---

## 7. `git status` 확인 (Teardown, 규칙 K)

작업 종료 시점 `git status --porcelain` 결과, 이 unit이 만든 변경은 `pdf_to_hwpx/core/orchestrator.py` 1개 신규 파일뿐이다(그 외 항목은 전부 이 세션 시작 이전부터 존재하던 다른 unit들의 기존 변경/미추적 파일). `.harness-tmp/venv-unit8`과 그 안에서 생성한 검증용 PDF/HWPX 산출물(`unit8_smoke.pdf`, `unit8_smoke.hwpx`, `unit8_smoke_bad.pdf`, `unit8_smoke_bulkhead.hwpx`)은 모두 삭제 완료했다(`.harness-tmp/`가 빈 상태임을 재확인). 스크래치패드에 작성한 검증 스크립트 2개(`unit8_smoke.py`, `unit8_smoke_bulkhead.py`)는 저장소 밖 세션 전용 스크래치패드에만 존재하며 저장소에 흔적을 남기지 않는다.

---

## 8. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

03/04단계가 unit-8 전용 AC를 명시적으로 발급하지 않아 이 unit이 스스로 도출했다(A-3 근거: 지시문이 "AC는 이 unit이 스스로 도출해도 된다"고 명시적으로 위임함).

### AC-1. 정상 변환(REQ-008/009/010 기본 경로)
1. 텍스트만 있는 유효한 PDF(1페이지 이상)를 `convert(input_path, output_path)`로 변환하면 `result.success is True`, `result.output_path == output_path`, `result.errors == []`.
2. 반환된 `output_path`가 가리키는 파일이 실제로 존재하고, 표준 `zipfile.ZipFile`로 예외 없이 열리며 `mimetype`/`Contents/section0.xml` 엔트리를 포함한다.
3. `Contents/section0.xml`이 well-formed XML이고(`lxml.etree.fromstring()` 파싱 성공), 입력 PDF의 텍스트 내용이 `<hp:t>` 텍스트로 포함되어 있다.
4. `result.stats.total_pages`가 PDF의 실제 페이지 수와 일치한다.

### AC-2. REQ-005 보존 우선순위 dedup(표>텍스트)
5. 표 영역과 2D bbox 겹침비 0.5 이상으로 겹치는 텍스트 블록은 최종 `section0.xml`에 자유 텍스트(`<hp:tbl>` 바깥의 `<hp:p>`)로 중복 등장하지 않는다 — 표 셀 안(`<hp:tc>/<hp:subList>/<hp:p>`)에만 존재해야 한다.
6. 표와 겹치지 않는 텍스트(표 위/아래의 일반 문단)는 정상적으로 `<hp:p>`로 포함된다.
7. **이미지는 표와의 bbox 겹침 여부와 무관하게 항상 포함된다**(2-1절 결정 — 표가 있는 페이지의 이미지가 사라지면 회귀로 간주해야 한다).

### AC-3. 예외 계층 -> `ConversionResult.errors` 매핑(REQ-009)
8. 암호화된 PDF -> `success=False`, `errors`에 `code="EncryptedPdfError"`, `message`가 "비밀번호로 보호된 PDF는 지원하지 않습니다."를 포함하는 항목이 정확히 1개 존재.
9. 손상된/파싱 불가 PDF -> `code="CorruptedPdfError"`. 0페이지 PDF -> `code="EmptyPdfError"`.
10. 위 세 경우 모두 `output_path`가 가리키는 파일이 생성되지 않는다(로드 실패는 컨테이너 생성 이전 단계).
11. `ConversionError` 계층에 속하지 않는 예상치 못한 예외(예: 향후 회귀로 어떤 내부 함수가 `ValueError`를 던지는 경우)가 페이지 처리 도중이 아니라 그 외 지점(예: 섹션 조립 단계)에서 발생하면 `code="INTERNAL_ERROR"`, `message`에 내부 스택트레이스/파일 경로가 노출되지 않아야 한다(로그에는 `logger.exception`으로 전체 traceback이 남아야 함 — 06단계는 `caplog`로 이 로그 존재까지 확인할 것을 권장).
12. 페이지 처리 도중 예외가 발생하면(위와 별개 케이스) `code="PAGE_PROCESSING_FAILED"`, `page_index`가 실패한 페이지의 0-기반 인덱스와 일치해야 하며, **다른 페이지의 처리는 계속 진행**되어야 한다(한 페이지의 실패가 나머지 페이지의 `ConversionIssue`/통계 수집을 막지 않는지 별도 검증 필요 — 단, 최종 `result.success`는 어떤 페이지든 하나라도 실패하면 `False`).

### AC-4. `OutputPathError` 사전 검증
13. `output_path`가 이미 존재하고 `overwrite_existing=False`(기본값)이면, `load_pdf`가 호출되기도 전에 `success=False`, `code="OutputPathError"`로 즉시 반환된다(PDF 자체가 손상돼도 이 케이스에서는 그 결함이 보고되지 않아야 함 — 순서 보장 검증 필요, 예: `load_pdf`를 스파이로 감싸 호출 안 됐음을 확인).
14. 같은 조건에서 `overwrite_existing=True`이면 정상적으로 변환이 진행되고 기존 파일이 교체된다.
15. 출력 디렉터리가 존재하지 않지만 상위 조상 디렉터리가 쓰기 가능하면 정상 진행된다(디렉터리 자동 생성은 `build_empty_container`가 담당).

### AC-5. `ConversionWarning` 매핑(이미지 제외 경고 포함)
16. CCITT/JBIG2/미지원 포맷 이미지가 있는 PDF를 변환하면 `result.warnings`에 `code`가 `image_embedder.ImageEmbedWarning.code`(예: `"IMAGE_FORMAT_INCOMPLETE_BITSTREAM"`, `"IMAGE_FORMAT_UNSUPPORTED"`)와 동일하고, `page_index`가 해당 이미지가 속한 페이지의 0-기반 인덱스와 일치하며, `detail`이 원본 `ImageEmbedWarning.message`와 동일한 항목이 존재한다.
17. 그 이미지는 `result.stats.images_embedded`에 카운트되지 않는다(경고 처리된 이미지는 실제 BinData에 등록되지 않음).

### AC-6. `ConversionStats` 정확성
18. `tables_detected`는 모든 페이지에서 `extract_table_blocks`가 반환한 표 개수의 총합과 정확히 일치한다.
19. `tables_preserved_fully`는 `has_merged_cells is False`인 표만 카운트한다(병합 셀이 있는 표는 `tables_detected`에는 포함되지만 `tables_preserved_fully`에는 포함되지 않아야 함).
20. `images_embedded`는 실제 BinData(`<hp:pic>`)로 임베딩된 이미지 수와 정확히 일치한다(경고 처리된 이미지 제외).
21. `chars_extracted`는 모든 페이지의 모든 `TextBlockIR.text` 길이 합과 일치한다(REQ-005 dedup으로 제외된 텍스트도 포함한 값).
22. `chars_replaced_with_placeholder`는 `to_unicode_missing=True`인 `TextBlockIR`의 `text` 길이 합과 정확히 일치한다.
23. `elapsed_seconds`는 0보다 크다(성공/실패 모든 경로에서 측정되어야 함).

### AC-7. `progress_callback` 호출 순서
24. `progress_callback`이 지정되면, 호출된 `ProgressEvent.stage` 시퀀스가 다음 패턴을 만족해야 한다: 최초 1회는 반드시 `"loading"`, 마지막 1회는 반드시 `"done"`(성공 케이스에 한함 — 실패 케이스는 `"done"`이 호출되지 않아야 함, 25번 참고), `"done"` 바로 직전은 반드시 `"saving"`. 그 사이에 각 페이지마다 `"extracting"`과 `"building"`이 최소 1회씩 나타나야 하며, `current_page`/`total_pages` 값이 해당 페이지 처리 시점의 실제 값과 일치해야 한다.
25. 변환이 어떤 이유로든 실패하면(`success=False`) `"done"` 스테이지는 호출되지 않아야 한다(2-5절 결정 — 실패는 "완료"가 아니다).

### AC-8. 알려진 리스크(회귀 아님, 06단계가 실패로 취급하면 안 되는 것)
26. 이미지가 있는 여러 페이지를 변환했을 때, 모든 `<hp:pic>`의 `<hp:pos>`/`<hp:sz>`가 페이지별 실제 배치와 무관하게 동일한 값(페이지 크기 기준 폴백)으로 나오는 것은 **이 unit의 결함이 아니라 unit-2/unit-4의 이미 알려진 한계가 통합 시점에 드러난 것**이다(2-3절). 06단계가 이를 "이미지 위치가 부정확함"으로 발견하더라도 unit-8 반려 사유로 삼지 말고, 08(전체시스템테스트)/실제 한글 검증으로 이관된 리스크임을 확인만 하면 된다.

---

## 9. 공유 문서 갱신 요청 (오케스트레이터가 반영)

이번 호출은 병렬 웨이브가 아니었지만, 지시문이 "traceability.md/decisions.md는 직접 수정하지 마라"고 명시했으므로 동일한 형식으로 갱신안을 남긴다.

### 9-1. `traceability.md` 갱신안

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-005 | 작업 단위 | `unit-8` 추가(보존 우선순위 dedup 구현) |
| REQ-005 | 구현 상태 | `Not Started` → **"unit-8: 05단계 구현 완료(표>텍스트 dedup만 구현, 이미지는 unit-2의 bbox 폴백 한계로 dedup 대상에서 제외 — unit-8-note.md §2-1 근거), 06단계 단위테스트 대기"** |
| REQ-009 | 작업 단위 | `unit-8` 추가 |
| REQ-009 | 구현 상태 | `Not Started` → **"unit-8: 05단계 구현 완료(예외 계층 7종 전부 ConversionResult.errors로 매핑, 페이지 단위 벌크헤드 구현, INTERNAL_ERROR 캐치올 포함), 06단계 단위테스트 대기"** |
| REQ-010 | 작업 단위 | `unit-8` 추가(비고: "HWPX 바이트 생성까지만 담당, 실제 브라우저 다운로드 HTTP 응답은 unit-20 책임 — 03 §4-4") |
| REQ-010 | 구현 상태 | `Not Started` → **"unit-8: 05단계 구현 완료(핵심 변환 로직 관점의 '다운로드 가능한 HWPX 파일 생성'까지), 06단계 단위테스트 대기. 실제 웹 다운로드 응답(unit-20)은 별도 미착수"** |

### 9-2. `decisions.md` 신규 결정 후보

| 후보 논제 | 배경 | 옵션 | 영향 | 권고 |
|---|---|---|---|---|
| 다중 페이지 이미지 절대좌표 충돌(§2-3) | `image_block_to_picture_fragment`가 페이지 로컬 bbox를 절대 HWPUNIT 좌표로 사용 + `ImageBlockIR.bbox`가 항상 페이지 전체 크기 폴백 → 여러 페이지의 이미지가 항상 동일 좌표(0,0, 페이지 전체 크기)로 배치됨(실측 확인, 4절) | (a) 현행 유지, 08/실제 한글 검증으로 이관(이번 unit 채택) / (b) orchestrator가 페이지별 오프셋(예: 페이지 y축 누적 높이)을 좌표에 더해 최소한 페이지 간 겹침만 회피(단, `schema.py`가 "페이지 기준 상대좌표"를 가정하는지 자체가 미검증이라 오히려 틀린 보정이 될 위험) / (c) unit-2 bbox 정확도 개선(콘텐츠 스트림 파서 추가, 별도 unit) + unit-4 좌표 해석 방식 확정(DEC-017 후속) | 실제 한글에서 이미지가 어떻게 보이는지 확인하기 전까지는 (b)가 "고친 것처럼 보이지만 검증 안 된 임의 보정"이 될 수 있어 위험. 08단계가 실제 한글로 열어본 뒤 재논의 권고 | 이번 unit은 (a) 채택. 08 완료 후 실제 관찰 결과에 따라 (b) 또는 (c) 여부를 신규 DEC로 확정할 것을 제안 |
| 페이지 단위 부분 실패 시 "부분 성공" 상태 도입 여부(§2-5) | 현재는 페이지 하나 실패 시 전체 `success=False`+파일 미제공(03 §3-2 계약 그대로 준수) | (a) 현행 유지(이번 unit 채택) / (b) `ConversionResult`에 신규 필드(예: `partial: bool`) 추가해 부분 성공 시에도 파일 제공 | (b)는 03 §4-1/§3-2 계약 갱신(3단계 설계 변경)이 선행되어야 함 | 이번 unit은 (a) 채택(계약 범위 내). (b)가 필요하다고 판단되면 03 재작업 필요 |

### 9-3. 기타 후속 조치 제안 (강제 아님)

- unit-11(CLI)/unit-20(웹 뷰)이 `ConversionResult.errors[].code`를 사용자 메시지로 매핑할 때, `code`가 예외 클래스명 문자열(`"EncryptedPdfError"` 등)이거나 `"INTERNAL_ERROR"`/`"PAGE_PROCESSING_FAILED"`라는 점을 계약으로 인지해야 한다 — 04 §패널C 표의 "코드" 컬럼과 정확히 대응된다(웹 레이어의 문구 재해석은 04가 이미 설계해 두었으므로 그대로 참고 가능).
- unit-14(quality_report)가 `tables_preserved_fully` 판단 기준(has_merged_cells 기반)을 그대로 재사용할지, 더 정교한 기준(예: `table_builder`가 실제 정밀 배치를 수행했으므로 병합 표도 "완전 보존"으로 볼지)을 재검토할지는 unit-14 착수 시점에 결정 필요.

---

## 절차 준수 확인

- 게이트 1(정적분석/컴파일): 통과(5절).
- 게이트 2(자체 코드 리뷰 체크리스트): 통과(6절).
- 로컬 동작 확인(정상 변환/dedup/좌표 리스크 실측/progress 순서/통계/OutputPathError/CorruptedPdfError/페이지 벌크헤드 8종): 완료(4절), `.harness-tmp` 정리 완료(7절).
- traceability.md/decisions.md: 직접 수정하지 않음 — 위 9절 "공유 문서 갱신 요청"에 반영 내용 기재.
- 06단계(단위테스트) handoff 준비 완료. 이 세션은 06을 직접 수행하지 않는다(지시문 명시).
