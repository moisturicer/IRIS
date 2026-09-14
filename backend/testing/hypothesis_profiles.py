"""Hypothesis profiles: how much slowness the machine is allowed to have.

`test_property_chunking_is_deterministic` failed a full-suite run with
`FailedHealthCheck: too_slow` — eleven draws at 0.005-0.008s and one at
35.010s. Nothing about the strategy is slow; one draw stalled on a loaded
container. The test passes in isolation (IR-194).

Twenty property tests across `apps/ai` carry that exposure, and which one
trips is a matter of which draw lands while the box is busy. GitHub Actions
runners are shared and throttled, so this recurs in CI — and since IR-163 the
backend job is a real gate, where a red build nobody can act on is how people
learn to re-run rather than read.

So the leniency is expressed once, here, as a profile, rather than as twenty
`@settings` edits. Two profiles, not one: `ci` stops a stalled draw from
failing a build, while `default` keeps a developer's machine strict, because
suppressing `too_slow` everywhere would also hide a strategy that really has
become expensive — which is a signal worth keeping.

The selection is a pure function of the environment so it can be tested
without the environment it is deciding about — see
`apps/tests/test_hypothesis_profiles.py`, and `testing/harness.py` for the
same pattern applied to database skipping.
"""

from __future__ import annotations

from typing import Mapping

from hypothesis import HealthCheck, settings

from .harness import env_flag_enabled

#: The strict profile: what a developer's machine runs.
DEFAULT_PROFILE = "default"

#: The lenient profile: what a shared, throttled runner runs.
CI_PROFILE = "ci"

#: Set by GitHub Actions (and every other CI provider) without being asked.
#: Chosen over `IRIS_REQUIRE_DB` deliberately: that one answers "must the
#: database be present", which is a different question from "is this machine
#: contended".
CI_ENV_VAR = "CI"

#: Forces a profile regardless of `CI`, so either behaviour can be reproduced
#: on either kind of machine.
PROFILE_ENV_VAR = "HYPOTHESIS_PROFILE"

_PROFILE_NAMES = (DEFAULT_PROFILE, CI_PROFILE)

#: Suppressed in both profiles. Every property test in `apps/ai` already
#: passes this by hand; hoisting it here means the profiles cannot quietly
#: re-enable what those decorators switched off.
_ALWAYS_SUPPRESSED = (HealthCheck.function_scoped_fixture,)


def profile_for(environ: Mapping[str, str]) -> str:
    """Pick a profile name for this environment.

    An explicit `HYPOTHESIS_PROFILE` wins over `CI` detection, and an
    unrecognized one raises rather than falling back — a typo that silently
    selects the strict profile in CI would restore exactly the flake this
    module exists to remove.
    """
    explicit = environ.get(PROFILE_ENV_VAR)
    if explicit is not None and explicit.strip():
        name = explicit.strip()
        if name not in _PROFILE_NAMES:
            raise ValueError(
                f"Unknown {PROFILE_ENV_VAR}={name!r}. "
                f"Known profiles: {', '.join(_PROFILE_NAMES)}."
            )
        return name

    return CI_PROFILE if env_flag_enabled(environ, CI_ENV_VAR) else DEFAULT_PROFILE


def register_profiles() -> None:
    """Register both profiles. Idempotent — re-registering replaces."""
    settings.register_profile(
        DEFAULT_PROFILE,
        suppress_health_check=list(_ALWAYS_SUPPRESSED),
    )
    settings.register_profile(
        CI_PROFILE,
        # A stalled draw is the machine's fault, not the strategy's. Both are
        # needed: `too_slow` covers a stall during data generation, `deadline`
        # a stall inside the test body.
        deadline=None,
        suppress_health_check=[*_ALWAYS_SUPPRESSED, HealthCheck.too_slow],
    )


def activate_profile(environ: Mapping[str, str]) -> str:
    """Register both profiles and load the one this environment calls for.

    Returns the name loaded, so `conftest.py` can report it.
    """
    register_profiles()
    name = profile_for(environ)
    settings.load_profile(name)
    return name
