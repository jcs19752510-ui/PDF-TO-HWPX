# unit-7 구현 노트 — Feature A, HWPX 이미지 임베딩 (05-unit-developer)

- 커버 REQ-ID: REQ-003(PDF 이미지 추출 → HWPX 원본 바이트 임베딩)
- 소속: Feature A(코어 변환 파이프라인)
- 선행 단위: unit-2(`pdf_reader/image_extractor.py`, Verified — 06단계 PASS, DEC-028 반영), unit-4(`hwpx_kernel/schema.py`/`container.py`, Verified — 06단계 PASS)
- 속도 트랙: **L3(일반)** — 호출 프롬프트에 별도 트랙 지정 없어 기본값 적용.
- **병렬 웨이브 호출**: 이 호출과 동시에 unit-5(`hwpx_writer/paragraph_builder.py`), unit-6(`hwpx_writer/table_builder.py`) 05-unit-developer 호출이 별도로 진행 중이었다. 확정 파일 범위(`pdf_to_hwpx/hwpx_writer/image_embedder.py` 신규 1개 파일)만 수정했고, 다른 두 unit의 파일은 전혀 건드리지 않았다(작업 종료 시점 `git status`로 재확인, 아래 4절).
- 선행 문서: `docs/harness/units/unit-2-note.md`(§9 "2차 재작업(DEC-028)", §7-4-2 CCITT/JBIG2 경고), `docs/harness/units/unit-4-note.md`(§2-2, §8 "BinData 저장을 위한 container.py 확장 필요" 제안), `pdf_to_hwpx/hwpx_kernel/schema.py`(`image_block_to_picture_fragment`), `pdf_to_hwpx/hwpx_kernel/container.py`(현재 함수 목록 직접 확인), `pdf_to_hwpx/pdf_reader/ir.py`(`ImageBlockIR`)

---

## 1. 구현 범위

### 1-1. 만든 함수/타입 (`pdf_to_hwpx/hwpx_writer/image_embedder.py`, 신규 파일, 이 파일만 수정)

```python
SUPPORTED_IMAGE_FORMATS: frozenset[str]  # {"jpeg", "jp2", "png", "tiff"}

@dataclass(frozen=True)
class EmbeddedImage:
    bin_data_id: str
    image_format: str
    raw_bytes: bytes
    fragment: etree._Element

@dataclass(frozen=True)
class ImageEmbedWarning:
    code: str
    message: str
    image_index: int

def embed_image_blocks(
    blocks: list[ImageBlockIR],
    *,
    start_index: int = 0,
) -> tuple[list[EmbeddedImage], list[ImageEmbedWarning], int]:
    """반환: (embedded, warnings, next_start_index)"""
```

- 입력: `pdf_to_hwpx.pdf_reader.ir.ImageBlockIR` 목록(unit-2 산출물). `ir.py`는 수정하지 않고 import만 했다.
- 처리: 각 이미지에 순차적으로 `bin{N}` 형태의 BinData id를 부여하고, `hwpx_kernel.schema.image_block_to_picture_fragment(block, bin_data_id=그_id)`를 호출해 배치 프래그먼트를 만든다. `schema.py`는 수정 없이 import해서 소비만 했다(unit-4 AC-2-7 계약 준수).
- `start_index`/반환된 `next_start_index`로 여러 페이지에 걸친 BinData id 유일성을 오케스트레이터(unit-8)가 체이닝할 수 있게 했다(문서 전체에서 id 충돌 방지 — 03 §1-2 컴포넌트 다이어그램상 orchestrator가 유일한 통합점이라는 점과 일관).

### 1-2. BinData 실제 저장 — 진행 불가 지점(공유 자원 이슈, 아래 3절에서 상세)

지시문이 예고한 대로, `container.py`를 실제로 확인한 결과(추측 없이 직접 읽음) **BinData 삽입 함수가 전혀 없음**을 재확인했다(`build_empty_container`, `add_section_xml` 2개 함수뿐). 이 unit은 05-unit-developer 병렬 호출 규칙에 따라 `container.py`(unit-4 확정 파일 범위, 이 unit의 파일 범위 밖)를 직접 확장하지 않았다. 대신:
- `EmbeddedImage`가 `bin_data_id`/`raw_bytes`/`image_format` 3종을 그대로 담아 반환하도록 해, 후속 작업(container.py 확장 담당자 또는 오케스트레이터)이 `ImageBlockIR`을 다시 들추지 않고 이 3종만으로 BinData 파트를 쓸 수 있게 계약을 좁혔다.
- 필요한 `container.py` 확장의 제안 시그니처를 3절에 구체적으로 남겼다.

이 unit 자체(“BinData id 할당 + 배치 프래그먼트 생성”)는 **완전히 구현 완료**했다 — 진행 불가 지점은 "그 id로 실제 바이트를 zip에 넣는 것"(container.py 확장) 단 하나로 명확히 좁혀져 있다.

### 1-3. CCITT/JBIG2 및 기타 미지원 포맷 처리 판단 (지시문 요청 사항)

**결정: `image_format`이 `SUPPORTED_IMAGE_FORMATS = {"jpeg", "jp2", "png", "tiff"}`에 속하지 않으면(즉 `"ccitt"`/`"jbig2"`/`"unknown"`/그 외 향후 unit-2가 반환할 수 있는 값) 해당 이미지를 결과에서 제외하고 `ImageEmbedWarning`으로 알린다.**

근거:
1. `"ccitt"`/`"jbig2"`는 unit-2-note.md §7-4-2가 명시한 대로 "너비/행수 등 PDF 메타데이터 없이는 독립적으로 열 수 없는 원본 비트스트림"이다 — TIFF/PNG 같은 표준 컨테이너 헤더가 없어, 이 바이트를 그대로 HWPX BinData에 넣으면 한글이 열지 못하거나 깨진 이미지로 표시할 위험이 매우 크다. 이를 실제로 열 수 있는 파일로 만들려면 XObject의 `/Columns`/`/Rows`/`/K`(CCITT) 등 추가 메타데이터가 필요한데, 이는 `ImageBlockIR`(공유 계약)에 없는 필드라 이 unit이 임의로 만들어 넣거나 지어낸 변환 로직(예: 실존하지 않는 라이브러리 사용)을 추가하지 않았다.
2. `"unknown"`(및 향후 unit-2가 인식하지 못하는 필터를 만나 반환할 수 있는 값)도 완결된 파일 형식임을 보장할 수 없다(unit-2 모듈 docstring "재작업" 절 — 필터 배열이 여러 개 연쇄된 드문 경우 `raw_bytes`가 아직 전송용 필터로 감싸인 상태일 수 있음).
3. 조용히 누락시키지 않고 `ImageEmbedWarning`(코드: `IMAGE_FORMAT_INCOMPLETE_BITSTREAM` 또는 `IMAGE_FORMAT_UNSUPPORTED`)으로 명시적으로 알리는 방식을 택해, REQ-005 "미보존 요소 고지" 정신에 부합시켰다(unit-2가 왕복검증 실패/미지원 인코딩을 예외로 명시적으로 실패시킨 것과 같은 방향의 "조용히 넘어가지 않는다"는 원칙).
4. 이것이 "합리적으로 범위를 좁히는 것"에 해당한다고 판단했다 — 실제로 열 수 있는 CCITT/JBIG2 임베딩까지 지원하려면 `ir.py` 확장(공유 계약, 이 unit 파일 범위 밖)과 새로운 설계 결정이 필요해 과설계 방지 원칙상 이번 unit에서 임의로 시도하지 않았다.

---

## 2. 게이트 1 — 정적 분석/린트

- 프로젝트에 lint/type-check/formatter 설정(`ruff`/`flake8`/`black`/`mypy`/`pylint`/`.pre-commit-config.yaml`)이 여전히 없음을 재확인했다(리포지토리 루트 검색, unit-0/1/2/4-note.md와 동일 결론).
- `python -m py_compile pdf_to_hwpx/hwpx_writer/image_embedder.py` — **컴파일 성공**.
- 병렬 웨이브 중 동시 진행 중이던 unit-5/unit-6의 미완성 코드는 이 unit이 import하지 않으므로 (`schema.py`/`ir.py`만 import) 전체 실행 실패나 격리 보고 대상이 없었다.

## 3. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — unit-4-note.md §2-2가 명시한 "unit-7은 BinData id 부여 + 배치 프래그먼트 생성을 담당하고, 실제 저장은 필요 시 container.py 확장을 공유 자원 이슈로 보고해야 한다"는 계약을 정확히 그대로 따랐다. `schema.py`의 `image_block_to_picture_fragment` 시그니처(`block, *, bin_data_id`)를 변경 없이 그대로 호출했다.
- [x] 에러 처리가 누락된 경로가 없는가 — 이 모듈에 `try/except`가 없다(예외를 삼키는 코드 없음). `schema.image_block_to_picture_fragment` 호출이 내부적으로 던질 수 있는 예외(예: bbox 형식 이상)는 그대로 전파된다 — unit-2/unit-4와 동일하게 "예외를 임의로 흡수하지 않고 orchestrator(unit-8) 몫으로 남긴다"는 03 §5 벌크헤드 설계 전제를 따랐다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 모듈의 입력(`ImageBlockIR` 목록)은 사용자 입력이 아니라 unit-2가 이미 만든 내부 IR이다(경계 검증은 unit-0/unit-2 책임이라는 기존 전제와 동일). `image_format` 화이트리스트 검사(`SUPPORTED_IMAGE_FORMATS`) 자체가 이 모듈 안에서 유일하게 필요한 "입력 분류" 로직이며, 이를 누락 없이 수행한다(모든 미지원 값이 반드시 `ImageEmbedWarning` 경로로 빠짐 — 화이트리스트 방식이라 새로운 미지원 포맷이 추가돼도 안전 쪽으로 기본 동작함).
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(순수 데이터 변환 로직).
- [x] 새로 추가한 외부 의존성이 있다면 실존 패키지인지 확인했는가 — 신규 의존성 추가 없음(`lxml`은 unit-0/unit-4가 이미 `pyproject.toml`에 등록, `dataclasses`는 표준 라이브러리). `pyproject.toml`을 전혀 수정하지 않았다.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `pdf_to_hwpx/hwpx_writer/image_embedder.py` 1개 파일만 신규 생성했다(작업 종료 시점 `git status --porcelain` 재확인, 4절). `ir.py`/`schema.py`/`container.py`/`pyproject.toml` 어느 것도 수정하지 않았고, unit-5/unit-6이 만드는 `paragraph_builder.py`/`table_builder.py`도 건드리지 않았다.

## 4. 로컬 동작 확인 (자체 테스트 아님, 최소 확인)

리포지토리 안에서 `python -` 인라인 스크립트로 직접 실행 후 파일을 남기지 않았다(`.harness-tmp` 등 스크립트 파일 생성 없이 stdin heredoc으로만 실행). 확인한 항목:

1. **JPEG 1건(완결된 포맷, 지시문 필수 요청 사항)**: `ImageBlockIR(bbox=(0,0,100,200), raw_bytes=<가짜 JPEG 바이트>, image_format="jpeg")`를 `embed_image_blocks([block])`에 넣은 결과 —
   - `len(embedded) == 1`, `embedded[0].bin_data_id == "bin0"`
   - `embedded[0].raw_bytes`가 입력 `raw_bytes`와 완전히 동일(재인코딩 없음, REQ-003 유지 확인)
   - `embedded[0].fragment.get("binDataIDRef") == "bin0"`, `fragment.tag`가 `}pic`로 끝남(=`hp:pic`)
   - `schema.fragment_to_bytes(embedded[0].fragment)`로 직렬화 성공, `<?xml` 미포함, `b"bin0"` 포함 확인(스키마 계약과의 통합 확인).
2. **CCITT 1건 + unknown 1건 + PNG 1건을 섞은 목록**: CCITT는 `ImageEmbedWarning(code="IMAGE_FORMAT_INCOMPLETE_BITSTREAM", image_index=1)`로, unknown은 `code="IMAGE_FORMAT_UNSUPPORTED", image_index=2`로 각각 정확히 분류되어 경고 목록에 담기고, PNG는 `bin1`으로 정상 임베딩됨을 확인(경고 대상은 BinData id를 소비하지 않음 — `next_start_index == 2`로 정확히 확인).
3. **여러 페이지 체이닝**: 1차 호출 `start_index=0` → `next_start_index=2` 반환 → 2차 호출에 `start_index=2`로 그대로 넘기면 새 이미지가 `bin2`를 받음을 확인(문서 전체 유일성 체이닝 동작 확인).
4. **빈 목록**: `embed_image_blocks([], start_index=5)` → `([], [], 5)` 반환 확인(예외 없음).

## 5. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

### AC-1. 기본 임베딩 (REQ-003)
1. `image_format`이 `{"jpeg", "jp2", "png", "tiff"}` 중 하나인 `ImageBlockIR`은 `embed_image_blocks()`가 반환하는 `embedded` 목록에 입력 순서대로 포함된다.
2. 각 `EmbeddedImage.raw_bytes`는 입력 `ImageBlockIR.raw_bytes`와 바이트 단위로 완전히 동일해야 한다(이 unit은 재인코딩을 전혀 수행하지 않는다 — REQ-003 연쇄 보존 확인).
3. `EmbeddedImage.bin_data_id`는 `start_index`부터 시작해 `"bin{N}"` 형태로, **임베딩된 이미지에만** 순차 부여된다(건너뛴 이미지는 번호를 소비하지 않음).
4. `EmbeddedImage.fragment`는 `hwpx_kernel.schema.image_block_to_picture_fragment(block, bin_data_id=그_id)`가 반환한 것과 정확히 동일한 구조(로컬 이름 `pic`, `binDataIDRef` 속성이 부여된 id와 일치, `format` 속성이 `block.image_format`과 일치)를 가진다.

### AC-2. CCITT/JBIG2/미지원 포맷 제외 (지시문 필수 요건)
5. `image_format`이 `"ccitt"` 또는 `"jbig2"`인 이미지는 `embedded`에 포함되지 않고, `warnings`에 `code == "IMAGE_FORMAT_INCOMPLETE_BITSTREAM"`인 `ImageEmbedWarning`이 정확히 그 이미지의 원래 인덱스(`image_index`, `blocks` 리스트 기준)로 추가된다.
6. `image_format`이 `"unknown"`이거나 `SUPPORTED_IMAGE_FORMATS`에 없는 임의의 다른 문자열인 이미지는 `code == "IMAGE_FORMAT_UNSUPPORTED"`인 경고로 처리된다(5번과 코드 구분 필수).
7. 위 두 경우 모두 예외를 던지지 않는다(정상적으로 목록에서 제외 + 경고만 남김) — 이 함수 자체가 예외를 던지는 경우는 `schema.image_block_to_picture_fragment` 내부에서 예외가 발생하는 경우(예: bbox 이상)뿐이며, 그 예외는 그대로 전파된다(삼키지 않음).

### AC-3. 다중 페이지 체이닝
8. `embed_image_blocks(blocks_page1, start_index=0)`이 반환한 3번째 값(`next_start_index`)을 `embed_image_blocks(blocks_page2, start_index=next_start_index)`에 그대로 넘기면, `blocks_page2`에서 임베딩된 이미지의 `bin_data_id`가 `blocks_page1`에서 쓰인 어떤 id와도 겹치지 않는다.
9. `next_start_index == start_index + len(embedded)`(경고 처리된 이미지 수와 무관, 오직 실제로 id를 소비한 개수만 반영).

### AC-4. 빈 입력/안정성
10. `embed_image_blocks([], start_index=N)`은 예외 없이 `([], [], N)`을 반환한다.
11. 이 함수는 입력 `blocks`(및 그 안의 각 `ImageBlockIR`)를 읽기 전용으로만 사용하며 어떤 상태도 변경하지 않는다(같은 입력으로 여러 번 호출해도 각 호출의 `embedded`/`warnings` 내용이 동일 — `bin_data_id` 번호만 `start_index`에 의해 달라짐).

### AC-5. BinData 실제 저장은 이 unit의 범위 밖 (6단계가 반드시 인지할 것)
12. **이 unit은 실제 zip(BinData 파트) 쓰기를 전혀 수행하지 않는다.** `EmbeddedImage.raw_bytes`가 실제 `.hwpx` 파일 안에 들어가는지는 이 unit의 단위 테스트 대상이 아니다 — `container.py`가 BinData 삽입 기능을 갖추고 오케스트레이터(unit-8)가 통합한 이후에만 종단 간(end-to-end) 검증이 가능하다(아래 6절 공유 자원 이슈 참고). 06단계는 이 unit을 "BinData id 할당 로직 + 프래그먼트 생성 로직"의 단위 테스트로만 범위를 한정해야 하며, "실제 한글에서 이미지가 보이는가"는 unit-8/07단계 이후로 명확히 이관해야 한다.

---

## 6. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 일괄 반영)

### 6-1. BinData 저장 — `container.py` 확장 필요 (공유 자원 이슈, 최우선 전달 사항)

**문제**: `hwpx_kernel/container.py`(unit-4 확정 파일 범위)에 BinData(이미지 바이너리 파트)를 zip에 쓰고 `META-INF/manifest.xml`/`Contents/content.hpf`에 등록하는 함수가 없다. 이 unit(unit-7)의 파일 범위(`hwpx_writer/image_embedder.py`)로는 이 문제를 해결할 수 없다(05-unit-developer 병렬 호출 규칙 — 공유 자원은 직접 수정하지 않고 이관).

**제안 시그니처** (참고용, 최종 설계는 container.py 담당자/오케스트레이터 판단):
```python
def add_bin_data(
    container_path: Path,
    entries: Mapping[str, tuple[bytes, str]],  # bin_data_id -> (raw_bytes, image_format)
) -> None:
    """각 항목을 BinData/<bin_data_id>.<확장자>(확장자는 image_format에서 유도,
    예: jpeg->jpg, jp2->jp2, png->png, tiff->tif)로 zip에 쓰고,
    META-INF/manifest.xml에 media-type(예: image/jpeg)을 등록하며,
    Contents/content.hpf의 manifest/spine에도 반영한다.
    add_section_xml과 동일한 "전체 zip 재작성 후 원자적 치환" 패턴을 권장한다
    (기존 엔트리 무결성 보존, 실패 시 ContainerBuildError)."""
```

- 호출 시점: unit-8(오케스트레이터)이 `image_embedder.embed_image_blocks()`가 반환한 `EmbeddedImage` 목록에서 `{bin_data_id: (raw_bytes, image_format)}` 딕셔너리를 만들어 `container.add_bin_data()`를 호출하고, 같은 배치의 `fragment`들은 `schema.fragment_to_bytes()` 등을 거쳐 섹션 본문(`add_section_xml`)에 삽입하는 두 단계로 통합해야 한다.
- **누가 이 작업을 언제 할지는 오케스트레이터 판단이 필요하다**(unit-4 담당자 재호출 또는 unit-8 통합 시점에 함께 처리 — 이 unit이 결정할 사안이 아니라 지시문에서도 오케스트레이터 몫으로 명시함).
- 이 확장이 이루어지기 전까지 "이미지가 실제 HWPX 파일에 임베딩되어 한글에서 보이는지"는 검증 불가능한 상태로 남는다 — 06단계는 이 사실을 알고 unit-7의 단위 테스트 범위를 AC-5(5절)대로 한정해야 한다.

### 6-2. `traceability.md` REQ-003 행 갱신 요청

| REQ-ID | 컬럼 | 값 |
|---|---|---|
| REQ-003 | 작업 단위 | 기존 "unit-2, unit-7"에서 unit-7 진행 상태만 갱신 |
| REQ-003 | 구현 상태 | "unit-7: Not Started" → **"unit-7: 05단계 구현 완료(BinData id 할당 + 배치 프래그먼트 생성), 06단계 단위테스트 대기 — 단, 실제 BinData zip 저장은 `container.py` 확장(unit-4 후속 조치, 6-1절) 대기 중이라 종단 간(실제 .hwpx에 이미지가 들어가는지) 검증은 불가. 06단계는 image_embedder.py 자체 로직(id 할당/CCITT-JBIG2 제외/체이닝)만 단위 테스트 범위로 삼을 것"** |
| REQ-003 | 비고 | 추가: "unit-7이 CCITT/JBIG2/unknown 포맷을 지원 범위 밖으로 명시하고 제외+경고 처리하기로 결정(unit-7-note.md §1-3) — CCITT/JBIG2를 실제로 임베딩 가능하게 하려면 `ir.py`(`ImageBlockIR`)에 `/Columns`/`/Rows` 등 추가 메타데이터 필드가 필요하며, 이는 별도 공유 계약 확장 결정 사항(현재 미결)" |

### 6-3. `decisions.md` 갱신 요청

이번 unit에서 규칙 A 질문을 발동한 사례는 없다(지시문이 "합리적으로 범위를 좁히는 것도 선택지"라고 명시적으로 허용한 범위 안에서 CCITT/JBIG2/unknown 처리 방침을 자체 판단으로 결정하고 근거를 기록했을 뿐). 다만 참고용으로 아래를 남긴다(결정이 필요하면 오케스트레이터가 신규 DEC로 승격 가능):

| 후보 논제 | 배경 | 옵션 | 영향 |
|---|---|---|---|
| CCITT/JBIG2 이미지의 실제 임베딩 지원 여부 | 현재는 unit-7이 이 두 포맷을 제외+경고 처리(unit-7-note.md §1-3) — 실무에서 스캔 PDF에 CCITT가 흔히 쓰인다는 점을 고려하면 향후 지원 필요성이 있을 수 있음 | (a) 현행 유지(제외+경고, 최소 침습) / (b) `ir.py`에 `/Columns`/`/Rows`/`/K` 등 필드를 추가해 unit-2가 채우고 unit-7이 TIFF 컨테이너로 감싸 임베딩 | `ir.py` 공유 계약 확장 여부, unit-2/unit-7 양쪽 재작업 필요 여부 |

### 기타 후속 조치 제안 (강제 아님, 참고용)
- unit-8(오케스트레이터) 설계 시, `ImageEmbedWarning`(이 unit의 임시 표현)을 unit-8/14가 정의할 정식 `ConversionWarning`으로 매핑하는 지점이 필요하다(`code`/`message`/`image_index` 필드를 그대로 옮기거나 재구성). 이 unit은 `core/` 패키지에 의존하지 않기 위해 자체 데이터클래스로 남겨뒀다(파일 범위 밖 의존 회피).

---

## 절차 준수 확인

- 게이트 1(정적분석/컴파일): 통과(2절).
- 게이트 2(자체 코드 리뷰 체크리스트): 통과(3절).
- 로컬 동작 확인(JPEG 1건 포함): 완료(4절).
- traceability.md/decisions.md: 병렬 호출 규칙에 따라 직접 수정하지 않음 — 위 6절 "공유 문서 갱신 요청"에 반영 내용 기재.
- 06단계(단위테스트) handoff 준비 완료. **단, BinData 실제 저장(6-1절)은 unit-4/8 후속 조치 대기 상태이므로, 06단계는 이 unit의 테스트 범위를 5절 AC-1~AC-4(id 할당/프래그먼트 생성/CCITT-JBIG2 제외/체이닝/빈 입력)로 한정하고, AC-5(BinData 실제 저장 검증)는 "unit-4/8 후속 조치 대기 — 이번 06 사이클에서는 테스트 불가"로 명확히 분리해서 다뤄야 한다.**
