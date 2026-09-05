from .base import *  # noqa

DEBUG = True


INSTALLED_APPS += ["debug_toolbar"]  # noqa

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa

INTERNAL_IPS = ["127.0.0.1"]

# Looser CORS for local dev
CORS_ALLOW_ALL_ORIGINS = True

# Local dev: print emails (activation links, notifications) to the container log
# instead of trying to reach an SMTP server with placeholder credentials.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "iris@localhost"
