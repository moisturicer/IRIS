"""Mapping a Record onto the policy's three inputs (IR-127).

Tested against stubs rather than the ORM: the mapping is the interesting part
and it is pure, so making these database tests would buy nothing and cost the
ability to run them anywhere. Real rows are in ``test_embargo_rows.py``.
"""

import pytest

from apps.ai.policy.records import decision_for_record, inputs_for_record
from core.enums import EmbargoState


class _Record:
    """The three attributes the adapter reads, and nothing else."""

    def __init__(self, *, is_ip=False, dpa_accepted=True, embargo_state=EmbargoState.NONE):
        self.is_ip = is_ip
        self.dpa_accepted = dpa_accepted
        self.embargo_state = embargo_state


class RecordAdapterTests:
    def test_it_reads_the_ip_flag(self):
        assert inputs_for_record(_Record(is_ip=True)).is_ip is True
        assert inputs_for_record(_Record(is_ip=False)).is_ip is False

    def test_consent_comes_from_the_per_disclosure_dpa_stamp(self):
        """`Record.dpa_accepted` (IR-226), not `User.consent_given` -- the
        latter records that a person accepted terms once at signup, which is a
        different fact about a different subject."""
        assert inputs_for_record(_Record(dpa_accepted=True)).consent_given is True
        assert inputs_for_record(_Record(dpa_accepted=False)).consent_given is False

    @pytest.mark.parametrize("state", list(EmbargoState))
    def test_it_hands_over_the_embargo_state(self, state):
        assert inputs_for_record(_Record(embargo_state=state)).embargo is state

    def test_the_verdict_is_the_policy_applied_to_those_inputs(self):
        assert decision_for_record(_Record()).allowed is True
        assert decision_for_record(_Record(embargo_state=EmbargoState.UNKNOWN)).allowed is False
