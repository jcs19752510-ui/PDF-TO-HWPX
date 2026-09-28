# unit-4 구현 노트 — Feature A 공통 선행(unit-5/6/7의 선행 단위) (05-unit-developer)

- 커버 REQ-ID: REQ-008 (HWPX 파일 생성)
- 소속: Feature A(코어 변환 파이프라인). 선행 단위 없음. **산출물이 unit-5/6/7의 공통 선행 계약**(03 §1-3, §1-2).
- 속도 트랙: **L3(일반)**
- **병렬 웨이브였음**: 이 호출과 동시에 unit-1(text_extractor), unit-2(image_extractor), unit-3(table_recognizer) 05-unit-developer 호출이 별도로 실행 중이었다(파일 범위 완전 분리로 충돌 없음). 이 unit은 `pdf_to_hwpx/hwpx_kernel/container.py`, `pdf_to_hwpx/hwpx_kernel/schema.py` 두 파일만 수정했다.
- 선행 문서: `docs/harness/03-system-design.md`(§1-2, §1-3 unit-4 행, §2-1, §3-1, §4-2), `docs/harness/02-planning.md` REQ-008, `docs/harness/decisions.md` **DEC-017**, `pdf_to_hwpx/pdf_reader/ir.py`.

---

## 1. 최우선 리스크 — 실제 한글(한컴오피스) 미검증 (DEC-017)

원래 설계(03 §2-1, §8-1 트레이드오프 2번)는 "실제 한글이 저장한 최소 빈 문서(.hwpx)를 리버스엔지니어링한 참조 템플릿"을 확보해 그 파일을 기준으로 컨테이너 골격을 구현하는 전략이었다. **개발 환경에 한글(한컴오피스) 프로그램이 설치되어 있지 않아 그런 참조 파일을 확보할 수 없다는 사실을 사용자에게 확인받았다(DEC-017).** 따라서 이번 구현은 **공개 표준(OWPML/KS X 6101)에 대한 일반 지식(ODF/OOXML/EPUB류 zip+XML 패키지 포맷의 공통 관례 포함)에만 근거**했다.

**이 산출물은 "구조상 그럴듯한 zip+XML"까지만 확인되었고, 실제 한글에서 경고 없이 열리는지는 전혀 검증되지 않았다.** 06/07단계, 그리고 실제 배포 전 반드시 실제 한글로 열어보는 검증이 필요하다(이번 호출 범위 밖 — 개발 환경 제약).

### 확신 vs 추정(미검증) 구분
**확신(구조적으로 안정적)**:
- HWPX는 zip 컨테이너이며 내부는 XML 파트들로 구성된다(공개 표준 사실).
- `mimetype`을 zip 첫 엔트리로 비압축(`ZIP_STORED`) 저장하는 관례는 ODF/EPUB류 포맷에서 일반적이며 HWPX도 같은 계열로 분류된다(01보고서/03 §2-1 근거) — 단, 한글이 이 관례를 실제로 강제하는지 100% 확인된 것은 아님.
- 본문(문단/표/그림)과 스타일 정의(글자모양/문단모양)를 별도 XML 파트로 분리하는 구조는 OWPML 계열에서 일반적.
- HWPUNIT = 1/7200 inch, 1pt = 100 HWPUNIT 변환 계수(여러 공개 HWP 관련 프로젝트에서 일관되게 확인되는 값) — 다만 이 프로젝트 환경에서 직접 재검증은 못함.

**추정/미검증(세부 사항 전부)**:
- 정확한 파트 파일명(`content.hpf`, `header.xml`, `section0.xml`, `settings.xml`, `version.xml`, `META-INF/container.xml`, `META-INF/manifest.xml`) 및 그 안의 XML 태그/속성 이름.
- `NAMESPACES` 딕셔너리의 모든 네임스페이스 URI 문자열(`http://www.hancom.co.kr/hwpml/2011/...` 형태) — 실제 한글이 쓰는 정확한 문자열과 다를 수 있음.
- `hp:tbl`/`hp:tr`/`hp:tc`(표)의 병합 셀 배치 방식, `hp:pic`(그림)의 바이너리 참조 방식(`binDataIDRef`) — OWPML 스펙 원문을 대조하지 못한 채 만들어 불확실성이 가장 큼.
- 완전히 빈 `<hs:sec>`가 유효한지 불명확해, 안전 쪽으로 빈 문단 1개를 포함시킨 것(추정 선택).

각 항목은 `container.py`/`schema.py`의 모듈·함수 docstring에도 동일하게 명시해 두었다(코드만 읽어도 리스크가 드러나게 함).

---

## 2. 구현 범위

### 2-1. `hwpx_kernel/container.py`
- `NAMESPACES`: hh(header)/hs(section)/hp(paragraph)/hc(core, 예비)/ha(settings)/hv(version)/opf(content.hpf)/ocf(container.xml·manifest.xml) 8개 네임스페이스 URI 상수(전부 추정치, 1절 참고).
- 내부 빌더 함수(전부 private, `_` 접두): `_build_version_xml`, `_build_container_xml`, `_build_manifest_xml`, `_build_content_hpf`, `_build_header_xml`(charShape/paraShape id="0" 기본값 정의), `_build_settings_xml`, `_build_empty_section_xml`(빈 문단 1개 포함).
- `build_empty_container(output_path: Path) -> None`: 위 8개 파트로 구성된 페이지 0개 최소 zip 골격을 생성. zip 엔트리 순서는 `mimetype`(비압축, `ZIP_STORED`) → `version.xml` → `settings.xml` → `META-INF/container.xml` → `META-INF/manifest.xml` → `Contents/header.xml` → `Contents/section0.xml` → `Contents/content.hpf`. zip 엔트리 타임스탬프는 고정값(1980-01-01)으로 둬서 실제 생성 시각이 파일에 남지 않게 했다(개인정보 최소화, 03 §6-2 방향과 일치 + 재현성).
  - 실패(디스크 공간 부족, 출력 디렉터리 생성 불가, 권한 없음 등 `OSError`) 시 `ContainerBuildError`(`common/exceptions.py`, unit-0 정의)를 `raise ... from exc`로 던진다.
- `add_section_xml(container_path: Path, xml_bytes: bytes, section_name: str = "section0.xml") -> None`: 기존 zip에서 대상 항목만 교체(없으면 추가)하고 나머지 항목은 그대로 복사한 새 zip을 만든 뒤 `Path.replace()`로 원자적 치환. 실패 시 임시 파일을 정리하고 `ContainerBuildError`를 던진다(`OSError`, `zipfile.BadZipFile` 모두 처리).
  - **의도적 범위 한정**: 현재 단일 섹션(`section0.xml`)의 교체만 지원한다. 여러 섹션으로 나누려면 `content.hpf`의 spine도 함께 갱신해야 하는데, 03 §1-2 컴포넌트 다이어그램상 orchestrator(unit-8)가 유일한 통합점이고 문서당 섹션 1개를 전제로 하고 있어 그 이상은 이번 unit 범위에 넣지 않았다. 다중 섹션이 필요해지면 이 함수를 확장해야 한다(설계서 대비 편차 아님 — 03 설계서 자체가 다중 섹션 spine 갱신을 명시하지 않았음).

### 2-2. `hwpx_kernel/schema.py`
- `SCHEMA_VERSION = "1.0"` (03 §3-1 마이그레이션 전략 근거).
- `HWPUNIT_PER_POINT = 100`, `pt_to_hwpunit(value_pt) -> int` 헬퍼.
- 계약 함수(전부 `pdf_to_hwpx.pdf_reader.ir`의 IR 타입을 소비, `hwpx_kernel.container.NAMESPACES`를 재사용):
  - `text_block_to_paragraph_fragment(block: TextBlockIR, *, char_shape_id="0", para_shape_id="0") -> etree._Element` — unit-5 소비 대상.
  - `table_cell_to_cell_fragment(cell: TableCellIR, *, row: int, col: int, ...) -> etree._Element`, `table_block_to_table_fragment(block: TableBlockIR) -> etree._Element` — unit-6 소비 대상.
  - `image_block_to_picture_fragment(block: ImageBlockIR, *, bin_data_id: str) -> etree._Element` — unit-7 소비 대상. **주의**: 이 함수는 배치(위치/크기) 프래그먼트만 만들고, `block.raw_bytes`를 실제 BinData 파트에 저장하는 것은 unit-7의 책임이다. `container.py`는 아직 BinData 삽입 함수를 제공하지 않는다 — 필요해지면 unit-4 파일 범위(`container.py`) 확장이 필요하므로 unit-7이 직접 만들지 말고 공유 자원 이슈로 보고해야 한다(4절 "공유 문서 갱신 요청" 참고).
  - `fragment_to_bytes(element) -> bytes` — XML 선언 없는 UTF-8 직렬화(프래그먼트 삽입용).
  - `build_reference_section_body(fragments: list[etree._Element]) -> bytes` — **계약의 필수 부분이 아닌 참고용 편의 함수**. 실제 통합(REQ-005/009/010 우선순위 정책 포함)은 orchestrator(unit-8)의 책임이며, 이 함수는 unit-4가 로컬 동작 확인을 위해 만든 예시 조립기다. unit-8이 그대로 써도 되고, 자체 로직으로 대체해도 된다.
- 표 그리드 배치 가정: `table_block_to_table_fragment`는 `block.cells`가 행 우선(row-major) 순서로 rows*cols를 빠짐없이 채운다고 가정하고 `divmod(idx, cols)`로 좌표를 추정하는 **단순화된 기본 구현**이다. 실제 병합 셀 배치가 이 가정과 다르면(REQ-004 best-effort) unit-6이 `table_cell_to_cell_fragment()`를 직접 호출해 (row, col)을 명시적으로 계산해 넘기는 방식을 쓰도록 docstring에 안내했다.

---

## 3. 설계서 대비 편차

없음(구조적 편차 없음). 다만 03 설계서가 세부 파일명/네임스페이스/속성을 규정하지 않았으므로(그 정도로 세밀하게 설계되어 있지 않음), 그 빈 부분을 1절에 기술한 "추정" 방식으로 채웠다 — 이는 편차가 아니라 설계서가 위임한 세부 구현 결정이며, DEC-017이 이 방식 자체(공개 표준 일반 지식 기반 진행)를 사전에 승인했다.

**참고(수정하지 않음)**: `pdf_to_hwpx/hwpx_kernel/__init__.py`(unit-0이 만든 placeholder)의 docstring이 여전히 "schema.py/container.py는 아직 생성되지 않았다"고 적혀 있어 이제는 사실과 다르다. 이 파일은 이번 unit의 확정 파일 범위(container.py, schema.py 두 개만) 밖이라 직접 수정하지 않았다 — 오케스트레이터가 후속 정리(4절 갱신 요청에 포함)하거나 별도 단위에서 처리해야 한다.

---

## 4. 게이트 1 — 정적 분석/린트
- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`)이 여전히 없음을 재확인했다(`pyproject.toml`, 리포지토리 루트 검색 — unit-0-note.md 3절과 동일 결론).
- `python -m py_compile pdf_to_hwpx/hwpx_kernel/container.py pdf_to_hwpx/hwpx_kernel/schema.py` — **컴파일 성공** (전역 인터프리터 및 아래 전용 가상환경 양쪽에서 확인).
- 병렬 웨이브 중 다른 unit(1/2/3)의 미완성/동시 수정 코드로 인한 전체 실행 실패는 없었다 — 이 unit은 해당 unit들이 만드는 파일을 import하지 않으므로 `py_compile` 대상에 영향이 없었다.
- 의존성 확인: `pdf_to_hwpx/hwpx_kernel/`용 신규 패키지는 `lxml` 하나이며, 이미 unit-0이 `pyproject.toml`에 `lxml>=5.0.0,<7.0`으로 등록해 두었다(신규 추가 아님, 매니페스트 미접촉). 다른 병렬 unit이 만든 venv(`.harness-tmp/venv-unit1`, `venv-unit3`)와의 충돌을 피하기 위해 이 unit 전용 가상환경 `.harness-tmp/venv-unit4`를 새로 만들어 `pip install -e ".[dev]"` 성공, `pip index versions lxml` 재조회로 PyPI 실존(6.1.3 등) 재확인했다.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트
- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 §1-3 unit-4 행(파일 범위·역할), §1-2("schema.py는 계약")을 그대로 따름. 세부 미규정 부분은 1절/3절에 명시한 대로 DEC-017 방침에 따라 "추정 + 명시"로 처리.
- [x] 에러 처리가 누락된 경로가 없는가 — `build_empty_container`/`add_section_xml` 모두 실패 시 `ContainerBuildError`로 변환해 던지며(`OSError`, `add_section_xml`은 `zipfile.BadZipFile`도 포함), 예외를 조용히 삼키는 코드 없음. `add_section_xml` 실패 시 임시 파일(`.tmp`)을 정리한다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — `add_section_xml`은 대상 컨테이너 파일 존재 여부를 먼저 확인하고 없으면 즉시 `ContainerBuildError`를 던진다. (이 unit의 함수들은 최종 사용자 입력을 직접 받지 않고 상위 unit-5/6/7/8이 만든 값을 받는 내부 계약이라, "외부 경계" 검증의 상당 부분은 unit-0(파일 경로)·unit-8(오케스트레이션)이 이미 책임진다 — 03 §1-2 아키텍처상 일치.)
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음.
- [x] 새로 추가한 외부 의존성이 실제 존재하는지 확인했는가 — 신규 의존성 추가 없음(lxml은 unit-0이 이미 등록). 실존은 위 4절에서 재확인.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `container.py`, `schema.py` 두 파일만 수정했다. `pdf_to_hwpx/pdf_reader/ir.py`는 import만 하고 수정하지 않았다. `hwpx_kernel/__init__.py`의 stale docstring도 건드리지 않았다(3절 참고, 범위 밖).

## 6. 로컬 동작 확인 (테스트 아님, 최소 확인)
스크래치패드에 임시 검증 스크립트를 작성해 `.harness-tmp/venv-unit4`에서 실행(리포지토리에는 남기지 않음, `.harness-tmp/unit4_verify.hwpx` 산출물도 삭제함 — `.gitignore`로 이미 추적 제외 대상이기도 함). 확인한 항목:
1. `build_empty_container()`로 실제 `.hwpx` zip 파일 생성 성공(크기 2143 bytes).
2. 표준 `zipfile`로 재오픈해 엔트리 목록이 예상한 8개 파트와 정확히 일치함을 확인: `mimetype`, `version.xml`, `settings.xml`, `META-INF/container.xml`, `META-INF/manifest.xml`, `Contents/header.xml`, `Contents/section0.xml`, `Contents/content.hpf`.
3. `mimetype`이 첫 번째 엔트리이고 `ZIP_STORED`(비압축)이며 내용이 `b"application/hwp+zip"`임을 확인.
4. `lxml.etree.fromstring()`으로 `mimetype`을 제외한 모든 파트가 **well-formed XML**임을 확인(파싱 에러 없음).
5. `schema.py`의 4개 계약 함수(`text_block_to_paragraph_fragment`, `table_block_to_table_fragment`, `image_block_to_picture_fragment`, `build_reference_section_body`)를 실제 IR 인스턴스(한글 텍스트 포함)로 호출해 `etree.Element`가 정상 생성되고 `fragment_to_bytes()`로 직렬화됨을 확인.
6. `build_reference_section_body()`로 조립한 섹션 XML을 `add_section_xml()`로 기존 컨테이너에 교체 삽입 → 재오픈 시 `mimetype`이 여전히 첫 엔트리·비압축 상태로 유지되고, `Contents/section0.xml`에 삽입한 텍스트/id(`c0`, `bin0`)가 들어있으며 well-formed XML임을 확인.

**명시적으로 하지 않은 것**: 실제 한글(한컴오피스)로 이 `.hwpx` 파일을 열어보는 검증은 개발 환경에 한글이 설치되어 있지 않아 이 단계에서 수행 불가능하다(1절 리스크 참고). 이 검증은 반드시 이후 단계(06/07 또는 실제 한글 확보 후 재검토)에서 별도로 수행되어야 한다.

---

## 7. 6단계 테스터 / unit-5·6·7을 위한 인수 조건 (Acceptance Criteria)

### AC-1. `hwpx_kernel/container.py`
1. `build_empty_container(output_path)` 호출 후 `output_path`가 존재하고, 표준 `zipfile.ZipFile`로 열렸을 때 예외가 발생하지 않는다.
2. 생성된 zip의 `namelist()`가 정확히 다음 8개(순서 포함)다: `mimetype`, `version.xml`, `settings.xml`, `META-INF/container.xml`, `META-INF/manifest.xml`, `Contents/header.xml`, `Contents/section0.xml`, `Contents/content.hpf`.
3. `zf.infolist()[0].filename == "mimetype"`이고 `compress_type == zipfile.ZIP_STORED`이며 `zf.read("mimetype") == b"application/hwp+zip"`.
4. `mimetype`을 제외한 모든 엔트리가 `lxml.etree.fromstring()`으로 파싱 가능한 well-formed XML이다.
5. 존재하지 않는 상위 디렉터리 경로를 줘도 `mkdir(parents=True)`로 자동 생성되어 성공한다.
6. 쓰기 불가능한 경로(예: 존재하지 않는 드라이브 문자, 읽기 전용 위치)를 주면 `ContainerBuildError`(`common.exceptions`)가 발생한다.
7. `add_section_xml(container_path, xml_bytes)`를 호출하면 `Contents/section0.xml`의 내용이 `xml_bytes`로 교체되고, 그 외 7개 엔트리는 그대로 유지된다(다시 `zipfile`로 열어 `namelist()`와 `mimetype`의 `compress_type`이 이전과 동일한지 비교).
8. 존재하지 않는 `container_path`로 `add_section_xml`을 호출하면 `ContainerBuildError`가 발생한다.
9. `add_section_xml`이 실패해도(예: 손상된 zip을 대상으로 호출) 원본 `container_path` 파일이 훼손되지 않고(임시 파일에만 쓰다가 실패), `.tmp` 임시 파일이 남지 않는다.

### AC-2. `hwpx_kernel/schema.py`
1. `SCHEMA_VERSION == "1.0"`.
2. `pt_to_hwpunit(1.0) == 100`.
3. `text_block_to_paragraph_fragment(TextBlockIR(...))`가 `lxml.etree._Element`를 반환하고, 로컬 이름이 `p`이며 `{http://www.hancom.co.kr/hwpml/2011/paragraph}p`로 완전한정된다. 자식으로 `run` → `t`가 존재하고 `t.text`가 입력 `block.text`와 동일하다.
4. `TableBlockIR(rows=2, cols=2, cells=[4개 TableCellIR])`을 `table_block_to_table_fragment`에 넣으면 `tr` 2개, 각 `tr`에 `tc` 2개(총 4개)가 생성된다.
5. `image_block_to_picture_fragment(ImageBlockIR(...), bin_data_id="X")`가 반환한 `pic` 엘리먼트의 `binDataIDRef` 속성이 `"X"`와 같다.
6. `fragment_to_bytes(element)`가 반환한 바이트에 XML 선언(`<?xml`)이 **포함되지 않는다**(프래그먼트이므로).
7. unit-5/6/7은 이 모듈의 함수를 **수정하지 않고 import해서 소비만** 한다 — 만약 시그니처를 바꿔야 할 필요가 생기면(예: 여러 문단을 가진 셀 지원) 이 계약 파일 자체를 갱신하고 `SCHEMA_VERSION`을 올려야 하며, unit-4가 담당하지 않는 한 오케스트레이터에게 공유 자원 변경으로 보고해야 한다.

### unit-5/6/7을 위한 사용 안내(요약)
- 문단: `hwpx_kernel.schema.text_block_to_paragraph_fragment(text_block_ir)` 호출 → 반환된 `<hp:p>`를 orchestrator가 섹션 본문에 순서대로 삽입.
- 표: 병합 셀이 없는 단순 표는 `table_block_to_table_fragment(table_block_ir)`을 그대로 호출. 병합 셀이 있어 행 우선 순회 가정이 깨지는 경우 `table_cell_to_cell_fragment(cell, row=..., col=...)`를 직접 반복 호출해 `<hp:tr>`/`<hp:tbl>`을 unit-6이 직접 조립.
- 그림: 먼저 `block.raw_bytes`를 BinData 파트에 저장하는 로직이 필요(현재 `container.py`에 없음 — 필요 시 공유 자원 이슈로 오케스트레이터에 보고), 저장 후 부여한 id를 `image_block_to_picture_fragment(image_block_ir, bin_data_id=그_id)`에 넘겨 배치 프래그먼트를 받는다.
- 완성된 프래그먼트들은 `fragment_to_bytes()`로 직렬화하거나, `etree.Element`인 채로 orchestrator가 `hwpx_kernel.schema.build_reference_section_body(fragments)`(또는 자체 조립 로직)로 섹션 본문을 만든 뒤 `hwpx_kernel.container.add_section_xml(container_path, section_bytes)`를 호출해 `build_empty_container()`가 만든 골격에 실제 내용을 채운다.

---

## 8. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

### traceability.md
- **REQ-008** 행의 "작업 단위" 컬럼: 기존 값 확인 후 `unit-4`(container.py/schema.py, 공용 계약)가 포함되도록 갱신(이미 unit-4로 되어 있다면 변경 불필요, 비고에 unit-5/6/7이 이어서 REQ-008을 마저 구현한다는 점 추가 권장).
- **REQ-008** 행의 "구현 상태" 컬럼: `Not Started` → **`Implemented (unit-4 컨테이너 골격/공용 계약, 05단계 완료, 06단계 단위테스트 대기) — 단, 실제 한컴오피스 뷰어에서 열리는지는 미검증(DEC-017). 공개 표준(OWPML/KS X 6101) 일반 지식 기반 추정 구현이며, unit-5/6/7 통합(unit-8) 이후 또는 실제 한글 확보 후 별도 호환성 검증이 반드시 필요함`** 형태로 갱신 요청(문구에 "실제 한글 미검증" 단서를 반드시 포함해 달라는 요청).

### decisions.md
- 별도 신규 결정(DEC) 추가 요청 없음 — 이번 unit은 DEC-017이 이미 승인한 방침(공개 표준 일반 지식 기반 진행)을 그대로 수행했을 뿐, 새로운 비가역적 판단을 하지 않았다.

### 기타 후속 조치 제안(강제 아님, 참고용)
- `pdf_to_hwpx/hwpx_kernel/__init__.py`의 stale docstring("schema.py/container.py는 아직 생성되지 않았다") 정리 — 이 unit의 파일 범위 밖이라 직접 수정하지 않았다(3절 참고). unit-5/6/7 착수 전 또는 다음 정리 단위에서 갱신 권장.
- BinData(이미지 바이너리 파트) 삽입을 위한 `container.py` 확장 필요 여부는 unit-7 착수 시점에 재확인 필요(7절 "unit-5/6/7을 위한 사용 안내" 참고) — 이 unit의 현재 파일 범위에는 BinData 관련 함수가 없다.

---

## 9. 추가 반영 (2026-09-28, 오케스트레이터 직접 기재) — `add_bin_data()` 신규 함수

- 위 8절이 예고한 대로, unit-7 착수 결과 BinData 삽입 기능이 실제로 필요해졌고 `container.py`에 `add_bin_data(container_path, entries: Mapping[str, tuple[bytes, str]]) -> None`(약 146줄)이 추가 구현되었다. 이 함수의 설계 근거·계약·범위 한정은 `container.py` 286~319행 docstring에 상세히 기술되어 있다.
- **05단계 산출물인 이 note가 원래 이 추가를 반영하지 못한 채 남아 있었던 절차적 공백**을 `docs/harness/units/unit-4-test.md`의 "재작업/추가검증 (2026-09-28)" 섹션(R0)이 발견했다 — 코드 자체는 게이트1(컴파일)/게이트2(자체 코드리뷰)를 그 06 세션이 독립적으로 재구성해 통과 확인했으므로 05단계로 반려되지 않았다. 본 절은 그 공백을 메우기 위해 오케스트레이터가 직접 추가한 것이다(신규 05 세션 재호출 없이 처리 — 문서 공백일 뿐 기능 결함이 아니었기 때문).
- 06단계 검증 결과(회귀 48/48 PASS + 신규 29개 PASS, 라인커버리지 100%, 뮤테이션 2건 모두 탐지, 결함 0건, 리스크 4건)는 `unit-4-test.md` R1~R11에 완전히 기록되어 있으므로 여기서 반복하지 않는다.
- 최종 판정: **PASS** — unit-7 AC-5(BinData 실제 zip 저장) 및 unit-8(오케스트레이터 통합)에서 이 함수를 그대로 소비 가능.
