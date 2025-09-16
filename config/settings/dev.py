# config/settings/dev.py

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
INTERNAL_IPS = ["127.0.0.1", "localhost"]
