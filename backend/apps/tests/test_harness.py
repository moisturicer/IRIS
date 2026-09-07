"""The decision table behind conftest.py's skipping.

These tests are deliberately pure — no Django, no database, no markers. A test
that guards against a silently-skipped suite must not itself be skippable, or
it inherits the very failure it exists to catch (IR-163).
"""

import pytest

from testing.harness import (
    STRICT_ENV_VAR,
    HarnessMode,
    harness_decision,
    strict_mode_requested,
)


class HarnessDecisionTests:
    """deps x database x strict — the whole table, not just the corners."""

    def test_a_capable_environment_runs_everything(self):
        d = harness_decision(deps_installed=True, db_reachable=True, strict=False)
        assert d.mode is HarnessMode.FULL

    def test_strict_mode_changes_nothing_when_the_environment_is_capable(self):
        d = harness_decision(deps_installed=True, db_reachable=True, strict=True)
        assert d.mode is HarnessMode.FULL

    def test_missing_dependencies_skip_the_django_tests(self):
        d = harness_decision(deps_installed=False, db_reachable=False, strict=False)
        assert d.mode is HarnessMode.SKIP_DJANGO
        assert "dependencies" in d.reason

    def test_an_unreachable_database_skips_only_the_database_tests(self):
        d = harness_decision(deps_installed=True, db_reachable=False, strict=False)
        assert d.mode is HarnessMode.SKIP_DB
        assert "PostgreSQL" in d.reason

    def test_strict_mode_fails_when_dependencies_are_missing(self):
        d = harness_decision(deps_installed=False, db_reachable=False, strict=True)
        assert d.mode is HarnessMode.FAIL

    def test_strict_mode_fails_when_the_database_is_unreachable(self):
        """The IR-165 defect: CI ran, skipped every APITestCase, went green."""
        d = harness_decision(deps_installed=True, db_reachable=False, strict=True)
        assert d.mode is HarnessMode.FAIL

    def test_a_failure_names_the_switch_that_produced_it(self):
        """An operator reading a red build must be able to act on the message."""
        d = harness_decision(deps_installed=True, db_reachable=False, strict=True)
        assert STRICT_ENV_VAR in d.reason

    def test_a_failure_states_what_would_otherwise_have_been_skipped(self):
        d = harness_decision(deps_installed=True, db_reachable=False, strict=True)
        assert "PostgreSQL" in d.reason

    @pytest.mark.parametrize(
        "deps,db,strict",
        [
            (True, True, False),
            (True, True, True),
            (True, False, False),
            (False, False, False),
            (False, False, True),
            (True, False, True),
        ],
    )
    def test_every_outcome_carries_a_reason(self, deps, db, strict):
        d = harness_decision(deps_installed=deps, db_reachable=db, strict=strict)
        assert d.reason.strip(), "a decision with no stated reason is a silent one"

    def test_dependencies_are_checked_before_the_database(self):
        """Without Django installed, 'database reachable' is not a meaningful
        claim — reporting it as the cause would send someone after the wrong
        thing."""
        d = harness_decision(deps_installed=False, db_reachable=True, strict=False)
        assert d.mode is HarnessMode.SKIP_DJANGO


class StrictModeRequestedTests:
    """Reading the switch out of the environment."""

    def test_absent_means_lenient(self):
        assert strict_mode_requested({}) is False

    def test_empty_means_lenient(self):
        assert strict_mode_requested({STRICT_ENV_VAR: ""}) is False

    @pytest.mark.parametrize("value", ["0", "false", "False", "no", "off"])
    def test_falsey_values_mean_lenient(self, value):
        assert strict_mode_requested({STRICT_ENV_VAR: value}) is False

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on"])
    def test_truthy_values_mean_strict(self, value):
        assert strict_mode_requested({STRICT_ENV_VAR: value}) is True

    def test_an_unrecognized_value_means_strict(self):
        """Fail closed. A typo in the CI workflow must not silently restore the
        lenient behaviour this ticket exists to remove."""
        assert strict_mode_requested({STRICT_ENV_VAR: "yolo"}) is True
