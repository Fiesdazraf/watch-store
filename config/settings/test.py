"""
Settings for running automated tests.
"""

from typing import TYPE_CHECKING

from .base import *  # noqa: F401,F403

if TYPE_CHECKING:
    from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE

print("Using TEST SETTINGS with test_db.sqlite3")

DEBUG = False
SECRET_KEY = "test-key"
ALLOWED_HOSTS = ["*"]

# ---------- Database ----------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

# ---------- Speed Optimizations ----------
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# ---------- Static ----------
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STORAGES = globals().get("STORAGES", {}) or {}
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}

# ---------- Remove problematic debug_toolbar ----------
# Filter out debug_toolbar from INSTALLED_APPS and MIDDLEWARE
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    mw for mw in MIDDLEWARE if "debug_toolbar.middleware.DebugToolbarMiddleware" not in mw
]

# ---------- Root URL ----------
ROOT_URLCONF = "config.urls"
