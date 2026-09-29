"""pytest 공용 픽스처 — unit-0 테스트 전용 PDF 샘플 생성.

06단계(단위테스트) 규칙 K: 테스트용 임시 PDF 픽스처는 리포지토리 루트가 아니라
``.harness-tmp/`` 하위(``.harness-tmp/pdf_fixtures_06_unit0/``)에만 생성한다.
이 디렉터리는 프로젝트 표준 ``.gitignore``에 이미 포함되어 있다.

실제 PDF 픽스처가 필요해, mock 대신 ``pypdf``(0페이지/암호화 PDF 생성)와
``reportlab``(정상 텍스트 PDF 생성)로 즉석에서 만든다. ``reportlab``은
프로젝트의 런타임 의존성이 아니라 06단계 테스트 전용으로 격리된 venv
(``.harness-tmp/venv_06_unit0/``)에만 설치했다(테스트 결과서 3절 참고).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

import pypdf
import pytest
from reportlab.pdfgen import canvas

FIXTURE_DIR = Path(__file__).resolve().parent.parent / ".harness-tmp" / "pdf_fixtures_06_unit0"


def _make_text_pdf(path: Path, page_count: int) -> None:
    """reportlab으로 지정한 페이지 수만큼 텍스트가 있는 정상 PDF를 만든다."""
    c = canvas.Canvas(str(path))
    for i in range(page_count):
        c.drawString(72, 720, f"unit-0 테스트 픽스처 - {i + 1} 페이지")
        c.showPage()
    c.save()


def _make_empty_pdf(path: Path) -> None:
    """pypdf로 페이지가 0개인(구조는 유효한) PDF를 만든다."""
    writer = pypdf.PdfWriter()
    with path.open("wb") as f:
        writer.write(f)


def _make_encrypted_pdf(path: Path) -> None:
    """pypdf로 사용자 비밀번호가 걸린 1페이지 PDF를 만든다."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="unit0-test-secret", owner_password="unit0-test-owner")
    with path.open("wb") as f:
        writer.write(f)


def _make_corrupted_no_header_pdf(path: Path) -> None:
    """PDF 헤더(``%PDF-``)가 아예 없는 임의 바이트 파일을 만든다."""
    path.write_bytes(b"this is not a pdf file at all - unit-0 fixture" * 5)


def _make_zero_byte_file(path: Path) -> None:
    """내용이 전혀 없는(0바이트) 파일 — "0페이지 PDF"와는 다른 별개의 경계값.

    0페이지 PDF는 구조가 유효하지만 페이지가 없는 경우(EmptyPdfError)이고,
    이 픽스처는 PDF 헤더조차 파싱할 대상이 없는 완전히 빈 파일이다
    (내부 검증 2차에서 추가된 케이스 — verify-log_unit-0-test.md 참고).
    """
    path.write_bytes(b"")


def _make_corrupted_truncated_pdf(path: Path, source: Path) -> None:
    """유효한 PDF를 앞부분만 잘라내 구조(트레일러/xref)가 깨진 파일을 만든다."""
    data = source.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def _make_corrupted_page_tree_pdf(path: Path, source: Path) -> None:
    """``pypdf.PdfReader()`` 생성 자체는 성공하지만 페이지 목록 순회
    (``len(reader.pages)``)에서 실패하는 PDF를 만든다.

    loader.py의 "PDF 구조는 열리지만 페이지 목록을 못 읽는" 방어 분기
    (``except Exception: raise CorruptedPdfError`` around ``len(reader.pages)``)를
    실제로 트리거하기 위한 픽스처. ``/Pages`` 객체의 ``/Kids`` 값을 배열이
    아닌 값으로 바꿔 pypdf가 "Expected /Kids to be an array"로 실패하게 한다.
    """
    data = source.read_bytes()
    # reportlab이 매기는 객체 번호(예: "3 0 R")는 문서 내용에 따라 달라지므로
    # 고정 번호가 아니라 패턴으로 "/Kids [ <숫자> 0 R ]" 자체를 찾아 치환한다.
    patched, count = re.subn(rb"/Kids \[ \d+ 0 R \]", b"/Kids 42", data, count=1)
    if count == 0:
        raise RuntimeError(
            "corrupted_page_tree 픽스처 생성 실패: 원본 PDF에서 /Kids [ <n> 0 R ] "
            "패턴을 찾지 못함(reportlab 버전이 바뀌어 내부 PDF 구조가 달라졌을 수 있음)"
        )
    path.write_bytes(patched)


@pytest.fixture(scope="session")
def pdf_fixtures() -> Iterator[dict[str, Path]]:
    """unit-0 테스트 전체에서 재사용하는 PDF 샘플 경로 모음.

    세션 종료 시 스스로 만든 파일만 정리한다(규칙 K).
    """
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    normal_1page = FIXTURE_DIR / "normal_1page.pdf"
    _make_text_pdf(normal_1page, page_count=1)

    normal_3page = FIXTURE_DIR / "normal_3page.pdf"
    _make_text_pdf(normal_3page, page_count=3)

    normal_20page = FIXTURE_DIR / "normal_20page.pdf"
    _make_text_pdf(normal_20page, page_count=20)

    empty_0page = FIXTURE_DIR / "empty_0page.pdf"
    _make_empty_pdf(empty_0page)

    encrypted = FIXTURE_DIR / "encrypted.pdf"
    _make_encrypted_pdf(encrypted)

    corrupted_no_header = FIXTURE_DIR / "corrupted_no_header.pdf"
    _make_corrupted_no_header_pdf(corrupted_no_header)

    zero_byte = FIXTURE_DIR / "zero_byte.pdf"
    _make_zero_byte_file(zero_byte)

    corrupted_truncated = FIXTURE_DIR / "corrupted_truncated.pdf"
    _make_corrupted_truncated_pdf(corrupted_truncated, source=normal_3page)

    corrupted_page_tree = FIXTURE_DIR / "corrupted_page_tree.pdf"
    _make_corrupted_page_tree_pdf(corrupted_page_tree, source=normal_1page)

    nonexistent = FIXTURE_DIR / "does_not_exist_unit0.pdf"
    if nonexistent.exists():  # pragma: no cover - 방어적, 정상 흐름에서는 존재하지 않음
        nonexistent.unlink()

    paths = {
        "normal_1page": normal_1page,
        "normal_3page": normal_3page,
        "normal_20page": normal_20page,
        "empty_0page": empty_0page,
        "encrypted": encrypted,
        "corrupted_no_header": corrupted_no_header,
        "zero_byte": zero_byte,
        "corrupted_truncated": corrupted_truncated,
        "corrupted_page_tree": corrupted_page_tree,
        "nonexistent": nonexistent,
    }

    yield paths

    for path in paths.values():
        if path.exists():
            path.unlink()
    try:
        FIXTURE_DIR.rmdir()
    except OSError:
        # 다른 파일이 남아있다면(다른 테스트가 같은 세션에서 추가 생성 등) 강제로 지우지 않는다.
        pass
