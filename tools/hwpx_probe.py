"""G1 프로브 생성기 (unit-4R, 분석서 §12-2, 게이트 G1).

사용자가 실제 한글에서 열어 확인할 프로브 HWPX를 만든다. 자동 테스트만으로는 한글 수용을
판정할 수 없다(DEC-051). 출력은 기본 ``.harness-tmp/probe/`` 이고 ``--out``으로 다른 경로를
지정할 수 있다. 저장소에 산출물을 커밋하지 않는다.

    python tools/hwpx_probe.py [--out DIR] [--only P1a,P2,...]

P2~P4는 변수를 줄이기 위해 version.xml을 R1 관찰 값(P1a와 동일)으로 쓴다. P1b만 자체 값이다.
P5(그림)는 04_그림.hwpx 수령 후 unit-4P 범위다.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lxml import etree

from pdf_to_hwpx.hwpx_kernel import fonts
from pdf_to_hwpx.hwpx_kernel.constants import pt_to_hwpunit
from pdf_to_hwpx.hwpx_kernel.container import (
    VERSION_OWN,
    VERSION_R1_OBSERVED,
    HwpxPackage,
    PackageMeta,
    VersionInfo,
    format_preview_text,
)
from pdf_to_hwpx.hwpx_kernel.context import DocContext
from pdf_to_hwpx.hwpx_kernel.flow import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    LEFT_QUANTUM,
    MIN_ROW_HEIGHT,
    quantize,
)
from pdf_to_hwpx.hwpx_kernel.schema import (
    make_lineseg,
    make_paragraph,
    make_run,
    make_table,
    make_table_cell,
)
from pdf_to_hwpx.hwpx_kernel.section import PageSetup, build_section_xml
from pdf_to_hwpx.hwpx_kernel.styles import SOLID_THIN, CharSpec, ParaSpec

DEFAULT_OUT = REPO_ROOT / ".harness-tmp" / "probe"
CELL_MARGIN_TOTAL = 282  # cellMargin left+right (03 §3-3-5)


@dataclass(frozen=True)
class ProbeInfo:
    name: str
    filename: str
    purpose: str
    expect: str


@dataclass
class _Doc:
    ctx: DocContext
    page: PageSetup
    paragraphs: list[etree._Element]
    texts: list[str]


def _new_doc() -> _Doc:
    return _Doc(DocContext.new(), PageSetup.a4(), [], [])


def _text_paragraph(
    doc: _Doc,
    text: str,
    *,
    size_pt: float = 10.0,
    bold: bool = False,
    family: str = fonts.SANS,
    align: str = ALIGN_LEFT,
    left: int = 0,
    prev: int = 0,
    vertpos: int = 0,
    page_break: bool = False,
    lineseg: bool = True,
) -> etree._Element:
    height = pt_to_hwpunit(size_pt)
    char_id = doc.ctx.registry.char_pr(CharSpec(height=height, family=family, bold=bold))
    para_id = doc.ctx.registry.para_pr(ParaSpec(align=align, left=left, prev=prev))
    left_q = quantize(left, LEFT_QUANTUM)
    segs = None
    if lineseg:
        segs = [
            make_lineseg(
                vertpos=vertpos, vertsize=height, horzpos=left_q, horzsize=doc.page.text_width - left_q
            )
        ]
    para = make_paragraph(
        para_pr_id=para_id, runs=[make_run(char_id, text)], linesegs=segs, page_break=page_break
    )
    doc.paragraphs.append(para)
    doc.texts.append(text)
    return para


def _package(doc: _Doc, version: VersionInfo) -> bytes:
    pkg = HwpxPackage(PackageMeta(version=version))
    pkg.set_header(doc.ctx.build_header(1))
    pkg.add_section(build_section_xml(doc.paragraphs, doc.page))
    pkg.set_preview_text(format_preview_text(doc.texts))
    return pkg.to_bytes()


# ---- 프로브 정의 ---------------------------------------------------------------------


def _p1a() -> bytes:
    return _package(_new_doc(), VERSION_R1_OBSERVED)


def _p1b() -> bytes:
    return _package(_new_doc(), VERSION_OWN)


def _p2() -> bytes:
    doc = _new_doc()
    _text_paragraph(doc, "P2-1 보통 글자 10pt 돋움")
    _text_paragraph(doc, "P2-2 굵은 글자 10pt", bold=True)
    _text_paragraph(doc, "P2-3 큰 글자 20pt", size_pt=20)
    _text_paragraph(doc, "P2-4 가운데 정렬", align=ALIGN_CENTER)
    _text_paragraph(doc, "P2-5 왼쪽 들여쓰기 20pt", left=2000)
    _text_paragraph(doc, "P2-6 바탕 계열 글꼴", family=fonts.SERIF)
    _text_paragraph(doc, "P2-7 돋움체 계열 글꼴 ABC abc 123", family=fonts.MONO)
    return _package(doc, VERSION_R1_OBSERVED)


def _table_paragraph(doc: _Doc, grid: Sequence[Sequence[tuple[int, int, str] | None]], row_h: int) -> None:
    """grid[r][c] = (colSpan, rowSpan, text) 시작 셀 또는 None(병합으로 덮임)."""
    ctx = doc.ctx
    row_cnt, col_cnt = len(grid), len(grid[0])
    total_w = doc.page.text_width
    col_w = [total_w // col_cnt] * col_cnt
    col_w[-1] += total_w - sum(col_w)  # 마지막 열이 나머지를 흡수: 첫 행 폭 합 = sz.width (분석서 §7)
    border_id = ctx.registry.border_fill(SOLID_THIN)
    char_id = ctx.registry.char_pr(CharSpec())
    para_id = ctx.registry.para_pr(ParaSpec())
    rows = []
    for r, row in enumerate(grid):
        tcs = []
        for c, cell in enumerate(row):
            if cell is None:
                continue
            col_span, row_span, text = cell
            width = sum(col_w[c : c + col_span])
            seg = make_lineseg(vertpos=0, vertsize=1000, horzpos=0, horzsize=width - CELL_MARGIN_TOTAL)
            para = make_paragraph(para_pr_id=para_id, runs=[make_run(char_id, text)], linesegs=[seg])
            tcs.append(
                make_table_cell(
                    col=c, row=r, col_span=col_span, row_span=row_span, width=width,
                    height=row_h * row_span, border_fill_id=border_id, paragraphs=[para],
                )
            )
            doc.texts.append(text)
        rows.append(tcs)
    tbl_id, z_order = ctx.ids.next_table()
    height = row_h * row_cnt
    tbl = make_table(
        tbl_id=tbl_id, z_order=z_order, rows=rows, row_cnt=row_cnt, col_cnt=col_cnt,
        width=total_w, height=height, border_fill_id=border_id,
    )
    seg = make_lineseg(vertpos=0, vertsize=height, horzpos=0, horzsize=total_w)
    doc.paragraphs.append(
        make_paragraph(para_pr_id=para_id, runs=[make_run(char_id, children=[tbl])], linesegs=[seg])
    )


def _p3() -> bytes:
    doc = _new_doc()
    _text_paragraph(doc, "P3 표 확인: 아래 2x2 표와 병합 표가 보여야 합니다.")
    _table_paragraph(doc, [[(1, 1, "가"), (1, 1, "나")], [(1, 1, "다"), (1, 1, "라")]], MIN_ROW_HEIGHT + 400)
    _text_paragraph(doc, "P3 아래는 가로 병합(첫 행 3칸 병합, 셋째 행 2칸 병합) 표입니다.", prev=1000)
    _table_paragraph(
        doc,
        [
            [(3, 1, "가로 병합 3칸"), None, None],
            [(1, 1, "A"), (1, 1, "B"), (1, 1, "C")],
            [(2, 1, "가로 병합 2칸"), None, (1, 1, "D")],
        ],
        MIN_ROW_HEIGHT + 400,
    )
    _text_paragraph(doc, "P3 끝.", prev=1000)
    return _package(doc, VERSION_R1_OBSERVED)


_LINE_PT = 12.0
_PREV = 300  # 3pt 문단 앞 간격 (양자화 단위 100의 배수)


def _p4(*, mode: str, lineseg: bool) -> bytes:
    """mode='forced': 30문단 + pageBreak=1 + 30문단. mode='natural': 쪽 넘김 표시 없이 100문단."""
    doc = _new_doc()
    height = pt_to_hwpunit(_LINE_PT)
    step = height + _PREV
    count = 60 if mode == "forced" else 100
    y = 0
    for i in range(count):
        forced_break = mode == "forced" and i == 30
        if forced_break or (mode == "natural" and y + step > doc.page.text_height):
            y = 0
        _text_paragraph(
            doc,
            f"P4 {i + 1}번째 문단. 문단 앞 간격 3pt.",
            size_pt=_LINE_PT,
            prev=_PREV,
            vertpos=y + _PREV,
            page_break=forced_break,
            lineseg=lineseg,
        )
        y += step
    return _package(doc, VERSION_R1_OBSERVED)


PROBES: dict[str, tuple[ProbeInfo, Callable[[], bytes]]] = {
    "P1a": (
        ProbeInfo(
            "P1a", "P1a_empty_r1version.hwpx",
            "빈 문서(문단 1개). 초집합 패키지·header·section 수용 여부. version.xml은 한글이 저장한 값과 동일.",
            "문서로 열리고 빈 페이지 1개가 보인다. 복구/손상 경고가 없다. 다른 이름으로 저장이 된다.",
        ),
        _p1a,
    ),
    "P1b": (
        ProbeInfo(
            "P1b", "P1b_empty_ownversion.hwpx",
            "P1a와 같은 내용, version.xml의 application/appVersion만 자체 값(pdf-to-hwpx). 실험 E-V.",
            "P1a와 동일. P1a는 열리는데 P1b만 안 열리면 한글이 생성기 이름을 검사한다는 뜻이다(질문 Q4로 이어짐).",
        ),
        _p1b,
    ),
    "P2": (
        ProbeInfo(
            "P2", "P2_char_para_style.hwpx",
            "글자/문단 서식 동적 생성(charPr/paraPr): 굵게, 20pt, 가운데 정렬, 들여쓰기, 바탕/돋움체 계열.",
            "문단 7개가 서식대로 보인다: 1 보통 10pt / 2 굵게 / 3 20pt 큰 글자 / 4 가운데 / 5 왼쪽 들여쓰기 / 6 바탕체 느낌 / 7 고정폭 느낌.",
        ),
        _p2,
    ),
    "P3": (
        ProbeInfo(
            "P3", "P3_tables.hwpx",
            "표 구조와 borderFill: 2x2 표, 가로 병합 표(첫 행 3칸 병합, 셋째 행 2칸 병합), 사방 실선.",
            "표 2개가 사방 실선으로 보이고, 셀 글자가 그대로 보이며, 병합 셀이 한 칸으로 합쳐져 보인다. 표 셀을 클릭해 편집할 수 있다.",
        ),
        _p3,
    ),
    "P4a": (
        ProbeInfo(
            "P4a", "P4a_2pages_lineseg.hwpx",
            "2쪽 분량(강제 쪽 나눔 pageBreak=1) + 문단 앞 간격(prev 3pt) + linesegarray 있음. 실험 E-B, E-L.",
            "정확히 2쪽이고 둘째 쪽이 31번째 문단부터 시작한다. 문단 사이 간격이 일정하고 겹치거나 한 줄로 뭉치지 않는다.",
        ),
        lambda: _p4(mode="forced", lineseg=True),
    ),
    "P4b": (
        ProbeInfo(
            "P4b", "P4b_2pages_nolineseg.hwpx",
            "P4a와 같은 내용, linesegarray 전부 생략. 한글이 열 때 줄 배치를 다시 계산하는지 확인(E-L).",
            "P4a와 똑같이 보이면 linesegarray를 생략해도 된다. 열리지 않거나 배치가 깨지면 linesegarray가 필요하다는 뜻이다.",
        ),
        lambda: _p4(mode="forced", lineseg=False),
    ),
    "P4c": (
        ProbeInfo(
            "P4c", "P4c_natural_pagebreak.hwpx",
            "(추가 진단용) 강제 쪽 나눔 없이 100문단 자연 넘김 + linesegarray 있음. pageBreak=1의 영향을 분리해 본다.",
            "여러 쪽으로 자연스럽게 넘어간다(문단이 쪽 경계에서 잘리거나 겹치지 않는다).",
        ),
        lambda: _p4(mode="natural", lineseg=True),
    ),
}


def guide_text(names: Sequence[str]) -> str:
    lines = [
        "HWPX 프로브 확인 안내 (게이트 G1)",
        "=" * 50,
        "각 파일을 한컴오피스 한글에서 열어 아래 양식으로 기록해 주세요.",
        "  파일명 / 한글 버전(도움말 > 한글 정보) /",
        "  (1) 문서로 인식되어 열리는가(예/아니오, 아니오면 무엇이 보이는가) /",
        "  (2) 경고·복구 대화상자 여부(문구를 그대로) /",
        "  (3) 내용 표시가 아래 기대와 일치하는가 /",
        "  (4) 다른 이름으로 저장이 되는가",
        "",
        "순서 권장: P1a -> P1b -> P2 -> P3 -> P4a -> P4b -> P4c. P1a가 안 열리면 나머지는 보지 않아도 됩니다.",
        "P2~P4는 변수를 줄이려고 version.xml을 P1a와 같은 값으로 만들었습니다.",
        "",
    ]
    for name in names:
        info = PROBES[name][0]
        lines += [f"[{info.name}] {info.filename}", f"  내용: {info.purpose}", f"  기대: {info.expect}", ""]
    return "\n".join(lines)


def build_probes(out_dir: Path, names: Sequence[str] | None = None) -> dict[str, Path]:
    selected = list(names) if names else list(PROBES)
    unknown = [n for n in selected if n not in PROBES]
    if unknown:
        raise ValueError(f"알 수 없는 프로브: {unknown}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name in selected:
        info, build = PROBES[name]
        path = out_dir / info.filename
        path.write_bytes(build())
        written[name] = path
    (out_dir / "README-probe.txt").write_text(guide_text(selected), encoding="utf-8")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="출력 디렉터리 (기본: .harness-tmp/probe)")
    parser.add_argument("--only", default="", help="쉼표로 구분한 프로브 이름 (예: P1a,P2)")
    args = parser.parse_args(argv)
    names = [n.strip() for n in args.only.split(",") if n.strip()] or None
    try:
        written = build_probes(args.out, names)
    except ValueError as exc:
        parser.error(str(exc))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for name, path in written.items():
        print(f"{name}: {path}")
    print()
    print(guide_text(list(written)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
