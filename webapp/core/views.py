"""core 앱 최소 뷰(03-system-design.md §4-4).

`healthz`: DB 접속 확인 없는 얕은(shallow) 헬스체크 — Neon 콜드스타트 오탐
방지 목적(AI-AUTO-WORK 패턴 재사용, 03 §4-4 `/healthz` 행).
"""

from django.http import HttpResponse


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")
