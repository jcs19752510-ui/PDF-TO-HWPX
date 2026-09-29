"""IR -> HWPX XML 프래그먼트 변환 "계약" (unit-4, REQ-008).

`pdf_to_hwpx.pdf_reader.ir`의 IR 데이터클래스(``TextBlockIR``/``ImageBlockIR``/
``TableBlockIR``/``TableCellIR``)를 입력으로 받아, HWPX 본문 XML 프래그먼트
(lxml ``etree._Element``)를 만드는 함수 시그니처를 이 모듈이 확정한다.

**이 unit은 계약(인터페이스)까지만 확정한다** (03-system-design.md §1-2:
"schema.py는 코드가 아니라 계약이다" / §1-3 unit-5/6/7 행). 아래 각 함수는
동작하는 최소 기본 구현을 담고 있지만, 실제 세로 위치 정밀도(REQ-008 6-6)·
병합 셀 best-effort 처리(REQ-004)·이미지 배치 최적화 등 도메인 로직의 완성은
각각 ``hwpx_writer/paragraph_builder.py``(unit-5), ``table_builder.py``(unit-6),
``image_embedder.py``(unit-7)의 책임이다. 이 함수들의 시그니처(인자/반환 타입)를
바꾸면 세 unit 모두에 영향을 주므로, 바꿔야 한다면 반드시 이 계약부터 갱신하고
``SCHEMA_VERSION``을 올려야 한다(마이그레이션 전략, 03 §3-1).

**미검증 리스크**: 이 모듈이 생성하는 XML 태그/속성 이름(``hp:p``, ``hp:run``,
``hp:t``, ``hp:tbl`` 등)과 네임스페이스는 `hwpx_kernel/container.py` 모듈
docstring에 적은 것과 동일한 사유로 **공개 표준 일반 지식에 근거한 추정이며
실제 한글(한컴오피스)에서 열리는지 검증되지 않았다**(docs/harness/decisions.md
DEC-017). 특히 표(``hp:tbl``/``hp:tr``/``hp:tc``)의 병합 셀 배치 방식과 그림
(``hp:pic``)의 바이너리 참조 방식은 실제 OWPML 스펙 문서 원문을 대조하지 못한
채 만든 것이므로 불확실성이 가장 크다.
"""

from __future__ import annotations

from lxml import etree

from pdf_to_hwpx.hwpx_kernel.container import NAMESPACES
from pdf_to_hwpx.pdf_reader.ir import (
    ImageBlockIR,
    TableBlockIR,
    TableCellIR,
    TextBlockIR,
)

# 계약(인터페이스) 버전. 아래 함수들의 시그니처나 생성되는 프래그먼트 구조가
# 바뀌면(필드 추가/삭제 등) 올린다 (03 §3-1 "마이그레이션 전략").
SCHEMA_VERSION = "1.0"

# HWPUNIT = 1/7200 inch, pt = 1/72 inch 이므로 1pt = 100 HWPUNIT.
# (여러 공개 HWP 관련 프로젝트에서 일관되게 확인되는 값이라 "확신" 수준의 근거지만,
# 이 프로젝트 개발 환경에서 실제 한글로 직접 재검증하지는 못했다.)
HWPUNIT_PER_POINT = 100

_DEFAULT_CHAR_SHAPE_ID = "0"
_DEFAULT_PARA_SHAPE_ID = "0"


def pt_to_hwpunit(value_pt: float) -> int:
    """포인트(pt) 좌표/길이를 HWPUNIT 정수로 변환한다."""
    return round(value_pt * HWPUNIT_PER_POINT)


def _qname(prefix: str, tag: str) -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def text_block_to_paragraph_fragment(
    block: TextBlockIR,
    *,
    char_shape_id: str = _DEFAULT_CHAR_SHAPE_ID,
    para_shape_id: str = _DEFAULT_PARA_SHAPE_ID,
) -> etree._Element:
    """``TextBlockIR`` 1개를 문단(``hp:p``) 프래그먼트로 변환한다.

    unit-5 인터페이스 계약:
    - 입력 ``block.text``는 unit-15(hangul_normalizer)가 NFC 정규화를 이미
      끝낸 상태로 가정한다(재정규화하지 않는다).
    - ``char_shape_id``/``para_shape_id``는 `container.py`의
      ``_build_header_xml()``이 정의한 스타일 id(기본값 "0")와 반드시 일치해야
      한다 — 다른 id를 쓰려면 unit-5가 header.xml에 해당 id의 스타일을 먼저
      추가하는 로직을 별도로 책임져야 한다(이 unit은 id="0" 기본 스타일 1개만
      정의했다).
    - 반환된 ``<hp:p>`` 엘리먼트에는 원본 bbox를 ``bboxPt`` 속성(디버깅/추후
      정밀 배치용, "x0,y0,x1,y1" pt 단위 문자열)으로 부착해 두었다. 실제 HWPX가
      요구하는 절대/상대 위치 지정 방식(고정폭 vs 흐름형 배치)은 이 unit이
      확정하지 않았으므로, 세로 위치 오차(REQ-008 6-6) 대응은 unit-5가 이
      속성을 참고해 실제 위치 속성으로 정밀화해야 한다.
    - ``to_unicode_missing=True``인 경우 이미 ``block.text``에 대체문자(□)가
      치환되어 있다고 가정한다(REQ-007, IR 계약) — 이 함수가 추가로 치환하지
      않는다.
    """
    p = etree.Element(_qname("hp", "p"), attrib={"paraShapeIDRef": para_shape_id})
    x0, y0, x1, y1 = block.bbox
    p.set("bboxPt", f"{x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f}")

    run = etree.SubElement(p, _qname("hp", "run"), attrib={"charShapeIDRef": char_shape_id})
    if block.bold:
        run.set("bold", "1")
    if block.italic:
        run.set("italic", "1")
    if block.font_name:
        run.set("fontName", block.font_name)
    if block.font_size is not None:
        run.set("fontSizeHwpunit", str(pt_to_hwpunit(block.font_size)))

    t = etree.SubElement(run, _qname("hp", "t"))
    t.text = block.text
    return p


def table_cell_to_cell_fragment(
    cell: TableCellIR,
    *,
    row: int,
    col: int,
    char_shape_id: str = _DEFAULT_CHAR_SHAPE_ID,
    para_shape_id: str = _DEFAULT_PARA_SHAPE_ID,
) -> etree._Element:
    """``TableCellIR`` 1개를 표 셀(``hp:tc``) 프래그먼트로 변환한다.

    unit-6 인터페이스 계약:
    - ``row``/``col``은 0-기반 그리드 좌표로, 호출자(unit-6)가 병합 셀
      (``row_span``/``col_span`` > 1)을 감안해 실제 그리드 상의 시작 좌표를
      계산해서 넘겨야 한다 — 이 함수는 좌표 계산 로직을 갖지 않는다(순수 변환).
    - 셀 텍스트는 내부에 문단 1개(``hp:subList``/``hp:p``)로 감싼다. 여러
      줄/문단으로 나뉜 셀 내용을 지원해야 한다면 unit-6이 이 함수를 셀 내
      문단 수만큼 반복 호출하도록 확장하거나, 이 계약 자체를 갱신해야 한다
      (현재는 셀당 문단 1개로 단순화 — SCHEMA_VERSION 1.0 범위).
    """
    tc = etree.Element(
        _qname("hp", "tc"),
        attrib={
            "rowAddr": str(row),
            "colAddr": str(col),
            "rowSpan": str(cell.row_span),
            "colSpan": str(cell.col_span),
        },
    )
    sub_list = etree.SubElement(tc, _qname("hp", "subList"))
    p = etree.SubElement(sub_list, _qname("hp", "p"), attrib={"paraShapeIDRef": para_shape_id})
    run = etree.SubElement(p, _qname("hp", "run"), attrib={"charShapeIDRef": char_shape_id})
    t = etree.SubElement(run, _qname("hp", "t"))
    t.text = cell.text
    return tc


def table_block_to_table_fragment(block: TableBlockIR) -> etree._Element:
    """``TableBlockIR`` 1개를 표(``hp:tbl``) 프래그먼트로 변환한다.

    unit-6 인터페이스 계약:
    - 기본 구현은 ``block.cells``가 **행 우선(row-major) 순서로, 병합 셀도
      포함해 rows*cols 그리드를 빠짐없이 순회 가능한 순서**로 채워져 있다고
      가정하고 단순 나눗셈(``divmod(idx, cols)``)으로 (row, col)을 추정한다.
      실제 PDF 표에서 병합 셀이 있는 경우 이 가정이 깨질 수 있다(REQ-004
      "병합 셀은 best-effort") — unit-6이 실제 병합 셀 배치를 정확히 계산해야
      한다면, 이 함수 대신 ``table_cell_to_cell_fragment()``를 직접
      호출해 (row, col)을 명시적으로 넘기는 방식을 쓰는 것을 권장한다(이
      함수는 "간단한 경우의 편의 함수"로 남겨둔다).
    - ``block.has_merged_cells``가 True면 ``<hp:tbl hasMergedCells="1">``
      속성을 부착해 unit-8/quality_report(unit-14)가 REQ-004 best-effort
      경고를 남길 근거로 쓸 수 있게 한다.
    """
    tbl = etree.Element(
        _qname("hp", "tbl"),
        attrib={"rowCnt": str(block.rows), "colCnt": str(block.cols)},
    )
    if block.has_merged_cells:
        tbl.set("hasMergedCells", "1")

    cols = block.cols if block.cols > 0 else max(len(block.cells), 1)
    rows_xml: dict[int, etree._Element] = {}
    for idx, cell in enumerate(block.cells):
        row, col = divmod(idx, cols)
        tr = rows_xml.get(row)
        if tr is None:
            tr = etree.SubElement(tbl, _qname("hp", "tr"))
            rows_xml[row] = tr
        tr.append(table_cell_to_cell_fragment(cell, row=row, col=col))
    return tbl


def image_block_to_picture_fragment(
    block: ImageBlockIR,
    *,
    bin_data_id: str,
) -> etree._Element:
    """``ImageBlockIR`` 1개를 그림(``hp:pic``) 배치 프래그먼트로 변환한다.

    unit-7 인터페이스 계약:
    - 이 함수는 **배치(위치/크기) 프래그먼트만** 만든다. ``block.raw_bytes``
      (원본 이미지 바이트, REQ-003 재인코딩 금지)를 실제 HWPX 컨테이너의
      BinData 파트에 저장하고 그 항목에 ``bin_data_id``를 부여하는 작업은
      unit-7의 책임이며, 이 함수는 그 id를 참조만 한다(파일 I/O 없음).
      BinData 파트 자체의 zip 내 경로/디렉터리 구조는 `container.py`가
      아직 정의하지 않았다 — unit-7이 실제 이미지 삽입을 구현할 때 필요하면
      `container.py`에 BinData 관련 함수를 추가해야 하며, 이는 unit-4의
      확정 파일 범위(`container.py`, `schema.py`) 안이므로 unit-7이 직접
      수정하지 말고 오케스트레이터에게 후속 작업으로 알려야 한다(unit-note
      "공유 문서 갱신 요청" 참고).
    - 크기/위치는 bbox(pt)를 HWPUNIT으로 변환해 부착한다(``pt_to_hwpunit``).
    """
    x0, y0, x1, y1 = block.bbox
    width_pt = x1 - x0
    height_pt = y1 - y0

    pic = etree.Element(
        _qname("hp", "pic"),
        attrib={"binDataIDRef": bin_data_id, "format": block.image_format},
    )
    etree.SubElement(
        pic,
        _qname("hp", "pos"),
        attrib={
            "xHwpunit": str(pt_to_hwpunit(x0)),
            "yHwpunit": str(pt_to_hwpunit(y0)),
        },
    )
    etree.SubElement(
        pic,
        _qname("hp", "sz"),
        attrib={
            "widthHwpunit": str(pt_to_hwpunit(width_pt)),
            "heightHwpunit": str(pt_to_hwpunit(height_pt)),
        },
    )
    return pic


def fragment_to_bytes(element: etree._Element) -> bytes:
    """프래그먼트 엘리먼트를 (XML 선언 없는) UTF-8 바이트로 직렬화한다.

    섹션 본문에 삽입할 조각(fragment)이므로 문서 전체의 XML 선언은 붙이지
    않는다 — 전체 섹션 XML 조립은 unit-8(orchestrator)의 책임이다(§1-2
    컴포넌트 다이어그램: PARA/TABLEB/IMGB --> ORCH --> CONTAINER).
    """
    return etree.tostring(element, xml_declaration=False, encoding="UTF-8")


def build_reference_section_body(fragments: list[etree._Element]) -> bytes:
    """[참고용 편의 함수] 프래그먼트 목록을 하나의 ``<hs:sec>`` 섹션 XML로 감싼다.

    **이 함수는 계약의 필수 부분이 아니다.** unit-8(orchestrator)이 5/6/7의
    출력을 실제로 어떤 순서/우선순위 정책(REQ-005/009/010)으로 통합할지는
    orchestrator 자신의 책임이며, orchestrator는 이 함수를 그대로 쓸 수도,
    자체 조립 로직을 새로 짤 수도 있다. 이 함수는 unit-4가 로컬 동작 확인
    (컨테이너에 실제 섹션을 넣어 zip 구조를 검증)을 하기 위해 만든 참고
    구현으로 함께 제공한다.
    """
    root = etree.Element(
        _qname("hs", "sec"),
        nsmap={"hs": NAMESPACES["hs"], "hp": NAMESPACES["hp"]},
    )
    for fragment in fragments:
        root.append(fragment)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
