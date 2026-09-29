from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    # 03 §4-4 라우트 표: `GET /privacy/`.
    path("privacy/", views.privacy, name="privacy"),
]
