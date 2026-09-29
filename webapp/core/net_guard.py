"""
아웃바운드 네트워크 화이트리스트 (REQ-011 부분 구현, DEC-033).

03-system-design.md §6-3: `socket.create_connection`을 몽키패치해, 접속
목적지 호스트가 허용목록(Neon `DATABASE_URL`의 호스트, R2 `R2_ENDPOINT_URL`의
호스트)에 있을 때만 통과시키고 그 외는 `NetworkAccessBlockedError`로 차단한다.
허용목록은 하드코딩하지 않고 기동 시 환경변수에서 동적으로 구성한다.

디펜스-인-뎁스 목적: 코드 리뷰 없이도 "실수로 추가된 제3자 API 호출"을 기술적으로
막는다(REQ-020 Out-of-Scope 정책의 보조 방어선일 뿐, 유일한 방어선이 아니다).

알려진 한계(traceability.md REQ-011에 이미 문서화됨, 다시 논의할 필요 없음):
`psycopg[binary]`는 libpq(C 확장)가 자체적으로 소켓 syscall을 수행하므로 이
몽키패치를 우회한다 — 다만 Neon은 애초에 허용 대상이므로 우회되어도 보안
저하는 아니다. 이 모듈이 실제로 가로챌 수 있는 것은 파이썬 `socket` 모듈을
경유하는 호출(urllib3/requests/boto3 — botocore가 내부적으로 http.client를
거쳐 socket을 쓰므로 R2 접근은 이 방어 범위 안에 있다)뿐이다.

미문서화 위험(수동 확인 필요, unit-9 파일범위 밖 — 6단계/09단계 인지 필요):
production.py는 SMTP(`EMAIL_HOST`)로 장애 알림 메일을 발송한다(§7-2). 03 §6-3
원문은 허용목록에 Neon/R2/Render 플랫폼 트래픽만 명시하고 SMTP 호스트는
언급하지 않는다 — 이 모듈은 설계서 원문 그대로 SMTP 호스트를 허용목록에
포함하지 않으므로, EMAIL_HOST가 설정되면 메일 발송 시도가 차단될 수 있다.
"""

import logging
import os
import socket
from urllib.parse import urlsplit

logger = logging.getLogger("core.net_guard")

_original_create_connection = socket.create_connection
_installed = False


class NetworkAccessBlockedError(Exception):
    """허용목록에 없는 목적지로의 아웃바운드 접속 시도가 차단됐을 때 발생."""


def _extract_host(url_value):
    if not url_value:
        return None
    hostname = urlsplit(url_value).hostname
    return hostname.lower() if hostname else None


def _build_allowed_hosts():
    allowed = set()
    for env_name in ("DATABASE_URL", "R2_ENDPOINT_URL"):
        host = _extract_host(os.environ.get(env_name))
        if host:
            allowed.add(host)
        else:
            logger.warning(
                "net_guard: %s 환경변수에서 호스트를 파싱하지 못했다(값 없음 또는 형식 이상)",
                env_name,
            )
    return allowed


def install(enforce=True):
    """기동 시 1회 호출(진입점: config/wsgi.py).

    enforce=False(dev)면 화이트리스트를 적용하지 않는다 — 로컬 개발 중
    SQLite 폴백(DATABASE_URL 미설정) 등 다양한 목적지 접속이 net_guard 때문에
    막히면 안 되기 때문이다(unit-19가 확립한 dev/production 분리 패턴).
    """
    global _installed
    if _installed:
        logger.debug("net_guard: 이미 설치되어 있어 재설치를 건너뜀")
        return

    if not enforce:
        logger.info("net_guard: enforce=False(dev) — 아웃바운드 화이트리스트를 적용하지 않는다")
        _installed = True
        return

    allowed_hosts = _build_allowed_hosts()
    logger.info(
        "net_guard: 아웃바운드 화이트리스트 활성화, 허용 호스트=%s",
        sorted(allowed_hosts),
    )

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else None
        if host is not None and host.lower() not in allowed_hosts:
            logger.warning("net_guard: 허용되지 않은 아웃바운드 접속 시도 차단, host=%s", host)
            raise NetworkAccessBlockedError(f"허용되지 않은 목적지: {host}")
        return _original_create_connection(address, *args, **kwargs)

    socket.create_connection = guarded_create_connection
    _installed = True
