"""
IR-1001: production refuses to start with the sign-in lockout off.

Development leaves it off by default (IR-865), so a deployment that forgot the
line would quietly run without it. **Seam: the real settings module**, imported
in a fresh process the way a deployment imports it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

PRODUCTION = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DEBUG": "False",
    "ALLOWED_HOSTS": "testserver",
    "CORS_ALLOWED_ORIGINS": "https://iris.example.edu",
    "REGISTRATION_EMAIL_DOMAINS": "cit.edu",
    "TRUSTED_PROXY_COUNT": "2",
    "FRONTEND_URL": "https://iris.example.edu",
    "EMAIL_HOST": "smtp.example.edu",
    "EMAIL_HOST_USER": "iris@example.edu",
    "EMAIL_HOST_PASSWORD": "test-only",
    "LLAMAPARSE_API_KEY": "llx-test",
    "LLAMAPARSE_VERSION": "2026-09-28",
}


def boot(axes_enabled):
    env = {**os.environ, **PRODUCTION}
    env.pop("AXES_ENABLED", None)
    if axes_enabled is not None:
        env["AXES_ENABLED"] = axes_enabled
    return subprocess.run(
        [sys.executable, "-c",
         "import django; django.setup(); from django.conf import settings; print('AXES', settings.AXES_ENABLED)"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("value", [None, "False", "0", ""])
def test_production_refuses_to_start_with_the_lockout_off_or_unset(value):
    result = boot(value)

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "AXES_ENABLED is not True" in result.stderr


def test_production_starts_with_the_lockout_on():
    result = boot("True")

    assert result.returncode == 0, result.stderr[-2000:]
    assert "AXES True" in result.stdout


def test_development_still_leaves_the_lockout_off_by_default():
    env = {key: value for key, value in os.environ.items() if key != "AXES_ENABLED"}
    env.update(DJANGO_SETTINGS_MODULE="config.settings.development")
    result = subprocess.run(
        [sys.executable, "-c",
         "import decouple; decouple.config = decouple.Config(decouple.RepositoryEmpty()); "
         "from config.settings import development; print('AXES', development.AXES_ENABLED)"],
        cwd=BACKEND, env={**env, "SECRET_KEY": "test-only", "DB_NAME": "t", "DB_USER": "t", "DB_PASSWORD": "t"},
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert "AXES False" in result.stdout
