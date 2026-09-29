from django.apps import AppConfig


class CoreConfig(AppConfig):
    """웹 서비스 횡단 관심사를 담는 앱(03-system-design.md §1-3 패키지 레이아웃).

    unit-19는 이 AppConfig와 최소 헬스체크 라우트만 만든다. `net_guard.py`
    (unit-9), `admin_auth.py`(unit-23이 필요시 재사용), `core/middleware.py`
    (unit-24, ContentLengthLimitMiddleware)는 각자의 unit이 이 앱에 추가한다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "웹 서비스 횡단 관심사"
