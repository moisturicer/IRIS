"""
The clearance strip (IR-1083, audit spec §4.4).

Which clearances a resubmission kept is the thesis contribution, and until
this ticket it could be read only inside the record. The strip says it on
every list that names the record -- My Reviews, the office console, My
Library -- and inside the record, from one builder, in the server's words.

`test_tracker_carryover.py` proves the rule; this proves the strip states it,
the same on every surface, in a flat number of queries.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from core.enums import Party

from .clearance_strip import clearance_strips
from .test_new_version import NewVersionTestBase

MINE = "/api/v1/reviews/mine/"


def by_party(strip):
    return {entry["party"]: entry for entry in strip}


def words(entry):
    """What a reader sees: the text, then the note when there is one."""
    return " · ".join(part for part in (entry["text"], entry["note"]) if part)


class ClearanceStripTests(NewVersionTestBase):

    def resubmitted(self):
        """ITSO cleared v1, IERC asked for a revision, the owner sent v2."""
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)
        self.submitted(record)
        return record

    def strip(self, record):
        return by_party(clearance_strips([record.pk])[record.pk])

    # -- the builder ---------------------------------------------------------

    def test_a_kept_clearance_reads_kept_from_the_version_it_was_cleared_on(self):
        strip = self.strip(self.resubmitted())

        self.assertEqual(strip[Party.ITSO]["kind"], "kept")
        self.assertEqual(words(strip[Party.ITSO]), "Cleared · Kept from v1")

    def test_a_reset_clearance_is_being_reviewed_again_and_says_which_version_reset_it(self):
        strip = self.strip(self.resubmitted())

        self.assertEqual(strip[Party.IERC]["kind"], "reviewing")
        self.assertEqual(words(strip[Party.IERC]), "Reviewing v2 · Reset by v2")

    def test_before_a_new_version_nothing_is_kept_or_reset(self):
        strip = self.strip(self.itso_cleared_and_ierc_asked())

        self.assertEqual((strip[Party.ITSO]["kind"], words(strip[Party.ITSO])), ("cleared", "Cleared"))
        self.assertEqual(
            (strip[Party.IERC]["kind"], words(strip[Party.IERC])),
            ("revision", "Asked for revision"),
        )

    def test_an_office_nobody_has_claimed_is_unclaimed(self):
        strip = self.strip(self.thesis(Party.KTTO))

        self.assertEqual((strip[Party.KTTO]["kind"], words(strip[Party.KTTO])), ("unclaimed", "Unclaimed"))

    def test_an_office_never_routed_the_record_is_not_drawn(self):
        strip = self.strip(self.thesis(Party.KTTO))

        self.assertNotIn(Party.ITSO, strip)
        self.assertNotIn(Party.IERC, strip)

    def test_once_the_office_clears_the_new_version_it_is_no_longer_reset(self):
        record = self.resubmitted()

        self.cleared(record, self.ierc)

        strip = self.strip(record)
        self.assertEqual((strip[Party.IERC]["kind"], words(strip[Party.IERC])), ("cleared", "Cleared"))
        self.assertEqual(words(strip[Party.ITSO]), "Cleared · Kept from v1")

    def test_it_carries_no_review_content(self):
        entry = self.strip(self.resubmitted())[Party.IERC]

        self.assertEqual(
            set(entry), {"party", "label", "kind", "text", "note", "version"},
        )

    def test_the_query_count_is_flat_in_the_records(self):
        def queries(ids):
            with CaptureQueriesContext(connection) as ctx:
                clearance_strips(ids)
            return len(ctx)

        first = self.resubmitted()
        small = queries([first.pk])
        more = [self.resubmitted().pk for _ in range(3)]
        self.assertEqual(queries([first.pk, *more]), small)

    # -- every surface says the same ----------------------------------------

    def test_my_reviews_rows_carry_it(self):
        record = self.resubmitted()
        self.client.force_authenticate(self.ierc)

        response = self.client.get(MINE, {"tab": "in_review"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [row] = [r for r in response.data["rows"] if r["record"] == record.pk]
        strip = by_party(row["clearance_strip"])
        self.assertEqual(words(strip[Party.ITSO]), "Cleared · Kept from v1")
        self.assertEqual(words(strip[Party.IERC]), "Reviewing v2 · Reset by v2")

    def test_the_office_console_rows_carry_it(self):
        record = self.resubmitted()
        self.ierc.is_office_coordinator = True
        self.ierc.save(update_fields=["is_office_coordinator"])
        self.client.force_authenticate(self.ierc)

        response = self.client.get(reverse("reviews-office"), {"office": "ierc"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [row] = [r for r in response.data["rows"] if r["record"] == record.pk]
        strip = by_party(row["clearance_strip"])
        self.assertEqual(words(strip[Party.ITSO]), "Cleared · Kept from v1")
        self.assertEqual(words(strip[Party.IERC]), "Reviewing v2 · Reset by v2")

    def test_my_library_rows_carry_it(self):
        record = self.resubmitted()
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("record-mine"))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [row] = [r for r in response.data if r["id"] == record.pk]
        strip = by_party(row["clearance_strip"])
        self.assertEqual(words(strip[Party.ITSO]), "Cleared · Kept from v1")
        self.assertEqual(words(strip[Party.IERC]), "Reviewing v2 · Reset by v2")

    def test_the_record_tracker_says_the_same_as_its_row_in_a_list(self):
        record = self.resubmitted()

        in_the_record = self.tracker(record)["clearance_strip"]

        self.assertEqual(in_the_record, clearance_strips([record.pk])[record.pk])
        self.assertEqual(words(by_party(in_the_record)[Party.ITSO]), "Cleared · Kept from v1")
