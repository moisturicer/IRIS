"""Mapping a Record onto the policy's three inputs (IR-127).

Tested against stubs rather than the ORM: the mapping is the interesting part
and it is pure, so making these database tests would buy nothing and cost the
ability to run them anywhere. Real rows are in ``test_embargo_rows.py``.
"""

import pytest

from apps.ai.policy.records import decision_for_record, inputs_for_record
from core.enums import EmbargoState


class _Record:
    """The attributes the adapter reads, and nothing else."""

    def __init__(self, *, is_ip=False, ip_released=False, ai_consent=True,
                 embargo_state=EmbargoState.RELEASED):
        self.is_ip = is_ip
        self.ip_released = ip_released
        self.ai_consent = ai_consent
        self.embargo_state = embargo_state


class RecordAdapterTests:
    def test_it_reads_the_ip_flag(self):
        assert inputs_for_record(_Record(is_ip=True)).is_ip is True
        assert inputs_for_record(_Record(is_ip=False)).is_ip is False

    def test_it_reads_ktto_s_release_of_the_mark(self):
        assert inputs_for_record(_Record(is_ip=True, ip_released=True)).ip_released is True
        assert inputs_for_record(_Record(is_ip=True)).ip_released is False

    @pytest.mark.parametrize(("stored", "given"), [(True, True), (False, False), (None, False)])
    def test_consent_is_the_answer_the_paper_keeps(self, stored, given):
        """`Record.ai_consent` (ADR-054 decisions 9-10, IR-791), replacing the
        per-paper stamp `Record.dpa_accepted` deliberately. Only True is consent:
        a No and no stored answer are both refused."""
        assert inputs_for_record(_Record(ai_consent=stored)).consent_given is given

    @pytest.mark.parametrize("state", list(EmbargoState))
    def test_it_hands_over_the_embargo_state(self, state):
        assert inputs_for_record(_Record(embargo_state=state)).embargo is state

    def test_the_verdict_is_the_policy_applied_to_those_inputs(self):
        assert decision_for_record(_Record()).allowed is True
        assert decision_for_record(_Record(embargo_state=EmbargoState.ACTIVE)).allowed is False
