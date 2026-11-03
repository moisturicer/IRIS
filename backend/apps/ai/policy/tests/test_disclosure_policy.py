"""The decision table behind what may leave the deployment (IR-127, ADR-052).

Pure, and deliberately so: this is the gate ADR-015 puts in front of every
outbound call to a commercial AI vendor, and a gate whose tests need a
database, a network or a clock is a gate nobody runs.

The policy reads a paper's embargo *state* and never a date (ADR-052 §9), so
there is no boundary to test here. That a passed date stays refused is asserted
against real rows in ``test_embargo_rows.py``.
"""

import pytest

from apps.ai.policy.disclosure import DisclosureInputs, Reason, may_disclose
from core.enums import EmbargoState


def _inputs(**overrides) -> DisclosureInputs:
    """A record that is allowed to leave, unless a test says otherwise."""
    base = dict(is_ip=False, embargo=EmbargoState.NONE, consent_given=True)
    base.update(overrides)
    return DisclosureInputs(**base)


class EmbargoStateTests:
    """ADR-052 §3's table: two states allow and two refuse."""

    @pytest.mark.parametrize("state", [EmbargoState.NONE, EmbargoState.RELEASED])
    def test_an_answered_no_or_a_release_allows(self, state):
        assert may_disclose(_inputs(embargo=state)).allowed is True

    def test_an_active_embargo_is_refused_even_with_consent(self):
        decision = may_disclose(_inputs(embargo=EmbargoState.ACTIVE, consent_given=True))
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGOED,)

    def test_an_unanswered_paper_is_refused_when_everything_else_passes(self):
        decision = may_disclose(
            _inputs(embargo=EmbargoState.UNKNOWN, is_ip=False, consent_given=True)
        )
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGO_UNKNOWN,)

    @pytest.mark.parametrize("value", ["", "expired", None])
    def test_a_state_the_policy_does_not_know_refuses(self, value):
        """Fails closed. ADR-052 replaced the "expired" state, and a value that
        reaches this gate by mistake must never read as permission."""
        decision = may_disclose(_inputs(embargo=value))
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGO_UNKNOWN,)


class RefusingTests:
    def test_a_record_without_consent_is_refused_even_when_unembargoed(self):
        decision = may_disclose(_inputs(consent_given=False, embargo=EmbargoState.NONE))
        assert decision.allowed is False
        assert Reason.NO_CONSENT in decision.reasons

    def test_an_ip_record_is_refused(self):
        """Unpublished IP is the case KTTO cares about most: disclosing it to a
        third party can itself defeat a patent claim."""
        decision = may_disclose(_inputs(is_ip=True))
        assert decision.allowed is False
        assert Reason.UNRELEASED_IP in decision.reasons

    def test_an_ip_mark_is_unreleased_unless_said_otherwise(self):
        assert DisclosureInputs(
            is_ip=True, embargo=EmbargoState.NONE, consent_given=True,
        ).ip_released is False


class IpReleaseTests:
    """ADR-052 §11-13: KTTO's release opens the gate for a marked paper."""

    def test_a_released_mark_allows(self):
        assert may_disclose(_inputs(is_ip=True, ip_released=True)).allowed is True

    def test_a_release_without_a_mark_changes_nothing(self):
        assert may_disclose(_inputs(is_ip=False, ip_released=True)).allowed is True

    @pytest.mark.parametrize("state", [EmbargoState.ACTIVE, EmbargoState.UNKNOWN])
    def test_a_released_mark_does_not_release_an_embargo(self, state):
        decision = may_disclose(_inputs(is_ip=True, ip_released=True, embargo=state))
        assert decision.allowed is False
        assert Reason.UNRELEASED_IP not in decision.reasons

    def test_a_released_embargo_does_not_release_a_mark(self):
        decision = may_disclose(_inputs(is_ip=True, embargo=EmbargoState.RELEASED))
        assert decision.reasons == (Reason.UNRELEASED_IP,)

    def test_both_released_still_needs_consent(self):
        decision = may_disclose(_inputs(
            is_ip=True, ip_released=True, embargo=EmbargoState.RELEASED, consent_given=False,
        ))
        assert decision.reasons == (Reason.NO_CONSENT,)


class ReportingTests:
    def test_every_failing_input_is_reported_not_just_the_first(self):
        """A refusal that names one cause sends the reader to fix one thing and
        be refused again."""
        decision = may_disclose(
            _inputs(is_ip=True, embargo=EmbargoState.ACTIVE, consent_given=False)
        )
        assert decision.allowed is False
        assert set(decision.reasons) == {
            Reason.UNRELEASED_IP,
            Reason.EMBARGOED,
            Reason.NO_CONSENT,
        }


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
            dict(embargo=EmbargoState.ACTIVE),
            dict(consent_given=False),
        ],
    )
    def test_any_single_failing_input_refuses_on_its_own(self, overrides):
        assert may_disclose(_inputs(**overrides)).allowed is False
