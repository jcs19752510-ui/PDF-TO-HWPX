# 03. 시스템 설계서 (System Design) — PDF-TO-HWPX

- 작성 에이전트: 03-system-designer
- 버전: v3 (사용자 확정 답변 DEC-014/015 반영)
- 입력: `docs/harness/02-planning.md` (v3, PASS), `docs/harness/01-trend-analysis.md`(취합본 + `_parallel/01-기술이슈.md` 조각), `docs/harness/decisions.md` DEC-001~006, `docs/harness/traceability.md`
- **핵심 전제 재확인**: 프로젝트 루트 Glob 재스캔 결과 실제 소스코드는 여전히 없음(`.git/objects` 내용물과 `TEST`, `GIT정보 copy.MD` 등 텍스트 파일만 확인) — 02단계의 "신규 프로젝트" 판단을 그대로 승계한다. 배포형태(로컬 전용, DEC-004), 과금모델(후원, DEC-005), 공개범위(오픈소스, DEC-006)는 모두 확정 상태이므로 이 설계서는 추가 질문 없이 착수한다.
- 이 문서의 도구 권한은 Read/Write/Grep/Glob/Bash로 제한되어 있어(에이전트 정의), 실시간 웹 조사(WebSearch/WebFetch)를 수행하지 않았다. 01단계 조사 결과에 없는 사실(예: 특정 한컴오피스 버전 번호)은 추측으로 채우지 않고 "확인 필요"로 명시했다(§8 참고).

---

## 1. 아키텍처 개요

### 1-1. 설계 원칙
- **로컬 단일 프로세스 아키텍처**: 서버/클라이언트 분리가 없다. GUI든 CLI든 하나의 파이썬 프로세스 안에서 "PDF 파싱 → 중간표현(IR) → HWPX 라이팅 → 로컬 저장"이 끝난다. 배포형태(DEC-004)가 로컬 전용으로 확정되었으므로, 이 구조는 되돌릴 필요가 없는 한 계속 유지한다.
- **파이프라인 + 중간표현(IR) 패턴**: 01단계 기술 조사(§1 "시사점")가 지적한 대로, `pdf2docx`류가 이미 검증한 "파서 → 중간 구조(문단/표/이미지) → 타깃 포맷 라이터" 패턴을 그대로 채택한다. PDF 파서 계열과 HWPX 라이터 계열이 서로의 내부 구현을 몰라도, 공용 IR 스키마(§3)만 지키면 독립적으로 개발·교체 가능하다 — 이는 향후 "PDF 파서를 바꾼다"거나 "HWPX 라이터를 바꾼다"는 변경이 발생해도 반대편에 영향이 없게 하는 장애 격리 설계다.
- **횡단 관심사는 진입점 1곳에서만 초기화**: 네트워크 차단(REQ-011), 로깅(REQ-019)은 GUI/CLI 두 진입점 각각에서 앱 시작 시 1회 호출하는 구조로 통일해, "이 모듈은 초기화됐는지 안 됐는지 매번 확인"하는 방식(암묵적 상태 의존)을 피한다.
- **과설계 배제**: 실사용자 트래픽이 없는 개인용 단일 실행 도구이므로, DB·메시지 큐·마이크로서비스·인증 서버 같은 것은 도입하지 않는다(필요할 이유가 없다). 설정/이력 저장은 로컬 JSON 파일 하나로 충분하다(§3).

### 1-2. 컴포넌트/모듈 경계 다이어그램

```mermaid
flowchart TD
    subgraph Entry["진입점 (unit-11 / unit-13)"]
        CLI["CLI (cli/__main__.py)"]
        GUI["GUI (gui/app.py)"]
    end

    subgraph Cross["횡단 관심사 (unit-0 확장 / unit-9)"]
        LOG["logging_setup.py<br/>(로컬 로거 초기화)"]
        NET["net_guard.py<br/>(아웃바운드 소켓 차단)"]
    end

    subgraph Reader["PDF 판독 계열 (Feature A 전반부)"]
        LOADER["pdf_loader.py (unit-0)"]
        TEXT["text_extractor.py (unit-1)"]
        IMG["image_extractor.py (unit-2)"]
        TBL["table_recognizer.py (unit-3)"]
        HANGUL["hangul_normalizer.py (unit-15)"]
        FORMULA["formula_approximator.py (unit-16)"]
        OCR["ocr_engine.py (unit-12)"]
    end

    subgraph Writer["HWPX 라이팅 계열 (Feature A 후반부)"]
        SCHEMA["hwpx_kernel/schema.py<br/>(공용 IR↔XML 프래그먼트 계약, unit-4)"]
        CONTAINER["hwpx_kernel/container.py<br/>(zip 골격/필수 파트, unit-4)"]
        PARA["paragraph_builder.py (unit-5)"]
        TABLEB["table_builder.py (unit-6)"]
        IMGB["image_embedder.py (unit-7)"]
    end

    subgraph Core["오케스트레이션 (unit-8)"]
        ORCH["orchestrator.py<br/>(우선순위 정책/예외→메시지 매핑/저장)"]
        REPORT["quality_report.py (unit-14)"]
    end

    CLI --> NET
    GUI --> NET
    NET --> LOG
    CLI --> ORCH
    GUI --> ORCH

    ORCH --> LOADER
    LOADER --> TEXT
    LOADER --> IMG
    LOADER --> TBL
    TEXT --> HANGUL
    IMG -.->|수식 후보 bbox| FORMULA
    TBL -.->|비-표 영역 후보| FORMULA
    TEXT -.->|스캔본(텍스트 0)| OCR

    CONTAINER --> SCHEMA
    HANGUL --> PARA
    TBL --> TABLEB
    IMG --> IMGB
    FORMULA -.->|근사 실패시 이미지 대체| IMGB
    SCHEMA -.->|계약| PARA
    SCHEMA -.->|계약| TABLEB
    SCHEMA -.->|계약| IMGB

    PARA --> ORCH
    TABLEB --> ORCH
    IMGB --> ORCH
    ORCH --> CONTAINER
    ORCH --> REPORT
    ORCH --> LOG
```

- **읽는 법**: 실선은 데이터가 실제로 흐르는 의존, 점선은 조건부/보조 관계다. `orchestrator.py`가 유일하게 "PDF 판독 계열"과 "HWPX 라이팅 계열" 양쪽을 알고 통합하는 지점이며, 두 계열은 서로를 직접 알지 못한다(장애 격리: 라이터 쪽 버그가 파서 쪽 코드를 오염시키지 않는다).
- `hwpx_kernel/schema.py`는 "코드"가 아니라 **계약(인터페이스)**이다 — 문단/표/이미지 빌더가 각각 만들어내는 XML 프래그먼트의 형태를 고정해 두어, `paragraph_builder.py`/`table_builder.py`/`image_embedder.py`가 서로 다른 개발자(또는 병렬 작업단위)가 동시에 작업해도 파일이 겹치지 않게 한다(1-3절 참고).

### 1-3. 작업 단위 확정표 (02단계 §9 후보표 검증·확정)

> 02단계 §9는 "불확실(3단계 확정 필요)"로 남긴 칸이 많았다. 아래 표는 그 칸을 모두 채우고, 실제 파일 경로를 구체화했다. 02 대비 달라진 점(파일 분리로 공유자원 문제를 해소한 unit-15/16, 로거를 unit-0으로 승격한 것 등)은 "비고"에 표시하고 8절에서 사유를 다시 설명한다.

**패키지 레이아웃(확정)**:
```
pdf_to_hwpx/
  common/            logging_setup.py, exceptions.py, constants.py   (unit-0 확장, unit-18 상수)
  pdf_reader/        loader.py, text_extractor.py, image_extractor.py,
                     table_recognizer.py, hangul_normalizer.py,
                     formula_approximator.py, ocr_engine.py           (unit-0~3, 12, 15, 16)
  hwpx_kernel/       schema.py, container.py                          (unit-4)
  hwpx_writer/       paragraph_builder.py, table_builder.py,
                     image_embedder.py                                 (unit-5, 6, 7)
  core/              orchestrator.py, net_guard.py, quality_report.py  (unit-8, 9, 14)
  cli/               __main__.py                                      (unit-11)
  gui/               app.py                                           (unit-13, 18 삽입지점)
  LICENSE, NOTICE, THIRD_PARTY_LICENSES.md                             (unit-10)
```

| 단위ID | 소속 | 커버 REQ-ID | 선행 단위 | 확정 파일 범위 | 공유 자원 접촉(확정) | 병렬 가능(확정) | 02 대비 비고 |
|---|---|---|---|---|---|---|---|
| **unit-0(확장)** | 공통 선행 | REQ-001, REQ-019(기반) | 없음 | `common/logging_setup.py`, `common/exceptions.py`, `pdf_reader/loader.py` | 없음(신규) — 단, 사실상 **모든 unit이 이 모듈을 import해서 소비**하므로 실질적 공통 선행 단위 | 불가(공통 선행, 최우선 착수) | **변경**: 02의 unit-0(PDF 로더만)에 로컬 로거·공통 예외 클래스를 편입해 범위를 넓혔다. 이유는 8절 |
| unit-1 | Feature A | REQ-002, REQ-006(적용대상), REQ-007 | unit-0 | `pdf_reader/text_extractor.py` | unit-0의 `PdfDocument` 객체(읽기 전용 소비) | 가능(확정) — unit-2·3과 다른 파일 | 확정(02와 동일) |
| unit-2 | Feature A | REQ-003 | unit-0 | `pdf_reader/image_extractor.py` | 동일 | 가능(확정) | 확정 |
| unit-3 | Feature A | REQ-004 | unit-0 | `pdf_reader/table_recognizer.py` | 동일 | 가능(확정) | 확정 |
| **unit-4** | Feature A | REQ-008 | 없음 | `hwpx_kernel/container.py`(zip 골격/필수 파트), `hwpx_kernel/schema.py`(문단·표·이미지 XML 프래그먼트 공용 계약) | 없음(신규) — 산출물 자체가 unit-5/6/7의 **공유 계약**이 됨 | 가능(확정, unit-0~3와 입력 무관) — 단 **unit-5/6/7의 공통 선행 단위**로 반드시 먼저 완료 | 02와 동일 역할, 범위에 `schema.py`(공용 계약) 명시 추가 |
| unit-5 | Feature A | REQ-002, REQ-006, REQ-008 | unit-1(또는 unit-15), unit-4 | `hwpx_writer/paragraph_builder.py` | `hwpx_kernel.schema`의 계약을 **소비만** 함(파일 비접촉) | 가능(확정) — unit-6·7과 파일 분리, 공유 계약은 데이터 의존이지 파일 의존이 아님 | **불확실 해소**: 02가 우려한 "공용 유틸 공유"는 계약(인터페이스)만 공유하고 실제 XML 트리 조작은 unit-8에서 순차 통합하므로 병렬 저해 없음 |
| unit-6 | Feature A | REQ-004 | unit-3, unit-4 | `hwpx_writer/table_builder.py` | 동일 | 가능(확정) | 동일 사유로 해소 |
| unit-7 | Feature A | REQ-003 | unit-2, unit-4 | `hwpx_writer/image_embedder.py` | 동일 | 가능(확정) | 동일 사유로 해소 |
| unit-8 | Feature A | REQ-005, REQ-009, REQ-010 | unit-5, unit-6, unit-7 | `core/orchestrator.py` | **실제 통합 지점**: `hwpx_kernel.container`의 문서 트리에 5/6/7 결과를 순차 삽입 — 이 지점 자체가 설계상 유일한 통합점이므로 "공유 자원 충돌"이 아니라 "의도된 배리어" | 불가(확정) — 선행 3개 단위 완료 후 착수(02와 동일 판단 유지) | 확정 |
| unit-9 | Feature A(횡단) | REQ-011 | unit-0 | `core/net_guard.py` | 모듈 자체는 독립. 단 GUI(unit-13)·CLI(unit-11) 진입점 파일에 `net_guard.install()` 1줄 호출 삽입 필요(경미한 접촉, 각자 자기 소유 파일 수정이라 충돌 아님) | 가능(확정) | **불확실 해소**: "전역 설정 레지스트리" 우려 대신 진입점 1회 호출 구조로 단순화해 공유자원 문제 제거 |
| unit-10 | Feature A | REQ-012 | 없음 | `LICENSE`, `NOTICE`, `THIRD_PARTY_LICENSES.md` | 없음(문서) | 가능(확정) | 확정 |
| unit-11 | Feature B | REQ-013 | unit-8 | `cli/__main__.py` | `orchestrator.convert()` 공개 API를 읽기 전용 소비 | 가능(확정) — unit-13과 진입점 파일 분리 | **불확실 해소** |
| unit-12 | Feature B | REQ-014 | unit-1 | `pdf_reader/ocr_engine.py` | unit-1의 IR 출력 스키마를 소비(스캔본 페이지에 대해서만 대체 텍스트 소스로 사용) | 가능(확정) — 별도 파일 | **불확실 해소** |
| unit-13 | Feature B | REQ-015 | unit-8 | `gui/app.py` | `orchestrator.convert()` 공개 API 소비 + `ConversionOptions.progress_callback` 구현 | 가능(확정) | **불확실 해소**. 배포형태 확정(DEC-004)으로 착수 보류 사유는 이미 02에서 소멸 |
| unit-14 | Feature B | REQ-016 | unit-8 | `core/quality_report.py` | unit-8이 만드는 `ConversionResult.warnings` 스키마 소비 | 가능(확정) — 단 unit-8의 출력 스키마(§3/§4)가 선행 확정되어 있어야 함(이미 본 설계서에서 확정) | **불확실 해소** |
| unit-15 | Feature B | REQ-017 | unit-1 | **신규 별도 파일** `pdf_reader/hangul_normalizer.py` (unit-1/5를 직접 수정하지 않음) | unit-1의 텍스트 출력을 입력으로 받아 정규화된 텍스트를 unit-5에 넘기는 **파이프라인 후처리 단계**로 재설계 | 가능(확정) | **02 대비 변경(중요)**: 02는 "기존 unit-1/5 수정"으로 정의해 파일 충돌 우려가 있었다. 본 설계는 별도 후처리 모듈로 분리해 병렬 가능하게 만들었다 — 8절에 사유 기재 |
| unit-16 | Feature B | REQ-018 | unit-2, unit-3 | **신규 별도 파일** `pdf_reader/formula_approximator.py` (unit-3/6을 직접 수정하지 않음) | unit-2(이미지 bbox)·unit-3(비-표 영역)의 출력을 소비, 실패 시 unit-7(이미지 임베딩) 경로로 폴백 | 가능(확정) | **02 대비 변경(중요)**: 위와 동일 사유로 별도 모듈 분리 |
| unit-17 | Feature B | REQ-019 | unit-0(로거 기반) | `common/logging_setup.py`의 정책 확장(어떤 이벤트를 INFO/WARNING/ERROR로 남길지, 개인정보 미포함 규칙) | unit-0 로거 설정을 확장 소비 | 가능(확정) | **범위 축소**: 로거 "생성" 자체는 unit-0으로 이관되어, unit-17은 "정책"만 다룸 |
| unit-18 | Feature B | REQ-025 | unit-11, unit-13, unit-10 | 신규: `common/constants.py`(SPONSOR_URL 등 상수). 삽입: `gui/app.py`, `cli/__main__.py`, `README.md` | **파일 접촉 있음(확정)** — GUI/CLI 진입점 파일에 문구·버튼을 삽입해야 함 | **불가(확정, 02와 다름)** — unit-11/13이 자기 파일의 골격을 먼저 완성한 뒤, unit-18이 이어서 같은 파일에 최소 삽입을 하는 **순차 배치**로 확정. 동일 파일을 동시에 건드리는 병렬 조합은 금지 | **불확실 해소, 병렬 가능 → 불가로 정정**: 02는 "가능(추정)"이었으나, 실제로는 GUI/CLI 파일을 공유 접촉하므로 순차가 맞다 |

**공유 파일/공통 선행 요약**:
- 모든 unit이 공통으로 의존하는 파일: `common/logging_setup.py`, `common/exceptions.py` (unit-0 확장 산출물) — 이것이 이 프로젝트의 **공통 선행 unit-0**이다. 오케스트레이터는 unit-0을 최우선 웨이브에 단독 배치해야 한다.
- 두 번째 공통 선행: `hwpx_kernel/schema.py`, `hwpx_kernel/container.py` (unit-4) — unit-5/6/7 착수 전 반드시 완료.
- 명시적으로 동시 수정 금지(같은 파일 동시 접촉) 조합: (unit-11, unit-18), (unit-13, unit-18) — 순차 배치.
- 그 외 unit-1/2/3, unit-5/6/7, unit-11/12/13/14/17/18(선행 완료 후)은 서로 다른 파일을 다루므로 병렬 웨이브 구성이 가능하다(ORCHESTRATOR.md P1 기준 최대 4개 동시 실행 상한 적용).

---

## 2. 기술 스택 선정 및 근거

> 본 프로젝트는 외부 클라우드 API/서비스를 전혀 사용하지 않는다(REQ-011, DEC-004). 따라서 "제공자 이용약관(상업적 이용, 호출 한도)" 확인 대상이 되는 외부 API 자체가 없다 — 이 사실 자체가 이 설계의 핵심 아키텍처 결정이다. 유일하게 외부와 상호작용하는 지점은 REQ-025 후원 링크(사용자가 클릭하면 OS 기본 브라우저로 정적 URL을 여는 것뿐, 앱이 호출하는 API가 아님)이며, 이용약관 확인 대상이 아니다. 후원 플랫폼 자체는 **GitHub Sponsors로 확정**(DEC-015)됐으나, **실제 프로필 URL은 05단계 unit-18 착수 시점에 확정**하므로 이 설계서에는 `common/constants.py`의 자리표시자 상수로만 정의한다(§8 미해결 사항 2번 참고).

### 2-1. 핵심 스택 요약

| 영역 | 채택 | 대안(기각) | 근거 |
|---|---|---|---|
| 언어/런타임 | **Python 3.11+ (CPython)** | Java(hwpxlib 기반), Rust | 01보고서 기술 축이 확인한 PDF 파싱(PyMuPDF/pdfplumber/pypdf)·HWPX 쓰기(python-hwpx)·OCR(Tesseract/PaddleOCR) 후보가 모두 Python 생태계에 존재해 생태계 일관성이 가장 높다. Java(`hwpxlib`)는 HWPX 라이팅 성숙도는 더 높아 보이나, PDF 파싱 생태계(PyMuPDF 등)와 언어가 갈려 하나의 실행 프로세스·하나의 패키징 파이프라인을 유지하기 어렵다 |
| PDF 파싱(텍스트/표) | **pdfplumber** (MIT, pdfminer.six 기반) | PyMuPDF/fitz | PyMuPDF는 **AGPL-3.0과 상용 라이선스의 듀얼 라이선스**다(Artifex). 이 결정(DEC-007) 당시에는 프로젝트 자체 라이선스가 "오픈소스 공개"(DEC-006)까지만 확정되고 구체적 SPDX 식별자는 미정이었다. AGPL 라이브러리를 채택했다면 사실상 프로젝트 전체를 AGPL 계열로만 배포할 수 있게 되어 **사용자의 향후 라이선스 선택권을 미리 좁히는 비가역적 제약**이 됐을 것이다. pdfplumber(MIT)는 이 제약이 없다. 이후 프로젝트 라이선스는 **MIT로 확정**됐고(DEC-014), pdfplumber(MIT)와 완전히 동일 계열이라 이 선택은 결과적으로도 최적이었음이 확인된다. 표 추출(`extract_tables()`)도 REQ-004 요구를 충족하는 수준의 기능을 제공한다 |
| PDF 파싱(이미지 원본 바이트 추출) | **pypdf** (BSD 계열) | PyMuPDF | REQ-003("원본 이미지 바이트를 재인코딩 없이 그대로 삽입")을 충족하려면 임베딩된 이미지 스트림에 접근해야 한다. `pypdf`의 `Page.images[i].data`가 원본 바이트를 제공하며 라이선스도 pdfplumber와 동일 계열(허용적)이라 §2-1의 라이선스 정책과 일치한다 |
| HWPX 읽기/쓰기 | **자체 OWPML 라이터**(Python 표준 `zipfile` + `lxml`), `python-hwpx`(Apache-2.0)는 구조 참고용으로만 활용 | `python-hwpx`를 그대로 채택, `hwpxlib`(Java) 연동 | 01보고서가 명시한 대로 `python-hwpx`의 표/이미지/복잡 서식 지원 성숙도는 README 수준만 확인되고 검증되지 않았다(불확실). REQ-008이 요구하는 "특정 크기/개체 조합에서만 나타나는 세로 위치 오차(6-6)"와 "암묵적 검증 규칙 미준수로 인한 경고창(6-8)"까지 잡으려면 생성되는 XML 전 과정을 직접 통제할 수 있어야 하는데, 성숙도 미검증 서드파티 라이브러리의 고수준 API 뒤에서는 이 통제가 어렵다. HWPX는 공개 표준(OWPML, KS X 6101) 기반 ZIP+XML이라 표준 라이브러리만으로 직접 생성 가능하다(REQ-012의 "2차 저작물 제작은 자유" 조건과 부합). `lxml`은 BSD 라이선스 (DEC-008). **컨테이너 골격(unit-4) 구현 전략**: "스펙에 맞는 XML"만으로는 6-8절의 암묵적 검증 규칙을 충족하지 못할 위험이 있으므로(01보고서), 처음부터 규격 문서만 보고 XML을 새로 설계하지 않고 **실제 한컴오피스/한글 뷰어가 저장한 최소 빈 문서(.hwpx)를 05/06단계에서 확보해 이를 리버스엔지니어링한 참조 템플릿(fixture)으로 삼아 골격을 구성**한다 — 참조 템플릿 확보는 "재배포 금지" 대상인 한컴의 사양 문서 원문이 아니라 사용자가 직접 만든 결과물이므로 REQ-012(사양 원문 재배포 금지)와 충돌하지 않는다 |
| 로컬 OCR | **Tesseract** (Apache-2.0) + `pytesseract`(Apache-2.0) 래퍼 | PaddleOCR, EasyOCR, Naver Clova OCR | Clova는 클라우드 API라 REQ-011(100% 로컬 처리)과 정면 충돌해 채택 불가. PaddleOCR의 한국어 모델(`korean_PP-OCRv5_mobile_rec`)은 01보고서 확인 결과 **2026년 기준 비교적 최근에 추가**되어 실사용 검증 사례가 적다. Tesseract는 한국어(`kor`) 언어팩이 오래전부터 존재해 상대적으로 성숙하다(속도가 느리다는 트레이드오프는 있음, DEC-010) |
| GUI | **Tkinter (Python 표준 라이브러리, PSF 라이선스)** | PySide6(LGPLv3), PyQt6(GPL/상용), wxPython | REQ-015가 요구하는 범위는 "파일 선택 다이얼로그 + 변환 진행률 표시" 수준의 **최소 GUI**다. Tkinter는 추가 의존성·라이선스 검토가 필요 없고(표준 라이브러리), PyInstaller 패키징 크기·복잡도를 최소화한다. PySide6/PyQt는 더 세련된 UI를 만들 수 있지만 이 최소 요구사항 대비 과설계다(DEC-009) |
| CLI | **argparse (표준 라이브러리)** | Click, Typer | REQ-013 배치 변환 수준의 인자 파싱에는 표준 라이브러리로 충분, 추가 의존성 불필요 |
| 패키징 | **PyInstaller** (GPLv2+예외조항, 번들되는 앱 코드의 라이선스를 제한하지 않음) | cx_Freeze, Nuitka | 가장 널리 쓰이고 문서화가 풍부한 Python→단일 실행파일 패키저. 1차 배포 타깃 OS는 **Windows**(DEC-011) — 01보고서가 확인한 대로 HWPX/한컴오피스 생태계 사용자는 사실상 전원 Windows 환경으로 추정되기 때문. 코드 자체는 OS 종속 API를 쓰지 않아(경로 처리에 `pathlib`+`platformdirs` 사용) 향후 macOS/Linux 빌드 확장이 가능하도록 열어둔다 |
| 로컬 경로/설정 | `pathlib`(표준) + `platformdirs`(MIT) | 수동 OS 분기 | 로그·설정 파일 저장 위치(Windows `%LOCALAPPDATA%`, macOS `~/Library/Application Support`, Linux `~/.local/share`)를 표준화된 방식으로 얻기 위함. 허용적 라이선스라 §2-1 정책과 부합 |
| 설정/이력 저장 | **로컬 JSON 파일 1개** (`settings.json`) | SQLite, 임베디드 DB | 저장할 데이터가 "최근 변환 파일 목록, GUI 창 크기" 수준으로 단순해 DB 도입은 과설계다(설계 원칙 1-1) |

### 2-2. 라이선스 호환성 정리 (REQ-012 연계)

| 의존성 | 라이선스 | 재배포 시 의무 | 프로젝트 목적과 충돌 여부 |
|---|---|---|---|
| pdfplumber, pdfminer.six | MIT | 저작권/라이선스 고지 포함 | 없음 |
| pypdf | BSD-3-Clause | 저작권 고지 포함 | 없음 |
| lxml | BSD | 저작권 고지 포함 | 없음 |
| python-hwpx (참고용, 코드 직접 포함하지 않고 구조만 참고) | Apache-2.0 | 코드를 실제로 vendoring하면 NOTICE 고지 필요 | 없음(참고만 하고 자체 구현하므로 고지 의무 자체가 발생하지 않을 가능성이 높음 — 05 구현 시 실제로 코드를 복사/포크하면 반드시 NOTICE에 추가) |
| Tesseract, pytesseract | Apache-2.0 | 저작권/NOTICE 고지, 수정 시 고지 | 없음. Tesseract 실행 바이너리를 PyInstaller 패키지에 동봉하는 방안(DEC-013)도 Apache-2.0이 허용 |
| Tkinter, argparse, pathlib, zipfile | Python 표준 라이브러리(PSF License) | 없음(사실상 제약 없음) | 없음 |
| platformdirs | MIT | 저작권 고지 포함 | 없음 |
| PyInstaller | GPLv2 + 부트로더 예외조항 | PyInstaller **자체 소스**를 수정 배포할 때만 GPL 의무 발생, 번들되는 앱 코드의 라이선스에는 영향 없음(공식 FAQ 기준) | 없음 |
| **(기각) PyMuPDF/fitz** | AGPL-3.0 / 상용 듀얼 | 배포 시 전체 조합 저작물을 AGPL 호환 라이선스로 공개해야 함(또는 상용 라이선스 구매) | **채택하지 않음** — 프로젝트 라이선스 선택권을 미리 제한하므로 §2-1에서 pdfplumber+pypdf로 대체 |

**프로젝트 자체 라이선스: MIT (확정, DEC-014)**. 위 조합은 모두 허용적(MIT/BSD/Apache-2.0) 또는 실질적 제약이 없는 라이선스이므로, 애초에 MIT/Apache-2.0/BSD/GPL 계열 중 무엇을 고르든 재배포 의무 충돌이 없었다(설계 당시 선택지를 넓게 유지하는 것이 목표였다). 사용자가 최종적으로 **MIT**를 택했으므로(DEC-014), 전체 의존성(pdfplumber/pdfminer.six MIT, pypdf BSD-3-Clause, lxml BSD, python-hwpx 참고 Apache-2.0, Tesseract/pytesseract Apache-2.0, platformdirs MIT, PyInstaller GPLv2+예외조항)이 모두 MIT와 호환됨을 한 줄로 재확인한다 — 표 안의 어느 항목도 MIT 공개와 충돌하는 재배포 의무(예: 소스 공개 강제)를 발생시키지 않는다. **LICENSE 파일 자체(및 THIRD_PARTY_LICENSES.md 채우기)의 생성 작업은 지금 이 설계 단계에서 하지 않고, 05단계(초기 스캐폴딩) 또는 11단계(문서화)에서 처리한다** — unit-10의 파일 범위(§1-3)는 그대로 유지된다.

---

## 3. 데이터 모델 (중간표현 IR, 설정 파일, 마이그레이션 전략)

> 관계형 DB/영속 스키마가 없는 로컬 도구이므로, 여기서의 "데이터 모델"은 (a) 파이프라인 내부를 흐르는 **중간표현(IR) 객체**, (b) 로컬에 영속되는 **설정/이력 JSON 파일** 두 가지를 의미한다.

### 3-1. 중간표현(IR) 엔티티

```python
# pdf_reader가 만들어 hwpx_writer/orchestrator에 넘기는 공용 스키마
@dataclass
class PageIR:
    page_index: int
    width_pt: float
    height_pt: float
    text_blocks: list[TextBlockIR]
    image_blocks: list[ImageBlockIR]
    table_blocks: list[TableBlockIR]
    formula_candidates: list[FormulaCandidateIR]   # unit-16 소비
    is_scanned: bool                                # True면 orchestrator가 unit-12(OCR) 경로로 라우팅

@dataclass
class TextBlockIR:
    bbox: tuple[float, float, float, float]
    text: str            # unit-15(hangul_normalizer)가 NFC 정규화 완료한 상태로 전달됨
    font_name: str | None
    font_size: float | None
    bold: bool
    italic: bool
    to_unicode_missing: bool   # REQ-007: True면 대체문자(□)로 치환된 상태, quality_report에 경고로 집계

@dataclass
class ImageBlockIR:
    bbox: tuple[float, float, float, float]
    raw_bytes: bytes      # 재인코딩 없이 원본 그대로(REQ-003)
    image_format: str     # "jpeg"|"png"|... (pypdf가 판별한 원본 포맷)

@dataclass
class TableBlockIR:
    bbox: tuple[float, float, float, float]
    rows: int
    cols: int
    cells: list[TableCellIR]
    has_merged_cells: bool   # REQ-004: True면 best-effort 처리, quality_report에 기록

@dataclass
class TableCellIR:
    row_span: int
    col_span: int
    text: str

@dataclass
class FormulaCandidateIR:
    bbox: tuple[float, float, float, float]
    source: Literal["image_region", "non_table_glyph_cluster"]
```

- **IR의 역할**: `hwpx_kernel/schema.py`가 정의하는 "IR → XML 프래그먼트 변환 계약"의 입력측 절반이 이 IR이다. `paragraph_builder.py`/`table_builder.py`/`image_embedder.py`는 이 IR 데이터클래스만 알면 되고, PDF가 pdfplumber로 파싱됐는지 다른 라이브러리로 파싱됐는지 몰라도 된다(파서 교체 시 라이터 계열은 수정 불필요 — 1-1절 장애 격리 원칙의 구체화).
- **마이그레이션 전략**: IR은 영속 저장되지 않는(메모리에서만 존재하다 소멸하는) 휘발성 객체이므로 스키마 마이그레이션 개념이 적용되지 않는다. 다만 `dataclass`에 필드를 추가/삭제할 경우 `hwpx_kernel/schema.py`의 계약 버전을 올리고(예: `SCHEMA_VERSION = "1.1"`), 5/6/7 unit이 이를 인지하도록 CHANGELOG에 남긴다.

### 3-2. 로컬 영속 파일

| 파일 | 형식 | 내용 | 보관 정책 |
|---|---|---|---|
| `settings.json` | JSON | 최근 변환 파일 경로(최대 10개), GUI 창 크기, 마지막 사용 OCR 언어 | 사용자가 삭제하면 기본값으로 재생성. 개인정보 포함하지 않음(파일 "경로"만 저장 — 경로 자체에 개인정보성 문자열이 포함될 수 있어 §6에서 별도 고지) |
| `logs/pdf-to-hwpx.log` (+`.1`,`.2`...) | 텍스트(RotatingFileHandler) | 타임스탬프, 로그 레벨, 이벤트 코드, 파일명(전체 경로 아님, 6-1 참고), 오류 코드 | 5MB × 5개 롤링, 초과분 자동 삭제(REQ-019) |
| 변환 중 임시 파일 | `tempfile.TemporaryDirectory()` | OCR 중간 이미지, 압축 해제 스테이징 | 변환 성공/실패와 무관하게 `with` 블록 종료 시 즉시 삭제(§6 개인정보 처리 원칙) |

- **개인정보를 다루는 항목이 없다** — 원본 PDF·추출 텍스트·이미지·OCR 결과 중 어느 것도 `settings.json`이나 로그에 본문 형태로 영속 저장되지 않는다(§6에서 상술).

---

## 4. API/인터페이스 명세

> 웹 API가 아니라 (a) 파이썬 공개 함수 시그니처, (b) CLI 인자 명세, (c) GUI 이벤트 계약, (d) 예외 계층으로 구성된다. "이 설계서로 구현할 개발자"가 추가 질문 없이 착수할 수 있도록 예외 케이스까지 명시한다.

### 4-1. 핵심 공개 API (`core/orchestrator.py`)

```python
def convert(
    input_path: Path,
    output_path: Path,
    options: ConversionOptions | None = None,
) -> ConversionResult:
    """PDF 1개를 HWPX 1개로 변환한다. 실패해도 예외를 던지지 않고
    ConversionResult.success=False + errors에 담아 반환한다(REQ-009).
    호출자(CLI/GUI)가 이 결과를 사용자 메시지로 매핑한다."""

@dataclass
class ConversionOptions:
    enable_ocr: bool = False
    ocr_lang: str = "kor"                 # pytesseract 언어 코드, 복수 지정은 "kor+eng"
    overwrite_existing: bool = False
    target_hwpx_min_version: str = HWPX_MIN_SUPPORTED_VERSION   # §5, §8 "확인 필요" 참고
    progress_callback: Callable[[ProgressEvent], None] | None = None
    # 주의: 보존 우선순위(표>이미지>텍스트, REQ-005)는 사용자 옵션이 아니라
    #       orchestrator 내부 고정 정책이다 — 옵션으로 노출하지 않는다(과설계 배제).

@dataclass
class ProgressEvent:
    stage: Literal["loading", "extracting", "building", "saving", "done"]
    current_page: int
    total_pages: int
    message: str

@dataclass
class ConversionResult:
    success: bool
    output_path: Path | None
    warnings: list[ConversionWarning]     # REQ-005/009/016이 소비
    errors: list[ConversionIssue]
    stats: ConversionStats

@dataclass
class ConversionWarning:
    code: str            # 예: "TABLE_MERGE_NOT_PRESERVED", "TOUNICODE_MISSING", "FORMULA_FALLBACK_IMAGE"
    page_index: int
    detail: str           # 사용자에게 그대로 노출 가능한 한국어 문구

@dataclass
class ConversionStats:
    total_pages: int
    tables_detected: int
    tables_preserved_fully: int
    images_embedded: int
    chars_extracted: int
    chars_replaced_with_placeholder: int   # REQ-007
    elapsed_seconds: float
```

### 4-2. 예외 계층 (`common/exceptions.py`) — REQ-009 "실패/부분실패 안내"의 근거

```
ConversionError (기반, orchestrator가 항상 잡아서 ConversionResult.errors로 변환)
├── PdfLoadError
│   ├── EncryptedPdfError      # 비밀번호로 보호된 PDF — "지원하지 않습니다" 메시지 고정
│   ├── CorruptedPdfError      # 파싱 자체가 실패
│   └── EmptyPdfError          # 0페이지
├── HwpxWriteError
│   ├── ContainerBuildError    # unit-4 zip 골격 생성 실패(디스크 공간 부족 등)
│   └── OutputPathError        # 출력 경로 쓰기 권한 없음 / overwrite_existing=False인데 파일 존재
└── OcrEngineError
    └── TesseractNotFoundError # 바이너리 미탐지(개발 중 미번들 환경 한정, §8 DEC-013 참고)
```

- 위 계층 밖의 예상 못한 예외(버그)는 orchestrator 최상위에서 `except Exception`으로 잡아 `ConversionIssue(code="INTERNAL_ERROR", ...)`로 변환하고 **반드시 traceback을 로컬 로그에만 기록**한다(화면에는 노출하지 않음 — 내부 경로/스택트레이스가 사용자 파일 경로를 포함할 수 있어 §6 개인정보 원칙과 연결). 이 경로가 REQ-009의 "미처리 예외 0%" KPI(02 §5)를 만족시키는 최후 방어선이다.
- **정의된 엣지 케이스(2차 검증에서 명시적으로 확인)**:
  - 암호화 PDF → `EncryptedPdfError` → "비밀번호로 보호된 PDF는 지원하지 않습니다."
  - 손상된 PDF → `CorruptedPdfError` → "PDF 파일을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다."
  - 0페이지 PDF → `EmptyPdfError` → "빈 PDF 파일입니다."
  - 출력 파일 이미 존재 + `overwrite_existing=False` → `OutputPathError` → "같은 이름의 파일이 이미 있습니다. 덮어쓰거나 다른 이름을 지정하세요."
  - 출력 디렉터리 쓰기 권한 없음 → `OutputPathError`
  - Tesseract 미설치(바이너리 없음, `enable_ocr=True`인데 발생) → `TesseractNotFoundError` → "OCR 엔진을 찾을 수 없습니다. 프로그램을 재설치하거나 문의해주세요."(정상 배포판은 바이너리 동봉이 원칙 — DEC-013 — 이므로 이 오류는 개발 환경/비정상 설치에서만 발생 가정)
  - 수식 후보 판정이 애매한 경우 → 예외를 던지지 않고 항상 안전한 폴백(이미지 대체, REQ-018)으로 처리 — "판정 불가"는 오류가 아니라 정상 동작 경로다.
  - 대용량 PDF(수백 MB) → 하드 상한을 두지 않는다(로컬 도구이므로 사용자 하드웨어에 위임). 다만 500MB 초과 시 `ConversionWarning(code="LARGE_FILE_SLOW")`로 처리 시간이 길어질 수 있음을 사전 경고한다.

### 4-3. CLI 명세 (`cli/__main__.py`, REQ-013)

```
pdftohwpx convert <input.pdf> [-o <output.hwpx>] [--ocr] [--lang kor+eng] [--overwrite]
pdftohwpx batch <input_dir> [-o <output_dir>] [--ocr] [--lang kor+eng] [--overwrite]
```
- 종료 코드: `0`=완전 성공, `1`=부분 성공(warnings 존재), `2`=실패(errors 존재). `batch`는 파일 중 하나라도 실패하면 종료 코드 `2`, 전부 경고만 있으면 `1`.
- 표준출력: 파일별 1줄 요약(`[OK] a.pdf -> a.hwpx (경고 2건)`), `--verbose`로 상세 로그.
- 진행률: `ProgressEvent`를 받아 단순 텍스트 진행바로 렌더링(`\r` 캐리지리턴 갱신).

### 4-4. GUI 이벤트 계약 (`gui/app.py`, REQ-015)

- 파일 선택(Tkinter `filedialog.askopenfilename`) → 변환 버튼 클릭 → **UI 스레드가 아닌 별도 `threading.Thread`에서 `orchestrator.convert()` 호출**(Tkinter는 스레드 안전하지 않으므로, 워커 스레드는 `queue.Queue`에 `ProgressEvent`를 넣고 UI 스레드는 `after()` 폴링으로 큐를 소비해 진행률 바를 갱신한다 — 명시하지 않으면 구현자가 UI 프리징이나 스레드 충돌을 겪을 수 있는 지점이라 2차 검증에서 구체화함).
- 변환 완료 시 `ConversionResult.warnings`를 리스트 박스에 표시(REQ-016 품질 리포트와 동일 데이터 재사용).
- 취소 버튼은 v1 범위에 포함하지 않는다(REQ-015가 요구하지 않음, YAGNI — §8에 명시).
- 후원 버튼(REQ-025, unit-18): 클릭 시 `webbrowser.open(SPONSOR_URL)` 호출만 하며, 클릭 이벤트 자체를 로컬에도 원격에도 기록하지 않는다(§6).

---

## 5. 비기능 요구사항

> 02단계 §5 KPI를 설계 수준의 구체적 목표·측정 지점으로 옮긴다. 실측/검증 자체는 06~08단계 몫이다.

| 항목 | 목표 | 측정 지점(설계상 근거) |
|---|---|---|
| 변환 성공률 | ≥95% (알려진 한계 케이스는 "정상 실패 안내"까지 포함해 100%) | `ConversionResult.success` 또는 `errors`가 사용자 메시지로 매핑되는지를 06단계 테스트 코퍼스로 측정 |
| 텍스트 보존 정확도 | ≥98%(표준 완성형 한글 기준) | `ConversionStats.chars_extracted` 대비 `chars_replaced_with_placeholder` 비율 |
| 표 구조 보존율 | ≥80%(병합 없는 단순 표), 병합 표는 "정상 손상 안내" 여부로만 판정 | `ConversionStats.tables_preserved_fully` / `tables_detected` |
| HWPX 뷰어 호환성 | 명시한 지원 버전 범위 내 100% | REQ-008, `HWPX_MIN_SUPPORTED_VERSION` 상수 — 정확한 버전 번호는 §8 "확인 필요" |
| 처리 시간 | A4 10p+이미지 3장, OCR 미사용 시 ≤10초 | `ConversionStats.elapsed_seconds`, 06단계 벤치마크 |
| 미처리 예외/크래시율 | 0% | 4-2절 예외 계층 + 최상위 `except Exception` 방어선 |

**장애 대응(로컬 프로세스 맥락으로 재해석 — 서버형 재시도/서킷브레이커는 해당 없음)**:
- **페이지 단위 격리(벌크헤드 패턴)**: 한 페이지 파싱/빌드 중 예외가 나도 `orchestrator`가 해당 페이지만 `ConversionWarning(code="PAGE_SKIPPED")`으로 건너뛰고 나머지 페이지는 계속 처리한다 — 문서 전체를 실패시키지 않는 것이 REQ-005(부분 실패 안내)의 설계적 근거다.
- **OCR 타임아웃**: 페이지당 OCR 처리에 30초 타임아웃을 두고, 초과 시 해당 페이지를 텍스트 없이 이미지만 삽입 + 경고(무한 대기 방지).
- **재시도**: 출력 파일 쓰기 시 `PermissionError`(다른 프로그램이 파일을 잠근 경우 등) 발생 시 1회, 0.5초 대기 후 재시도 — 그 이상은 사용자에게 오류로 안내(무한 재시도 금지).
- **확장성/가용성**: 서버가 없는 단일 사용자 로컬 도구이므로 "동시 사용자 수" 개념이 없다. 대신 "동시에 여러 PDF를 배치 변환할 때 한 파일의 실패가 다른 파일에 전파되지 않는다"(REQ-013)는 것이 이 맥락에서의 격리 목표이며, `batch` 명령은 파일 단위로 독립된 `convert()` 호출을 순차 실행한다(멀티프로세싱은 v1 범위 아님 — CPU 코어 활용 최적화보다 정확성/단순성을 우선한 YAGNI 판단, §8).

---

## 6. 보안 설계 원칙

### 6-1. 인증/인가
**해당 없음.** 배포형태가 로컬 전용으로 확정(DEC-004)되어 있어 다중 사용자·원격 접근 개념이 없다. 파일 접근 제어는 OS 파일 권한에 위임한다.

### 6-2. 개인정보 처리 원칙 (01단계 5-2/5-3절 규제 발견사항과 교차 확인 — 필수 명시)
- **처리 주체와 위치**: PDF에 포함될 수 있는 개인정보(성명, 주민등록번호, 연락처, 계약 조건, 병력 등 — 관공서 서식·스캔 신분서류 특성상 포함 가능성이 낮지 않음, 01보고서 5-2절)는 **사용자 본인의 로컬 컴퓨터 안에서만** 메모리/임시 디렉터리에 존재하며, 애플리케이션이 이를 어떤 형태로든 외부 서버로 전송하지 않는다(REQ-011, unit-9 `net_guard`로 기술적으로 강제). 이 설계에서는 서버가 없으므로 애초에 개인정보처리자 지위(수집·처리자)가 발생하지 않는다(01보고서 5-2절 결론과 일치).
- **수집 최소화**: 애플리케이션은 변환에 필요한 최소 정보(입력 PDF의 파일 경로, 출력 대상 경로)만 다룬다. 사용자 계정 생성, 이메일 수집, 원격 분석(텔레메트리) 등 **어떤 형태의 사용자 식별 정보 수집도 하지 않는다** — 이는 REQ-011의 "100% 로컬 처리" 정신을 문자 그대로의 PDF 전송 금지를 넘어 텔레메트리 비수집까지 확장 적용한 설계 결정이다(§8에 트레이드오프로 기록).
- **보관 기간과 파기**:
  - PDF 원문·추출된 텍스트/이미지/표 데이터(IR)는 변환이 끝나는 즉시 메모리에서 해제되며, 어떤 파일로도 영속화되지 않는다.
  - 변환 중 생성되는 임시 파일(OCR 중간 산출물 등)은 `tempfile.TemporaryDirectory()`의 `with` 블록 스코프로 관리해, 변환 성공·실패·예외 발생과 무관하게 **함수 종료 시 즉시 삭제**된다(3-2절).
  - `logs/pdf-to-hwpx.log`에는 PDF 본문 텍스트를 남기지 않는다 — 파일명(전체 경로가 아닌 basename만, 예: `계약서.pdf`가 아니라 해시화된 식별자 또는 순번을 권장), 페이지 수, 오류 코드, 처리 시간만 기록한다(REQ-019 "개인정보 미포함" 조건의 구체적 구현). **파일명 자체에 개인정보가 담길 수 있다는 점**(예: `주민등록증_홍길동.pdf`)을 인지해, 로그에는 기본적으로 파일명 대신 세션 내 일련번호(`doc#1`)를 쓰고, 전체 경로/원본 파일명은 `--verbose` 모드에서만(사용자가 명시적으로 상세 로그를 요청한 경우에만) 남긴다.
  - `settings.json`의 "최근 변환 파일 목록"은 경로 문자열을 담으므로 같은 이유로 민감할 수 있다 — GUI에 "최근 목록 지우기" 기능을 제공한다(REQ-015 최소 GUI 범위 내 저비용 추가로 판단, 과설계 아님).
- **제3자 제공**: 없음. 유일한 외부 상호작용은 REQ-025 후원 링크 클릭(사용자가 능동적으로 클릭했을 때만 OS 브라우저가 여는 정적 URL 이동)이며, 이때도 애플리케이션이 사용자 식별 정보나 클릭 추적 파라미터를 URL에 붙이지 않는다(4-4절).
- **고유식별정보(주민등록번호 등) — OCR 경로 특별 고지(REQ-014 연계)**: 01보고서 5-2절은 "고유식별정보를 서버에서 구조화·추출하면 별도 근거가 필요할 수 있다"고 지적했다. 본 설계는 OCR을 Tesseract로 **완전 로컬 실행**하도록 고정해(unit-12, DEC-010) 이 문제를 원천 회피한다 — OCR으로 주민등록번호가 인식되더라도 그 처리자는 사용자 본인이며 어떤 시점에도 외부로 전송되지 않는다.

### 6-3. 네트워크 차단 (REQ-011의 기술적 강제, unit-9)
- `net_guard.install()`을 GUI/CLI 양쪽 진입점의 최초 실행 라인에서 호출한다. 구현은 `socket.socket.connect`/`connect_ex`를 몽키패치해 호출 시 `NetworkAccessBlockedError`를 던지고 로그에 남기는 **디펜스-인-뎁스** 방식이다(단순히 "네트워크 라이브러리를 의존성에 안 넣었다"는 것보다 한 단계 더 강한 보장 — 09단계 보안검증에서 실제 트래픽 캡처로 재검증 예정).
- 이 차단은 후원 링크(`webbrowser.open`)에는 적용되지 않는다 — `webbrowser.open`은 OS 기본 브라우저를 별도 프로세스로 띄우는 것이라 애플리케이션 자체의 소켓 호출이 아니기 때문이다. 이 경계를 설계서에 명시해 09단계가 "왜 후원 링크는 net_guard에 안 걸리는가"를 결함으로 오판하지 않게 한다.

### 6-4. 의존성 공급망
- `requirements.txt`에 정확한 버전을 고정(pin)한다. 가능하면 `pip install --require-hashes`로 해시 검증까지 적용을 권장한다(구체 적용은 05 구현 시).
- 오픈소스 공개(DEC-006) 전제이므로, 의존성 CVE·라이선스 스캔은 09단계(보안검증) 범위에서 다시 확인한다 — 이 설계서는 §2-2에서 초기 라이선스 조사만 수행했다.

### 6-5. LLM/AI 기능 관련
REQ-020(LLM/VLM 레이아웃 복원)은 02단계에서 Out-of-Scope로 확정됐다. 본 설계서는 그 결정을 그대로 승계하며, 규칙 J가 요구하는 4개 안전장치(프롬프트 인젝션 방어 등)는 **적용 대상 기능이 아예 없으므로** 이 설계서에 포함하지 않는다(의도적 제외, traceability.md에도 동일하게 기록됨).

---

## 7. 운영/관측성

> 중앙 서버가 없는 로컬 배포형 도구이므로, "서버 모니터링 대시보드/중앙 에러율 집계"는 애초에 성립하지 않는다. 아래는 그 제약을 인정한 위에서 설계한 로컬 관측성이다.

### 7-1. 로깅
- `common/logging_setup.py`가 앱 시작 시 `RotatingFileHandler`(maxBytes=5MB, backupCount=5)를 등록한다. 저장 위치는 `platformdirs.user_log_dir("pdf-to-hwpx")` (Windows 기준 `%LOCALAPPDATA%\pdf-to-hwpx\Logs`).
- 로그 레벨: `INFO`=변환 시작/종료·요약 통계, `WARNING`=REQ-005/007/017/018 등 best-effort 저하 이벤트, `ERROR`=4-2절 예외 발생. 기본 레벨은 `INFO`, `--verbose`/GUI 설정에서 `DEBUG`로 전환 가능.
- 모든 로그 라인에 앱 버전·Python 버전·OS 정보를 포함해(재현성), 사용자가 GitHub Issue를 등록할 때 그대로 첨부할 수 있게 한다.
- 6-2절 원칙에 따라 PDF 본문 텍스트나 전체 파일 경로(기본 모드)는 로그에 남기지 않는다.

### 7-2. 크래시 리포트
- `sys.excepthook`을 후킹해, 처리되지 않은 예외가 프로세스를 종료시키기 직전에 traceback을 `logs/pdf-to-hwpx.log`에 `CRITICAL` 레벨로 기록한다.
- GUI는 크래시 시 "예상치 못한 오류가 발생했습니다. 로그 폴더 열기 / GitHub Issue 등록하기" 버튼이 있는 오류 다이얼로그를 띄운다. **자동 전송은 하지 않는다** — 사용자가 직접 로그를 확인하고 원하면 수동으로 첨부하는 방식(REQ-011 정신 유지, 6-2절과 일관).
- CLI는 동일 정보를 표준에러로 출력하고 종료 코드 `2`를 반환한다.

### 7-3. 에러율/장애 알림 채널 (10단계 검증 대비 명시)
- **중앙 알림 채널 없음**: 서버가 없으므로 Sentry류 중앙 에러 집계는 적용하지 않는다(DEC-003이 이미 확인한 대로 이 프로젝트/세션에는 Sentry 등 MCP 연동도 설정되어 있지 않다).
- 대신 **오픈소스 공개(DEC-006) 전제 하에 GitHub Issues를 사실상의 "장애 신고 채널"로 채택**한다 — README(unit-10/11단계 문서화 범위)에 이슈 등록 방법과 로그 첨부 방법을 안내한다. 이것이 이 로컬 도구가 가질 수 있는 유일하게 합리적인 "장애 알림 채널"이며, 10단계 배포테스트에서는 "README에 이 채널이 실제로 안내되어 있는지"를 검증 항목으로 삼아야 한다(자동화된 실시간 알림이 아니라 수동 채널이라는 점을 10단계가 오판하지 않도록 여기 명시).

### 7-4. 롤백 전략
- 배포 산출물은 GitHub Releases에 버전 태그(`v1.0.0` 등)로 게시한다. 특정 버전에서 회귀가 발견되면 사용자가 이전 릴리즈를 재다운로드하는 것이 롤백 수단이다.
- **자동 업데이트 기능은 v1 범위에 포함하지 않는다** — 자동 업데이트는 필연적으로 앱이 시작 시 외부 서버에 접속해 최신 버전을 조회하는 네트워크 호출을 요구하는데, 이는 6-3절의 "네트워크 차단"·REQ-011의 로컬 원칙과 정면으로 충돌한다. 따라서 이 설계는 자동 업데이트를 의도적으로 배제한다(§8 트레이드오프에 재기술).

---

## 8. 기획서 대비 트레이드오프 및 미해결 사항

### 8-1. 트레이드오프(자체 판단으로 결정, 근거와 함께 decisions.md에 기록 — DEC-007~013)
1. **PyMuPDF(성능/성숙도 우수) 대신 pdfplumber+pypdf(허용적 라이선스) 채택** — AGPL이 프로젝트 라이선스 선택권을 미리 제한하는 것을 피하기 위함. 트레이드오프: 복잡한 레이아웃/대용량 PDF에서 PyMuPDF 대비 파싱 속도·견고성이 낮을 수 있다(01보고서가 인용한 "10~50배 빠르다"는 비교는 미검증이지만 방향성은 참고). 05 구현 단계에서 성능이 KPI(§5, 10초 목표)를 못 맞추면 재검토 대상.
2. **`python-hwpx` 채택 대신 자체 OWPML 라이터 구현** — 라이브러리 성숙도 미검증 리스크를 설계 단계에서 직접 통제 가능한 리스크로 바꾸기 위함. 트레이드오프: 초기 구현 비용이 더 크다(zip 골격, content.hpf, settings.xml 등을 직접 작성해야 함). 대신 REQ-008의 호환성 요구(6-6/6-8)를 충족하기 위한 통제력을 확보하며, §2-1에서 명시한 "실제 한글이 저장한 빈 문서를 참조 템플릿(fixture)으로 리버스엔지니어링" 전략으로 6-8절의 암묵적 검증 규칙 리스크를 낮춘다.
3. **Tkinter 채택** — 라이선스·패키징 단순성 우선, 최신 UI 트렌드 대비 디자인 표현력은 제한적(디자이너 관점에서는 04단계 UX 설계 시 Tkinter의 위젯 한계를 감안해야 함 — 04단계에 인수인계할 사항).
4. **자동 업데이트 기능 배제** — 네트워크 차단 원칙과의 충돌을 피하기 위해 v1에서는 아예 만들지 않는다(7-4절). 향후 "선택적 업데이트 확인(사용자가 명시적으로 버튼을 눌러야만 1회 네트워크 호출)" 형태로 재검토 가능하나, 이는 REQ-011 재해석이 필요해 규칙 A 질문 대상이 될 사안이다.
5. **취소(Cancel) 버튼 없음** — REQ-015가 요구하지 않고, KPI상 처리시간이 10초 내외로 짧아 우선순위가 낮다고 판단(YAGNI). 사용자 피드백에 따라 배포 후 추가 검토 가능.
6. **텔레메트리(사용 통계) 완전 배제** — REQ-011이 문자 그대로 요구하지는 않지만(PDF 전송 금지가 원문), "로컬/프라이버시" 가치 제안(02 §3 ①)과의 정합성을 위해 확장 적용. 트레이드오프: 실사용 패턴(어떤 기능이 자주 쓰이는지)을 데이터로 파악할 수 없어, 배포 후 KPI(02 §5 "배포 후 추가 예정" 사용자 지표)는 GitHub Star/이슈/후원 클릭 수 등 외부 관측 가능한 지표로만 근사해야 한다.
7. **Windows 우선 패키징** — 코드는 크로스플랫폼 유지, 배포(패키징 산출물)만 Windows 우선. macOS/Linux 사용자는 v1에서 소스 실행만 가능(이 자체를 REQ로 등록하지는 않음 — 02 기획서에 "배포 OS 범위"에 대한 REQ가 없었고, 01보고서도 이 프로젝트 사용자층을 국내 개인/관공서 제출자로 좁혔으므로 Windows 집중이 근거 있는 범위 축소라고 판단).
8. **Tesseract 바이너리 동봉(패키지 크기 증가)** vs 별도 설치 요구 — "무료·개인용 사용성"(02 §3 ②) 가치 제안을 지키기 위해 동봉을 선택했으나, 설치 파일 크기가 커진다(수백 MB대 예상). 사용자가 설치 크기에 민감하면 "OCR 미포함 경량판" 별도 빌드도 고려할 수 있으나 v1 범위에서는 단일 빌드로 단순화한다.

### 8-2. 02단계 §9 대비 달라진 점 (1-3절 요약 재기재)
- unit-15(옛한글), unit-16(수식 근사)을 "기존 unit-1/5, unit-3/6 수정"에서 "신규 별도 파일"로 재설계해 병렬 가능 여부를 "불확실 → 가능(확정)"으로 바꿨다.
- unit-18(후원 링크)을 "가능(추정)"에서 "불가(확정, 순차)"로 정정했다 — 실제로 GUI/CLI 진입점 파일을 공유 접촉하는 것이 설계 단계에서 드러났기 때문이다.
- unit-0의 범위를 "PDF 로더"에서 "PDF 로더 + 로컬 로거 + 공통 예외 클래스"로 확장해, 사실상 모든 unit의 공통 선행 단위임을 명시적으로 확정했다(02는 이를 명시하지 않았다).
- unit-9(네트워크 차단)를 "전역 설정 레지스트리 접촉 가능성 있음(불확실)"에서 "독립 모듈 + 진입점 1줄 호출(공유자원 없음, 병렬 가능 확정)"으로 단순화했다.

### 8-3. 미해결 사항 — 사용자 확인 필요 (규칙 A, 임의로 정하지 않음)
아래 항목은 자체 조사(01보고서)로 근거가 부족하거나, 순수 기술적 판단을 넘어 사용자의 가치 선택이 필요한 사안이라 임의로 확정하지 않았다:

1. ~~**프로젝트 자체의 오픈소스 라이선스(SPDX 식별자)**~~ — **해소됨(DEC-014, MIT 확정)**. DEC-006은 "오픈소스로 공개한다"까지만 확정했었고, MIT/Apache-2.0/GPL-3.0 중 무엇으로 할지는 미정이었으나 사용자가 **MIT**로 확정 응답했다. §2-2에서 재확인한 대로 채택한 의존성 전체가 MIT와 호환된다. LICENSE 파일 생성은 05단계(스캐폴딩) 또는 11단계(문서화)에서 처리한다.
2. **실제 후원(기부) 플랫폼과 URL** (REQ-025) — 플랫폼 자체는 **GitHub Sponsors로 확정**(DEC-015)됐다. 다만 **실제 프로필 URL은 05단계 unit-18 착수 시점**(사용자가 실제 GitHub Sponsors 계정을 개설한 뒤)에 확정하기로 했으므로, 그 전까지는 본 설계서대로 `common/constants.py`에 `SPONSOR_URL = "https://example.com/PLACEHOLDER"` 형태의 자리표시자만 유지한다.
3. **HWPX 지원 대상 버전의 정확한 번호** (REQ-008, 02 §8 A-9) — 01보고서도 이를 "확인 필요"로 남겼고, 본 에이전트는 도구 권한상(Read/Write/Grep/Glob/Bash) 실시간 웹 조사를 할 수 없어 특정 한컴오피스 버전 번호를 임의로 지어내지 않았다. `HWPX_MIN_SUPPORTED_VERSION` 상수는 05/06단계에서 실제 한컴오피스(또는 한컴 뷰어) 여러 버전에 생성물을 직접 열어보며 실측 확정하는 것을 권고한다 — 이는 사용자 확인이 아니라 **구현 단계의 실측 작업**으로 처리 가능하므로 지금 당장 진행을 막지는 않는다.

1번은 DEC-014로 완전히 해소되어 더 이상 미해결 사항이 아니다(이력 보존을 위해 취소선으로만 남긴다). 2번은 플랫폼 선택은 해소됐고 URL 값만 REQ-025 UI 착수(05단계 unit-18) 이전에 확정하면 되며, 3번은 착수를 막지 않는다.

---

## 9. 변경 이력

| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-09-27 | v0 | 초안 작성 (9개 섹션 전체, 작업단위 확정표 포함) | 3단계 최초 작성 |
| 2026-09-27 | v1 | 1차 내부검증 결함 반영 수정 (`verify-log_03-system-design.md` 1차 참고: GUI 스레드 안전성 미명시, HWPX 컨테이너 참조 템플릿 전략 미기재, net_guard와 후원링크 webbrowser.open의 관계 미기재 등 보완) | 규칙 B 1차 검증 |
| 2026-09-27 | v2 | 2차 내부검증(구현자 관점) 결함 반영 수정, 최종본 확정 (`verify-log_03-system-design.md` 2차 참고: 엣지케이스 목록 표로 정리, 예외 계층에 EmptyPdfError/TesseractNotFoundError 추가, ConversionOptions에서 우선순위 정책이 비-옵션임을 명시) | 규칙 B 2차 검증, PASS 확정 |
| 2026-09-27 | v3 | 사용자 확정 답변(DEC-014: 프로젝트 라이선스 MIT, DEC-015: 후원 플랫폼 GitHub Sponsors) 반영. §8-3 미해결사항 1번을 해소 처리, 2번을 "플랫폼 확정/URL만 unit-18 착수 시 결정"으로 정리, §2-1/§2-2에 "프로젝트 자체 라이선스: MIT" 명시 및 전체 의존성 호환 재확인, LICENSE 파일 생성은 05/11단계로 위임 명시, §2-1 pdfplumber 선정 근거 서술을 확정 이후 시점으로 갱신 | 오케스트레이터가 기록한 사용자 응답(DEC-014/015) 반영, 추가 검증 PASS |

---

## 다음 단계(4단계) 착수 조건 안내
- 4단계(UX 디자인) 착수를 위한 입력 계약(본 문서 PASS + 2회 이상 검증)은 충족되었다.
- 04단계는 Tkinter GUI(DEC-009)의 위젯 표현력 한계를 감안해 "최소 GUI"(REQ-015: 파일 선택, 진행률 표시, 경고 목록, 후원 버튼)를 설계하면 된다. 8-3절의 미해결 사항 중 프로젝트 라이선스(1번)는 DEC-014(MIT)로 이미 해소됐고, 후원 플랫폼(2번)도 DEC-015(GitHub Sponsors)로 플랫폼은 확정됐다(실제 URL만 05단계 unit-18 착수 시 확정) — 남은 3번(HWPX 지원 버전 실측)만 착수를 막지 않는 상태로 남아 있다.
