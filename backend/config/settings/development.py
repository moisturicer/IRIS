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

# A page load here makes 15-30 API calls, so base.py's 1000/day was spent in
# about forty loads of local clicking, and every call then answered 429.
# `ai_query` is left alone: it bounds paid model calls, not page loads.
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa: F405
        "anon": "1000/hour",
        "user": "5000/hour",
    },
}
