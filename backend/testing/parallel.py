"""Safe module-preserving local parallelism (IR-854)."""

import os

import pytest

from testing import run_lock

# These suites provision/use cluster-wide roles. Keep every consumer together,
# including dispatch which imports the runtime fixture from the run suite.
ROLE_MODULES = frozenset({
    "test_research_grants_db.py", "test_research_read_policy_db.py",
    "test_research_reads.py", "test_ai_runtime_runs_db.py",
    "test_ai_runtime_research_db.py", "test_ai_runtime_admission_db.py",
    "test_ai_runtime_dispatch_db.py",
})


def scope_for(nodeid):
    module = nodeid.split("::", 1)[0]
    if module.rsplit("/", 1)[-1] in ROLE_MODULES:
        return "postgres-roles"
    return module


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_make_scheduler(config, log):
    from xdist.scheduler.loadfile import LoadFileScheduling

    class IsolatedModules(LoadFileScheduling):
        def _split_scope(self, nodeid):
            return scope_for(nodeid)

    return IsolatedModules(config, log)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    config = session.config
    if (hasattr(config, "workerinput") or not config.getoption("numprocesses", default=0)
            or config.option.collectonly or os.environ.get(run_lock.HELD_ENV_VAR)):
        return
    # xdist controllers never collect; acquire BEFORE workers are spawned.
    from django.conf import settings

    try:
        connection = run_lock.connect_to_maintenance_database(settings.DATABASES["default"])
        config._iris_run_lock = run_lock.acquire(connection)
    except run_lock.ConcurrentTestRun as refused:
        pytest.exit(str(refused), returncode=1)
    os.environ[run_lock.HELD_ENV_VAR] = "1"


@pytest.fixture(scope="session", autouse=True)
def isolated_worker_media(request, tmp_path_factory):
    if not hasattr(request.config, "workerinput"):
        yield
        return
    try:
        from django.test import override_settings
    except ImportError:
        yield
        return

    with override_settings(MEDIA_ROOT=str(tmp_path_factory.mktemp("media"))):
        yield
