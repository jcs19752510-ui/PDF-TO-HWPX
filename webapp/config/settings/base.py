"""
Django settings shared by all environments.

Env-specific overrides live in dev.py / production.py
(03-system-design.md §1-3 unit-19 확정 파일범위, AI-AUTO-WORK의 base/dev/
production 분리 관례를 그대로 재사용, DEC-020).

주의: `legal`(unit-25)/`converter`의 뷰 계층(unit-20)/`core`의 net_guard(unit-9)
등 아직 착수되지 않은 unit의 파일은 이 시점에 import/INSTALLED_APPS에
추가하지 않는다 — 존재하지 않는 모듈을 참조하면 `manage.py runserver` 자체가
깨지기 때문이다(오케스트레이터 지시사항, unit-19의 최우선 목표: 로컬 즉시
기동 가능 상태).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = PROJECT_DIR

# .env는 로컬 개발 편의용이다. Render 등 실제 배포 환경은 플랫폼이 주입하는
# 실제 환경변수를 그대로 사용하고 .env 파일을 두지 않는다(AI-AUTO-WORK 관례
# 재사용, 03 §2-1).
load_dotenv(BASE_DIR / ".env")


# Application definition

INSTALLED_APPS = [
    "core",
    "converter",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# XForwardedForMiddleware(config/middleware.py)는 production.py에서만
# 맨 앞에 prepend된다(03 §6-4) — dev 로컬 실행에는 Render 엣지라는 전제가
# 없으므로 base에는 등록하지 않는다.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            PROJECT_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
# ASGI는 사용하지 않는다(03 §2-1 — 실시간 양방향 통신 불필요, WSGI+gthread로
# 충분). asgi.py 파일 자체를 만들지 않는다(설계서 패키지 레이아웃 "wsgi.py만
# 사용" 명시).


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization

LANGUAGE_CODE = "ko"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript)

STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"

# 오브젝트 스토리지(R2) 폴백 토대(오케스트레이터 지시사항 — unit-19 책임).
# 기본값(dev)은 로컬 디스크(FileSystemStorage)다. production.py가 R2 자격증명이
# 있을 때만 S3Storage(django-storages)로 덮어쓴다. 실제 업로드/다운로드
# 로직(storage.py)은 unit-21/22 몫 — 여기서는 STORAGES 설정 골격만 제공한다.
MEDIA_ROOT = BASE_DIR / ".dev-media"
MEDIA_URL = "/media/"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 레이트리밋 카운터(unit-23) 등이 재사용할 캐시 백엔드 — 03 §2-1이 이미
# LocMemCache로 확정했으므로(DEC-032) unit-19가 settings 골격에 미리
# 반영해둔다(단일 워커 전제에서만 정확함, 03 §2-1과 동일 트레이드오프).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
