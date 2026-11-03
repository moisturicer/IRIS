"""Worker isolation regressions (IR-854)."""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from testing.parallel import ROLE_MODULES, scope_for


def test_role_consumers_share_one_scope_and_other_modules_remain_whole():
    assert {scope_for(f"apps/ai/tests/{name}::test_x") for name in ROLE_MODULES} == {"postgres-roles"}
    assert scope_for("apps/test_a.py::SomeTests::test_x") == "apps/test_a.py"
    assert scope_for("apps/test_b.py::test_x") != scope_for("apps/test_a.py::test_y")


@pytest.mark.db_required
@pytest.mark.django_db
def test_workers_and_their_children_use_separate_databases(tmp_path):
    from django.conf import settings

    database = settings.DATABASES["default"]
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    env.update(DB_NAME="ir854_probe_" + uuid.uuid4().hex[:10],
               DB_USER=database["USER"], DB_PASSWORD=database["PASSWORD"],
               DB_HOST=database["HOST"], DB_PORT=str(database["PORT"]),
               PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    (tmp_path / "pytest.ini").write_text("[pytest]\nDJANGO_SETTINGS_MODULE=config.settings.development\n")
    body = r'''
import json, os, subprocess, sys, time
from pathlib import Path
import pytest
@pytest.mark.django_db(transaction=True)
def test_isolated():
    from django.db import connection
    from apps.accounts.models import User
    User.objects.create_user(email="same@cit.edu", password="test")
    database = connection.settings_dict
    env = dict(os.environ, DB_NAME=database["NAME"])
    probe = ("import django; django.setup(); from django.db import connection; "
             "c=connection.cursor(); c.execute('SELECT current_database()'); print(c.fetchone()[0])")
    child = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == database["NAME"]
    root = Path(__file__).parent
    (root / (__name__ + ".json")).write_text(json.dumps(database["NAME"]))
    deadline = time.monotonic() + 60
    while len(list(root.glob("*.json"))) < 2:
        assert time.monotonic() < deadline, "workers did not run concurrently"
        time.sleep(0.05)
'''
    for name in ("test_first", "test_second"):
        (tmp_path / (name + ".py")).write_text(body)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "xdist.plugin", "-p", "django",
         "-p", "testing.parallel", "-n", "2", "-q"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    databases = [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]
    assert len(databases) == len(set(databases)) == 2


@pytest.mark.db_required
@pytest.mark.django_db
def test_second_parallel_controller_is_refused_before_workers_start():
    from testing import run_lock

    env = dict(os.environ)
    env.pop(run_lock.HELD_ENV_VAR, None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-n", "2", "apps/tests/test_parallel.py",
         "-k", "role_consumers"],
        cwd=Path(__file__).resolve().parents[2], env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Another backend test run" in result.stdout + result.stderr
    assert "created:" not in result.stdout


def test_real_scheduler_preserves_modules_and_role_group(tmp_path):
    from testing import run_lock

    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    env[run_lock.HELD_ENV_VAR] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    body = ("import os\nfrom pathlib import Path\n"
            "def record(name):\n"
            "    Path(__file__).with_suffix('.' + name).write_text(os.environ['PYTEST_XDIST_WORKER'])\n"
            "def test_first(): record('first')\n"
            "def test_second(): record('second')\n")
    names = ["test_regular", "test_other", "test_research_grants_db", "test_research_reads"]
    for name in names:
        (tmp_path / (name + ".py")).write_text(body)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "xdist.plugin", "-p", "testing.parallel", "-n", "2", "-q"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "8 passed" in result.stdout
    workers = {}
    for name in names:
        first = (tmp_path / (name + ".first")).read_text()
        second = (tmp_path / (name + ".second")).read_text()
        assert first == second
        workers[name] = first
    assert workers["test_research_grants_db"] == workers["test_research_reads"]


def test_all_current_research_role_consumers_are_grouped():
    import re

    directory = Path(__file__).resolve().parents[1] / "ai" / "tests"
    consumers = {
        path.name for path in directory.glob("test_*.py")
        if re.search(r"grant_db|probe_login|probe_credentials|provision_research_roles|test_ai_runtime_runs_db",
                     path.read_text(encoding="utf-8"))
    }
    assert consumers <= ROLE_MODULES, "new role consumers must share the Postgres role scope"


@pytest.mark.db_required
@pytest.mark.django_db
def test_rollback_tests_keep_migration_seeds_after_a_transactional_flush(tmp_path):
    from django.conf import settings

    database = settings.DATABASES["default"]
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    env.update(DB_NAME="ir854_seed_" + uuid.uuid4().hex[:10],
               DB_USER=database["USER"], DB_PASSWORD=database["PASSWORD"],
               DB_HOST=database["HOST"], DB_PORT=str(database["PORT"]),
               PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    (tmp_path / "pytest.ini").write_text("[pytest]\nDJANGO_SETTINGS_MODULE=config.settings.development\n")
    (tmp_path / "conftest.py").write_text(
        "import pytest\n@pytest.hookimpl(trylast=True)\n"
        "def pytest_collection_modifyitems(items): items.sort(key=lambda item: item.nodeid)\n")
    (tmp_path / "test_seed.py").write_text(
        "import pytest\n@pytest.mark.django_db(transaction=True)\n"
        "def test_00_flush(): pass\n"
        "@pytest.mark.django_db\n"
        "def test_01_initial_lookup_data():\n"
        "    from apps.accounts.models import Role\n"
        "    from core.permissions import ROLE_STUDENT\n"
        "    assert Role.objects.filter(name=ROLE_STUDENT).exists()\n")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "xdist.plugin", "-p", "django",
         "-p", "testing.parallel", "-n", "1", "-q"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
