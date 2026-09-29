"""unit-0 AC-2 — `pdf_to_hwpx/common/logging_setup.py` 검증.

근거: docs/harness/03-system-design.md §7-1(로깅), §6-2(개인정보 미포함/마스킹),
unit-0-note.md AC-2.

이 테스트가 만드는 로그 파일은 pytest의 ``tmp_path``(테스트별 격리된 임시
디렉터리, pytest가 자동 정리)에만 둔다 — 리포지토리나 실제 사용자 로그
위치(``platformdirs.user_log_dir``)를 건드리지 않는다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pdf_to_hwpx.common.logging_setup import (
    BACKUP_COUNT,
    LOGGER_NAME,
    LOG_FILE_NAME,
    MAX_BYTES,
    SessionFileRegistry,
    describe_input_for_log,
    get_logger,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _reset_logger():
    """각 테스트 사이에 전역 로거 핸들러가 새지 않도록 정리한다."""
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


# AC-2-1: setup_logging(log_dir=<임시 디렉터리>) 호출 후 로그 파일이 생성된다.
def test_setup_logging_creates_log_file(tmp_path: Path):
    setup_logging(log_dir=tmp_path)
    log_path = tmp_path / LOG_FILE_NAME
    assert log_path.exists()
    assert log_path.name == "pdf-to-hwpx.log"


# AC-2-2: verbose=False(기본)일 때 INFO, verbose=True일 때 DEBUG.
def test_default_level_is_info(tmp_path: Path):
    logger = setup_logging(log_dir=tmp_path)
    assert logger.level == logging.INFO


def test_verbose_level_is_debug(tmp_path: Path):
    logger = setup_logging(verbose=True, log_dir=tmp_path)
    assert logger.level == logging.DEBUG


# AC-2-3: 로그 파일의 각 줄에 app=, python=, os= 컨텍스트가 포함된다.
def test_log_lines_include_app_python_os_context(tmp_path: Path):
    logger = setup_logging(log_dir=tmp_path)
    logger.info("테스트 로그 라인")
    for handler in logger.handlers:
        handler.flush()

    content = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    assert lines, "로그 파일에 최소 1줄이 기록되어야 한다"
    for line in lines:
        assert "app=" in line
        assert "python=" in line
        assert "os=" in line


# AC-2-4: SessionFileRegistry(verbose=False).register(path)가 doc#1, doc#2 ...
# 순으로 반환하고 원본 경로 문자열을 포함하지 않는다.
def test_session_file_registry_masks_paths_by_default():
    registry = SessionFileRegistry(verbose=False)
    sensitive_path = Path("/home/user/주민등록증_홍길동.pdf")

    first = registry.register(sensitive_path)
    second = registry.register(Path("/home/user/other.pdf"))

    assert first == "doc#1"
    assert second == "doc#2"
    assert str(sensitive_path) not in first
    assert "홍길동" not in first
    assert "홍길동" not in second


# AC-2-5: SessionFileRegistry(verbose=True).register(path)는 str(path)와 동일한 문자열 반환.
def test_session_file_registry_exposes_full_path_when_verbose():
    registry = SessionFileRegistry(verbose=True)
    path = Path("/home/user/계약서.pdf")

    result = registry.register(path)

    assert result == str(path)


def test_session_file_registry_sequence_increments_across_many_files():
    """경계값: 파일 여러 개(10개) 연속 등록 시 순번이 어긋나지 않는다."""
    registry = SessionFileRegistry(verbose=False)
    results = [registry.register(Path(f"/tmp/f{i}.pdf")) for i in range(10)]
    assert results == [f"doc#{i}" for i in range(1, 11)]


def test_describe_input_for_log_helper_respects_verbose_flag():
    path = Path("/home/user/개인정보포함.pdf")
    assert describe_input_for_log(path, "doc#1", verbose=False) == "doc#1"
    assert describe_input_for_log(path, "doc#1", verbose=True) == str(path)


# AC-2-6: setup_logging()을 같은 프로세스에서 2회 호출해도 핸들러 중복으로
# 로그 한 줄당 중복 기록이 발생하지 않는다.
def test_setup_logging_twice_does_not_duplicate_handlers(tmp_path: Path):
    logger1 = setup_logging(log_dir=tmp_path)
    logger2 = setup_logging(log_dir=tmp_path)

    assert logger1 is logger2  # 동일 이름 로거(logging.getLogger 싱글턴)
    assert len(logger2.handlers) == 1

    logger2.info("중복 방지 확인용 라인")
    for handler in logger2.handlers:
        handler.flush()

    content = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    matching_lines = [line for line in content.splitlines() if "중복 방지 확인용 라인" in line]
    assert len(matching_lines) == 1


def test_setup_logging_also_log_to_console_adds_second_handler(tmp_path: Path):
    """also_log_to_console=True는 파일 핸들러 외 콘솔 핸들러 1개를 추가로 등록한다
    (핸들러 중복 방지 로직이 의도한 두 번째 핸들러까지 지워버리지 않는지 확인)."""
    logger = setup_logging(log_dir=tmp_path, also_log_to_console=True)
    assert len(logger.handlers) == 2


# AC-2-7: RotatingFileHandler의 maxBytes=5*1024*1024, backupCount=5 설정값이
# 코드에 반영되어 있다 + 실제 rollover 동작 확인(작은 maxBytes로 재현).
def test_rotating_file_handler_configured_constants():
    assert MAX_BYTES == 5 * 1024 * 1024
    assert BACKUP_COUNT == 5


def test_rotating_file_handler_actually_rolls_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """AC-2-7의 "설정값 검사 + 실제 rollover 동작까지 확인" 권고를 반영.

    운영값(5MB)을 그대로 채우면 시간 대비 비용이 크므로, 모듈 상수를 테스트
    전용으로 아주 작게 주입해 회전 로직 자체가 동작하는지 검증한다.
    """
    import pdf_to_hwpx.common.logging_setup as logging_setup_module

    monkeypatch.setattr(logging_setup_module, "MAX_BYTES", 200)
    monkeypatch.setattr(logging_setup_module, "BACKUP_COUNT", 2)

    logger = logging_setup_module.setup_logging(log_dir=tmp_path)
    for _ in range(200):
        logger.info("rollover 유발용 로그 라인 - 충분히 길게 채우기 위한 반복 문자열")
    for handler in logger.handlers:
        handler.flush()

    rotated_files = list(tmp_path.glob(f"{LOG_FILE_NAME}.*"))
    assert rotated_files, "maxBytes를 초과했는데도 회전 파일(.1 등)이 생성되지 않았다"
    assert len(rotated_files) <= 2  # backupCount=2 주입값을 넘지 않아야 함


def test_get_logger_returns_same_logger_after_setup(tmp_path: Path):
    configured = setup_logging(log_dir=tmp_path)
    fetched = get_logger()
    assert fetched is configured
    assert fetched.name == LOGGER_NAME


def test_get_logger_before_setup_returns_handlerless_logger_without_raising():
    """setup_logging()을 아직 호출하지 않은 상태에서도 예외 없이 로거를 반환한다
    (표준 logging 모듈 관례 — 조용히 유실될 뿐 크래시하지 않음)."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    fetched = get_logger()
    assert fetched.name == LOGGER_NAME
    assert fetched.handlers == []


def test_get_default_log_dir_uses_platformdirs():
    from pdf_to_hwpx.common.logging_setup import get_default_log_dir

    log_dir = get_default_log_dir()
    assert "pdf-to-hwpx" in str(log_dir).lower() or "pdf-to-hwpx" in str(log_dir)
