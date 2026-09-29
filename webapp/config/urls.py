"""프로젝트 루트 URL 설정(03-system-design.md §4-4 라우트 표, §1-3 unit-19).

`GET /`(업로드 폼)·`POST /convert`·`/api/jobs/<job_id>/`·`/download/<job_id>/`는
unit-20이 만든 `converter/urls.py`를 여기 include한다(unit-20 확정 파일범위
"config/urls.py의 1줄 include" — 03 §1-3). `/privacy/`는 unit-25(legal 앱)가
연결한다.

이번 파일은 unit-19(admin/healthz)에 이어 unit-20/unit-25가 **병렬 웨이브에서
각자 1줄씩 추가**한 상태다(둘 다 "필요하면 이 unit이 한다"고 개별 지시받음) —
오케스트레이터가 두 변경이 실제로 함께 반영됐는지 병합 결과를 재확인할 것
(unit-20-note.md "공유 문서 갱신 요청" 참고).
"""

from django.contrib import admin
from django.urls import include, path

from converter import urls as converter_urls
from core import urls as core_urls
from legal import urls as legal_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(core_urls)),
    path("", include(legal_urls)),
    path("", include(converter_urls)),
]
