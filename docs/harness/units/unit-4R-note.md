# unit-4R 구현 노트 (HWPX 커널 재작업, 공통 선행)

- 단계: 05 구현 / 근거: DEC-051, DEC-055~062, 03 v5.2 §1-4·§2-4·§3-3·§3-4, `docs/harness/analysis/hwpx-reference-structure.md`(분석서)
- 커버 REQ: REQ-008 (호환 버전 준수). 이력: 기존 `unit-4-note.md`(v1, 자체 스키마)는 보존한다. 이 노트가 현행이다.
- **속도 트랙: L3 (오케스트레이터가 표기하지 않아 기본값 적용)**
- 병렬 실행: 예(병렬 웨이브). 동시에 unit-27(구조 검증기)과 webapp 수정 에이전트 2명이 작업 중이었다. unit-27 파일은 읽기만 했고(`git status` 확인용), 수정·import하지 않았다. webapp은 읽지도 수정하지도 않았다.
- **상태: 자동 테스트/게이트 1·2 통과. 그러나 AC-H1(사용자가 한글에서 열어 확인, 게이트 G1)은 미수행 = "G1 대기". 이 unit을 PASS로 선언하지 않는다.**

## 1. 구현 범위

| 파일 | 내용 |
|---|---|
| `hwpx_kernel/constants.py` | 15개 네임스페이스, 패키지 메타 네임스페이스 3종, `qn()`, `XML_PROLOG`(R1 바이트 형태), `serialize_xml()`, `new_root()`, `pt_to_hwpunit()` |
| `hwpx_kernel/fonts.py` | PDF 글꼴명 -> sans/serif/mono 분류(서브셋 접두어 제거, sans를 serif보다 먼저 검사) -> 돋움(0)/바탕(1)/돋움체(2), lang별 typeInfo |
| `hwpx_kernel/flow.py` | L1 상수(양자화 200/100, 줄간격 100%, 정렬 임계값, `EMIT_LINESEGS`, baseline 0.85, flags 393216), `FlowTracker.place()/new_page()/for_page()`, `FlowPlacement` |
| `hwpx_kernel/styles.py` | `StyleRegistry`(charPr/paraPr/borderFill interning, id 시작값 0/0/1, 양자화, 5000건 소프트 한도), `serialize_header(sec_cnt)`(분석서 §5 순서, itemCnt/fontCnt/secCnt 자동, `hp:switch` default=case의 2배), `CharSpec/ParaSpec/BorderSide/BorderSpec`, `NO_BORDER`, `SOLID_THIN` |
| `hwpx_kernel/context.py` | `DocContext`(registry, `IdAllocator`(tbl id 순증가·zOrder 0부터), `unsupported` 경고 집계, `build_header()`) |
| `hwpx_kernel/schema.py` | `SCHEMA_VERSION="2.0"`, `sanitize_text`, `make_run/make_paragraph/make_lineseg/make_linesegarray/make_table/make_table_cell`. 표 그리드 검사(tr 수, rowAddr=tr 인덱스, colAddr 오름차순, 겹침·미덮임·그리드 밖). 자체 속성 없음. IR 직접 변환 함수(v1.0)는 폐기 |
| `hwpx_kernel/section.py` | `PageSetup`(`a4()`, `from_content_bounds()` 클램프 [2835,14173]/[4251,14173]), `build_sec_pr`, `build_col_pr_ctrl`, `inject_section_properties`(첫 문단 첫 run 맨 앞에 secPr, ctrl(colPr)), `build_section_xml`(문단 0개면 lineseg 있는 빈 문단 생성) |
| `hwpx_kernel/container.py` | `HwpxPackage`(`set_header/add_section/set_preview_text/to_bytes/write`), R1 zip 순서, mimetype·version.xml stored, 타임스탬프 1980-01-01, `VersionInfo`(`VERSION_R1_OBSERVED`/`VERSION_OWN`), `format_preview_text`, 메타 파트 빌더(version/container/manifest/settings/content.hpf). `write()`는 임시 파일 -> replace 원자적 쓰기, 실패는 `ContainerBuildError`. header `secCnt`와 구역 수 불일치는 `ContainerBuildError` |
| `common/exceptions.py` | `HwpxSchemaError(HwpxWriteError)` 추가만 |
| `tools/hwpx_probe.py` | 프로브 P1a/P1b/P2/P3/P4a/P4b(+P4c) 생성기와 안내 텍스트(`README-probe.txt`, 표준출력) |
| `tests/hwpx_kernel/*` | 전면 교체(132 테스트): `conftest.py`, `helpers.py`, `test_constants_fonts.py`, `test_flow.py`, `test_styles.py`, `test_schema.py`, `test_section.py`, `test_container.py`, `test_container_bin_data.py`(내용 교체, 6절 참고), `test_probe.py` |

구현하지 않은 것(의도): 그림 `hp:pic`·BinData(unit-4P, 04_그림 대기; `DocContext.note_unsupported("picture")` 집계 경로와 "미구현" 테스트만), 이탤릭, 가로 용지 값, 바탕쪽, pageNum, PrvImage, 머리말/꼬리말/각주, lineBreak, 탭 요소.

## 2. 설계서 대비 편차 (사유 포함)

1. **분석서에 값이 없던 구조 값을 R1에서 로컬로 읽어 확정했다.** 분석서는 구조·순서·일부 값만 적었고, charPr 하위 요소(ratio/spacing/relSz/offset/underline/strikeout/outline/shadow)의 기본값, paraPr `breakSetting`/`autoSpacing`/`heading`/`border` 값, numbering `paraHead` 7수준, tabPr 형태, lang별 `typeInfo`, settings.xml 항목, secPr 자식 속성 값, `hpf` `date` 문자열 형식은 없었다. 지시("필요하면 구조 확인을 위해 로컬에서 읽되")에 따라 태그/속성/enum/수치만 임시 스크립트로 출력해 확인했고, 본문·제목·고유명사는 복사하지 않았다. `numbering`의 `^1.` 같은 값은 번호 서식 토큰이며 문서 내용이 아니다. 스크립트·덤프는 `.harness-tmp/_05_unit4R/`에서 만들고 삭제했다.
2. **글꼴 id**: 설계(§2-4-4)대로 모든 lang에서 0=돋움, 1=바탕, 2=돋움체 3개만 등록한다. R1에는 이 글꼴들이 id 1~3에 있고 HFT 글꼴 등이 함께 있다(글꼴 수 7~16). 분석서가 "id는 lang 안에서 0부터 연속"이라고 관찰했으므로 0~2 연속 3개는 구조상 부합한다. 신규 문서의 실제 기본 글꼴은 01_빈문서 수령 후 재검토(`fonts.py` 표 1곳).
3. **`VERSION_OWN`을 패키지 기본값**으로 했다(03 §2-4-3 5번의 "정직한 표기 지향"). 다만 프로브 P1a와 P2~P4는 변수를 줄이기 위해 R1 관찰 값을 쓴다. G1에서 P1b(자체 값)가 거부되면 기본값을 `VERSION_R1_OBSERVED`로 바꿔야 하며 이는 사용자 판단(Q4)이다.
4. **프로브 추가 2건**: P2에 문단 6·7(바탕/돋움체 계열, 글꼴 id 1·2를 charPr가 실제로 참조하는 경로 확인), P4c(강제 쪽 나눔 없이 자연 넘김, `pageBreak="1"`의 영향을 분리). 분석서 §12-2의 P1a/P1b/P2/P3/P4a/P4b는 모두 포함.
5. **zip 속성**: `create_system=0`, `external_attr=0x20`으로 고정했다(OS 무관 결정성). R1은 `create_system=11`, `external_attr=0x81800020`이다. 분석서가 【미확인】으로 둔 항목이며, 실험으로만 확정한다(E-Z 계열, 11절 질문 1).
6. **`lineseg.horzsize`**: 설계(§3-3-4 6)대로 콘텐츠 폭 - left(= 42522)를 쓴다. R1 본문은 그보다 2 작은 42520을 쓴다(의미 【미확인】). E-L 결과 후 조정.
7. **`settings.xml` `CaretPosition pos`**: R1은 32, 우리는 0. 뷰어 상태값이라 내용과 무관하다는 분석서 추론에 따름.
8. **`content.hpf` `creator`**: R1은 빈 값이지만 설계(§2-4-3 6번)대로 생성기 이름을 넣는다.
9. `hpf` `date` 문자열은 R1의 구조 패턴(`YYYY년 MM월 DD일 X요일 오전|오후 H:MM:SS`, 시 무패딩)을 따랐다. 값은 변환 시각(UTC)이다. 형식 수용은 【실험 대상 아님, G1에서 함께 관찰】.
10. `FlowTracker.for_page(page_setup)`의 인자는 순환 import 회피를 위해 타입 주석을 생략했다(구조적 타이핑).

## 3. 후속 unit(5R/6R/7R/8R)을 위한 공개 계약 요약

```python
# context
ctx = DocContext.new()            # .registry: StyleRegistry, .ids.next_table() -> (tbl_id, zOrder), .note_unsupported(kind), .build_header(sec_cnt) -> bytes
# styles
ctx.registry.char_pr(CharSpec(height=<1/100pt int>, family='sans|serif|mono', bold=False, text_color='#000000')) -> int
ctx.registry.para_pr(ParaSpec(align='LEFT|CENTER|RIGHT|JUSTIFY', left=0, intent=0, prev=0, line_spacing=100)) -> int   # 값은 내부에서 양자화
ctx.registry.border_fill(SOLID_THIN | NO_BORDER | BorderSpec(...)) -> int
# fonts / flow
resolve_font(pdf_name) -> FontChoice(family, face, font_id)
FlowTracker.for_page(page_setup) ; tracker.place(top_pt, bottom_pt, x0_pt, x1_pt) -> FlowPlacement ; tracker.new_page()
# schema
make_run(char_pr_id, text=None, *, children=()) ; make_paragraph(para_pr_id=, runs=, linesegs=None, style_id=0, page_break=False)
make_lineseg(vertpos=, vertsize=, horzpos=, horzsize=) ; make_table(tbl_id=, z_order=, rows=[[tc..]..], row_cnt=, col_cnt=, width=, height=, border_fill_id=, page_break='CELL')
make_table_cell(col=, row=, col_span=, row_span=, width=, height=, border_fill_id=, paragraphs=[..], vert_align='CENTER')
# section / container
PageSetup.a4() | PageSetup.from_content_bounds(w_pt, h_pt, min_x0, max_x1, min_y0, max_y1)
build_section_xml(paragraphs, page_setup) -> bytes        # paragraphs[0]가 변경됨(secPr 주입)
pkg = HwpxPackage(PackageMeta(...)); pkg.set_header(ctx.build_header(n)); pkg.add_section(xml)*n; pkg.set_preview_text(format_preview_text(texts)); pkg.write(path) / pkg.to_bytes()
```
- 표를 담는 문단: `make_paragraph(runs=[make_run(char_id, children=[tbl])], linesegs=[lineseg(vertsize=표 높이, horzsize=콘텐츠 폭-left)])`(빌더 책임).
- 빌더는 `flow.EMIT_LINESEGS`가 False면 `linesegs=None`을 넘긴다(스위치 소비는 빌더 책임).
- 구역이 둘 이상이면 `ctx.build_header(구역 수)`를 마지막에 호출한다(레지스트리가 다 채워진 뒤).

## 4. 검증 결과 (게이트 1·2, 로컬 동작 확인)

- **게이트 1(린트/정적 분석)**: 프로젝트에 lint/type-check/formatter 설정이 **없다**(`pyproject.toml`에 ruff/black/mypy 설정 없음). 대신 ruff를 격리 venv(`.harness-tmp/_05_unit4R/venv`)에 설치해 실행했다. 주변에 적용된 설정(프로젝트 설정 파일은 없음, 규칙 집합은 기본보다 넓음)으로 **내 파일 전부 "All checks passed"**. `python -m pytest tests/hwpx_kernel` **132 passed**. (`pdf_to_hwpx/hwpx_kernel/validator.py`의 ruff 지적 2건은 unit-27 소유라 건드리지 않았다.)
- **로컬 구조 확인**: 프로브 P1a/P2/P3/P4b를 R1과 파트별로 비교(요소 경로·속성명 집합). 우리 출력에서 R1에 없는 요소 경로/속성 0건. R1에는 있으나 우리에게 없는 것은 선택 요소뿐(`diagonal`, `fillBrush`, `substFont`, tabPr 자식, `pageNum`, `masterPage`, `lineBreak`, `charStyleIDRef`; bold는 P2에서 확인). 생성 zip 전체 XML well-formed, 파트 내 루트 xmlns 정확히 15개.
- 구조 프로파일 diff(unit-27)는 완료 후 오케스트레이터가 통합 확인한다(이 unit은 validator를 import하지 않았다).
- **게이트 2 체크리스트**
  - [x] 설계서/분석서 명세와 실제 구현 일치(편차는 2절)
  - [x] 에러 처리 누락 없음: 쓰기 실패 -> `ContainerBuildError`, 인자 위반 -> `HwpxSchemaError`/`ValueError`, 예외를 삼키는 코드 없음
  - [x] 입력 검증이 경계에서 수행됨: 스타일 열거형/색/경계선 너비 정규식, 표 그리드, 텍스트 XML 금지 문자 제거
  - [x] 하드코딩 시크릿 없음
  - [x] 신규 외부 의존성 없음(lxml, 기존 선언). 새 패키지는 테스트/린트 전용으로 격리 venv에만 설치(`pytest`, `ruff`, `pypdf`, `reportlab`은 tests/conftest.py가 import하기 때문)
  - [x] 범위 밖 변경 없음(`exceptions.py`는 허용된 예외 추가 1건)
- 임시 아티팩트: 작업 스크립트·덤프·pytest 출력은 삭제. 격리 venv(`.harness-tmp/_05_unit4R/venv`)도 작업 종료 시 삭제. **프로브 파일은 사용자 전달물이라 `.harness-tmp/probe/`에 남겼다**(G1 완료 후 오케스트레이터가 삭제). 프로젝트 루트에 egg-info 등 부산물 없음(`pip install -e .`를 실행하지 않았다).

## 5. 수동으로 확인이 필요한 부분 (사용자, 게이트 G1)

프로브 위치: `C:\big21\vibe-coding\PDF-TO-HWPX\.harness-tmp\probe\` (재생성: `python tools/hwpx_probe.py`, 다른 경로는 `--out DIR`)

| 파일 | 확인 목적 | 기대 관찰 |
|---|---|---|
| `P1a_empty_r1version.hwpx` | 초집합 패키지/header/section 수용(version.xml은 R1 값) | 문서로 열림, 빈 1쪽, 경고 없음, 다른 이름으로 저장 가능 |
| `P1b_empty_ownversion.hwpx` | E-V: application/appVersion만 자체 값 | P1a와 동일. P1a만 열리면 Q4 발생 |
| `P2_char_para_style.hwpx` | charPr/paraPr 동적 생성 | 문단 7개: 보통 10pt / 굵게 / 20pt / 가운데 / 20pt 들여쓰기 / 바탕 계열 / 돋움체 계열 |
| `P3_tables.hwpx` | 표 구조·borderFill·병합 | 2x2 표, 3x3 병합 표(첫 행 3칸 병합, 셋째 행 2칸 병합), 사방 실선, 셀 편집 가능 |
| `P4a_2pages_lineseg.hwpx` | E-B(`pageBreak="1"`), 문단 앞 간격, lineseg 있음 | 정확히 2쪽, 둘째 쪽이 31번째 문단부터, 간격 일정 |
| `P4b_2pages_nolineseg.hwpx` | E-L: lineseg 생략 | P4a와 동일하게 보이면 생략 가능 |
| `P4c_natural_pagebreak.hwpx` | 강제 나눔 없는 자연 넘김 | 여러 쪽으로 자연스럽게 넘어감 |

열어보기 절차: (1) 위 폴더의 `README-probe.txt`를 연다. (2) P1a -> P1b -> P2 -> P3 -> P4a -> P4b -> P4c 순으로 한글에서 열어 분석서 §12-1 양식(파일명 / 한글 버전 / ① 열림 여부 / ② 경고·복구 대화상자 문구 / ③ 표시 일치 / ④ 다른 이름으로 저장 성공 여부)으로 기록한다. (3) **P1a가 열리지 않으면** 나머지는 볼 필요 없이 알려 주고, 01_빈문서.hwpx가 있으면 분석서 §12-3의 층 교체 진단(D-시리즈)으로 넘어간다. 진단 도구(`tools/`의 D-시리즈 스크립트)는 이 unit 범위에 없다. P1a 실패 시 별도 unit/지시가 필요하다.

기록 파일은 `docs/harness/units/unit-4R-hangul-check.md`에 작성한다(03 §1-4-3).

## 6. 6단계 테스터가 알아야 할 인수 조건 (Acceptance Criteria)

자동 확인 가능:
- **AC-4R-1** `pytest tests/hwpx_kernel` 132건 전부 통과(환경에 lxml, pytest, pypdf, reportlab 필요: `tests/conftest.py`가 pypdf/reportlab을 import함).
- **AC-4R-2** `HwpxPackage`가 만든 zip의 첫 엔트리는 `mimetype`(stored, 정확히 `application/hwp+zip` 19바이트, extra 없음), 엔트리 순서는 `mimetype, version.xml, Contents/header.xml, Contents/section<N>.xml, Preview/PrvText.txt, settings.xml, META-INF/container.xml, Contents/content.hpf, META-INF/manifest.xml`, 모든 타임스탬프 1980-01-01, `version.xml`만 mimetype 외에 stored. `masterpage`/`PrvImage.png`/`BinData` 없음.
- **AC-4R-3** 모든 XML 파트가 well-formed이고 `<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>` 직후 개행 없이 루트가 이어진다. `header/section/hpf` 루트는 15개 xmlns를 정확히 1회 선언한다(자식에 중복 선언 없음).
- **AC-4R-4** header: 최상위 순서 `beginNum, refList, compatibleDocument, docOption, trackchageConfig`, refList 순서 `fontfaces, borderFills, charProperties, tabProperties, numberings, paraProperties, styles`, `itemCnt/fontCnt/secCnt`가 실제 개수와 일치, borderFill·numbering id는 1부터 나머지는 0부터, `hp:switch` default 분기 길이 값 = case 값 x 2(lineSpacing PERCENT는 동일).
- **AC-4R-5** section: 구역마다 `hp:secPr` 정확히 1개가 첫 문단 첫 run 안에 있고 그 뒤에 `ctrl/colPr`, 문단 속성 `id paraPrIDRef styleIDRef pageBreak columnBreak merged`, 자식 순서 `run+ -> linesegarray`.
- **AC-4R-6** 표: `tbl -> sz -> pos -> outMargin -> inMargin -> tr*`, `tc -> subList -> cellAddr -> cellSpan -> cellSz -> cellMargin`, 병합으로 덮이는 셀은 `tc`가 없고 그리드를 겹침 없이 완전히 덮음(위반 시 `HwpxSchemaError`).
- **AC-4R-7** 어디에도 B0 시절 자체 이름(`bboxPt`, `fontName`, `fontSizeHwpunit`, `charShapeIDRef`, `paraShapeIDRef`, `tagID` 등)이 없다. 모든 ID 참조가 header에 존재(끊김 0), `opf:title`은 비어 있음.
- **AC-4R-8** 같은 입력 + 고정 `PackageMeta(created=...)`이면 출력 바이트가 동일(결정성).
- **AC-4R-9** `tools/hwpx_probe.py`가 7개 프로브와 `README-probe.txt`를 만들고, P1a/P1b는 `version.xml`의 application/appVersion만 다르며, P4b는 linesegarray가 없고, P4a는 `pageBreak="1"`이 정확히 31번째 문단에만 있다.
- **AC-4R-10 (유도, 독립 재현 가능)** unit-27 완료 후 오케스트레이터가 프로브 7개를 `validate_hwpx`에 통과시켰을 때 위반 0건.

사용자 확인 필요(자동으로 PASS 선언 금지):
- **AC-H1 (G1): 대기.** P1a/P1b/P2/P3/P4가 한글에서 열림(①문서로 인식 ②복구/손상 경고 없음 ④다른 이름으로 저장). `unit-4R-hangul-check.md`가 없으면 06은 **CONDITIONAL PASS(한글 확인 대기)**로만 판정하고 5R/6R/7R/8R 착수를 허용하지 않는다(DEC-061/062).

## 7. 후속 unit 영향 목록 (이 unit이 깨뜨린 것, "후속 unit 재작업에서 복구")

이 unit은 `hwpx_writer/*`, `core/orchestrator.py`, 다른 테스트를 수정하지 않았다. 새 커널 API로 아래가 깨진다(실측: import 시 `ImportError` 확인).

| 대상 | 깨지는 이유 | 복구 unit |
|---|---|---|
| `hwpx_writer/paragraph_builder.py` | `schema.text_block_to_paragraph_fragment` 삭제 | unit-5R |
| `hwpx_writer/table_builder.py` | `container.NAMESPACES`, `schema.table_cell_to_cell_fragment` 삭제 | unit-6R |
| `hwpx_writer/image_embedder.py` | `schema.image_block_to_picture_fragment` 삭제 | unit-4P -> 7R |
| `core/orchestrator.py` | `container.build_empty_container/add_section_xml/add_bin_data`, `schema.build_reference_section_body`, `SCHEMA_VERSION`("1.0"->"2.0", `HWPX_MIN_SUPPORTED_VERSION` 의미 변경) | unit-8R |
| `tests/hwpx_writer/*`, `tests/core/test_orchestrator.py`, `tests/integration/test_feature_a_pipeline.py` | 위 모듈 import 실패 (`NAMESPACES` import 포함) | 각 후속 unit |
| **`webapp/converter` 등 `pdf_to_hwpx.core.orchestrator`를 import하는 모든 경로** | 위 orchestrator가 import 단계에서 실패. 이 unit은 webapp을 읽지 않아 실제 영향 지점을 확인하지 못했다 | **오케스트레이터가 확인 필요**(webapp 테스트가 orchestrator를 실제로 import하면 unit-8R 전까지 실패) |

## 8. 공유 문서 갱신 요청 (오케스트레이터 반영 대기 — 이 unit은 traceability.md/decisions.md/설계서를 수정하지 않았다)

- traceability.md: REQ-008 "작업 단위"에 `unit-4R` 추가, "구현 상태": `구현됨(자동 테스트 132 PASS, 한글 수용 G1 대기)`. REQ-002/003/004/005/009/010은 변경 없음(5R/6R/7R/8R 대기).
- 조정 요청: `tests/hwpx_kernel/test_container_bin_data.py`의 파일명이 내용(DocContext/미지원 경로 테스트)과 맞지 않는다. 이 세션에서 `git rm`이 권한 정책으로 거부되어 삭제·이름변경을 못 했다. 오케스트레이터/사용자가 `test_context.py` 등으로 정리하면 된다(내용 그대로 옮기면 됨).
- decisions.md 후보(모두 가역·근거 note 2절): (1) 분석서에 없던 구조 값의 R1 로컬 확인 후 코드 상수화(2절 1번, 기밀 규칙 준수), (2) `VERSION_OWN` 기본값·프로브 P2~P4의 R1 version 고정(2절 3번, Q4 대기), (3) 프로브 P4c·P2 문단 6~7 추가(2절 4번).

## 9. git status 원문 (작업 종료 시점)

```
 M docs/harness/03-system-design.md                     (03 소유, 타 단위)
 M docs/harness/decisions.md                            (오케스트레이터)
 M docs/harness/traceability.md                         (오케스트레이터)
 M docs/harness/units/unit-20-note.md                   (unit-20 계열, 타 단위)
 M docs/harness/units/unit-20-test.md                   (unit-20 계열, 타 단위)
 M docs/harness/units/unit-22-note.md                   (unit-22, 타 단위)
 M docs/harness/verify-log_03-system-design.md          (03, 타 단위)
 M docs/harness/verify-log_unit-20-note.md              (unit-20 계열, 타 단위)
 M docs/harness/verify-log_unit-20-test.md              (unit-20 계열, 타 단위)
 M pdf_to_hwpx/common/exceptions.py                     (unit-4R: HwpxSchemaError 추가)
 M pdf_to_hwpx/hwpx_kernel/__init__.py                  (unit-4R)
 M pdf_to_hwpx/hwpx_kernel/container.py                 (unit-4R, 전면 교체)
 M pdf_to_hwpx/hwpx_kernel/schema.py                    (unit-4R, 전면 교체)
 M tests/hwpx_kernel/test_container.py                  (unit-4R, 전면 교체)
 M tests/hwpx_kernel/test_container_bin_data.py         (unit-4R, 내용 교체)
 M tests/hwpx_kernel/test_schema.py                     (unit-4R, 전면 교체)
 M webapp/converter/cleanup.py                          (webapp 수정 에이전트, 타 단위)
 M webapp/converter/views.py                            (webapp 수정 에이전트, 타 단위)
?? "00 교육자료/"                                        (사용자 소유로 보이는 무관 디렉터리, 이 unit 아님)
?? docs/harness/analysis/                               (03)
?? docs/harness/verify-log_unit-22-note.md              (unit-22, 타 단위)
?? pdf_to_hwpx/hwpx_kernel/{constants,context,flow,fonts,section,styles}.py   (unit-4R 신규)
?? pdf_to_hwpx/hwpx_kernel/validator.py                 (unit-27, 타 단위)
?? tests/fixtures/                                      (unit-27, 타 단위)
?? tests/hwpx_kernel/{conftest,helpers,test_constants_fonts,test_flow,test_probe,test_section,test_styles}.py   (unit-4R 신규)
?? tests/hwpx_validator/                                (unit-27, 타 단위)
?? tools/                                               (hwpx_probe.py = unit-4R, 그 외 = unit-27)
?? docs/harness/units/unit-4R-note.md, docs/harness/verify-log_unit-4R-note.md   (unit-4R, 본 문서)
```
(주: 위 목록은 종료 직전 `git status --short` 출력에 소유 주석을 붙인 것이다. `.harness-tmp/`는 .gitignore 대상이라 나타나지 않는다.)

## 10. 미결 질문 (규칙 A)

1. zip `create_system`/`external_attr`를 R1 값(11 / 0x81800020)으로 맞춰야 하는지는 분석서 【미확인】이다. P1a가 열리면 불필요, 안 열리면 D-시리즈 진단 후보다.
2. G1에서 P1b(자체 version)가 거부되면 한글 표기 모사 여부는 사용자 판단(Q4).
3. P1a 실패 시 분석서 §12-3 D-시리즈 진단 도구를 별도 unit으로 만들지(01_빈문서.hwpx 필요) 결정 필요.
4. `참조HWPX/`에는 현재 `README-파일만들기.txt`만 있다. 01_빈문서/04_그림/02_글자서식이 오면 2절 2번(글꼴 표)과 unit-4P를 진행한다.
