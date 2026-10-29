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
    carryover,
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


class CarryoverTests:
    """Preserved *or reset*, with the version each applies to (IR-624). The
    client renders whichever the server names and infers neither."""

    # v1 went in before any clearance; v2 and v3 are revisions.
    V1, V2, V3 = T0 - timedelta(days=1), LATER, LATER_STILL + timedelta(days=1)
    VERSIONS = [(1, V1, "submission"), (2, V2, "revision"), (3, V3, "revision")]

    def _carryover(self, status, *, created=T0, updated=T0, resubmitted=LATER, versions=None):
        return carryover(
            status=status, clearance_created_at=created, clearance_updated_at=updated,
            last_resubmitted_at=resubmitted,
            versions=self.VERSIONS[:2] if versions is None else versions,
        )

    def test_a_clearance_that_survived_the_version_names_the_version_it_was_cleared_on(self):
        """Cleared on v1, kept through v2."""
        assert self._carryover("cleared") == ("preserved", 1)
        assert self._carryover("cleared").label == "Cleared on v1, preserved"

    def test_a_clearance_the_version_set_back_to_pending_is_reset_by_it(self):
        """IERC asked; `submit_new_version` wrote v2, then reset IERC's row."""
        reset = self._carryover("pending", updated=LATER + timedelta(seconds=1))
        assert reset == ("reset", 2)
        assert reset.label == "Reset by v2"

    def test_a_reset_survives_a_later_version_it_did_not_touch(self):
        """IERC reset by v2 and still pending when another party's revision
        makes v3: IERC still waits on its review of the resubmission, so it is
        still reset -- by v2, which is what set it back."""
        reset = self._carryover(
            "pending", updated=LATER + timedelta(seconds=1),
            resubmitted=self.V3, versions=self.VERSIONS,
        )
        assert reset == ("reset", 2)

    def test_restart_all_resets_an_office_that_had_not_concluded(self):
        """RESTART_ALL rewrites every row, pending ones included: that office's
        review restarts on the new version, which is what reset means."""
        assert self._carryover("pending", updated=LATER + timedelta(seconds=1)) == ("reset", 2)

    def test_an_office_still_undecided_and_untouched_is_neither(self):
        """Pending since before the version and not reset by it."""
        assert self._carryover("pending", updated=T0) is None

    def test_an_office_first_routed_after_the_version_is_not_reset(self):
        """A row created after the version was never set back."""
        assert self._carryover("pending", created=LATER_STILL, updated=LATER_STILL) is None

    def test_an_office_that_reviewed_the_new_version_is_neither(self):
        """Re-cleared, or found against, on the new version: ordinary review."""
        assert self._carryover("cleared", updated=LATER_STILL) is None
        assert self._carryover("not_cleared", updated=LATER_STILL) is None

    def test_nothing_carries_over_on_a_record_never_resubmitted(self):
        assert self._carryover("cleared", resubmitted=None, versions=self.VERSIONS[:1]) is None
        assert self._carryover("pending", resubmitted=None, versions=self.VERSIONS[:1]) is None

    def test_no_version_is_invented(self):
        """Versions began with IR-416. A resubmission the retired pipeline
        recorded with no version still carries over, naming none."""
        kept = self._carryover("cleared", versions=[])
        assert kept == ("preserved", None)
        assert kept.label == "Cleared earlier, preserved"
        reset = self._carryover("pending", updated=LATER, versions=[])
        assert reset == ("reset", None)
        assert reset.label == "Reset by the new version"


class DecliningOfficeTests:
    def test_a_clearance_office_decline_names_that_office(self):
        assert declining_office("ierc") == "ierc"

    def test_every_clearance_office_is_nameable(self):
        for office in CLEARANCE_OFFICES:
            assert declining_office(office) == office

    def test_a_party_that_clears_nothing_names_no_office(self):
        """The Adviser, RDCO and the retired intake hold no clearance, so a
        revision they asked for names no office; inventing one would imply a
        preservation nobody performed. IR-274 corrected the inputs: they were
        pipeline *statuses* (`adviser_review`, `rdco_review`), which a
        `Review.stage` never holds, plus the removed `rdco_intake`."""
        for stage in ("adviser", "intake", "rdco"):
            assert declining_office(stage) is None

    def test_no_decline_names_no_office(self):
        assert declining_office(None) is None


class RestartAllPolicyTests:
    """Under RESTART_ALL (IR-137) a new version resets every clearance, so
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
