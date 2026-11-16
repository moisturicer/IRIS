from .base import *  # noqa

DEBUG = True


INSTALLED_APPS += ["debug_toolbar"]  # noqa

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa

INTERNAL_IPS = ["127.0.0.1"]

# Report, don't block, in development (IR-823). The debug toolbar injects inline
# scripts and styles, and DRF's browsable API has inline style attributes; an
# enforced policy would break both for whoever is developing. Production
# enforces (base.py), and the CSP walk-through runs against production settings.
CONTENT_SECURITY_POLICY_REPORT_ONLY = True

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

# Recovery links are secrets and must never be printed to application logs.
# Local mail is in memory unless a developer explicitly configures SMTP.
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.locmem.EmailBackend")  # noqa: F405
DEFAULT_FROM_EMAIL = "iris@localhost"

# Request budgets come from the same explicit environment keys as production.
# See backend/.env.example for opt-in local values (IR-371).

# IR-666, ADR-072: a teammate develops without the ClamAV container unless they
# set MALWARE_SCAN=clamd and MALWARE_SCAN_HOST (the `scan` Compose profile).
# Uploads are then stored unscanned, each one logged. Never allowed in production.
MALWARE_SCAN = config("MALWARE_SCAN", default="off")  # noqa: F405
