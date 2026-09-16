"""Mapping a Record onto the policy's three inputs (IR-127).

Tested against stubs rather than the ORM: the mapping is the interesting part
and it is pure, so making these database tests would buy nothing and cost the
ability to run them anywhere.
"""

from datetime import date

from apps.ai.policy.disclosure import EmbargoUnknown, Reason, may_disclose
from apps.ai.policy.records import inputs_for_record


class _Record:
    """The three attributes the adapter reads, and nothing else."""

    def __init__(self, *, is_ip=False, dpa_accepted=True, **extra):
        self.is_ip = is_ip
        self.dpa_accepted = dpa_accepted
        for name, value in extra.items():
            setattr(self, name, value)


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

    def test_embargo_is_unknown_while_the_model_carries_no_such_field(self):
        """`Record` has no embargo field. The adapter must say so rather than
        report "not embargoed", which would send unpublished work to a vendor
        on the strength of a field nobody implemented."""
        assert inputs_for_record(_Record()).embargoed_until is EmbargoUnknown

    def test_a_record_with_no_embargo_field_is_refused_end_to_end(self):
        decision = may_disclose(inputs_for_record(_Record(is_ip=False, dpa_accepted=True)))
        assert decision.allowed is False
        assert Reason.EMBARGO_UNKNOWN in decision.reasons

    def test_the_adapter_starts_honouring_an_embargo_field_the_day_it_exists(self):
        """Read with `getattr`, so adding the field to `Record` is all that is
        needed -- this adapter does not also have to be remembered."""
        record = _Record(embargoed_until=date(2026, 12, 1))
        inputs = inputs_for_record(record, today=date(2026, 9, 15))
        assert inputs.embargoed_until == date(2026, 12, 1)
        assert Reason.EMBARGOED in may_disclose(inputs).reasons

    def test_an_explicit_null_embargo_means_known_not_embargoed(self):
        record = _Record(embargoed_until=None)
        inputs = inputs_for_record(record, today=date(2026, 9, 15))
        assert inputs.embargoed_until is None
        assert may_disclose(inputs).allowed is True

    def test_today_is_injectable_so_a_boundary_is_testable(self):
        inputs = inputs_for_record(_Record(), today=date(2020, 1, 1))
        assert inputs.today == date(2020, 1, 1)

    def test_today_defaults_to_the_real_date_when_not_supplied(self):
        assert inputs_for_record(_Record()).today == date.today()
