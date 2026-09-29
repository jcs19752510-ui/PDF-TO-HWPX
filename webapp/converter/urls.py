"""converter 앱 URL 등록 (03-system-design.md §4-4 라우트 표, unit-20).

`/convert`는 설계서 원문 그대로 trailing slash 없이 등록한다(unit-19의
`core/urls.py::healthz`와 동일한 "설계서 원문 그대로" 원칙 유지).
"""

from django.urls import path

from . import views

app_name = "converter"

urlpatterns = [
    path("", views.index, name="index"),
    path("convert", views.convert, name="convert"),
    path("api/jobs/<uuid:job_id>/", views.job_status, name="job-status"),
    path("download/<uuid:job_id>/", views.download, name="download"),
]
