"""legal 앱 뷰(03-system-design.md §1-3/§4-4, REQ-030).

이 앱은 DB/API 조회가 전혀 없는 100% 정적 콘텐츠 페이지만 제공한다
(04-ux-design.md W-2 — "정상 상태만 존재", 실패할 조건 자체가 없음).
"""

from django.shortcuts import render


def privacy(request):
    return render(request, "legal/privacy.html")
