"""What the test harness may skip, and when it may not.

`conftest.py` skips Django- and database-backed tests when the environment
cannot support them. That is right on a laptop with no Postgres running, and
wrong in CI, where "the database went away" must be a red build rather than a
green one.

Until 2026-09-06 it was wrong in CI too: the workflow ran `pytest` with no
database service, `conftest.py` skipped every `TransactionTestCase` — which
`APITestCase` is — and the whole authorization suite was collected, skipped,
and reported green. IR-165 added the service; `-ra` then made the skips
*visible*. Visible is not fatal, and a gate that cannot fail is not a gate, so
this module supplies the missing half: with ``IRIS_REQUIRE_DB`` set, an
environment that would have skipped fails instead.

The decision is a pure function of three booleans so it can be tested without
the very environment it is deciding about — see `apps/tests/test_harness.py`.
"""

from __future__ import annotations

import enum
from typing import Mapping, NamedTuple

#: Set this in any environment where skipping is a failure rather than a
#: courtesy. CI sets it; a developer's machine deliberately does not.
STRICT_ENV_VAR = "IRIS_REQUIRE_DB"

#: Values that turn strict mode *off*. Everything else turns it on, so a typo
#: in the workflow fails closed instead of quietly restoring the old
#: lenient behaviour.
_LENIENT_VALUES = frozenset({"", "0", "false", "no", "off"})


class HarnessMode(enum.Enum):
    """What the collected suite should do about this environment."""

    FULL = "full"
    SKIP_DJANGO = "skip_django"
    SKIP_DB = "skip_db"
    FAIL = "fail"


class HarnessDecision(NamedTuple):
    mode: HarnessMode
    reason: str


def strict_mode_requested(environ: Mapping[str, str]) -> bool:
    """Read the strict switch out of an environment mapping."""
    raw = environ.get(STRICT_ENV_VAR)
    if raw is None:
        return False
    return raw.strip().lower() not in _LENIENT_VALUES


def harness_decision(
    *,
    deps_installed: bool,
    db_reachable: bool,
    strict: bool,
) -> HarnessDecision:
    """Decide how to treat an environment that may be missing pieces.

    Dependencies are checked before the database: with Django uninstalled,
    "the database is reachable" is not a claim worth reporting, and naming it
    as the cause sends the reader after the wrong thing.
    """
    if deps_installed and db_reachable:
        return HarnessDecision(
            HarnessMode.FULL,
            "backend dependencies and PostgreSQL are both available",
        )

    if not deps_installed:
        cause = "backend dependencies are not installed in this environment"
    else:
        cause = "no PostgreSQL with pgvector reachable in this environment"

    if not strict:
        mode = HarnessMode.SKIP_DJANGO if not deps_installed else HarnessMode.SKIP_DB
        return HarnessDecision(mode, cause)

    return HarnessDecision(
        HarnessMode.FAIL,
        f"{cause}, and {STRICT_ENV_VAR} is set. Refusing to skip those tests "
        f"and report success: a suite that cannot fail is not evidence. "
        f"Fix the environment, or unset {STRICT_ENV_VAR} if skipping really is "
        f"acceptable here.",
    )
