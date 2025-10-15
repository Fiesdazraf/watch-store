"""
Base settings for Watch Store (Django 5.x)
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # <project-root>

# ---------- Env ----------
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# ---------- Core ----------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-key")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

# Comma-separated: "localhost,127.0.0.1,example.com"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# ---------- I18N / TZ ----------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Tehran")
USE_I18N = True
USE_TZ = True

# ---------- Apps ----------
INSTALLED_APPS = [
    # Local apps
    "apps.catalog",
    "apps.customers",
    "apps.orders.apps.OrdersConfig",
    "apps.accounts",
    "apps.payments",
    "apps.backoffice",
    "apps.invoices",
    "apps.core",
    # Django contrib
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # برای humanize filterها (intcomma, naturaltime, floatformat ...)
    "django.contrib.humanize",
    # 3rd-party
    "django_extensions",
    "widget_tweaks",
]

# Debug toolbar only in DEBUG
if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]

# ---------- Middleware ----------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise must be right after SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# DebugToolbar at the very beginning (only in DEBUG)
if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

# ---------- Caches ----------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "watch-store-cache",
        "TIMEOUT": 60 * 5,  # 5 minutes
    }
}

# ---------- URLs / WSGI / ASGI ----------
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------- Templates ----------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",  # برای base.html و partials/
            BASE_DIR / "templates/apps",  # برای تمپلیت‌های اپ‌ها
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.orders.context_processors.cart_summary",
            ],
        },
    },
]

# ---------- Database ----------
db_url = (os.getenv("DATABASE_URL") or "").strip()
if db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            db_url,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "600")),
            ssl_require=os.getenv("DB_SSL_REQUIRE", "False") == "True",
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------- Auth / Accounts ----------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "home"  # make sure the 'home' route exists

# ---------- Email ----------
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    (
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "SafeCode Store <no-reply@safecode.store>")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"

# ---------- Passwords ----------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- Static / Media (Django 5: use STORAGES) ----------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # ensure the folder exists
STATIC_ROOT = BASE_DIR / "staticfiles"

# Django 5+ storage config
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # WhiteNoise storage (compressed + hashed)
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Optional media config (if you serve user uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------- Security (override via env in prod) ----------
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False") == "True"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False") == "True"
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False") == "True"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))  # e.g., 31536000 in prod
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False") == "True"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False") == "True"

# If behind a proxy/loader that sets X-Forwarded-Proto (Railway, etc.)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if os.getenv("USE_PROXY_SSL_HEADER", "True") == "True"
    else None
)
USE_X_FORWARDED_HOST = os.getenv("USE_X_FORWARDED_HOST", "True") == "True"

# CSRF trusted origins: space/comma separated (Django expects scheme)
# Example: "https://example.com,https://www.example.com"
_csrf_raw = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if _csrf_raw:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_raw.replace(" ", "").split(",") if o.strip()]

# Internal IPs for debug toolbar
if DEBUG:
    INTERNAL_IPS = ["127.0.0.1", "localhost"]

# Clickjacking and other headers
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")

# Append slash behavior
APPEND_SLASH = os.getenv("APPEND_SLASH", "True") == "True"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Logging (minimal sane defaults) ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
