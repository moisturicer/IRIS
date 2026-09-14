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
