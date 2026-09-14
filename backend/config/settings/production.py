"""Production settings — the module that refuses to start (IR-154).

Everything below the transport-security block is a check rather than a value.
Production is the one environment where a misconfiguration is not visible in
development first, so the checks run at import: if this module loads, the
process is configured, and if it is not, nothing serves a request while
someone works out why.

The rules themselves live in `config.settings.validation` as pure functions,
tested in `apps/tests/test_settings_validation.py` against crafted inputs.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import csv_list, required
from .validation import production_problems

DEBUG = False

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Re-read without base.py's `localhost` default. Inheriting that default is
# not "ALLOWED_HOSTS is set for production" — it is the development value
# reaching a public deployment, which is the failure this ticket names.
ALLOWED_HOSTS = required("ALLOWED_HOSTS", cast=csv_list)

# Same reasoning: the deployed frontend origin is a per-deployment fact, and
# falling back to FRONTEND_URL's http://localhost:5173 would put a dead
# localhost entry in a production allowlist.
CORS_ALLOWED_ORIGINS = required("CORS_ALLOWED_ORIGINS", cast=csv_list)

# ---- Startup checks ------------------------------------------------------

_problems = production_problems(
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    cors_allowed_origins=CORS_ALLOWED_ORIGINS,
    # Absent is the point — `globals()` rather than a reference, so this reads
    # False when no settings module defines it and stays honest if one does.
    cors_allow_all_origins=globals().get("CORS_ALLOW_ALL_ORIGINS", False),
)

if _problems:
    raise ImproperlyConfigured(
        "This deployment is not safe to expose publicly (IR-154):\n  - "
        + "\n  - ".join(_problems)
    )

del _problems

# TODO: configure S3 for MEDIA_ROOT via django-storages
# TODO: configure Sentry DSN
