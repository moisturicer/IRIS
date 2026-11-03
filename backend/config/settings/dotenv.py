"""Narrow what ``backend/.env`` may supply (IR-853).

A test run sets ``IRIS_DOTENV_ALLOWLIST`` so a developer's ``.env`` (vendor
keys, AI switches, the development bypass) cannot change what the suite tests.
Unset, nothing changes. Child processes inherit the variable.
"""

import os
from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv

ALLOWLIST_VAR = "IRIS_DOTENV_ALLOWLIST"
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def allowed_names(environ=os.environ):
    value = environ.get(ALLOWLIST_VAR)
    if value is None:
        return None
    return frozenset(name.strip() for name in value.split(",") if name.strip())


def restrict_dotenv(auto_config, path=DOTENV_PATH, environ=os.environ):
    """Load only the allowed names from ``path`` into decouple's ``config``."""
    names = allowed_names(environ)
    if names is None:
        return
    if not path.exists():
        auto_config.config = Config(RepositoryEmpty())
        return
    repository = RepositoryEnv(str(path))
    repository.data = {k: v for k, v in repository.data.items() if k in names}
    auto_config.config = Config(repository)
