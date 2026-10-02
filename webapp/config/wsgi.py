"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

ASGI는 사용하지 않는다(03-system-design.md §2-1) — WSGI+gthread(gunicorn)만
사용한다.
"""

import os

from django.core.wsgi import get_wsgi_application

from core.net_guard import install as install_net_guard

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# 아웃바운드 화이트리스트(Neon/R2 호스트만 허용, 03 §6-3, DEC-033)를 기동 시
# 1회 적용한다. fail-closed: DJANGO_SETTINGS_MODULE이 정확히 dev 모듈일 때만
# 비활성화하고, 그 외(오탈자·대소문자 차이·빈 값 포함)는 모두 강제한다. settings가
# 아직 로드되지 않은 시점이라 환경변수 문자열로 판별한다.
_DEV_SETTINGS_MODULE = "config.settings.dev"

install_net_guard(
    enforce=os.environ.get("DJANGO_SETTINGS_MODULE") != _DEV_SETTINGS_MODULE
)

application = get_wsgi_application()
