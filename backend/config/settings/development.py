from .base import *  # noqa

DEBUG = True


INSTALLED_APPS += ["debug_toolbar"]  # noqa

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa

INTERNAL_IPS = ["127.0.0.1"]

# Local dev origins, listed rather than waved through (IR-154). This was
# `CORS_ALLOW_ALL_ORIGINS = True`, which combined with base.py's
# CORS_ALLOW_CREDENTIALS = True to let any origin make authenticated requests
# on a logged-in user's behalf. Vite binds 5173 and reports itself as
# localhost, but a browser reaching it by IP sends the 127.0.0.1 origin, so
# both spellings are here — that difference is the whole reason the wildcard
# looked necessary.
CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        CORS_ALLOWED_ORIGINS  # noqa: F405 — from base, honours FRONTEND_URL
        + [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
)

# Local dev: print emails (activation links, notifications) to the container log
# instead of trying to reach an SMTP server with placeholder credentials.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "iris@localhost"
