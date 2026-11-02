"""IR-835: one test run per Postgres server, and a `slow` selection."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from testing import run_lock
from testing.slow_tests import is_migration_test

BACKEND = Path(__file__).resolve().parents[2]
# Not the real key: this run already holds that one.
TEST_KEY = run_lock.LOCK_KEY + 1


def test_only_a_database_run_that_is_not_nested_takes_the_lock():
    decide = run_lock.should_lock
    assert decide(environ={}, collect_only=False, xdist_worker=False, needs_database=True)
    assert not decide(environ={}, collect_only=True, xdist_worker=False, needs_database=True)
    assert not decide(environ={}, collect_only=False, xdist_worker=True, needs_database=True)
    assert not decide(environ={}, collect_only=False, xdist_worker=False, needs_database=False)
    assert not decide(environ={run_lock.HELD_ENV_VAR: "1"}, collect_only=False,
                      xdist_worker=False, needs_database=True)


def test_the_refusal_names_the_holder_and_what_to_do():
    message = run_lock.refusal("iris-pytest pid=42 C:/IRIS/backend")
    assert "pid=42" in message
    assert "Wait for it to finish or stop it" in message
    assert "another session" in run_lock.refusal(None)


def test_the_application_name_fits_postgres_and_keeps_the_pid():
    name = run_lock.application_name(42, "C:/" + "x" * 200)
    assert len(name.encode()) <= 63
    assert name.startswith("iris-pytest pid=42 ")


@pytest.mark.db_required
@pytest.mark.django_db
def test_a_second_run_is_refused_until_the_first_ends():
    from django.conf import settings

    database = settings.DATABASES["default"]
    first = run_lock.acquire(run_lock.connect_to_maintenance_database(database), key=TEST_KEY)
    try:
        with pytest.raises(run_lock.ConcurrentTestRun) as refused:
            run_lock.acquire(run_lock.connect_to_maintenance_database(database), key=TEST_KEY)
        assert f"pid={os.getpid()}" in str(refused.value)
    finally:
        first.close()
    again = run_lock.acquire(run_lock.connect_to_maintenance_database(database), key=TEST_KEY)
    again.close()


def test_migration_tests_are_recognised_by_filename():
    assert is_migration_test("apps/reviews/test_seat_backfill_migration.py::test_x")
    assert is_migration_test("apps/ai/tests/test_embedding_space_migration.py::C::test_y")
    assert not is_migration_test("apps/ai/tests/test_migrations_are_complete.py::test_z")
    assert not is_migration_test("apps/records/test_capabilities.py::test_migration.py")


def test_not_slow_deselects_migration_and_marked_tests_at_collection():
    targets = ["apps/reviews/test_seat_backfill_migration.py", "apps/records/test_capabilities.py"]
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}

    def collected(*args):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:randomly", *args, *targets],
            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return {line for line in result.stdout.splitlines() if "::" in line}

    everything = collected()
    fast = collected("-m", "not slow")
    gone = everything - fast
    assert gone and fast
    assert all(is_migration_test(node) or "test_each_role_and_state_matches_the_endpoints" in node
               for node in gone)
    assert not any(is_migration_test(node) for node in fast)
