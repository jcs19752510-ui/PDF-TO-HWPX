"""
아웃바운드 네트워크 화이트리스트 (REQ-011 부분 구현, DEC-033).

03-system-design.md §6-3: 접속 목적지 호스트가 허용목록(Neon `DATABASE_URL`의
호스트, R2 `R2_ENDPOINT_URL`의 호스트)에 있을 때만 통과시키고 그 외는
`NetworkAccessBlockedError`로 차단한다. 허용목록은 하드코딩하지 않고 기동 시
환경변수에서 동적으로 구성한다.

디펜스-인-뎁스 목적: 코드 리뷰 없이도 "실수로 추가된 제3자 API 호출"을 기술적으로
막는다(REQ-020 Out-of-Scope 정책의 보조 방어선일 뿐, 유일한 방어선이 아니다).

패치 지점 선택 근거(DEF-001 재작업):
초기 구현은 `socket.create_connection`만 패치했으나, urllib3(botocore/boto3,
requests의 기반)는 그 함수를 거치지 않고 `getaddrinfo` + `socket.socket()` +
`sock.connect()`를 직접 조합한다. 어떤 TCP 클라이언트든 결국 통과하는 유일한
공통 지점은 `socket.socket.connect`/`connect_ex`(SSLSocket도 상속)이므로 이곳을
권위 있는 차단 지점으로 삼는다. 다만 connect 시점의 목적지는 이미 DNS로 IP가
된 뒤라 호스트명 허용목록과 직접 비교할 수 없다. 그래서 `socket.getaddrinfo`도
함께 감싸 (1) 허용목록에 없는 호스트명의 조회를 그 자리에서 차단하고(호스트명이
로그에 남고 DNS 질의도 나가지 않음), (2) 허용 호스트명이 풀린 IP를 허용 IP
집합에 기록해 connect가 그 IP를 통과시키게 한다. IP 리터럴로 직접 접속하는
경우는 허용 IP 집합에 없으면 connect에서 차단된다.

예외적으로 통과시키는 것: 루프백(127.0.0.0/8, ::1)과 AF_UNIX 소켓 — 외부로
나가지 않는 로컬 통신이며, 초기 구현에서도 raw socket.connect는 막지 않았으므로
회귀 방지 차원이다.

알려진 한계(traceability.md REQ-011에 이미 문서화됨, 다시 논의할 필요 없음):
`psycopg[binary]`는 libpq(C 확장)가 자체적으로 소켓 syscall을 수행하므로 이
몽키패치를 우회한다 — 다만 Neon은 애초에 허용 대상이므로 우회되어도 보안
저하는 아니다. 그 밖에 UDP `sendto`/`sendmsg`(비연결 전송)와 C 확장이 직접 여는
소켓도 이 방어 범위 밖이다. 허용 호스트와 IP를 공유하는 다른 호스트명으로
IP 리터럴 접속하는 것은 통과한다(IP 수준 검사의 본질적 한계).

미결(DEC-040, 정책 결정 대기): production.py는 SMTP(`EMAIL_HOST`)로 장애 알림
메일을 발송하지만 허용목록에는 SMTP 호스트가 포함되지 않는다 — 임의로 추가하지
않았으며 EMAIL_HOST 설정 시 메일 발송이 차단될 수 있다.
"""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlsplit

logger = logging.getLogger("core.net_guard")

_ORIGINAL_ATTR = "_net_guard_original"


def _unwrap(func):
    # 모듈 reload 등으로 이미 감싸진 함수를 원본으로 오인하지 않도록 한다.
    return getattr(func, _ORIGINAL_ATTR, func)


_original_getaddrinfo = _unwrap(socket.getaddrinfo)
_original_connect = _unwrap(socket.socket.connect)
_original_connect_ex = _unwrap(socket.socket.connect_ex)
_installed = False


class NetworkAccessBlockedError(Exception):
    """허용목록에 없는 목적지로의 아웃바운드 접속 시도가 차단됐을 때 발생."""


def _normalize_host(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return host.strip().lower().rstrip(".")


def _is_localhost(host):
    # 정확 일치만 허용: 공백 제거·다중 후행 점 허용 없이 대소문자와 단일 후행 점만 정규화한다.
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    host = host.lower()
    if host.endswith("."):
        host = host[:-1]
    return host == "localhost"


def _extract_host(url_value):
    if not url_value:
        return None
    hostname = urlsplit(url_value).hostname
    return _normalize_host(hostname) if hostname else None


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


def _parse_ip(host):
    """IP 리터럴이면 ip_address를, 호스트명이면 None을 반환. IPv4-mapped IPv6는 IPv4로 푼다."""
    candidate = host.split("%", 1)[0]  # IPv6 zone id(fe80::1%eth0) 제거
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


def _block(host):
    # repr로 개행·제어문자를 이스케이프해 로그/예외 메시지 인젝션을 막는다.
    logger.warning("net_guard: 허용되지 않은 아웃바운드 접속 시도 차단, host=%r", host)
    raise NetworkAccessBlockedError(f"허용되지 않은 목적지: {host!r}")


def _build_guards(allowed_hosts):
    allowed_ips = set()

    def check_host_for_lookup(host):
        if not host:
            return
        norm = _normalize_host(host)
        ip = _parse_ip(norm)
        if ip is not None:
            return  # IP 리터럴은 DNS를 타지 않으며 connect 단계에서 판정한다.
        if _is_localhost(host) or norm in allowed_hosts:
            return
        _block(host)

    def guarded_getaddrinfo(host, *args, **kwargs):
        check_host_for_lookup(host)
        results = _original_getaddrinfo(host, *args, **kwargs)
        if host and _normalize_host(host) in allowed_hosts:
            for _family, _type, _proto, _canon, sockaddr in results:
                ip = _parse_ip(sockaddr[0])
                if ip is not None:
                    allowed_ips.add(ip)
        return results

    def check_address(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return
        if not (isinstance(address, tuple) and address):
            # AF_INET/AF_INET6인데 (host, port, ...) 형태가 아니면 판정 불가 -> fail-closed.
            _block(address)
        host = address[0]
        if isinstance(host, (bytes, bytearray)):
            host = bytes(host).decode("ascii", "replace")
        if not isinstance(host, str):
            _block(host)
        norm = _normalize_host(host)
        ip = _parse_ip(norm)
        if ip is None:
            # 호스트명이 그대로 connect로 들어오는 경우(내부에서 C 레벨로 해석됨).
            if _is_localhost(host) or norm in allowed_hosts:
                return
            _block(host)
        if ip.is_loopback or ip in allowed_ips or str(ip) in allowed_hosts:
            return
        _block(host)

    def guarded_connect(self, address):
        check_address(self, address)
        return _original_connect(self, address)

    def guarded_connect_ex(self, address):
        check_address(self, address)
        return _original_connect_ex(self, address)

    for guard, original in (
        (guarded_getaddrinfo, _original_getaddrinfo),
        (guarded_connect, _original_connect),
        (guarded_connect_ex, _original_connect_ex),
    ):
        setattr(guard, _ORIGINAL_ATTR, original)

    return guarded_getaddrinfo, guarded_connect, guarded_connect_ex


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

    guarded_getaddrinfo, guarded_connect, guarded_connect_ex = _build_guards(allowed_hosts)
    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    _installed = True
