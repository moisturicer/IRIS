"""The rule that carries the thesis contribution (IR-139).

`preserved` distinguishes a clearance that *survived* a resubmission from one
granted again afterwards. That distinction is the observable form of
clearance-aware resubmission -- if the payload cannot express it, an evaluator
cannot count it, and the contribution is indistinguishable from not having been
built.

These are pure: no Django, no database. The rule is worth testing separately
from the plumbing that carries it.
"""

from datetime import datetime, timedelta, timezone as tz

from apps.reviews.clearance_state import (
    CLEARANCE_OFFICES,
    declining_office,
    is_preserved,
)

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=tz.utc)
LATER = T0 + timedelta(days=3)
LATER_STILL = LATER + timedelta(days=1)


class IsPreservedTests:
    def test_a_clearance_decided_before_the_resubmission_is_preserved(self):
        """The contribution: IERC declines, ITSO's earlier clearance survives."""
        assert is_preserved(
            status="cleared", clearance_updated_at=T0, last_resubmitted_at=LATER
        ) is True

    def test_a_clearance_granted_after_the_resubmission_is_not_preserved(self):
        """It was re-granted, which is ordinary review, not preservation."""
        assert is_preserved(
            status="cleared", clearance_updated_at=LATER_STILL, last_resubmitted_at=LATER
        ) is False

    def test_nothing_is_preserved_on_a_record_never_resubmitted(self):
        """Every clearance on a first pass was granted, not preserved. Counting
        these would inflate the number the evaluation reports."""
        assert is_preserved(
            status="cleared", clearance_updated_at=T0, last_resubmitted_at=None
        ) is False

    def test_a_pending_clearance_is_not_preserved(self):
        assert is_preserved(
            status="pending", clearance_updated_at=T0, last_resubmitted_at=LATER
        ) is False

    def test_a_declined_clearance_is_not_preserved(self):
        """The declining office is the one that reset -- the opposite of preserved."""
        assert is_preserved(
            status="declined", clearance_updated_at=T0, last_resubmitted_at=LATER
        ) is False

    def test_a_rejected_clearance_is_not_preserved(self):
        assert is_preserved(
            status="rejected", clearance_updated_at=T0, last_resubmitted_at=LATER
        ) is False

    def test_a_clearance_with_no_timestamp_is_not_preserved(self):
        assert is_preserved(
            status="cleared", clearance_updated_at=None, last_resubmitted_at=LATER
        ) is False

    def test_the_boundary_is_strict(self):
        """Decided at the exact resubmission instant is not 'before' it. Ties go
        to not-preserved, so the reported number is never flattered."""
        assert is_preserved(
            status="cleared", clearance_updated_at=LATER, last_resubmitted_at=LATER
        ) is False


class DecliningOfficeTests:
    def test_a_clearance_office_decline_names_that_office(self):
        assert declining_office("ierc") == "ierc"

    def test_every_clearance_office_is_nameable(self):
        for office in CLEARANCE_OFFICES:
            assert declining_office(office) == office

    def test_a_sequential_stage_decline_names_no_office(self):
        """A decline at adviser/RDCO deletes every clearance -- there is no
        office to name, and inventing one would imply a preservation that
        `resubmit_record` did not perform."""
        for stage in ("adviser_review", "rdco_intake", "rdco_review"):
            assert declining_office(stage) is None

    def test_no_decline_names_no_office(self):
        assert declining_office(None) is None


class RestartAllPolicyTests:
    """Under RESTART_ALL (IR-137) `resubmit_record` deletes every clearance, so
    there is nothing to preserve and the UI needs no policy branch -- the same
    payload shape answers both policies with an empty list."""

    def test_no_clearances_means_nothing_preserved_and_no_error(self):
        preserved = [
            office
            for office, status, ts in []  # a restarted record has no clearance rows
            if is_preserved(
                status=status, clearance_updated_at=ts, last_resubmitted_at=LATER
            )
        ]
        assert preserved == []
