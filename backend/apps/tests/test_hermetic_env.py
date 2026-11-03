"""IR-853: the suite reads from backend/.env only what CI supplies."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from config.settings import dotenv
from testing import hermetic_env

BACKEND = Path(__file__).resolve().parents[2]

CHILD_PROBE = """
import django
django.setup()
from apps.tests.test_hermetic_env import leaked_names
print(json.dumps(leaked_names()))
""".replace("print(", "import json; print(", 1)


def leaked_names():
    """``.env`` names outside the allowlist that decouple would still return."""
    from decouple import RepositoryEnv, config

    path = dotenv.DOTENV_PATH
    names = RepositoryEnv(str(path)).data if path.exists() else {}
    allowed = dotenv.allowed_names()
    missing = object()
    return sorted(
        name for name in names
        if name not in allowed and name not in os.environ
        and config(name, default=missing) is not missing
    )


def write_env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


class _AutoConfig:
    config = "untouched"


def test_only_allowed_names_are_read_from_the_file(tmp_path):
    path = write_env(tmp_path, "DB_NAME=iris\nLLM_API_KEY=sk-real\n")
    auto = _AutoConfig()
    dotenv.restrict_dotenv(auto, path=path, environ={dotenv.ALLOWLIST_VAR: "DB_NAME"})
    assert auto.config.repository.data == {"DB_NAME": "iris"}


def test_nothing_changes_without_the_allowlist(tmp_path):
    auto = _AutoConfig()
    dotenv.restrict_dotenv(auto, path=write_env(tmp_path, "X=1\n"), environ={})
    assert auto.config == "untouched"


def test_a_missing_file_supplies_nothing(tmp_path):
    auto = _AutoConfig()
    dotenv.restrict_dotenv(auto, path=tmp_path / ".env", environ={dotenv.ALLOWLIST_VAR: "DB_NAME"})
    assert "DB_NAME" not in auto.config.repository


def test_allowed_values_are_exported_without_overriding_the_shell(tmp_path):
    path = write_env(tmp_path, "DB_NAME=from-file\nDB_USER=from-file\nLLM_API_KEY=sk-real\n")
    environ = {"DB_USER": "from-shell"}
    hermetic_env.export_ci_supplied(environ=environ, path=path)
    assert environ["DB_NAME"] == "from-file"
    assert environ["DB_USER"] == "from-shell"
    assert "LLM_API_KEY" not in environ


def test_this_run_allows_exactly_what_ci_supplies():
    assert hermetic_env.ALLOWLIST_VAR == dotenv.ALLOWLIST_VAR
    assert dotenv.allowed_names() == frozenset(hermetic_env.CI_SUPPLIED)


@pytest.mark.django_required
def test_no_other_dotenv_name_reaches_the_run_or_its_children(settings):
    assert leaked_names() == []
    child = subprocess.run(
        [sys.executable, "-c", CHILD_PROBE], cwd=BACKEND, env=dict(os.environ),
        capture_output=True, text=True, timeout=60,
    )
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout.strip().splitlines()[-1]) == []


@pytest.mark.django_required
def test_vendor_keys_come_only_from_the_process_environment(settings):
    for name in ("LLM_API_KEY", "VOYAGE_API_KEY"):
        assert getattr(settings, name) == os.environ.get(name, "")
