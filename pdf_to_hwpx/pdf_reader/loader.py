"""PDF 로더 (docs/harness/03-system-design.md §1-3 unit-0, §1-2 컴포넌트 다이어그램).

이 모듈의 책임은 "열기 + 페이지수 확인 + 암호화 감지"까지다. 실제 텍스트/
이미지/표 파싱은 이 모듈의 범위가 아니다(각각 unit-1/2/3의 책임, 03 §1-2
"PDF 판독 계열" 다이어그램 참고).

반환값인 :class:`PdfDocument` 는 03 §1-3 표가 명시한 "unit-0의 PdfDocument
객체(읽기 전용 소비)"에 해당하며, unit-1(text_extractor)·unit-3
(table_recognizer)는 ``plumber_pdf``를, unit-2(image_extractor)는
``pypdf_reader``를 각자 읽기 전용으로 소비한다(03 §2-1: pdfplumber=텍스트/표,
pypdf=원본 이미지 바이트).

IR(``PageIR`` 등, 03 §3-1)은 이 모듈의 소관이 아니다 — 이 로더는 파싱 이전
단계(문서를 여는 단계)만 담당하므로 IR 데이터클래스는 이 파일에 두지 않는다.
IR을 실제로 생성하는 것은 unit-1/2/3이며, IR<->XML 변환 계약(``hwpx_kernel/
schema.py``)은 unit-4 소관이라 unit-0은 그 파일을 건드리지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pdfplumber
import pypdf

from pdf_to_hwpx.common.exceptions import CorruptedPdfError, EmptyPdfError, EncryptedPdfError


@dataclass
class PdfDocument:
    """열려 있는 PDF에 대한 읽기 전용 핸들 묶음.

    Attributes:
        path: 원본 PDF 파일 경로.
        page_count: 페이지 수(이미 0페이지가 아님이 검증된 상태, 즉 >= 1).
        plumber_pdf: 텍스트/표 추출용(unit-1/unit-3이 소비, 03 §2-1 pdfplumber).
        pypdf_reader: 원본 이미지 바이트 추출용(unit-2가 소비, 03 §2-1 pypdf).
    """

    path: Path
    page_count: int
    plumber_pdf: pdfplumber.PDF
    pypdf_reader: pypdf.PdfReader
    _stream: BinaryIO

    def close(self) -> None:
        """내부적으로 열어 둔 파일 핸들과 파서 리소스를 모두 해제한다."""
        try:
            self.plumber_pdf.close()
        finally:
            if not self._stream.closed:
                self._stream.close()

    def __enter__(self) -> "PdfDocument":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def load_pdf(path: Path) -> PdfDocument:
    """PDF 파일을 열고 기본 유효성(암호화 여부, 페이지 수)을 검증한다.

    시스템 경계(사용자가 지정한 임의의 파일)에서 들어오는 값이므로, 아래
    엣지 케이스를 03 §4-2가 정의한 예외로 변환해 던진다:

    - 암호화된 PDF -> :class:`EncryptedPdfError`
    - 파일을 열거나 파싱할 수 없음(없는 파일/권한 문제/손상된 구조 포함)
      -> :class:`CorruptedPdfError`
    - 0페이지 PDF -> :class:`EmptyPdfError`

    Args:
        path: 열어야 할 PDF 파일 경로.

    Returns:
        검증을 통과한 :class:`PdfDocument`. 호출자가 사용이 끝나면
        :meth:`PdfDocument.close` (또는 ``with`` 구문)로 반드시 해제해야 한다.
    """
    try:
        stream = path.open("rb")
    except OSError as exc:
        raise CorruptedPdfError(f"PDF 파일을 열 수 없습니다: {exc}") from exc

    try:
        try:
            reader = pypdf.PdfReader(stream)
        except Exception as exc:  # pypdf가 던지는 예외 유형이 버전마다 다양함
            raise CorruptedPdfError(f"PDF 구조를 읽을 수 없습니다: {exc}") from exc

        if reader.is_encrypted:
            raise EncryptedPdfError("비밀번호로 보호된 PDF는 지원하지 않습니다.")

        try:
            page_count = len(reader.pages)
        except Exception as exc:
            raise CorruptedPdfError(f"PDF 페이지 목록을 읽을 수 없습니다: {exc}") from exc

        if page_count == 0:
            raise EmptyPdfError("빈 PDF 파일입니다.")

        try:
            plumber_pdf = pdfplumber.open(str(path))
        except Exception as exc:
            raise CorruptedPdfError(f"PDF를 파싱할 수 없습니다: {exc}") from exc

        return PdfDocument(
            path=path,
            page_count=page_count,
            plumber_pdf=plumber_pdf,
            pypdf_reader=reader,
            _stream=stream,
        )
    except Exception:
        stream.close()
        raise
