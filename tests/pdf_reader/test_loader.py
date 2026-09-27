"""unit-0 AC-3 — `pdf_to_hwpx/pdf_reader/loader.py` 검증.

근거: docs/harness/03-system-design.md §1-3(unit-0 파일 범위), §4-2(엣지케이스
표), unit-0-note.md AC-3. PDF 픽스처는 `tests/conftest.py`의 `pdf_fixtures`가
`.harness-tmp/pdf_fixtures_06_unit0/`에 즉석 생성한다(정상/0페이지/암호화/손상
전부 mock이 아닌 실제 PDF 바이트).
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pypdf
import pytest

from pdf_to_hwpx.common.exceptions import CorruptedPdfError, EmptyPdfError, EncryptedPdfError
from pdf_to_hwpx.pdf_reader.loader import PdfDocument, load_pdf


# AC-3-1: 정상적인 1페이지 이상 PDF에 대해 load_pdf가 예외 없이 PdfDocument를
# 반환하고, page_count가 실제 페이지 수와 일치한다.
@pytest.mark.parametrize(
    "fixture_key, expected_pages",
    [
        ("normal_1page", 1),
        ("normal_3page", 3),
        ("normal_20page", 20),  # 경계값: 다수 페이지에서도 카운트가 정확한지
    ],
)
def test_load_pdf_normal_returns_correct_page_count(pdf_fixtures, fixture_key, expected_pages):
    doc = load_pdf(pdf_fixtures[fixture_key])
    try:
        assert isinstance(doc, PdfDocument)
        assert doc.page_count == expected_pages
    finally:
        doc.close()


# AC-3-2: PdfDocument.plumber_pdf가 pdfplumber.PDF 인스턴스,
# PdfDocument.pypdf_reader가 pypdf.PdfReader 인스턴스다.
def test_load_pdf_returns_correct_handle_types(pdf_fixtures):
    doc = load_pdf(pdf_fixtures["normal_1page"])
    try:
        assert isinstance(doc.plumber_pdf, pdfplumber.PDF)
        assert isinstance(doc.pypdf_reader, pypdf.PdfReader)
        assert doc.path == pdf_fixtures["normal_1page"]
    finally:
        doc.close()


# AC-3-3: 사용자/소유자 비밀번호가 걸린 PDF에 대해 load_pdf가 EncryptedPdfError를 던진다.
def test_load_pdf_encrypted_raises_encrypted_pdf_error(pdf_fixtures):
    with pytest.raises(EncryptedPdfError):
        load_pdf(pdf_fixtures["encrypted"])


# AC-3-4: 페이지가 0개인 PDF에 대해 load_pdf가 EmptyPdfError를 던진다.
def test_load_pdf_zero_pages_raises_empty_pdf_error(pdf_fixtures):
    with pytest.raises(EmptyPdfError):
        load_pdf(pdf_fixtures["empty_0page"])


# AC-3-5: 유효한 PDF 헤더가 없는(또는 구조가 완전히 깨진) 바이트로 구성된
# 파일에 대해 load_pdf가 CorruptedPdfError를 던진다. (두 변형 모두 확인)
def test_load_pdf_no_header_raises_corrupted_pdf_error(pdf_fixtures):
    with pytest.raises(CorruptedPdfError):
        load_pdf(pdf_fixtures["corrupted_no_header"])


def test_load_pdf_truncated_structure_raises_corrupted_pdf_error(pdf_fixtures):
    with pytest.raises(CorruptedPdfError):
        load_pdf(pdf_fixtures["corrupted_truncated"])


def test_load_pdf_zero_byte_file_raises_corrupted_pdf_error(pdf_fixtures):
    """내부검증 2차에서 추가된 경계값: 0바이트 파일은 "0페이지 PDF"(AC-3-4,
    구조는 유효하나 페이지가 없음)와 별개의 케이스다 — 헤더 자체를 파싱할
    대상이 없으므로 EmptyPdfError가 아니라 CorruptedPdfError여야 한다."""
    assert pdf_fixtures["zero_byte"].stat().st_size == 0
    with pytest.raises(CorruptedPdfError):
        load_pdf(pdf_fixtures["zero_byte"])


def test_load_pdf_corrupted_page_tree_raises_corrupted_pdf_error(pdf_fixtures):
    """추가 경계 케이스: pypdf.PdfReader() 생성 자체는 성공하지만
    len(reader.pages) 순회에서 실패하는 경우도 CorruptedPdfError로 변환되어야
    한다(loader.py의 별도 방어 분기, 03 §4-2 "파일을 열 수 없음" 포괄 해석)."""
    with pytest.raises(CorruptedPdfError):
        load_pdf(pdf_fixtures["corrupted_page_tree"])


# AC-3-6: 존재하지 않는 경로에 대해 load_pdf가 CorruptedPdfError를 던진다.
def test_load_pdf_nonexistent_path_raises_corrupted_pdf_error(pdf_fixtures):
    assert not pdf_fixtures["nonexistent"].exists()
    with pytest.raises(CorruptedPdfError):
        load_pdf(pdf_fixtures["nonexistent"])


def test_load_pdf_nonexistent_path_deep_missing_directory(tmp_path: Path):
    """경계값: 파일뿐 아니라 상위 디렉터리 자체가 없는 경로도 동일하게 처리."""
    missing = tmp_path / "no" / "such" / "dir" / "x.pdf"
    with pytest.raises(CorruptedPdfError):
        load_pdf(missing)


# AC-3-7: PdfDocument.close() 호출 후 내부 파일 스트림이 닫힌 상태가 된다.
def test_close_marks_internal_stream_closed(pdf_fixtures):
    doc = load_pdf(pdf_fixtures["normal_1page"])
    assert not doc._stream.closed
    doc.close()
    assert doc._stream.closed is True


# AC-3-8: with load_pdf(path) as doc: 구문이 정상 동작하고, 블록 종료 시
# 자동으로 리소스가 해제된다.
def test_context_manager_closes_resources_on_exit(pdf_fixtures):
    with load_pdf(pdf_fixtures["normal_1page"]) as doc:
        assert isinstance(doc, PdfDocument)
        assert doc.page_count == 1
        stream_ref = doc._stream
        assert not stream_ref.closed

    assert stream_ref.closed is True


def test_context_manager_closes_resources_even_on_exception_inside_block(pdf_fixtures):
    """경계값: with 블록 내부에서 예외가 나도 __exit__이 호출되어 리소스가 해제된다."""
    stream_ref = None
    with pytest.raises(ValueError):
        with load_pdf(pdf_fixtures["normal_1page"]) as doc:
            stream_ref = doc._stream
            raise ValueError("블록 내부 임의 예외")

    assert stream_ref is not None
    assert stream_ref.closed is True


# AC-3-9: 예외가 발생해 load_pdf가 중간에 실패하는 경로(암호화/0페이지/손상)에서도
# 내부적으로 연 파일 스트림이 누수 없이 닫힌다.
@pytest.mark.parametrize(
    "fixture_key, expected_exc",
    [
        ("encrypted", EncryptedPdfError),
        ("empty_0page", EmptyPdfError),
        ("corrupted_no_header", CorruptedPdfError),
        ("corrupted_truncated", CorruptedPdfError),
        ("corrupted_page_tree", CorruptedPdfError),
    ],
)
def test_no_stream_leak_on_failure_paths(pdf_fixtures, monkeypatch, fixture_key, expected_exc):
    opened_streams = []
    original_open = Path.open

    def spy_open(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        opened_streams.append(stream)
        return stream

    monkeypatch.setattr(Path, "open", spy_open)

    with pytest.raises(expected_exc):
        load_pdf(pdf_fixtures[fixture_key])

    assert opened_streams, "load_pdf가 Path.open을 전혀 호출하지 않았다(픽스처 문제 가능성)"
    assert all(s.closed for s in opened_streams), (
        f"{fixture_key} 실패 경로에서 파일 스트림이 닫히지 않고 누수됨"
    )


def test_no_stream_leak_on_failure_path_resource_warning_free(pdf_fixtures):
    """추가 확인: ResourceWarning이 error로 승격된 상태에서도 경고 없이 종료되는지
    (AC-3-9가 권고한 -W error::ResourceWarning 방식의 보완 확인)."""
    import gc
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        with pytest.raises(EncryptedPdfError):
            load_pdf(pdf_fixtures["encrypted"])
        gc.collect()
