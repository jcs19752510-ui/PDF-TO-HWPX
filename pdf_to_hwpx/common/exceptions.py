"""공통 예외 계층 (docs/harness/03-system-design.md §4-2).

orchestrator(core/orchestrator.py, unit-8)가 이 계층의 예외를 항상 잡아
``ConversionResult.errors``로 변환한다. 이 계층 밖의 예상 못한 예외는
orchestrator 최상위 ``except Exception``에서 ``INTERNAL_ERROR``로 변환되며
(03 §4-2), 그 catch-all 자체는 이 모듈의 책임이 아니다.

계층 구조 (03 §4-2 원문 그대로):

    ConversionError
    +-- PdfLoadError
    |   +-- EncryptedPdfError
    |   +-- CorruptedPdfError
    |   `-- EmptyPdfError
    +-- HwpxWriteError
    |   +-- ContainerBuildError
    |   `-- OutputPathError
    `-- OcrEngineError
        `-- TesseractNotFoundError
"""

from __future__ import annotations


class ConversionError(Exception):
    """모든 변환 관련 예외의 기반 클래스."""


class PdfLoadError(ConversionError):
    """PDF를 읽어 들이는 단계(pdf_reader.loader)에서 발생하는 예외의 기반 클래스."""


class EncryptedPdfError(PdfLoadError):
    """비밀번호로 보호된 PDF — 지원하지 않는다.

    사용자 메시지(04 §2 G-4): "비밀번호로 보호된 PDF는 지원하지 않습니다."
    """


class CorruptedPdfError(PdfLoadError):
    """PDF 파싱 자체가 실패한 경우(구조 손상, 잘못된 형식 등).

    사용자 메시지(04 §2 G-4): "PDF 파일을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다."
    """


class EmptyPdfError(PdfLoadError):
    """페이지가 0개인 PDF.

    사용자 메시지(04 §2 G-4): "빈 PDF 파일입니다."
    """


class HwpxWriteError(ConversionError):
    """HWPX 파일을 쓰는 단계(hwpx_kernel/hwpx_writer)에서 발생하는 예외의 기반 클래스."""


class ContainerBuildError(HwpxWriteError):
    """HWPX zip 컨테이너 골격 생성 실패(예: 디스크 공간 부족).

    사용자 메시지(04 §2 G-4): "HWPX 파일을 생성할 수 없습니다. 디스크 여유 공간을
    확인하고 다시 시도해주세요."
    """


class OutputPathError(HwpxWriteError):
    """출력 경로 문제.

    - 출력 파일이 이미 존재하는데 ``overwrite_existing=False``인 경우
    - 출력 디렉터리에 쓰기 권한이 없는 경우

    사용자 메시지(04 §2 G-4)는 두 경우가 서로 달라, orchestrator(unit-8)가
    상황에 맞는 문구를 선택해 매핑한다.
    """


class OcrEngineError(ConversionError):
    """OCR 엔진(pdf_reader/ocr_engine.py, unit-12) 관련 예외의 기반 클래스."""


class TesseractNotFoundError(OcrEngineError):
    """Tesseract 바이너리를 찾을 수 없는 경우(정상 배포판은 바이너리 동봉이 원칙, DEC-013).

    사용자 메시지(04 §2 G-4): "OCR 엔진을 찾을 수 없습니다. 프로그램을 재설치하거나
    문의해주세요."
    """
