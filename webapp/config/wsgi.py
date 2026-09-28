"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

ASGI는 사용하지 않는다(03-system-design.md §2-1) — WSGI+gthread(gunicorn)만
사용한다.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# unit-9(net_guard)가 완료되면 여기서 net_guard.install()을 호출해 아웃바운드
# 화이트리스트(Neon/R2 호스트만 허용)를 기동 시 1회 적용한다(03 §6-3, §1-3
# unit-9 행 "진입점(config/wsgi.py) 1줄 호출"). unit-9가 아직 착수되지
# 않아(Not Started) 존재하지 않는 모듈을 import하면 기동 자체가 깨지므로,
# 이번 unit(19)에서는 자리만 비워두고 실제 호출 코드는 추가하지 않는다.

application = get_wsgi_application()
