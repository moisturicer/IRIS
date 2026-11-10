"""Safe module-preserving local parallelism (IR-854)."""

import os

import pytest

from testing import run_lock

# These suites provision/use cluster-wide roles. Keep every consumer together,
# including dispatch which imports the runtime fixture from the run suite.
ROLE_MODULES = frozenset({
    "test_runtime_indexing.py",
    "test_runtime_extraction.py",
    "test_runtime_reader_progress.py",
    "test_runtime_reader_edge.py",
    "test_runtime_reader_e2e.py",
    "test_manuscript_publication.py",
    "test_research_grants_db.py", "test_research_read_policy_db.py",
    "test_research_reads.py", "test_ai_runtime_runs_db.py",
    "test_ai_runtime_research_db.py", "test_ai_runtime_admission_db.py",
    "test_ai_runtime_dispatch_db.py", "test_ai_runtime_agent_db.py",
    "test_ai_runtime_agent_loop_db.py", "test_ai_runtime_openai_agent_db.py",
    "test_ai_runtime_executor_selection_db.py", "test_ai_runtime_metadata_db.py",
    "test_ai_runtime_manuscript_db.py", "test_ai_runtime_partial_outage_db.py",
    "test_ai_runtime_recovery_db.py", "test_ai_runtime_compaction_db.py",
    "test_ai_runtime_turn_recovery_db.py",
    "test_ai_runtime_lifecycle_db.py",
    "test_ai_runtime_pool_db.py",
    "test_ai_runtime_turn_sources_db.py",
    "test_ai_runtime_revocation_db.py",
    "test_ai_runtime_grant_renewal_db.py",
    "test_ir740_runtime_collection_db.py",
    "test_ir739_runtime_record_vectors_db.py",
    "test_ir886_hybrid_search_db.py",
    "test_ir953_cached_tokens_db.py", "test_ir953_query_vector_cache_db.py",
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


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker, request):
    # Capture migration data before any test changes it.
    if hasattr(request.config, "workerinput"):
        from django.db import connection

        with django_db_blocker.unblock():
            request.config._iris_initial_data = connection.creation.serialize_db_to_string()
        request.config._iris_db_blocker = django_db_blocker
    yield


def database_mode(item):
    from django.test import TestCase, TransactionTestCase

    cls = getattr(item, "cls", None)
    if cls is not None and issubclass(cls, TransactionTestCase):
        return "rollback" if issubclass(cls, TestCase) else "transaction"
    marker = item.get_closest_marker("django_db")
    fixtures = set(item.fixturenames)
    if (marker is not None and (marker.kwargs.get("transaction") or marker.kwargs.get("reset_sequences"))
            or fixtures & {"transactional_db", "live_server", "django_db_reset_sequences"}):
        return "transaction"
    if marker is not None or "db" in fixtures:
        return "rollback"
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    config = item.config
    if (not getattr(config, "_iris_seed_data_flushed", False)
            or database_mode(item) != "rollback"):
        return
    from django.apps import apps
    from django.core.management import call_command
    from django.core.management.color import no_style
    from django.db import connection

    # Serial pytest-django runs rollback tests before flush tests. Worker queues
    # mix them; restore the initial DB only when crossing that boundary.
    with config._iris_db_blocker.unblock():
        call_command("flush", verbosity=0, interactive=False,
                     inhibit_post_migrate=True, reset_sequences=False)
        connection.creation.deserialize_db_from_string(config._iris_initial_data)
        statements = connection.ops.sequence_reset_sql(no_style(), apps.get_models())
        if statements:
            with connection.cursor() as cursor:
                cursor.execute(";".join(statements))
    config._iris_seed_data_flushed = False


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    yield
    if (hasattr(item.config, "_iris_initial_data")
            and database_mode(item) == "transaction"):
        item.config._iris_seed_data_flushed = True
