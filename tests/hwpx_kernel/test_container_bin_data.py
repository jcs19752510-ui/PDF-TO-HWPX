"""DocContext와 그림(BinData) 미지원 경로 (T1).

이 파일명은 이전 unit-4의 BinData 삽입 테스트를 전면 교체한 것이다. 그림/BinData는
04_그림.hwpx 관찰 전이라 unit-4R에서 구현하지 않으므로(unit-4P), 여기서는 (1) 구현하지 않았음을
보장하고 (2) 호출자가 쓸 경고 집계 경로와 DocContext 계약을 검증한다.
"""

from __future__ import annotations

import pytest

from pdf_to_hwpx.hwpx_kernel import container, schema
from pdf_to_hwpx.hwpx_kernel.context import DocContext, IdAllocator


def test_picture_and_bindata_api_not_implemented_yet():
    assert not hasattr(schema, "make_pic")
    assert not hasattr(container.HwpxPackage, "add_bin_data")


def test_unsupported_elements_are_counted_not_emitted(ctx):
    ctx.note_unsupported("picture")
    ctx.note_unsupported("picture")
    ctx.note_unsupported("italic")
    assert dict(ctx.unsupported) == {"picture": 2, "italic": 1}


def test_doc_context_new_gives_independent_state():
    first, second = DocContext.new(), DocContext.new()
    first.note_unsupported("x")
    assert not second.unsupported
    assert first.registry is not second.registry


def test_table_ids_sequential_positive_32bit_and_z_order_from_zero(ctx):
    got = [ctx.ids.next_table() for _ in range(3)]
    assert [z for _, z in got] == [0, 1, 2]
    ids = [i for i, _ in got]
    assert ids == sorted(set(ids))
    assert all(0 < i < 2**32 for i in ids)


def test_table_id_overflow_is_an_error():
    alloc = IdAllocator(_next_tbl_id=2**32)
    with pytest.raises(OverflowError):
        alloc.next_table()


def test_build_header_delegates_to_registry(ctx):
    data = ctx.build_header(3)
    assert b'secCnt="3"' in data
