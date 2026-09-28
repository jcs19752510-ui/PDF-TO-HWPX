import os

import dj_database_url

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# 실제 운영 시크릿을 절대 여기 하드코딩하지 않는다. 이 값은 "로컬에서 바로
# 실행 가능"하도록 하는 개발 전용 기본값이며 DEBUG=True에서만 쓰인다
# (AI-AUTO-WORK 관례 재사용).
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-dev-only-do-not-use-in-production"
)

ALLOWED_HOSTS = ["*"]

# DATABASE_URL 미설정 시 SQLite(webapp/db.sqlite3)로 폴백한다. 로컬
# Postgres/Neon으로 테스트하고 싶으면 .env에
# DATABASE_URL=postgres://... 를 지정하면 코드 변경 없이 전환된다
# (오케스트레이터 지시사항 — "로컬 기동은 실제 Neon 계정 없이도 가능해야
# 한다"를 만족하는 표준 Django/AI-AUTO-WORK 관례).
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# 오브젝트 스토리지도 dev는 항상 로컬 디스크(base.py의 FileSystemStorage,
# MEDIA_ROOT=webapp/.dev-media/)를 그대로 쓴다 — R2 자격증명 유무와 무관하게
# dev 환경에서는 로컬 폴백만 사용한다(오케스트레이터 지시사항). STORAGES를
# 여기서 재정의하지 않는다.

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
