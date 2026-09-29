"""PDF -> HWPX 변환 오케스트레이션 (unit-8, REQ-005/REQ-009/REQ-010).

(docs/harness/03-system-design.md §1-2 컴포넌트 다이어그램의 유일한 통합점,
§4-1 공개 API 계약 "v4 그대로, 변경 없음". 03 §1-3에 따라 이 파일
(``pdf_to_hwpx/core/orchestrator.py``) 하나만이 unit-8의 확정 파일 범위다.)

이 모듈은 unit-0~7이 만든 부품(로더/추출기/빌더/컨테이너)을 실제로 엮어
"PDF 1개 -> HWPX 1개"를 만드는 유일한 지점이다. 각 부품 모듈은 자신의
계약(시그니처)만 확정했을 뿐 통합 순서/우선순위/오류 매핑은 의도적으로
이 unit에 위임했다(unit-4/5/6/7 note가 반복적으로 명시). 03/04 설계서가
세부 사항까지 정하지 않아 이 unit이 직접 판단한 지점은 아래 6가지이며,
각 판단의 근거·한계는 ``docs/harness/units/unit-8-note.md``에 상술한다
(이 docstring에는 "무엇을 왜 이렇게 했는지"의 핵심만 남긴다):

1. **REQ-005 보존 우선순위(표>이미지>텍스트) dedup**: 표 bbox와 유의미하게
   겹치는 **텍스트** 블록만 제외한다(``_exclude_text_overlapping_tables``).
   **이미지는 이 dedup 대상에서 의도적으로 제외했다** — unit-2가 명시한 대로
   ``ImageBlockIR.bbox``는 콘텐츠 스트림의 배치 행렬을 해석하지 않고 항상
   "페이지 전체 크기 폴백값"이다(unit-2 모듈 docstring). 이 상태에서 이미지
   bbox와 표 bbox의 겹침비를 계산하면 표가 있는 모든 페이지의 이미지가
   전부 "표와 겹침"으로 판정되어 제외되는 잘못된 결과가 나온다(수학적으로
   거의 항상 겹침비가 1.0에 가까워짐). 실제로 유해한 동작을 피하기 위해
   이미지에는 이 휴리스틱을 적용하지 않는다(unit-8-note.md §2 상세).
2. **페이지 내부/페이지 간 배치 순서**: 문단(``<hp:p>``)과 표(``<hp:tbl>``)는
   각자의 ``bboxPt`` 속성(y0)을 기준으로 정렬해 대략적인 읽기 순서를
   근사한다(완벽한 z-order 병합은 REQ-008 범위 밖, YAGNI). 이미지는 신뢰할
   수 있는 위치 정보가 없으므로(위 1번과 동일 사유) 각 페이지의 맨 뒤에
   덧붙인다. 여러 페이지는 ``container.add_section_xml``이 단일 섹션만
   지원하므로 하나의 section0.xml에 순서대로 이어붙인다 — 명시적 페이지
   구분자는 ``schema.py`` 계약에 없어 추가하지 않았다(공유 자원 변경 없이는
   불가능).
3. **알려진 미해결 리스크(고치지 않고 그대로 이관)**: ``image_block_to_
   picture_fragment``는 페이지 로컬 bbox를 그대로 HWPUNIT 절대좌표로 쓴다
   (unit-4 확정 파일 범위, 이 unit이 손댈 수 없음). 여러 페이지를 한 섹션에
   이어붙이면 각 페이지의 이미지가 같은 절대좌표(대개 (0,0)-(page width,
   height))에 겹쳐 배치될 위험이 있다. 실제 한글이 이 좌표를 페이지
   기준으로 재해석하는지 문서 전체 절대좌표로 보는지 자체가 DEC-017
   미검증 영역이라 이 unit이 임의로 해결하지 않는다 — 실제 한글/07단계
   검증으로 명시적으로 이관한다.
4. **``ConversionStats`` 집계 기준**: ``tables_preserved_fully``는
   ``TableBlockIR.has_merged_cells is False``인 표만 센다 — REQ-004가
   병합 셀을 "best-effort"로 규정하고, unit-3의 병합 감지 자체가 미탐
   가능성이 있는 휴리스틱이라(unit-3-note.md) 병합이 확정된 표는 "완전
   보존을 보장할 수 없음"으로 보수적으로 분류한다. ``chars_extracted``는
   페이지에서 추출된 모든 ``TextBlockIR.text`` 길이의 합(표-dedup 이전,
   "추출"이라는 지표의 의미에 맞춤), ``chars_replaced_with_placeholder``는
   ``to_unicode_missing=True``인 블록의 ``text`` 길이의 합이다(지시문이
   명시한 정의를 그대로 따름 — □ 문자 개수가 아니라 그 블록 전체 글자 수).
5. **``HWPX_MIN_SUPPORTED_VERSION``**: 03 §4-2/§8-3이 "확인 필요"로 남긴
   미해결 항목이라 임의의 버전 문자열을 지어내지 않고,
   ``hwpx_kernel.schema.SCHEMA_VERSION``("1.0", unit-4가 이미 확정한 계약
   버전)을 그대로 재사용한다 — 별도의 독립적인 "HWPX 파일 포맷 최소 지원
   버전" 개념이 아직 존재하지 않으므로, 현재 유일하게 존재하는 버전 상수를
   가리키는 것이 "지어내지 않는" 가장 안전한 선택이다.
6. **``ConversionIssue`` 필드**: 03 §4-1은 이름만 정의하고 필드를 정하지
   않았다. ``code: str``(예외 클래스명 또는 ``INTERNAL_ERROR``/
   ``PAGE_PROCESSING_FAILED``), ``message: str``(사용자 노출 가능,
   ``common/exceptions.py`` 문서화된 04 §2 G-4 문구 재사용), ``page_index:
   int | None = None``(문서 전체 오류는 None, 페이지 단위 오류는 해당
   인덱스)로 정의했다 — ``ConversionWarning``과 최대한 일관된 모양을
   유지하면서, 문서 수준 오류를 표현할 수 있게 ``page_index``만 선택적으로
   두었다.

**페이지 단위 격리(벌크헤드), 03 §5 "장애 대응"**: unit-1/2/3의 추출 함수는
예외를 삼키지 않고 그대로 전파하는 계약이며(각 모듈 docstring), "한 페이지
실패가 문서 전체를 실패시키지 않는다"는 03 §5의 원칙을 실제로 구현하는
책임은 이 오케스트레이터에 있다(unit-2 모듈 docstring이 명시적으로 이렇게
지목한다). 따라서 페이지별 처리는 개별 ``try/except``로 감싸고, 실패한
페이지는 ``ConversionIssue(code="PAGE_PROCESSING_FAILED", page_index=...)``
로 기록한 뒤 다음 페이지를 계속 처리한다. 다만 ``ConversionResult``에는
"부분 성공(일부 페이지만 담긴 다운로드 가능 파일)"이라는 상태를 표현할
필드가 없고, 03 §3-2(``ConversionJob`` 상태 전이 주석)가 "DONE +
result_success=False -> 다운로드 자체를 제공하지 않고 오류만 노출"이라고
이미 확정해 두었다 — 이 계약과 일관되도록, **페이지 하나라도 처리에
실패하면 전체 결과를 ``success=False``로 반환하고 부분적으로 만들어진
출력 파일은 정리(삭제)한다**(unit-8-note.md §3에 이 결정의 근거와 대안
후보를 남긴다).

**OCR(REQ-014)은 이번 unit의 범위 밖이다.** ``ConversionOptions.enable_ocr``/
``ocr_lang``은 계약대로 받기만 하고, 이 값에 따라 실제로 다른 동작을
수행하는 로직은 아직 없다(``pdf_reader/ocr_engine.py``=unit-12,
스캔 판정 라우팅=unit-9가 모두 Not Started). ``PageIR.is_scanned``를 True로
설정하는 로직도 이 unit에는 없다. ``enable_ocr=True``를 넘겨도 현재는
실질적 동작 변화가 없다 — 이것은 결함이 아니라 명시적으로 이관된 범위 밖
항목이다(지시문 필수 명시 사항).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pdf_to_hwpx.common.exceptions import (
    ContainerBuildError,
    ConversionError,
    CorruptedPdfError,
    EmptyPdfError,
    EncryptedPdfError,
    OcrEngineError,
    OutputPathError,
    TesseractNotFoundError,
)
from pdf_to_hwpx.common.logging_setup import LOGGER_NAME
from pdf_to_hwpx.hwpx_kernel import container as hwpx_container
from pdf_to_hwpx.hwpx_kernel import schema as hwpx_schema
from pdf_to_hwpx.hwpx_writer.image_embedder import embed_image_blocks
from pdf_to_hwpx.hwpx_writer.paragraph_builder import build_paragraph_fragments
from pdf_to_hwpx.hwpx_writer.table_builder import table_blocks_to_fragments
from pdf_to_hwpx.pdf_reader.image_extractor import extract_image_blocks
from pdf_to_hwpx.pdf_reader.ir import TableBlockIR, TextBlockIR
from pdf_to_hwpx.pdf_reader.loader import load_pdf
from pdf_to_hwpx.pdf_reader.table_recognizer import extract_table_blocks
from pdf_to_hwpx.pdf_reader.text_extractor import extract_text_blocks

_logger = logging.getLogger(LOGGER_NAME)

# 03 §4-2/§8-3이 "확인 필요"로 남긴 미해결 항목 — 임의의 버전 문자열을 지어내지
# 않고, 현재 유일하게 존재하는 HWPX 계약 버전 상수(unit-4)를 그대로 가리킨다
# (docstring 5번 판단 근거).
HWPX_MIN_SUPPORTED_VERSION = hwpx_schema.SCHEMA_VERSION

# 표 bbox와 텍스트 블록 bbox의 2D 겹침비(교집합 면적 / 더 작은 쪽 면적)가 이
# 값 이상이면 "표 안에 있다"고 보고 그 텍스트 블록을 제외한다(REQ-005).
# unit-1/unit-5가 "같은 줄" 판정에 쓴 세로 겹침비율 0.5(_LINE_OVERLAP_RATIO)
# 선례를 2D 면적 비율로 확장한 값이다 — 근거 있는 표준값은 아니며, 03/04
# 설계서에 구체적 수치가 없어 합리적으로 정한 휴리스틱이다(불완전 판정
# 가능성 있음, unit-8-note.md 명시).
_TABLE_TEXT_OVERLAP_EXCLUSION_RATIO = 0.5

_USER_MESSAGE_BY_EXCEPTION_TYPE: dict[type[ConversionError], str] = {
    EncryptedPdfError: "비밀번호로 보호된 PDF는 지원하지 않습니다.",
    CorruptedPdfError: "PDF 파일을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다.",
    EmptyPdfError: "빈 PDF 파일입니다.",
    ContainerBuildError: (
        "HWPX 파일을 생성할 수 없습니다. 디스크 여유 공간을 확인하고 다시 시도해주세요."
    ),
    TesseractNotFoundError: "OCR 엔진을 찾을 수 없습니다. 프로그램을 재설치하거나 문의해주세요.",
    OcrEngineError: "OCR 처리 중 오류가 발생했습니다.",
}
_GENERIC_CONVERSION_ERROR_MESSAGE = "변환 중 오류가 발생했습니다."
_INTERNAL_ERROR_MESSAGE = "예상치 못한 오류가 발생했습니다. 문제가 계속되면 로그를 확인하거나 개발자에게 문의해주세요."


@dataclass
class ProgressEvent:
    """단계별 진행 상황 알림(03 §4-1). ``progress_callback``에 그대로 전달된다."""

    stage: Literal["loading", "extracting", "building", "saving", "done"]
    current_page: int
    total_pages: int
    message: str


@dataclass
class ConversionOptions:
    """``convert()`` 호출 옵션(03 §4-1). 보존 우선순위(표>이미지>텍스트)는
    옵션으로 노출하지 않는다 — 이 오케스트레이터의 내부 고정 정책이다
    (REQ-005, 모듈 docstring 1번)."""

    enable_ocr: bool = False
    ocr_lang: str = "kor"
    overwrite_existing: bool = False
    target_hwpx_min_version: str = HWPX_MIN_SUPPORTED_VERSION
    progress_callback: Callable[[ProgressEvent], None] | None = None


@dataclass
class ConversionWarning:
    """품질 저하가 있었지만 변환 자체는 계속 진행된 경우(REQ-005/REQ-009)."""

    code: str
    page_index: int
    detail: str


@dataclass
class ConversionIssue:
    """변환 실패 사유(REQ-009). 03 §4-1은 이름만 정의하고 필드는 위임했다
    (모듈 docstring 6번 판단 근거)."""

    code: str
    message: str
    page_index: int | None = None


@dataclass
class ConversionStats:
    """변환 통계(03 §4-1). 집계 기준은 모듈 docstring 4번 참고."""

    total_pages: int
    tables_detected: int
    tables_preserved_fully: int
    images_embedded: int
    chars_extracted: int
    chars_replaced_with_placeholder: int
    elapsed_seconds: float


@dataclass
class ConversionResult:
    """``convert()``의 반환값(03 §4-1, REQ-009 "예외를 던지지 않는다" 계약)."""

    success: bool
    output_path: Path | None
    warnings: list[ConversionWarning]
    errors: list[ConversionIssue]
    stats: ConversionStats


def convert(
    input_path: Path,
    output_path: Path,
    options: ConversionOptions | None = None,
) -> ConversionResult:
    """PDF 1개를 HWPX 1개로 변환한다.

    실패해도 예외를 던지지 않고 ``ConversionResult.success=False`` +
    ``errors``에 담아 반환한다(REQ-009). 호출자(CLI/웹 실행기)가 이 결과를
    사용자 메시지로 매핑한다.
    """
    options = options if options is not None else ConversionOptions()
    input_path = Path(input_path)
    output_path = Path(output_path)
    started_at = time.monotonic()

    stats = ConversionStats(
        total_pages=0,
        tables_detected=0,
        tables_preserved_fully=0,
        images_embedded=0,
        chars_extracted=0,
        chars_replaced_with_placeholder=0,
        elapsed_seconds=0.0,
    )
    warnings: list[ConversionWarning] = []
    errors: list[ConversionIssue] = []

    def _emit_progress(
        stage: Literal["loading", "extracting", "building", "saving", "done"],
        current_page: int,
        total_pages: int,
        message: str,
    ) -> None:
        if options.progress_callback is not None:
            options.progress_callback(
                ProgressEvent(
                    stage=stage,
                    current_page=current_page,
                    total_pages=total_pages,
                    message=message,
                )
            )

    container_built = False
    try:
        _validate_output_path(output_path, overwrite_existing=options.overwrite_existing)

        _emit_progress("loading", 0, 0, "PDF 파일을 여는 중입니다.")
        with load_pdf(input_path) as doc:
            total_pages = doc.page_count
            stats.total_pages = total_pages

            hwpx_container.build_empty_container(output_path)
            container_built = True

            all_fragments: list = []
            bin_data_entries: dict[str, tuple[bytes, str]] = {}
            next_bin_index = 0
            had_page_failure = False

            for page_index in range(total_pages):
                _emit_progress(
                    "extracting",
                    page_index + 1,
                    total_pages,
                    f"{page_index + 1}/{total_pages}페이지 내용을 추출하는 중입니다.",
                )
                try:
                    plumber_page = doc.plumber_pdf.pages[page_index]
                    pypdf_page = doc.pypdf_reader.pages[page_index]

                    text_blocks = extract_text_blocks(plumber_page)
                    table_blocks = extract_table_blocks(plumber_page)
                    image_blocks = extract_image_blocks(pypdf_page)

                    filtered_text_blocks = _exclude_text_overlapping_tables(
                        text_blocks, table_blocks
                    )

                    _emit_progress(
                        "building",
                        page_index + 1,
                        total_pages,
                        f"{page_index + 1}/{total_pages}페이지를 HWPX 요소로 조립하는 중입니다.",
                    )

                    paragraph_fragments = build_paragraph_fragments(filtered_text_blocks)
                    table_fragments = table_blocks_to_fragments(table_blocks)
                    embedded_images, image_embed_warnings, next_bin_index = embed_image_blocks(
                        image_blocks, start_index=next_bin_index
                    )

                    page_fragments = _order_page_fragments(
                        paragraph_fragments,
                        table_fragments,
                        [image.fragment for image in embedded_images],
                    )
                    all_fragments.extend(page_fragments)

                    for image in embedded_images:
                        bin_data_entries[image.bin_data_id] = (
                            image.raw_bytes,
                            image.image_format,
                        )
                    for warn in image_embed_warnings:
                        warnings.append(
                            ConversionWarning(
                                code=warn.code, page_index=page_index, detail=warn.message
                            )
                        )

                    stats.tables_detected += len(table_blocks)
                    stats.tables_preserved_fully += sum(
                        1 for table in table_blocks if not table.has_merged_cells
                    )
                    stats.images_embedded += len(embedded_images)
                    stats.chars_extracted += sum(len(block.text) for block in text_blocks)
                    stats.chars_replaced_with_placeholder += sum(
                        len(block.text) for block in text_blocks if block.to_unicode_missing
                    )
                except Exception:
                    _logger.exception(
                        "페이지 처리 중 예상치 못한 오류(page_index=%s)", page_index
                    )
                    had_page_failure = True
                    errors.append(
                        ConversionIssue(
                            code="PAGE_PROCESSING_FAILED",
                            message=f"{page_index + 1}번째 페이지를 처리하지 못했습니다.",
                            page_index=page_index,
                        )
                    )
                    continue

            if not had_page_failure:
                _emit_progress(
                    "saving", total_pages, total_pages, "HWPX 파일을 저장하는 중입니다."
                )
                section_bytes = hwpx_schema.build_reference_section_body(all_fragments)
                hwpx_container.add_section_xml(output_path, section_bytes)
                if bin_data_entries:
                    hwpx_container.add_bin_data(output_path, bin_data_entries)

        stats.elapsed_seconds = time.monotonic() - started_at

        if had_page_failure:
            # 03 §3-2 "DONE+result_success=False -> 다운로드 미제공" 계약과
            # 일관되도록, 부분 성공이라는 중간 상태를 만들지 않는다(모듈
            # docstring "페이지 단위 격리" 절 근거).
            _cleanup_partial_output(output_path)
            return ConversionResult(
                success=False,
                output_path=None,
                warnings=warnings,
                errors=errors,
                stats=stats,
            )

        _emit_progress("done", total_pages, total_pages, "변환이 완료되었습니다.")
        return ConversionResult(
            success=True,
            output_path=output_path,
            warnings=warnings,
            errors=errors,
            stats=stats,
        )
    except ConversionError as exc:
        stats.elapsed_seconds = time.monotonic() - started_at
        if container_built:
            _cleanup_partial_output(output_path)
        message = (
            str(exc)
            if isinstance(exc, OutputPathError)
            else _USER_MESSAGE_BY_EXCEPTION_TYPE.get(type(exc), _GENERIC_CONVERSION_ERROR_MESSAGE)
        )
        _logger.exception("변환 실패(%s)", type(exc).__name__)
        errors.append(ConversionIssue(code=type(exc).__name__, message=message, page_index=None))
        return ConversionResult(
            success=False, output_path=None, warnings=warnings, errors=errors, stats=stats
        )
    except Exception:
        stats.elapsed_seconds = time.monotonic() - started_at
        if container_built:
            _cleanup_partial_output(output_path)
        # traceback은 로컬 로그에만 남기고 사용자에게는 고정 문구만 노출한다
        # (내부 경로/구현 노출 방지, 03 §6 개인정보 원칙).
        _logger.exception("변환 중 예상치 못한 내부 오류")
        errors.append(
            ConversionIssue(code="INTERNAL_ERROR", message=_INTERNAL_ERROR_MESSAGE, page_index=None)
        )
        return ConversionResult(
            success=False, output_path=None, warnings=warnings, errors=errors, stats=stats
        )


def _validate_output_path(output_path: Path, *, overwrite_existing: bool) -> None:
    """출력 경로를 변환 시작 전에 미리 검증한다(``OutputPathError`` 사전 검증).

    - 파일이 이미 존재하는데 ``overwrite_existing=False``이면 즉시 실패.
    - 아직 존재하지 않는 상위 디렉터리를 만들어야 한다면, 실제로 쓰기가
      가능한지 가장 가까운 존재하는 조상 디렉터리의 쓰기 권한으로 판단한다
      (``os.access``는 Windows ACL을 완벽히 반영하지 못하는 알려진 한계가
      있으나, 표준 라이브러리 수준에서 합리적인 사전 점검이다).
    """
    if output_path.exists() and not overwrite_existing:
        raise OutputPathError(
            f"출력 파일이 이미 존재합니다: {output_path}. "
            "덮어쓰기를 허용하거나 다른 경로를 지정해주세요."
        )

    probe = output_path.parent
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    if not os.access(probe, os.W_OK):
        raise OutputPathError(f"출력 경로에 쓰기 권한이 없습니다: {output_path.parent}")


def _cleanup_partial_output(output_path: Path) -> None:
    """실패한 변환이 남긴 부분/빈 HWPX 산출물을 정리한다(best-effort).

    이 정리 자체가 실패해도(예: 파일이 다른 프로세스에 의해 잠김) 원래
    실패 사유를 가리지 않도록 예외를 다시 던지지 않는다 — 다만 조용히
    삼키지는 않고 로그로 남긴다.
    """
    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        _logger.warning(
            "실패한 변환의 부분 산출물을 정리하지 못했습니다: %s", output_path, exc_info=True
        )


def _bbox_overlap_ratio(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """두 bbox의 2D 겹침비(교집합 면적 / 더 작은 쪽 면적)를 계산한다."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    area_a = max(ax1 - ax0, 0.0) * max(ay1 - ay0, 0.0)
    area_b = max(bx1 - bx0, 0.0) * max(by1 - by0, 0.0)
    smaller = min(area_a, area_b)
    if smaller <= 0:
        return 0.0
    return intersection / smaller


def _exclude_text_overlapping_tables(
    text_blocks: list[TextBlockIR], table_blocks: list[TableBlockIR]
) -> list[TextBlockIR]:
    """REQ-005 보존 우선순위(표>텍스트) — 표 bbox와 유의미하게 겹치는 텍스트
    블록을 제외한다. 이미지에는 적용하지 않는다(모듈 docstring 1번 참고)."""
    if not table_blocks:
        return list(text_blocks)
    kept: list[TextBlockIR] = []
    for block in text_blocks:
        overlaps_table = any(
            _bbox_overlap_ratio(block.bbox, table.bbox) >= _TABLE_TEXT_OVERLAP_EXCLUSION_RATIO
            for table in table_blocks
        )
        if not overlaps_table:
            kept.append(block)
    return kept


def _fragment_top_y(fragment) -> float:
    """``bboxPt``("x0,y0,x1,y1") 속성에서 y0을 읽어 대략적인 세로 읽기 순서
    정렬 키로 쓴다. 속성이 없거나 파싱 불가하면 0.0(맨 앞 취급)으로 둔다."""
    bbox_attr = fragment.get("bboxPt")
    if not bbox_attr:
        return 0.0
    parts = bbox_attr.split(",")
    if len(parts) < 2:
        return 0.0
    try:
        return float(parts[1])
    except ValueError:
        return 0.0


def _order_page_fragments(paragraph_fragments, table_fragments, image_fragments):
    """페이지 1개 분량의 프래그먼트를 배치 순서로 정렬한다(모듈 docstring
    2번 판단 근거). 문단/표는 ``bboxPt`` y0 기준으로 정렬해 읽기 순서를
    근사하고, 이미지는 위치 정보가 신뢰할 수 없어(1번과 동일 사유) 페이지
    끝에 이어붙인다."""
    text_and_tables = list(paragraph_fragments) + list(table_fragments)
    text_and_tables.sort(key=_fragment_top_y)
    return text_and_tables + list(image_fragments)
