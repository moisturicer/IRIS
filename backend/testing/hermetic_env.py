"""Make the suite read only what CI supplies from ``backend/.env`` (IR-853).

Loaded with ``-p`` from pytest.ini, so it runs before pytest-django imports
the settings. CI has no ``.env`` and sets exactly these names, so a local run
tests the same configuration CI does. Anything else still comes from the
process environment, as in CI.
"""

import os
from pathlib import Path

from decouple import RepositoryEnv

DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"

# Not imported from config.settings.dotenv: importing `config` starts Celery
# before this has run.
ALLOWLIST_VAR = "IRIS_DOTENV_ALLOWLIST"
CI_SUPPLIED = (
    "SECRET_KEY",
    "RECOVERY_COUNTER_HMAC_KEY",
    "RECOVERY_MAIL_ENCRYPTION_KEY",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
)


def export_ci_supplied(environ=os.environ, path=DOTENV_PATH):
    """Put the allowed ``.env`` values in the environment, where CI has them.

    Some tests start Django with decouple's file reading switched off; CI's
    values still reach them, so ours must too.
    """
    environ.setdefault(ALLOWLIST_VAR, ",".join(CI_SUPPLIED))
    if not path.exists():
        return
    data = RepositoryEnv(str(path)).data
    for name in CI_SUPPLIED:
        if name in data:
            environ.setdefault(name, data[name])


export_ci_supplied()
