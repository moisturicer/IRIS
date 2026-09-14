"""Which Hypothesis profile an environment gets, and what that profile allows.

Pure, like `test_harness.py` next door and for the same reason: a test that
decides how the suite behaves must not itself depend on the environment it is
deciding about (IR-194).
"""

from hypothesis import HealthCheck, settings as hypothesis_settings

from testing.hypothesis_profiles import (
    CI_ENV_VAR,
    CI_PROFILE,
    DEFAULT_PROFILE,
    PROFILE_ENV_VAR,
    profile_for,
    register_profiles,
)


class ProfileSelectionTests:
    """environment -> profile name, the whole table."""

    def test_a_developer_machine_gets_the_strict_default(self):
        assert profile_for({}) == DEFAULT_PROFILE

    def test_ci_gets_the_lenient_profile(self):
        assert profile_for({CI_ENV_VAR: "true"}) == CI_PROFILE

    def test_ci_set_to_a_falsey_value_is_not_ci(self):
        for falsey in ("", "0", "false", "no", "off"):
            assert profile_for({CI_ENV_VAR: falsey}) == DEFAULT_PROFILE, falsey

    def test_an_explicit_profile_wins_over_ci_detection(self):
        env = {CI_ENV_VAR: "true", PROFILE_ENV_VAR: DEFAULT_PROFILE}
        assert profile_for(env) == DEFAULT_PROFILE

    def test_an_explicit_profile_works_without_ci(self):
        assert profile_for({PROFILE_ENV_VAR: CI_PROFILE}) == CI_PROFILE

    def test_an_unknown_explicit_profile_is_rejected_rather_than_ignored(self):
        """A typo must not silently hand back the strict default — that is the
        same silent-fallback failure the chunker registry refuses (IR-110)."""
        import pytest

        with pytest.raises(ValueError) as excinfo:
            profile_for({PROFILE_ENV_VAR: "nonesuch"})
        assert "nonesuch" in str(excinfo.value)
        assert CI_PROFILE in str(excinfo.value)


class RegisteredProfileTests:
    """What the profiles actually permit, asserted on the registered objects
    rather than on the call that registered them."""

    def test_both_profiles_are_registered(self):
        register_profiles()
        assert hypothesis_settings.get_profile(DEFAULT_PROFILE) is not None
        assert hypothesis_settings.get_profile(CI_PROFILE) is not None

    def test_ci_tolerates_a_stalled_draw(self):
        register_profiles()
        ci = hypothesis_settings.get_profile(CI_PROFILE)
        assert ci.deadline is None
        assert HealthCheck.too_slow in ci.suppress_health_check

    def test_the_default_profile_still_catches_a_genuinely_slow_strategy(self):
        """The whole point of keeping two profiles: silencing `too_slow`
        everywhere would hide a strategy that really has become expensive."""
        register_profiles()
        default = hypothesis_settings.get_profile(DEFAULT_PROFILE)
        assert HealthCheck.too_slow not in default.suppress_health_check

    def test_function_scoped_fixture_stays_suppressed_in_both(self):
        """Every property test in apps/ai already suppresses this one by hand;
        the profiles must not quietly re-enable it."""
        register_profiles()
        for name in (DEFAULT_PROFILE, CI_PROFILE):
            profile = hypothesis_settings.get_profile(name)
            assert HealthCheck.function_scoped_fixture in profile.suppress_health_check


class ProfileIsActuallyReachedTests:
    """The profile only governs a test that does not override it.

    This is the trap IR-194 fell into on the first attempt: registering a
    profile with ``too_slow`` suppressed changes nothing for a test whose own
    ``@settings`` passes ``suppress_health_check``, because an explicit value
    replaces the profile's list rather than extending it. ``deadline`` *is*
    inherited, which makes the failure quiet — the profile looks like it is
    working right up until a draw stalls.

    Asserted against the source rather than against a loaded profile, because
    the effective settings depend on which profile is loaded, and this must
    hold on a developer's machine too.
    """

    def _property_test_sources(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "ai"
        sources = [
            p for p in root.rglob("test_*.py") if "suppress_health_check" in p.read_text(encoding="utf-8")
        ]
        return sources

    def test_no_property_test_overrides_the_profiles_health_checks(self):
        offenders = [str(p) for p in self._property_test_sources()]
        assert offenders == [], (
            "These tests pass suppress_health_check themselves, which replaces "
            "the profile's list and re-exposes them to the too_slow flake "
            "IR-194 fixed. Delete the argument and let "
            "testing/hypothesis_profiles.py decide: "
            + ", ".join(offenders)
        )
