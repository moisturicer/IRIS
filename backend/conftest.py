"""Test harness bootstrap.

The chunking domain is pure Python and needs nothing from this file. What this
file does is make the *Django-dependent* tests honest: they skip with a stated
reason when the backend dependencies or the database are unavailable, instead
of erroring at collection or, worse, appearing to pass.

Skipping is the right answer on a laptop with no Postgres running and the wrong
one in CI, so the choice is not made here — `testing.harness` decides, and CI sets
``IRIS_REQUIRE_DB`` to turn a skip into a failed run (IR-163).

It also selects the Hypothesis profile, for the mirror-image reason: a shared
CI runner may stall a draw and fail a property test that has nothing wrong with
it, while a developer's machine should still be told when a strategy really has
become slow. `testing.hypothesis_profiles` decides that one (IR-194).
"""

import os
import socket

import pytest

from testing.harness import (
    HarnessMode,
    harness_decision,
    strict_mode_requested,
)


def pytest_configure(config):
    """Select the Hypothesis profile for this machine (IR-194).

    Guarded like the backend dependencies below: the chunking domain is pure
    and its tests are the only ones using Hypothesis, so an environment
    without it must still be able to collect and run everything else.
    """
    # Before the Hypothesis work below, and deliberately not after it: that
    # block returns early when Hypothesis is absent, and the hasher matters
    # to the Django half of the suite whether or not Hypothesis is installed.
    _use_fast_password_hashing()
    _use_in_process_celery_broker()
    _use_local_memory_cache()

    try:
        from testing.hypothesis_profiles import activate_profile
    except ImportError:
        return

    try:
        config.hypothesis_profile = activate_profile(os.environ)
    except ValueError as exc:
        # A pure ValueError from the domain becomes pytest's own "you invoked
        # this wrongly" error, so a typo reads as a one-line usage message
        # rather than an INTERNALERROR traceback.
        raise pytest.UsageError(str(exc)) from exc


#: Every Django test that logs anyone in pays for a password hash, and PBKDF2
#: is slow *on purpose* -- ~0.22s per call on a developer laptop, more on a
#: throttled shared runner. `WorkflowCharacterisationBase.setUpTestData` alone
#: builds six users, which is the 1.4-1.8s of *setup* that `--durations`
#: attributes to the first test of each such class. Multiplied across the
#: suite's classes this is the dominant cost: locally it takes apps/reviews
#: plus the authorization matrix from 55s to 14s. How much of IR-251's
#: 4h31m *CI* run it accounts for is not yet measured -- that number comes
#: from the first green run on a runner, not from this laptop.
#:
#: `apps/records/test_seed_demo.py` already reached this conclusion for one
#: module and fixed it there with `@override_settings`; this hoists the same
#: decision to the whole suite rather than leaving it as a thing each module
#: rediscovers.
#:
#: This is not weakening a gate. Nothing in the suite asserts which algorithm
#: hashed a password -- `check_password` round-trips through whatever hasher
#: is configured -- and the setting is a test-environment value that never
#: reaches a deployment, where `config/settings/` keeps Django's default.
FAST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _use_fast_password_hashing() -> None:
    """Swap in the cheap hasher, if Django is importable.

    Guarded like everything else here: the chunking domain's tests run in
    environments with no Django at all, and must not be broken by a
    performance tweak aimed at the Django-backed half of the suite.

    `ImportError` only. A broader guard would also swallow the
    `ImproperlyConfigured` that assigning to `settings` raises when
    DJANGO_SETTINGS_MODULE or SECRET_KEY is wrong -- and pytest.ini is
    explicit that booting Django eagerly at collection time is deliberate,
    so that failure has to stay loud.

    `reset_hashers` because assigning to `settings` does not fire the
    `setting_changed` signal Django clears its hasher cache from. Nothing has
    hashed anything this early, so the cache is empty either way; calling it
    makes that correct by construction rather than by running order. It is a
    signal receiver, so it takes the setting name as a keyword and ignores
    any other -- passing it is not optional.
    """
    try:
        from django.conf import settings
        from django.contrib.auth.hashers import reset_hashers
    except ImportError:
        return

    settings.PASSWORD_HASHERS = FAST_PASSWORD_HASHERS
    reset_hashers(setting="PASSWORD_HASHERS")


#: What `.delay()` publishes to during the test run. IR-251's measured cause of
#: the 4h31m CI run: CI runs no Redis, so `CELERY_BROKER_URL` falls back to
#: `redis://localhost:6379`, nothing listens there, and every `.delay()` blocks
#: for ~20s retrying the result backend before raising. `send_email_async`
#: catches that and sends synchronously, so the suite still passed -- it just
#: paid ~20s per notification, and the workflow tests fire hundreds.
#: Measured on the characterisation module, with the cheap hasher above: all 31
#: tests in ~2 minutes with a reachable broker, 14 of 31 after 11 minutes without.
#:
#: Celery's in-process transport is the one `apps/ai/tests/test_celery_routing.py`
#: already uses. A published task sits in memory and nothing consumes it, which
#: is what every test except that one wants: none asserts that an email was
#: delivered through the fallback (nothing reads `mail.outbox`), and tests that
#: care about email patch `send_email_async` at the boundary. It also makes a
#: run independent of whether the machine happens to have a Redis -- the
#: backend container has one and CI does not, which is how the same suite took
#: 20 minutes in one and hours in the other.
TEST_CELERY_BROKER_URL = "memory://"
TEST_CELERY_RESULT_BACKEND = "cache+memory://"


def _use_in_process_celery_broker() -> None:
    """Point Celery at its in-process transport, if Django is importable.

    Set through the **environment**, not `settings`: Celery reads
    ``CELERY_BROKER_URL`` and ``CELERY_RESULT_BACKEND`` from `os.environ`
    *before* anything configured (`celery.app.utils.Settings.broker_url` is
    ``os.environ.get('CELERY_BROKER_URL') or ...``). CI sets neither; the
    backend container sets both to its real Redis, so a settings-only switch
    worked in one and was silently ignored in the other.

    **Why the check inspects built objects, not configuration.** Once the
    environment is written, reading `conf.broker_url` back can only return what
    was just written -- the first version of this check compared exactly that,
    and could never fail (found in review of #89/#90). What can still go wrong
    is Celery having *already built* a Redis backend or connection before this
    ran, and caching it: then the configuration says memory while `.delay()`
    still blocks on Redis. So the check asks the app what it actually built.

    Side effect, stated rather than hidden: `os.environ` stays set for the
    session, so a test's `override_settings(CELERY_BROKER_URL=...)` no longer
    changes the broker. `apps/ai/tests/test_celery_routing.py` relies on that
    override to prove the IR-196 fix; flagged on IR-199 for its owner.
    """
    try:
        from config.celery import app as celery_app
    except ImportError:
        return

    os.environ["CELERY_BROKER_URL"] = TEST_CELERY_BROKER_URL
    os.environ["CELERY_RESULT_BACKEND"] = TEST_CELERY_RESULT_BACKEND
    _assert_celery_runs_in_process(celery_app)


def _assert_celery_runs_in_process(celery_app) -> None:
    """Fail the session unless Celery really built in-process objects.

    Both halves, because the ~20s stall measured above is the *result
    backend* retrying, not the broker -- switching only one would still crawl.
    """
    from celery.backends.cache import CacheBackend

    backend = celery_app.backend
    with celery_app.connection_for_write() as connection:
        transport = connection.transport.driver_type

    if not isinstance(backend, CacheBackend) or transport != "memory":
        raise pytest.UsageError(
            "conftest could not point Celery at its in-process transport (it "
            f"built backend={type(backend).__name__}, transport={transport!r}); "
            "every .delay() would block on an unreachable broker. See IR-251."
        )


def _use_local_memory_cache() -> None:
    """Swap Django's `"default"` cache to LocMemCache, if Django is importable.

    IR-132 gave `CACHES["default"]` a real Redis backend; CI provisions no
    Redis (see `_use_in_process_celery_broker` above), and DRF's
    `AnonRateThrottle`/`UserRateThrottle` read that same cache on every
    request, so any authenticated API test fails there with
    `redis.exceptions.ConnectionError`.
    """
    try:
        from django.conf import settings
        from django.test.signals import clear_cache_handlers
    except ImportError:
        return

    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    clear_cache_handlers(setting="CACHES")


def pytest_report_header(config):
    """Name the Hypothesis profile in the run header.

    Without this the profile is invisible, and "why did this pass locally and
    fail in CI" is exactly the question it changes the answer to.
    """
    name = getattr(config, "hypothesis_profile", None)
    return f"hypothesis profile: {name}" if name else None


def _backend_deps_installed() -> bool:
    try:
        import django  # noqa: F401
        import decouple  # noqa: F401
        import pgvector  # noqa: F401
    except ImportError:
        return False
    return True


def _database_reachable() -> bool:
    if not _backend_deps_installed():
        return False
    try:
        from django.conf import settings

        db = settings.DATABASES["default"]
        host = db.get("HOST") or "localhost"
        port = int(db.get("PORT") or 5432)
    except Exception:
        host, port = "localhost", 5432

    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _needs_a_real_database(item) -> bool:
    """True for Django TestCase/APITestCase-style tests, which hit the DB in
    setUp regardless of markers. SimpleTestCase (and plain functions) do not.
    """
    cls = getattr(item, "cls", None)
    if cls is None:
        return False
    try:
        from django.test import TransactionTestCase
    except ImportError:
        return False
    return issubclass(cls, TransactionTestCase)


def pytest_collection_modifyitems(config, items):
    deps = _backend_deps_installed()
    db = _database_reachable() if deps else False

    decision = harness_decision(
        deps_installed=deps,
        db_reachable=db,
        strict=strict_mode_requested(os.environ),
    )

    # Strict mode: an environment that would have skipped stops the run
    # instead. This is what makes the suite a gate in CI rather than a
    # formality — see testing/harness.py for the incident that motivated it.
    if decision.mode is HarnessMode.FAIL:
        pytest.exit(decision.reason, returncode=1)

    if decision.mode is HarnessMode.FULL:
        return

    skip = pytest.mark.skip(reason=decision.reason)

    for item in items:
        if decision.mode is HarnessMode.SKIP_DJANGO:
            if "django_required" in item.keywords:
                item.add_marker(skip)
            continue
        # Explicit db_required marker (apps/ai's own convention), or a bare
        # Django TestCase/APITestCase subclass (everyone else's convention —
        # these hit the database in setUp with no marker to opt in with).
        if "db_required" in item.keywords or _needs_a_real_database(item):
            item.add_marker(skip)
