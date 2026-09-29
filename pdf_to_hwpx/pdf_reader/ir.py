"""PDF 판독 결과의 공용 중간표현(IR) 데이터클래스.

(docs/harness/03-system-design.md §3-1 "중간표현(IR) 엔티티" 원문 그대로.)

이 파일은 03단계 작업단위 확정표(§1-3)에 명시적으로 배정되지 않은 공유
계약 파일이다 — unit-1(text_extractor)/unit-2(image_extractor)/
unit-3(table_recognizer)/unit-16(formula_approximator)이 이 IR을
"만들고", unit-5/6/7(hwpx_writer)·unit-8(orchestrator)이 이를
"소비"하는데(§3-1 "IR의 역할"), 정작 이 데이터클래스 자체를 어느 unit이
정의할지는 설계서에 명시되어 있지 않았다.

병렬 웨이브(unit-1/2/3/4)를 동시에 착수시키기 전에 오케스트레이터가
이 공유 자원 문제를 발견해 직접 해소했다(ORCHESTRATOR.md 1장 "병렬 실행
모드"의 "안전 규칙" — 공유 자원은 병렬 착수 전에 정리). 근거는
docs/harness/decisions.md DEC-016 참고. 이 파일은 dataclass 정의만
담은 순수 데이터 계약이라 unit-0의 exceptions.py와 같은 성격(로직 없음)
이며, 어느 unit도 이 파일을 "구현"하지 않고 import만 한다.

주의: ``hwpx_kernel/schema.py``(unit-4)는 이 IR을 입력으로 받아
XML 프래그먼트로 변환하는 "계약 함수"를 정의하는 곳이지, IR 자체를
재정의하는 곳이 아니다. unit-4는 이 모듈에서 IR을 import해서 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TextBlockIR:
    bbox: tuple[float, float, float, float]
    text: str  # unit-15(hangul_normalizer)가 NFC 정규화 완료한 상태로 전달됨
    font_name: str | None
    font_size: float | None
    bold: bool
    italic: bool
    to_unicode_missing: bool  # REQ-007: True면 대체문자(□)로 치환된 상태


@dataclass
class ImageBlockIR:
    bbox: tuple[float, float, float, float]
    raw_bytes: bytes  # 재인코딩 없이 원본 그대로(REQ-003)
    image_format: str  # "jpeg"|"png"|... (pypdf가 판별한 원본 포맷)


@dataclass
class TableCellIR:
    row_span: int
    col_span: int
    text: str


@dataclass
class TableBlockIR:
    bbox: tuple[float, float, float, float]
    rows: int
    cols: int
    cells: list[TableCellIR]
    has_merged_cells: bool  # REQ-004: True면 best-effort 처리, quality_report에 기록


@dataclass
class FormulaCandidateIR:
    bbox: tuple[float, float, float, float]
    source: Literal["image_region", "non_table_glyph_cluster"]


@dataclass
class PageIR:
    page_index: int
    width_pt: float
    height_pt: float
    text_blocks: list[TextBlockIR] = field(default_factory=list)
    image_blocks: list[ImageBlockIR] = field(default_factory=list)
    table_blocks: list[TableBlockIR] = field(default_factory=list)
    formula_candidates: list[FormulaCandidateIR] = field(default_factory=list)  # unit-16 소비
    is_scanned: bool = False  # True면 orchestrator가 unit-12(OCR) 경로로 라우팅
