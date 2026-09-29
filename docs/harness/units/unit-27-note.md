# unit-27 구현 노트 — HWPX 구조 검증기 + 구조 프로파일 + diff 테스트 (신규)

- 근거: 03-system-design.md v5.2 §1-4(unit-27 행), §3-4(3층 테스트, V1~V13), DEC-051/054/060/061/062, `analysis/hwpx-reference-structure.md`
- **속도 트랙: L3** (오케스트레이터로부터 표기를 전달받지 못해 기본값 적용)
- **병렬 실행**: unit-4R과 동시에 실행됨(4R 소유 파일은 읽기만 했고 수정하지 않았다. validator는 zip과 프로파일 JSON만 읽고 커널 모듈을 import하지 않는다).
- 목적 재확인: 이 검증기는 "우리 출력이 한글 저장본의 구조 프로파일과 얼마나 다른가"를 본다. **통과해도 한글 수용을 보장하지 않는다** (게이트 G1/G2가 별도).

## 1. 구현 범위

| 파일 | 내용 |
|---|---|
| `pdf_to_hwpx/hwpx_kernel/validator.py` | `validate_hwpx(source, profile=None, *, ignore=(), table_width_tolerance=10) -> list[Violation]`, `load_profile()`, `Profile`, `Violation(code, part, location, message)`, CLI(`python pdf_to_hwpx/hwpx_kernel/validator.py file.hwpx [--profile p.json]`, 위반 있으면 종료코드 1). 의존: 표준 라이브러리 + lxml(기존 의존성). 다른 커널 모듈 import 없음 |
| `tools/hwpx_profile_extract.py` | 참조 HWPX(1개 이상) -> 프로파일 JSON. 메모리 처리(임시 파일 없음), 저장 직전 누출 스캔에 실패하면 파일을 쓰지 않음. 여러 참조를 주면 병합(필수 = 전 발생에서 존재, 어휘 = 합집합) -> 01~04 수령 후 재생성용 |
| `tests/fixtures/hwpx_profile.json` | 내용 없는 구조 프로파일(61.5 KB, 요소 121종, 파트 패턴 11개). R1 1건에서 추출 |
| `tests/hwpx_validator/` | `synth.py`(프로파일 기반 합성 fixture 생성기), `cases.py`(음성 사례 72건 카탈로그), `test_negative.py`, `test_positive.py`, `test_mutants.py`(50 뮤턴트), `test_extractor.py`, `test_privacy_and_profile.py`, `conftest.py`, `helpers.py` |

프로파일에 담긴 것: 파트 패턴(종류·역할·필수 여부·manifest/spine 소속·루트 요소·루트 네임스페이스 선언 집합·관찰된 압축 방식), zip 규칙(mimetype 첫 엔트리·stored·정확한 내용, 관찰된 엔트리 순서), XML 프롤로그 바이트 형태, 네임스페이스 15종, **요소별** {허용 속성, 필수 속성, enum 어휘, 허용 자식, 필수 자식, 자식 순서 관계(관찰된 단방향 쌍), 텍스트 허용 여부, 개수 속성 규칙}, ID 정의/참조 관계표, 고유 ID 규칙, 열거형 시퀀스(fontface lang, pageBorderFill type), switch 배율 규칙(기호: `double`). **수치는 없다**(테스트가 수치 리프 0건을 상시 확인).

## 2. V1~V13 -> 구현 대응 (분석서와 대조)

| 규칙(03 §3-4) | 위반 코드 | 비고 |
|---|---|---|
| V1 zip 배치 | `V1.MIMETYPE_MISSING/ORDER/COMPRESSED/CONTENT/EXTRA`, `V1.DUPLICATE`, `V1.NOT_ZIP` | 분석서 §2: 첫 엔트리·stored·19바이트 내용·extra 없음 |
| V2 필수 파트 | `V2.PART_MISSING`, `V2.UNKNOWN_PART`, `V2.SECTION_GAP` | 필수 = 참조에 있고 분석서 §11에서 "생략 가능"이 아닌 것(masterpage, PrvImage만 선택) |
| V3 XML 적정성 | `V3.PROLOG`, `V3.XML_PARSE`, `V3.ROOT`, `V3.NS_MISSING/MISMATCH/UNKNOWN` | 프롤로그는 참조 바이트 형태(따옴표·`?>` 앞 공백·루트 직결) |
| V4 어휘 | `V4.ELEMENT`, `V4.ATTR` | B0의 `bboxPt`, `fontName`, `charShapeIDRef` 등 |
| V5 필수 속성 | `V5.ATTR_MISSING` | R1의 모든 발생에 있던 속성 |
| V6 자식 순서 | `V6.ORDER` | 관찰된 **단방향** 쌍만 강제(양방향 관찰 = 자유). 예: secPr/ctrl 순서는 R1에서 양쪽이 나타나 자유 |
| V7 ID 무결성 | `V7.DANGLING_REF` | 분석서 §5-4 그래프 16종 + fontRef 7종(언어별 글꼴 id). `none` 센티널(heading.idRef=0, paraHead.charPrIDRef=uint32 max) 처리 |
| V8 개수 | `V8.COUNT_MISMATCH`, `V8.SECCNT` | itemCnt/fontCnt/rowCnt/masterPageCnt는 자식 수, secCnt는 section 파트 수 |
| V9 enum | `V9.ENUM` | R1 어휘 밖의 값. 어휘가 확실히 불완전한 `pagePr@landscape`는 제외(분석서 §6-2) |
| V10 표 격자 | `V10.ROW_ADDR/OUT_OF_GRID/OVERLAP/COVERAGE/SPAN_INVALID/WIDTH_SUM` | 덮인 면적 = rows x cols, 겹침 없음, rowAddr = tr 순번, 첫 행 셀 폭 합 = 표 폭(허용치 10) |
| V11 switch | `V11.SCALE`, `V11.STRUCT` | default 값 = case 값 x2 (margin 5종, tabItem pos), lineSpacing(PERCENT)은 동일 |
| V12 문단/구역 | `V12.RUN_MISSING`, `V12.SECPR_COUNT`, `V12.SECPR_POSITION` | secPr은 구역 첫 문단의 첫 run 안에 정확히 1개 |
| V13 hpf | `V13.MANIFEST_MISSING`, `V13.HREF_DANGLING`, `V13.SPINE_IDREF`, `V13.SPINE_MISSING`, `V13.DUP_ITEM_ID` | manifest/spine 소속은 참조에서 관찰(header/section/settings/masterpage는 manifest, header/section은 spine) |

### 설계서 대비 편차 (임의 추가/삭제와 근거)
1. **추가** `V4.CHILD`(관찰되지 않은 부모-자식 계층), `V4.TEXT`(텍스트가 없던 요소에 텍스트), `V5.CHILD_MISSING`(참조의 모든 발생에 있던 자식이 없음): 분석서 §10의 B0 치명 결함("header 최소화", 계층이 다른 표)은 속성만 보는 V5로는 잡히지 않는다. 분석서 §11 "R1에서 항상 존재 = 초집합으로 발행" 정책과 같은 기준이다. `hp:p`의 `hp:run` 누락은 V12.RUN_MISSING이 담당(중복 보고 방지).
2. **추가** `V6.SEQUENCE`(fontface lang 7종 순서, pageBorderFill type 순서), `V7.DUP_ID`/`V7.BAD_ID`(같은 종류 id 중복·비정수, 표 id 전역 고유 — 분석서 §5-4/§7), `V8.SECCNT` 세분화, `V10.ATTR_INT`/`V10.TOO_LARGE`(악의적 rowCnt 방어), `V3.DOCTYPE`, `V3.TEXT_ENCODING`(PrvText: BOM/UTF-8/CRLF), `V3.PNG_SIGNATURE`, `V1.PATH`/`V1.TOO_LARGE`/`V1.UNREADABLE`(zip-slip·zip 폭탄·손상 방어), `V0.SUPPRESSED`(코드·파트당 25건 초과분 요약).
3. **변경** V10 "셀 폭 합 = 표 폭": 참조 표 17개 중 1개가 정확히 10 HWPUNIT 차이(분석서 §7의 16/17). 정확 일치로 구현하면 한글이 직접 저장한 R1 자체가 실패하므로 허용치 10(`DEFAULT_TABLE_WIDTH_TOLERANCE`, 인자로 조정 가능)으로 완화했다. 6R은 정확히 나누는 것을 권장.
4. **제외(의도)** 분석서에 수치 관계가 있으나 검증기에 넣지 않은 것: 0번 열 셀 높이 합 = 표 높이(11/17만 일치), lineseg 수식(`baseline = round(0.85 x vertsize)` 등 — 05R 단위 테스트 소관, 한글이 재계산할 가능성), 셀 안 문단 `horzsize` 관계. 근거: 참조에서 전수 일치하지 않는 규칙을 강제하면 정상 파일을 거부한다.
5. **의도적 비강제**: mimetype 이외 엔트리 순서(분석서 E-Z 미확정)와 파트별 압축 방식은 프로파일에 관찰값만 기록(`observed_order`, `observed_compression`), 검증하지 않는다.
6. **개수 규칙은 고정 표**(`COUNT_ATTR_CHILD`): 자동 유추는 2x2 표의 `colCnt`를 "tr 수와 같다"로 오인하는 우연 일치를 만들었다(합성 참조로 재현). 새 개수 속성은 검토 후 표에 추가해야 한다.

## 3. 구현 중 핵심 판단
- **프로파일은 요소 이름 기준(문맥 무관)**: 같은 이름의 요소는 어디서나 같은 규칙을 따른다. R1에서 이름이 겹치되 구조가 다른 사례(`hp:offset` vs `hh:offset`)는 접두어가 달라 충돌하지 않았다.
- **enum 어휘 채택 규칙**: 값이 표준 토큰 형태(대문자 토큰, `None/none/yes/no`, MIME, hancom URI)이고 서로 다른 값이 16개 이하이며, 글꼴명·스타일명 등 자유값 속성 이름(`FREE_VALUE_ATTRS`)이 아닐 때만. 추가로 **사람이 검토한 표준 enum 61종 폐쇄 집합**(`REVIEWED_ENUM_VALUES`) 밖의 값이 나오면 추출을 중단한다 -> 01~04 병합 시 새 어휘는 검토 후 그 집합에 추가.
- **V6은 "관찰된 쌍" 기반**: 관찰되지 않은 조합을 오탐하지 않는다(테스트 `test_unobserved_child_combinations_are_not_rejected`).
- **위반 메시지에 텍스트 없음**: 위치는 요소 경로(`/hs:sec/hp:p[3]/hp:run`)이고 속성 값은 프로파일 어휘에 있는 표준 상수일 때만 표시, 그 외는 `<비표준 값>`. lxml 오류 문구는 쓰지 않고 줄 번호만. 테스트가 본문·속성 값·끊긴 참조 값의 유출 0건을 확인.
- **의도적 생략 실험 지원**: `ignore={"V5.CHILD_MISSING:hp:linesegarray"}`처럼 특정 검사·특정 자식만 끌 수 있다(G1의 P4b 등). 코드 또는 `V<n>` 접두어 단위.

## 4. 프로파일 기밀 스캔 증빙 (개수만 기록)

| 검사 | 결과 |
|---|---|
| 프로파일 문자열 중 비ASCII(한글 포함) | **0건** |
| 프로파일 수치(숫자) 리프 | **0건** (테스트 `test_profile_has_no_numeric_leaves_or_free_text`) |
| 어휘(enum) 값 중 검토 집합 밖 | **0건** |
| 참조의 본문·메타 텍스트 노드·PrvText 토큰 + 이름/식별 속성값(글꼴명·스타일명·작성 도구 등) 토큰 ∩ 프로파일 어휘 값 토큰(표준 상수 제외) | **0건** |
| 위 집합 ∩ 프로파일 요소/속성 이름 토큰(정보용) | 0건 |
| 검토 완료 표준 상수가 본문 단어와 우연히 같은 경우(정보용, 실패 아님) | 2건 (표준 enum 상수 2개가 일반 단어와 철자가 같음) |
| 참조 본문/메타에서 만든 "문서 특유 단어"(프로젝트 일반 텍스트에 없는 것) 1111개 ∩ 내가 만든 코드·테스트·프로파일의 토큰 | **0건** (스캔 스크립트는 삭제됨) |
| 참조 파일명·제목 어휘가 tools/, tests/, validator.py에 있는지 grep | **0건** |
| 재현성: 추출기를 다시 실행한 출력 == 커밋 대상 프로파일 | 바이트 동일 |

주의: 위 스캔의 "수치 제외" 부분이 누출 방어의 일부다 — 본문 수치는 프로파일에 들어올 통로 자체가 없다(수치 리프 없음, 표준 상수는 코드에 있음). 이 note에도 참조 파일명·제목·본문 어떤 것도 적지 않았다(참조는 "R1"로만 지칭).

## 5. 설계서 대비 인수 확인 요약 (03 §1-4 "AC-H 없음(도구). B0 유형 결함 fixture를 반드시 FAIL")
B0 유형으로 재현한 결함 -> 검출 코드 (모두 `tests/hwpx_validator/cases.py`, 합성 생성, B0 파일 복사 없음):
header 최소화(자체 `charShapes/paraShapes`) -> V4.ELEMENT + V5.CHILD_MISSING + V7.DANGLING_REF / secPr 부재 -> V12.SECPR_COUNT / 자체 속성(`bboxPt`, `fontName`, `fontSizeHwpunit`, `bold`) -> V4.ATTR / `charShapeIDRef` 개명 -> V4.ATTR + V5.ATTR_MISSING / 네임스페이스 URI 불일치(opf, container) -> V3.NS_MISMATCH + V3.NS_UNKNOWN / 선언 누락 -> V3.NS_MISSING / 필수 파트 부재 -> V2.PART_MISSING(+V13.HREF_DANGLING) / mimetype 압축·순서·개행·extra -> V1.* / ID 끊김 7종 -> V7.DANGLING_REF / itemCnt·fontCnt·rowCnt·masterPageCnt·secCnt 불일치 -> V8.* / 표 겹침·구멍·rowAddr·격자 밖·폭 합·span 0 -> V10.* / switch 배율·구조 -> V11.* / 프롤로그(lxml 기본, BOM) -> V3.PROLOG / manifest·spine 불일치 -> V13.* / 복합 B0 -> 8개 이상 서로 다른 코드.
로컬 실행 결과: `pytest tests/hwpx_validator` **236 passed**, 뮤턴트 50개 전부 사망(코드 소실 57쌍, 예외 4쌍 — 뮤턴트-사례 쌍 61건 대상).

## 6. 게이트 1 — 정적 분석/린트
- 프로젝트에 lint/type-check/formatter 설정 **없음**(`pyproject.toml`에 ruff/black/mypy 항목 없음). 그래서 격리 venv에서 ruff를 `--isolated --select E9,F,B,UP,SIM --ignore SIM108,B905,SIM905`로 실행: 대상 전부 **All checks passed**. (unit-4R note가 언급한 validator.py ruff 지적 2건은 더 넓은 규칙 집합 기준이며 그 시점의 코드였다. 이 규칙 집합에서는 0건이다. 다른 규칙 집합(예: 줄 길이 E501)을 요구하면 알려 달라.)
- 설치 패키지: 격리 venv에 `lxml`, `pytest`, `ruff`(모두 PyPI 공식 패키지, 설치로 실재 확인). **프로젝트 매니페스트(pyproject)는 수정하지 않았다**(lxml은 기존 의존성, pytest는 dev 의존성).

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트
- [x] 설계서/디자인서 명세와 구현 일치 — 2절 대응표, 편차 근거 기록
- [x] 에러 처리 — zip 손상/암호화/읽기 실패는 `V1.*` 위반으로 보고, XML 파싱 오류는 `V3.XML_PARSE`, 프로파일 오류는 `ProfileError`(삼키는 예외 없음). 존재하지 않는 입력 파일은 `FileNotFoundError`를 그대로 전파(테스트)
- [x] 입력 검증(시스템 경계) — 입력 zip은 신뢰하지 않는다: 엔트리 경로(../, 절대, 백슬래시), 크기 상한(파트 256MB/총 1GB 선언 기준), XML은 엔티티 미해석·네트워크 금지·DTD 미로드·huge_tree 꺼짐 파서, DOCTYPE 거부, 표 격자 크기 상한, 정수 파싱은 길이 제한
- [x] 하드코딩 시크릿 없음 (테스트의 SECRET 문자열은 유출 탐지용 더미)
- [x] 신규 외부 의존성 없음 (lxml 기존, pytest dev 기존; ruff는 검증용 격리 venv 한정)
- [x] 범위 외 변경 없음 — 수정 파일은 소유 범위 내 신규 파일뿐(`hwpx_kernel/__init__.py`, 다른 커널 파일, hwpx_writer, core, webapp, 설계서, traceability, decisions, `tests/conftest.py` 미접촉)
- [x] 기밀 — 4절

## 8. 알려진 한계 (정직한 표기)
1. **프로파일이 R1 단일 관찰**이다. 따라서 (a) R1에 없던 표준 요소·속성·enum(예: `hp:pic`, `hp:fwSpace`, `hp:newNum`, `hh:memoProperties`, `hh:heading@type=OUTLINE` 등)은 위반 처리된다 -> 그림(4P)·서식(02) 단위는 해당 참조 도착 후 `tools/hwpx_profile_extract.py <참조들...>`로 프로파일을 재생성(병합)해야 통과한다. 이는 설계(§3-4 "01~04 수령 후 재생성")와 일치한다. (b) "R1에서 항상 존재"를 필수로 취급하므로(초집합 정책) 한글이 실제로는 생략을 허용하는 요소도 필수로 보고한다 — 실험 E-*로 확인된 생략은 `ignore`로 명시한다.
2. R1은 변환·재저장 이력이 있을 수 있다(분석서 §0). 특히 **V11의 "default = case x 2"**는 R1에서만 관찰된 규칙이다. 같은 폴더의 다른 한글 저장본 1건은 default와 case 값이 같았다(구체적 수치·내용은 열람하지 않음, 배율 판정만). 한글 버전에 따라 다를 수 있으므로 **Q-27-1**.
3. `META-INF/container.rdf`, `BinData/*`, `Contents/masterpage*` 이외의 파트는 프로파일에 없으면 `V2.UNKNOWN_PART`로 보고한다(4P 재생성 필요).
4. 검증기는 XML 속성 값의 형식(정수/색/mm 문자열)을 검사하지 않는다(정수 검사는 ID/개수/격자 규칙에 필요한 곳에서만). 값 형식 오류가 한글에서 문제를 일으킬 수 있다면 후속 unit.
5. 대형 파일 성능: R1(요소 수만 개)에서 약 0.2초. 수백 MB 입력은 크기 상한으로 거부한다.

## 9. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)
- **AC-27-1** `pytest tests/hwpx_validator`가 전부 통과한다(경량 환경: lxml+pytest만 있으면 됨. 저장소 루트 `tests/conftest.py`가 pypdf/reportlab을 요구하는 환경이면 `--confcutdir=tests/hwpx_validator`로 실행). 참조 HWPX 파일 없이 실행된다.
- **AC-27-2** 합성 최소 정상 fixture는 위반 0건. 음성 사례 72건은 각각 `cases.py`에 적힌 코드를 전부 받는다(부분집합 판정).
- **AC-27-3** 검사 끄기(`ignore={code}`)를 하면 대응 사례의 기대 코드가 사라진다(`test_turning_a_check_off_loses_the_detection`). 소스 조건 50개를 무력화한 뮤턴트가 전부 사망한다(`test_mutants.py`).
- **AC-27-4** 위반 메시지에 본문 텍스트·속성 값이 나오지 않는다(`test_privacy_and_profile.py`).
- **AC-27-5** `tests/fixtures/hwpx_profile.json`은 비ASCII 0건·수치 0건·검토 집합 밖 어휘 0건이고, 추출기 재실행 결과와 동일하다(재실행에는 참조 파일 필요 — 오케스트레이터/사용자 로컬 작업, 테스트는 참조를 읽지 않음).
- **AC-27-6** 추출기는 누출 스캔 실패 시 출력 파일을 쓰지 않고 종료코드 3을 반환한다(합성 참조로 테스트).
- **AC-27-7 (지연 인수)** unit-4R 산출물 통합 확인 — 아래 10절.
- 06단계가 볼 만한 추가 관점: 다른 한글 저장본(사용자 보유)에 대한 오탐 목록(Q-27-1), V10 허용치(10)의 적정성, `V4.CHILD` 오탐 가능성(단일 참조 한계).

## 10. unit-4R 통합 확인용 명령·절차 (오케스트레이터 수행)
1. (참고) 이 unit 작업 중 4R이 이미 만든 프로브 7개(`.harness-tmp/probe/`)를 미리 돌려 봤다: P1a/P1b/P2/P3/P4a/P4c는 **위반 0건**, P4b는 linesegarray 의도적 생략으로 `V5.CHILD_MISSING`만 나오고 `ignore={"V5.CHILD_MISSING:hp:linesegarray"}`로 0건. 4R이 이후에 코드를 바꿨다면 아래로 다시 확인한다.
2. 각 프로브(또는 4R 산출 HWPX)에 대해:
   `python pdf_to_hwpx/hwpx_kernel/validator.py <파일.hwpx>` (위반 0이면 종료코드 0)
   또는 코드에서 `from pdf_to_hwpx.hwpx_kernel.validator import validate_hwpx` (패키지 `__init__`이 다른 이유로 실패하면 `importlib.util.spec_from_file_location`으로 경로 import — 이 unit의 테스트가 그 방식이다).
3. 프로브 중 의도적 생략이 있는 P4b는 위 `ignore`를 지정한다. 위반이 나오면 `code/part/location`으로 4R 소유 코드(constants/styles/section/container)의 해당 지점을 수정 대상으로 넘긴다(검증기를 완화해 맞추지 말 것 — 완화는 참조 근거(분석서)가 있을 때만).
4. 5R/6R/8R 이후 각 unit 테스트가 `validate_hwpx(...) == []`를 호출하도록 하는 것이 03 §3-4 인수조건 (3)("검증기 위반이 남아 있으면 자동 FAIL")의 이행이다.

## 11. 수동으로 확인이 필요한 부분
- 이 검증기는 한글 수용을 보장하지 못한다 -> 게이트 G1/G2(사용자가 한글에서 열기)가 별도로 필수.
- 프로파일을 재생성할 때: `python tools/hwpx_profile_extract.py <참조1> <참조2> ... -o tests/fixtures/hwpx_profile.json` 후 (1) 콘솔의 누출 스캔 줄이 0인지, (2) 새 어휘로 추출이 중단되면 그 값이 표준 상수인지 사람이 확인하고 `REVIEWED_ENUM_VALUES`에 추가, (3) `pytest tests/hwpx_validator` 재실행. 참조 파일은 저장소 밖(`참조HWPX/`, gitignore)에 둔다.

## 12. 미결 질문 (규칙 A — 사용자/오케스트레이터 판단 필요)
- **Q-27-1 (V11 배율)**: 참조 R1은 switch의 `default` 길이 값이 `case`의 정확히 2배였으나, 같은 폴더의 다른 한글 저장본에서는 같은 값이었다. 검증기는 설계서대로 "2배 고정"으로 구현했다. 기본안: 유지(4R이 R1 형태를 초집합으로 발행하므로). 대안: "같음 또는 2배" 허용으로 완화. 결정 근거는 G1 결과(4R 프로브를 한글이 여는가)와 01_빈문서.hwpx 도착 시 값 비교.
- **Q-27-2 (다른 작성기 변형)**: 같은 폴더의 한 파일은 프롤로그 형태(`...?>` 뒤 개행, 소문자 utf-8), 루트 네임스페이스 선언 수, mimetype extra field, `container.rdf` 포함 등이 R1과 달랐다(검증기가 V1/V2/V3 위반으로 보고). 한글이 이런 변형도 여는지 알 수 없다. 실험 E-X/E-N/E-Z(분석서 §12-4)의 결과로 규칙을 풀지(=프로파일 병합) 결정. 그 전까지는 초집합 발행 정책 유지.
- **Q-27-3 (허용치)**: V10 표 폭 허용치 10 HWPUNIT은 R1 1건의 관찰에서 나온 값이다. 5R/6R이 나눗셈 오차를 내면 초과할 수 있다. 기본안: 6R이 정확 분배(마지막 열에 잔여분). 6R 재작업 시 재검토.

## 13. 공유 문서 갱신 요청 (오케스트레이터가 반영 — 이 unit은 traceability.md/decisions.md를 수정하지 않음)
- `traceability.md` REQ-008: 작업 단위에 `unit-27` 추가, 구현 상태 "구현 완료(05), 06 대기 — 구조 검증기 V1~V13 + 프로파일 + 뮤턴트 검증, 한글 수용은 G1/G2 대기".
- `decisions.md` 후보(권한 없어 기록 요청): (1) **DEC 후보 — 프로파일 enum 어휘를 사람이 검토한 폐쇄 집합으로 관리**(사유: 공개 저장소로의 문서 특유 값 유입 방지; 영향: 01~04 병합 시 새 어휘는 검토 후 추가), (2) **DEC 후보 — V10 허용치 10, V11은 설계서대로 2배(Q-27-1 결정 대기)**, (3) Q-27-1~3 기록.
- 05 웨이브 공통: `tests/hwpx_validator/`는 루트 `tests/conftest.py`(unit-0 의존성) 없이도 돌도록 `--confcutdir` 사용을 문서화함 — 06 실행 환경 설정 시 참고.

## 14. 임시 아티팩트 정리 / git status
- 임시 작업은 `.harness-tmp/_05_unit27/`(격리 venv 포함)에서만 했고 **삭제 완료**. 추출 중간 산출물·스캔 스크립트 없음(추출은 메모리 처리). 프로젝트 루트에 egg-info 등 부산물 없음(`pip install -e .` 미실행). `.pytest_cache`를 만들지 않도록 `-p no:cacheprovider`로 실행했고 내 `__pycache__`는 삭제.
- 남겨 둔 것: 없음(`.harness-tmp/probe`, `.harness-tmp/venv_run_local` 등은 다른 단위 소유).
- git status 원문(정리 후, `docs`/`webapp` 변경은 다른 에이전트·이전 작업 소유):

```
 M .gitignore                                  (타 단위 소유)
 M pdf_to_hwpx/common/exceptions.py            (unit-4R)
 M pdf_to_hwpx/hwpx_kernel/__init__.py         (unit-4R)
 M pdf_to_hwpx/hwpx_kernel/container.py        (unit-4R)
 M pdf_to_hwpx/hwpx_kernel/schema.py           (unit-4R)
 M tests/hwpx_kernel/test_container.py         (unit-4R)
 M tests/hwpx_kernel/test_container_bin_data.py(unit-4R)
 M tests/hwpx_kernel/test_schema.py            (unit-4R)
?? docs/harness/analysis/                      (03 산출, 타 단위)
?? docs/harness/units/unit-4R-note.md          (unit-4R)
?? docs/harness/verify-log_unit-22-note.md     (unit-22)
?? docs/harness/verify-log_unit-27-note.md     (이 unit)
?? docs/harness/verify-log_unit-4R-note.md     (unit-4R)
?? pdf_to_hwpx/hwpx_kernel/{constants,context,flow,fonts,section,styles}.py (unit-4R)
?? pdf_to_hwpx/hwpx_kernel/validator.py        (이 unit)
?? tests/fixtures/                             (이 unit: hwpx_profile.json)
?? tests/hwpx_kernel/{conftest,helpers,test_constants_fonts,test_flow,test_probe,test_section,test_styles}.py (unit-4R)
?? tests/hwpx_validator/                       (이 unit)
?? tools/                                      (hwpx_profile_extract.py = 이 unit, hwpx_probe.py = unit-4R)
```
(`docs/harness/units/unit-27-note.md` 자체도 이 unit의 신규 파일. 위 `docs/`·`webapp/` 기존 수정 항목은 생략.)
