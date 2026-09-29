import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"{name} environment variable is required in production.")
    return value


SECRET_KEY = _require_env("SECRET_KEY")

# Render가 자동 주입하는 호스트명 + 운영자가 직접 지정하는 추가 호스트
# (AI-AUTO-WORK 관례 재사용, 03 §2-1).
ALLOWED_HOSTS = []
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
ALLOWED_HOSTS += [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

# CSRF_TRUSTED_ORIGINS는 반드시 ALLOWED_HOSTS에서만 파생시킨다 — 목록 밖
# 오리진을 하드코딩으로 추가하지 않아 임의 오리진이 CSRF 신뢰 목록에 끼어들
# 여지를 원천 차단한다(AI-AUTO-WORK 관례 재사용).
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

# Neon PostgreSQL 필수 연결(03 §2-1 DEC-020/027). CONN_MAX_AGE=0은 Neon
# scale-to-zero 콜드스타트와 장시간 유지 연결이 충돌하지 않도록 보수적으로
# 설정한다(AI-AUTO-WORK 관례 재사용).
DATABASE_URL = _require_env("DATABASE_URL")
DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=0,
        ssl_require=True,
    )
}

# 전송 보안 — Render는 관리형 TLS를 기본 제공하므로 HTTPS를 강제한다.
# Render 엣지가 TLS를 종료하고 앱에는 평문 HTTP로 전달하므로
# X-Forwarded-Proto 헤더를 신뢰하도록 명시해야 한다(AI-AUTO-WORK 관례 재사용,
# 단일 홉 구조에서만 안전).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
# Render의 헬스체크 프로브가 X-Forwarded-Proto 헤더 없이 인스턴스에 직접
# 접속할 가능성이 있다. `/healthz`는 민감정보 없는 "ok" 응답뿐이므로 HTTPS
# 강제 리다이렉트 예외로 둔다(03 §4-4, AI-AUTO-WORK 관례 재사용).
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# HSTS는 배포 후 HTTPS가 안정적으로 동작함을 확인한 뒤 값을 늘려간다.
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# 클라이언트 실제 IP 처리(03 §6-4) — REMOTE_ADDR이 Render 엣지의 내부 IP로
# 고정되는 것을 막기 위해 X-Forwarded-For의 rightmost 값을 REMOTE_ADDR로
# 재설정한다. unit-23(레이트리밋)이 이 값을 그대로 신뢰해 쓸 수 있도록
# 미들웨어 체인 가장 앞단에 둔다.
MIDDLEWARE = ["config.middleware.XForwardedForMiddleware", *MIDDLEWARE]  # noqa: F405

# Cloudflare R2(S3 호환) — 03 §2-1, DEC-020/027. 실제 버킷/키는 아직
# 발급되지 않았으므로(10~12단계) 이 설정은 환경변수가 없으면 프로덕션 기동
# 자체를 막는다(원칙: 값을 여기서 추측/하드코딩하지 않는다, AI-AUTO-WORK
# 관례 재사용).
AWS_ACCESS_KEY_ID = _require_env("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = _require_env("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = _require_env("R2_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = _require_env("R2_ENDPOINT_URL")
AWS_S3_REGION_NAME = os.environ.get("R2_REGION", "auto")
# R2는 S3의 오브젝트 ACL 헤더를 지원하지 않는다 — ACL을 보내면 Cloudflare가
# 요청을 거부하므로 반드시 None(AI-AUTO-WORK 관례 재사용).
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = False

STORAGES["default"] = {  # noqa: F405
    "BACKEND": "storages.backends.s3.S3Storage",
}
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

# 장애 알림 채널(03 §7-2) — Django 500 에러를 운영자 이메일로 즉시 통지한다.
# `ADMINS`를 채우기만 하면 Django 기본 LOGGING(django.utils.log.DEFAULT_LOGGING)이
# 이미 `django.request` 로거에 mail_admins 핸들러를 연결해두므로 커스텀
# LOGGING dict가 필요 없다(과설계 방지, AI-AUTO-WORK 관례 재사용). 값이
# 비어 있어도 기동을 막지 않는다(이 기능은 앱 구동의 필수 전제가 아님).
_admin_emails = [
    email.strip()
    for email in os.environ.get("DJANGO_ADMIN_EMAIL", "").split(",")
    if email.strip()
]
ADMINS = [(email, email) for email in _admin_emails]
MANAGERS = ADMINS

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
SERVER_EMAIL = os.environ.get("SERVER_EMAIL") or (
    f"errors@{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else "errors@localhost"
)
DEFAULT_FROM_EMAIL = SERVER_EMAIL

# unit-9(net_guard)가 완료되면 여기(또는 config/wsgi.py)에서
# net_guard.install()을 호출해 DATABASE_URL/R2_ENDPOINT_URL 호스트만 허용하는
# 아웃바운드 화이트리스트를 적용한다(03 §6-3, DEC-033). unit-9가 아직
# 착수되지 않아 존재하지 않는 모듈을 import하면 기동이 깨지므로 이번
# unit(19)에서는 호출부를 추가하지 않는다.

try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
