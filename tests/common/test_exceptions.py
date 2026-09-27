"""unit-0 AC-1 — `pdf_to_hwpx/common/exceptions.py` 예외 계층 검증.

근거: docs/harness/03-system-design.md §4-2(예외 계층), unit-0-note.md AC-1.
"""

from __future__ import annotations

import pytest

from pdf_to_hwpx.common.exceptions import (
    ContainerBuildError,
    ConversionError,
    CorruptedPdfError,
    EmptyPdfError,
    EncryptedPdfError,
    HwpxWriteError,
    OcrEngineError,
    OutputPathError,
    PdfLoadError,
    TesseractNotFoundError,
)


# AC-1-1: ConversionError, PdfLoadError, HwpxWriteError, OcrEngineError가
# 모두 ConversionError(또는 그 하위)를 상속하는 계층으로 존재.
@pytest.mark.parametrize(
    "exc_class",
    [ConversionError, PdfLoadError, HwpxWriteError, OcrEngineError],
)
def test_top_level_classes_inherit_conversion_error(exc_class):
    assert issubclass(exc_class, ConversionError)


# AC-1-2: EncryptedPdfError, CorruptedPdfError, EmptyPdfError가 PdfLoadError의 하위 클래스.
@pytest.mark.parametrize(
    "exc_class",
    [EncryptedPdfError, CorruptedPdfError, EmptyPdfError],
)
def test_pdf_load_error_subclasses(exc_class):
    assert issubclass(exc_class, PdfLoadError)
    assert issubclass(exc_class, ConversionError)


# AC-1-3: ContainerBuildError, OutputPathError가 HwpxWriteError의 하위 클래스.
@pytest.mark.parametrize(
    "exc_class",
    [ContainerBuildError, OutputPathError],
)
def test_hwpx_write_error_subclasses(exc_class):
    assert issubclass(exc_class, HwpxWriteError)
    assert issubclass(exc_class, ConversionError)


# AC-1-4: TesseractNotFoundError가 OcrEngineError의 하위 클래스.
def test_tesseract_not_found_error_subclass():
    assert issubclass(TesseractNotFoundError, OcrEngineError)
    assert issubclass(TesseractNotFoundError, ConversionError)


# AC-1-5: 모든 클래스가 Exception처럼 메시지 문자열 1개를 받아 생성 가능.
@pytest.mark.parametrize(
    "exc_class",
    [
        ConversionError,
        PdfLoadError,
        EncryptedPdfError,
        CorruptedPdfError,
        EmptyPdfError,
        HwpxWriteError,
        ContainerBuildError,
        OutputPathError,
        OcrEngineError,
        TesseractNotFoundError,
    ],
)
def test_all_classes_constructible_with_message(exc_class):
    message = "테스트 메시지"
    with pytest.raises(exc_class) as excinfo:
        raise exc_class(message)
    assert str(excinfo.value) == message
    assert isinstance(excinfo.value, Exception)


def test_exception_hierarchy_has_exactly_nine_classes_plus_base():
    """설계서(03 §4-2)가 명시한 9개 리프/중간 클래스 + 기반 1개 = 10개 전부 존재.

    (기반 3 + 리프 6 = unit-0-note.md 1-2절 "총 9개 클래스" + ConversionError 기반 자체)
    """
    all_classes = {
        ConversionError,
        PdfLoadError,
        EncryptedPdfError,
        CorruptedPdfError,
        EmptyPdfError,
        HwpxWriteError,
        ContainerBuildError,
        OutputPathError,
        OcrEngineError,
        TesseractNotFoundError,
    }
    assert len(all_classes) == 10
