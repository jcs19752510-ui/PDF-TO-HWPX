from django.apps import AppConfig


class LegalConfig(AppConfig):
    """개인정보처리방침 등 정적 고지 페이지 전용 앱(03-system-design.md §1-3).

    Wagtail 미사용(DEC-026) — 순수 Django 템플릿 뷰만 제공한다. REQ-030 외
    다른 책임을 지지 않는다(DB/모델 없음, migrations 디렉터리도 불필요).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "legal"
    verbose_name = "법적 고지"
