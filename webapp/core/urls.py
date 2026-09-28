from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # 03 §4-4 라우트 표: `GET /healthz` — trailing slash 없음(설계서 원문 그대로).
    path("healthz", views.healthz, name="healthz"),
]
