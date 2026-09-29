"""뮤턴트 검증: 검증기 소스의 검사 조건을 하나씩 무력화하면 대응하는 음성 사례가 잡히지 않아야 한다(=사례가 그 검사를 실제로 시험한다).

각 뮤턴트는 validator.py의 조건식 하나를 `False`(또는 빈 집합)로 바꾼다. '죽은' 뮤턴트 = 대응 사례에서
(a) 예외가 나거나 (b) 기대 위반 코드가 사라진다. 살아남은 뮤턴트(코드 변경 후에도 사례가 그대로 통과)가 있으면
그 검사는 테스트로 보호되지 않는 것이다.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

from .cases import CASES
from .synth import build

ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = ROOT / "pdf_to_hwpx" / "hwpx_kernel" / "validator.py"
CASE_BY_ID = {c[0]: c for c in CASES}

# (뮤턴트 id, 원본 조각, 대체 조각, 죽여야 할 사례 id들)
MUTANTS: list[tuple[str, str, str, list[str]]] = [
    ("V1.mimetype_compressed", "if mt.compress_type != zipfile.ZIP_STORED:", "if False:", ["mimetype_compressed"]),
    ("V1.mimetype_order", 'if files[0].filename != "mimetype":', "if False:", ["mimetype_not_first"]),
    ("V1.mimetype_content", "if zf.read(mt) != prof.mimetype:", "if False:", ["mimetype_trailing_newline"]),
    ("V1.mimetype_extra", "if mt.extra:", "if False:", ["mimetype_extra_field"]),
    ("V1.duplicate", '        if n > 1:\n            run.emit("V1.DUPLICATE"', '        if False:\n            run.emit("V1.DUPLICATE"', ["duplicate_entry"]),
    ("V1.path", 'if name.startswith("/") or "\\\\" in name or ".." in parts or ":" in parts[0] or "" in parts:', "if False:", ["path_traversal"]),
    ("V2.unknown_part", 'run.emit("V2.UNKNOWN_PART", name, "프로파일에 없는 파트다")', "pass", ["unknown_part"]),
    ("V2.part_missing", 'if meta.get("required") and meta["role"] != "mimetype" and pat not in present:', "if False:", ["part_missing_container", "part_missing_version"]),
    ("V2.section_gap", "if idx and idx != list(range(len(idx))):", "if False:", ["section_gap"]),
    ("V3.prolog", 'if not raw.startswith(prof.prolog) or raw[len(prof.prolog):len(prof.prolog) + 1] != b"<":', "if False:", ["prolog_lxml_default", "bom"]),
    ("V3.doctype", "if root.getroottree().docinfo.doctype:", "if False:", ["doctype"]),
    ("V3.root", 'if root_name != meta.get("root"):', "if False:", ["wrong_root"]),
    ("V3.ns_mismatch", "elif declared[prefix] != uri:", "elif False:", ["ns_container_uri_wrong"]),
    ("V3.ns_missing", "if prefix not in declared:", "if False:", ["ns_declaration_missing"]),
    ("V3.ns_unknown", "if (name, uri) not in run._unknown_ns_seen:", "if False:", ["ns_foreign_element"]),
    ("V3.png", 'elif role == "prvimage" and not raw.startswith(_PNG_MAGIC):', "elif False:", ["prvimage_not_png"]),
    ("V3.prvtext_lf", 'if re.search(r"(?<!\\r)\\n", text):', "if False:", ["prvtext_bare_lf"]),
    ("V4.attr", "if an is None or an not in rule.attrs:", "if False:", ["own_attrs_b0", "charShapeIDRef_rename"]),
    ("V4.element", 'run.emit("V4.ELEMENT", name, f"프로파일에 없는 요소 {cname}", el)', "pass", ["header_minimal_b0"]),
    ("V4.child", "if n is not None and n in prof.elements and n not in rule.children:", "if False:", ["t_directly_under_sec"]),
    ("V4.text", "if not rule.text and el.text and el.text.strip():", "if False:", ["text_in_run"]),
    ("V5.attr_missing", "for missing in sorted(rule.required_attrs - present_attrs):", "for missing in sorted(set()):", ["required_attr_missing", "charShapeIDRef_rename"]),
    ("V5.child_missing", "for req in sorted(rule.required_children - name_set):", "for req in sorted(set()):", ["required_child_missing_linesegarray", "p_without_run"]),
    ("V6.order", "if b in first and first[b] < last[a]:", "if False:", ["order_swapped_in_p"]),
    ("V6.sequence", 'if got != seq["values"]:', "if False:", ["fontface_sequence_swapped"]),
    ("V7.dangling", 'if iv not in docs.defs.get((ref["kind"], ref.get("group")), ()):', "if False:", ["dangling_run_charpr", "dangling_fontref", "dangling_outline_numbering"]),
    ("V7.dup_id", "if iv in bucket:", "if False:", ["dup_charpr_id"]),
    ("V7.dup_unique", "if v in docs.unique_seen[cname]:", "if False:", ["dup_tbl_id"]),
    ("V7.bad_id", '        if iv is None:\n            run.emit("V7.BAD_ID"', '        if False:\n            run.emit("V7.BAD_ID"', ["charpr_id_not_int"]),
    ("V8.count", "if iv is None or iv != expected:", "if False:", ["itemcnt_mismatch", "fontcnt_mismatch", "rowcnt_mismatch", "masterpagecnt_mismatch"]),
    ("V8.seccnt", "if iv is None or iv != n_sections:", "if False:", ["seccnt_mismatch"]),
    ("V9.enum", "if enum is not None and an not in rule.open_enums and val not in enum:", "if False:", ["enum_out_of_vocab"]),
    ("V10.overlap", "if grid[base + cc]:", "if False:", ["tbl_cells_overlap"]),
    ("V10.coverage", "if trs and 0 in grid:", "if False:", ["tbl_hole"]),
    ("V10.row_addr", "if row_a != r_idx:", "if False:", ["tbl_rowaddr_wrong"]),
    ("V10.out_of_grid", "if col_a < 0 or row_a < 0 or col_a + col_s > cols or row_a + row_s > rows:", "if False:", ["tbl_out_of_grid"]),
    ("V10.span", "if col_s < 1 or row_s < 1:", "if False:", ["tbl_span_zero"]),
    ("V10.width_sum", "abs(row0_width - tbl_w) > run.tol", "False", ["tbl_first_row_width_sum"]),
    ("V10.attr_int", "if rows is None or cols is None or rows < 1 or cols < 1:", "if False:", ["tbl_colcnt_not_int"]),
    ("V10.too_large", "if rows * cols > MAX_GRID_CELLS:", "if False:", ["tbl_grid_huge"]),
    ("V11.scale", "if ib != 2 * ia:", "if False:", ["switch_default_not_double"]),
    ("V11.equal", "                if ib != ia:", "                if False:", ["switch_percent_not_equal"]),
    ("V11.struct", "if [run.canon(e.tag) for e in a_els] != [run.canon(e.tag) for e in b_els]:", "if False:", ["switch_structure_differs"]),
    ("V12.secpr_count", "if len(secprs) != 1:", "if False:", ["secpr_absent_b0", "secpr_twice"]),
    ("V12.secpr_position", "if not ok:", "if False:", ["secpr_misplaced"]),
    ("V13.dup_item", '        if n > 1:\n            run.emit("V13.DUP_ITEM_ID"', '        if False:\n            run.emit("V13.DUP_ITEM_ID"', ["hpf_dup_item_id"]),
    ("V13.href", "if h not in data:", "if False:", ["hpf_href_dangling"]),
    ("V13.spine_idref", "if idref not in id_to_href:", "if False:", ["hpf_spine_idref_unknown"]),
    ("V13.manifest_missing", 'if meta.get("in_manifest") and name not in hrefs:', "if False:", ["hpf_section_not_in_manifest"]),
    ("V13.spine_missing", 'if meta.get("in_spine") and name not in spine_hrefs:', "if False:", ["hpf_section_not_in_spine"]),
]


@pytest.fixture(scope="module")
def source() -> str:
    return SRC_PATH.read_text(encoding="utf-8")


def _load_mutant(name: str, text: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    mod.__dict__["__file__"] = str(SRC_PATH)
    exec(compile(text, f"<mutant {name}>", "exec"), mod.__dict__)
    return mod


def test_mutant_ids_unique():
    ids = [m[0] for m in MUTANTS]
    assert len(ids) == len(set(ids))


def test_every_case_target_exists():
    for mid, _old, _new, cases in MUTANTS:
        for c in cases:
            assert c in CASE_BY_ID, f"{mid}: 없는 사례 {c}"


@pytest.mark.parametrize("mid,old,new,case_ids", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_mutant_is_killed(mid, old, new, case_ids, source, profile_raw, tmp_path):
    assert source.count(old) == 1, f"뮤턴트 대상 조각이 소스에서 정확히 1번 나오지 않는다: {mid}"
    mod = _load_mutant(f"hwpx_validator_mutant_{mid.replace('.', '_')}", source.replace(old, new, 1))
    for cid in case_ids:
        _cid, mutate, expected = CASE_BY_ID[cid]
        pkg = build(copy.deepcopy(profile_raw))
        mutate(pkg)
        path = pkg.write(tmp_path / f"{cid}.hwpx")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                found = {v.code for v in mod.validate_hwpx(path, copy.deepcopy(profile_raw))}
        except Exception:  # 뮤턴트가 사례에서 관측 가능하게 깨졌다(예외) = 죽은 것으로 인정
            continue
        assert not expected <= found, f"뮤턴트 {mid}가 살아남았다: 사례 {cid}가 여전히 기대 코드를 모두 받는다"
