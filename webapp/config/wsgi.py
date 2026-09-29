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
# 1회 적용한다. production에서만 강제하고 dev는 비활성화한다(unit-19가 확립한
# dev/production 분리 패턴 재사용) — settings 모듈이 아직 완전히 로드되지
# 않은 이 시점에도 판별 가능하도록 DJANGO_SETTINGS_MODULE 값으로 분기한다.
install_net_guard(
    enforce=os.environ["DJANGO_SETTINGS_MODULE"].endswith(".production")
)

application = get_wsgi_application()
