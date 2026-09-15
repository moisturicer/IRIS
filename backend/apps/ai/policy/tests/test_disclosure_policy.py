"""The decision table behind what may leave the deployment (IR-127).

Pure, and deliberately so: this is the gate ADR-015 puts in front of every
outbound call to a commercial AI vendor, and a gate whose tests need a
database, a network or a clock is a gate nobody runs.
"""

from datetime import date

import pytest

from apps.ai.policy.disclosure import (
    Decision,
    DisclosureInputs,
    EmbargoUnknown,
    Reason,
    may_disclose,
)


def _inputs(**overrides) -> DisclosureInputs:
    """A record that is allowed to leave, unless a test says otherwise."""
    base = dict(
        is_ip=False,
        embargoed_until=None,
        consent_given=True,
        today=date(2026, 9, 15),
    )
    base.update(overrides)
    return DisclosureInputs(**base)


class AllowingTests:
    def test_an_unembargoed_consented_record_may_be_disclosed(self):
        assert may_disclose(_inputs()).allowed is True

    def test_an_expired_embargo_no_longer_refuses(self):
        decision = may_disclose(_inputs(embargoed_until=date(2026, 9, 14)))
        assert decision.allowed is True

    def test_an_embargo_expiring_today_no_longer_refuses(self):
        """The embargo runs *until* its date; on the day itself it is spent."""
        decision = may_disclose(_inputs(embargoed_until=date(2026, 9, 15)))
        assert decision.allowed is True


class RefusingTests:
    def test_a_record_under_embargo_is_refused_even_with_consent(self):
        decision = may_disclose(
            _inputs(embargoed_until=date(2026, 12, 1), consent_given=True)
        )
        assert decision.allowed is False
        assert Reason.EMBARGOED in decision.reasons

    def test_a_record_without_consent_is_refused_even_when_unembargoed(self):
        decision = may_disclose(_inputs(consent_given=False, embargoed_until=None))
        assert decision.allowed is False
        assert Reason.NO_CONSENT in decision.reasons

    def test_an_ip_record_is_refused(self):
        """Unpublished IP is the case KTTO cares about most: disclosing it to a
        third party can itself defeat a patent claim."""
        decision = may_disclose(_inputs(is_ip=True))
        assert decision.allowed is False
        assert Reason.UNRELEASED_IP in decision.reasons

    def test_every_failing_input_is_reported_not_just_the_first(self):
        """A refusal that names one cause sends the reader to fix one thing and
        be refused again."""
        decision = may_disclose(
            _inputs(is_ip=True, embargoed_until=date(2026, 12, 1), consent_given=False)
        )
        assert decision.allowed is False
        assert set(decision.reasons) == {
            Reason.UNRELEASED_IP,
            Reason.EMBARGOED,
            Reason.NO_CONSENT,
        }


class UnknownEmbargoTests:
    """There is no embargo field on `Record` yet. The policy must not paper
    over that by reading a missing value as "not embargoed"."""

    def test_an_unknown_embargo_is_refused_rather_than_assumed_absent(self):
        decision = may_disclose(_inputs(embargoed_until=EmbargoUnknown))
        assert decision.allowed is False
        assert Reason.EMBARGO_UNKNOWN in decision.reasons

    def test_an_unknown_embargo_refuses_even_when_everything_else_passes(self):
        decision = may_disclose(
            _inputs(embargoed_until=EmbargoUnknown, is_ip=False, consent_given=True)
        )
        assert decision.allowed is False


class DecisionValueTests:
    def test_a_decision_is_falsey_when_it_refuses(self):
        """So a caller cannot accidentally treat a refusal as permission by
        writing `if policy.may_disclose(...)`."""
        assert not may_disclose(_inputs(consent_given=False))
        assert may_disclose(_inputs())

    def test_an_allowing_decision_carries_no_reasons(self):
        assert may_disclose(_inputs()).reasons == ()

    def test_a_refusal_explains_itself_in_words(self):
        """The caller has to log why something was withheld; a bare enum makes
        every call site invent its own sentence."""
        decision = may_disclose(_inputs(is_ip=True))
        assert "IP" in decision.explain() or "intellectual property" in decision.explain().lower()

    def test_a_decision_cannot_be_mutated_after_the_fact(self):
        decision = may_disclose(_inputs())
        with pytest.raises(Exception):
            decision.allowed = False


class IndependentInputTests:
    """ADR-015 names three inputs. The point of keeping them separate is that
    a caller cannot collapse them into one flag and lose a case."""

    @pytest.mark.parametrize(
        "overrides",
        [
            dict(is_ip=True),
            dict(embargoed_until=date(2026, 12, 1)),
            dict(consent_given=False),
        ],
    )
    def test_any_single_failing_input_refuses_on_its_own(self, overrides):
        assert may_disclose(_inputs(**overrides)).allowed is False
