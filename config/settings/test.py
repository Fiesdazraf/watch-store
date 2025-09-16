# config/settings/test.py
"""
Settings for running tests.
"""

# Wildcard import is acceptable in settings; silence Ruff F401/F403.
from .base import *  # noqa: F401, F403

# Explicitly set to avoid F405 on star imports
ROOT_URLCONF = "config.urls"

# Use fast SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",  # super fast; change to file if needed
    }
}

# Speed up hashing (optional; also possible in conftest.py)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Cache dummy
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# If you have a custom user model, define it explicitly
# AUTH_USER_MODEL = "accounts.User"

# Make staticfiles forgiving in tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

from django.contrib.staticfiles.finders import AppDirectoriesFinder, FileSystemFinder  # noqa

STATICFILES_DIRS = getattr(globals(), "STATICFILES_DIRS", [])
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# ---- Force simple static storage in tests even if base uses STORAGES/WhiteNoise
STORAGES = globals().get("STORAGES", {}) or {}
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
