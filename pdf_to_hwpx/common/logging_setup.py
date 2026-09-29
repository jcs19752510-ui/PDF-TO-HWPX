"""로컬 로깅 설정 (docs/harness/03-system-design.md §7-1, §3-2, §6-2).

이 모듈은 GUI/CLI 두 진입점이 앱 시작 시 1회씩 호출하는 횡단 관심사 초기화
지점이다(03 §1-1 "횡단 관심사는 진입점 1곳에서만 초기화").

핵심 정책 (03 §7-1):
    - ``RotatingFileHandler`` (maxBytes=5MB, backupCount=5)
    - 저장 위치: ``platformdirs.user_log_dir("pdf-to-hwpx")``
      (Windows 기준 ``%LOCALAPPDATA%\\pdf-to-hwpx\\Logs``)
    - 기본 레벨 INFO, ``--verbose``/GUI 설정에서 DEBUG로 전환
    - 모든 로그 라인에 앱 버전·Python 버전·OS 정보를 포함(재현성)

개인정보 미포함 정책 (03 §6-2):
    - PDF 본문 텍스트는 어떤 레벨로도 로그에 남기지 않는다(호출자 책임 — 이
      모듈은 그런 인자를 받지 않는다).
    - 파일 경로/파일명은 기본 모드에서 로그에 남기지 않고, 세션 내 일련번호
      (``doc#1``, ``doc#2`` ...)로 대체한다. 전체 경로/원본 파일명은 사용자가
      명시적으로 ``--verbose``를 요청했을 때만 노출한다.
      -> :func:`describe_input_for_log` 가 이 마스킹 규칙을 구현한다.
"""

from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_dir

from pdf_to_hwpx import __version__

LOGGER_NAME = "pdf_to_hwpx"
LOG_FILE_NAME = "pdf-to-hwpx.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

_APP_CONTEXT = (
    f"app={__version__} python={platform.python_version()} "
    f"os={platform.system()}-{platform.release()}"
)


class _AppContextFilter(logging.Filter):
    """모든 레코드에 앱 버전/Python 버전/OS 정보를 부착한다(03 §7-1 재현성 요구)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.app_context = _APP_CONTEXT
        return True


def get_default_log_dir() -> Path:
    """플랫폼별 표준 로그 디렉터리를 반환한다(03 §7-1)."""
    return Path(user_log_dir("pdf-to-hwpx"))


def setup_logging(
    verbose: bool = False,
    log_dir: Path | None = None,
    *,
    also_log_to_console: bool = False,
) -> logging.Logger:
    """애플리케이션 로거를 초기화하고 반환한다.

    GUI/CLI 진입점에서 앱 시작 시 정확히 1회 호출해야 한다(03 §1-1). 중복
    호출해도 핸들러가 중복 등록되지 않도록 기존 핸들러를 정리한다.

    Args:
        verbose: True면 DEBUG 레벨, False면 INFO 레벨(03 §7-1 기본값).
        log_dir: 로그 파일을 둘 디렉터리. 생략하면 :func:`get_default_log_dir`.
        also_log_to_console: True면 stderr에도 동일 로그를 출력한다(주로
            개발/디버깅용, 기본은 파일에만 기록).

    Raises:
        OSError: 로그 디렉터리를 생성할 수 없는 경우(디스크/권한 문제). 이
            예외는 로깅 인프라 자체의 실패이므로 여기서 삼키지 않고 그대로
            전파한다 — 호출자가 "로그를 못 남기는 상태"를 인지해야 한다.
    """
    target_dir = log_dir if log_dir is not None else get_default_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / LOG_FILE_NAME

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(app_context)s - %(name)s: %(message)s"
    )
    context_filter = _AppContextFilter()

    file_handler = RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    logger.addHandler(file_handler)

    if also_log_to_console:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """이미 초기화된 애플리케이션 로거를 가져온다.

    :func:`setup_logging` 을 먼저 호출하지 않았다면 핸들러가 없는 로거가
    반환된다(로깅이 조용히 유실될 뿐 예외를 던지지 않음 — 표준 logging 모듈의
    관례를 따른다).
    """
    return logging.getLogger(LOGGER_NAME)


class SessionFileRegistry:
    """로그에 남길 "파일 표시 이름"을 세션 단위로 관리한다(03 §6-2).

    파일명 자체가 개인정보를 담을 수 있으므로(예: ``주민등록증_홍길동.pdf``),
    기본 모드에서는 ``doc#1``, ``doc#2`` 같은 세션 내 일련번호만 로그에
    남기고, 전체 경로/원본 파일명은 verbose 모드에서만 노출한다.

    orchestrator/CLI/GUI가 변환 대상 파일 1개당 :meth:`register` 를 1회
    호출해 로그 표시용 문자열을 얻어 쓰면 된다.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._next_index = 1

    def register(self, path: Path) -> str:
        """새 파일을 세션에 등록하고 로그에 쓸 표시 문자열을 반환한다."""
        display = str(path) if self._verbose else f"doc#{self._next_index}"
        self._next_index += 1
        return display


def describe_input_for_log(path: Path, sequence_label: str, verbose: bool = False) -> str:
    """단일 파일에 대해 로그 표시 문자열을 즉석에서 계산한다(등록 불필요한 경우용).

    :class:`SessionFileRegistry` 는 "여러 파일을 순서대로 처리"하는 배치
    변환(REQ-013)에 적합하고, 이 함수는 이미 순번이 정해진 단일 케이스(예:
    CLI 단일 ``convert`` 명령)에서 쓰기 위한 저수준 헬퍼다.
    """
    return str(path) if verbose else sequence_label
