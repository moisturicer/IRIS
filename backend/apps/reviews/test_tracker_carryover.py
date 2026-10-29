"""
The tracker names what a new version kept and what it reset (IR-624).

ADR-003's contribution, stated per office with the version each applies to,
so the Review section renders it without inferring either: ITSO cleared v1,
IERC asked for a revision, the owner submitted v2. ITSO's clearance is
preserved from v1; IERC's is reset by v2 until IERC reviews it.

`test_clearance_state.py` proves the rule; this proves the tracker carries it
through a real revision cycle, to each kind of viewer.
"""

from core.enums import Party

from .test_new_version import NewVersionTestBase


class TrackerCarryoverTests(NewVersionTestBase):

    def resubmitted(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)
        self.submitted(record)
        return record

    def carryover(self, row):
        return (row["carryover"], row["carryover_version"], row["carryover_label"])

    def test_nothing_is_kept_or_reset_before_a_new_version(self):
        record = self.itso_cleared_and_ierc_asked()

        rows = self.rows(self.tracker(record))
        self.assertEqual(self.carryover(rows[Party.ITSO]), (None, None, None))
        self.assertEqual(self.carryover(rows[Party.IERC]), (None, None, None))

    def test_the_office_that_cleared_is_preserved_and_the_one_that_asked_is_reset(self):
        record = self.resubmitted()

        rows = self.rows(self.tracker(record))
        self.assertEqual(
            self.carryover(rows[Party.ITSO]), ("preserved", 1, "Cleared on v1, preserved"),
        )
        self.assertEqual(self.carryover(rows[Party.IERC]), ("reset", 2, "Reset by v2"))
        # Parties that hold no clearance carry nothing over.
        self.assertEqual(self.carryover(rows[Party.ADVISER]), (None, None, None))

    def test_the_clearance_payload_says_the_same(self):
        record = self.resubmitted()

        for payload in (self.tracker(record), self.detail(record, self.owner)):
            by_office = {c["office"]: c for c in payload["clearances"]}
            self.assertEqual(self.carryover(by_office[Party.ITSO]), ("preserved", 1, "Cleared on v1, preserved"))
            self.assertEqual(self.carryover(by_office[Party.IERC]), ("reset", 2, "Reset by v2"))

    def test_once_the_office_reviews_the_new_version_it_is_no_longer_reset(self):
        record = self.resubmitted()

        self.cleared(record, self.ierc)

        rows = self.rows(self.tracker(record))
        self.assertEqual(self.carryover(rows[Party.IERC]), (None, None, None))
        self.assertEqual(rows[Party.ITSO]["carryover"], "preserved")

    def test_a_viewer_who_may_not_read_the_review_still_sees_what_was_kept(self):
        """What was kept and reset is an outcome, not review content: a
        non-participant office member reads it, and still no seat names."""
        record = self.resubmitted()

        self.client.force_authenticate(self.rdco2)
        response = self.client.get(f"/api/v1/records/{record.pk}/tracker/")
        self.assertEqual(response.status_code, 200)
        rows = self.rows(response.data)
        self.assertEqual(rows[Party.ITSO]["carryover"], "preserved")
        self.assertEqual(rows[Party.IERC]["carryover"], "reset")
        self.assertIsNone(rows[Party.ITSO]["seats"])
        self.assertIsNone(response.data["reviews"])
