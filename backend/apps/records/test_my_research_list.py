"""
`GET /records/mine/` -- My Library's *My research* list (IR-410).

The list carries only what My Library shows, not Record detail: a status line
from `workflow_state_label`, the next step from `workflow_state`, and enough
to draw a card (spec §4.9). It used to serialize every owned record with
`RecordDetailSerializer`, which cost about 15.6 queries per record (Jira
IR-410, comment 10547). Settled with the project lead on 2026-10-07: the list
gets its own serializer, and **its query count does not grow with the number
of records**.

**Seam: the records API.** Records reach each state through the public
endpoints, using the tracker tests' drivers; a document request is the
documents app's fixture shape, written directly.
"""

from django.db import connection
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.records.models import RecordOwner
from apps.records.test_tracker import TrackerTestBase
from apps.reviews.models import RecordAssignment
from core.enums import Party, PipelineStatus, RecordTypeName

MINE = reverse("record-mine")

#: Exactly what a *My research* card reads (frontend `MyResearchItem`).
LIST_FIELDS = {
    "id", "title", "record_type_name", "authors", "adviser_name",
    "pipeline_status", "workflow_state", "workflow_state_label",
    "holders", "cleared_offices", "submitter_status", "created_at", "updated_at", "can_continue",
}


class MyResearchListTestBase(TrackerTestBase):

    def mine(self, params=None, viewer=None):
        self.client.force_authenticate(viewer or self.owner)
        response = self.client.get(MINE, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"]: row for row in response.data}

    def revision_requested(self):
        record = self.at_parallel_review()
        seat = RecordAssignment.objects.get(record=record, party="ierc").seats.get(
            reviewer=self.ierc,
        )
        self.client.force_authenticate(self.ierc)
        opened = self.client.post(f"/api/v1/seats/{seat.pk}/open/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)
        requested = self.client.post(
            reverse("record-request-revision", args=[record.pk]),
            {"reason": "Please revise the consent procedure."}, format="json",
        )
        self.assertEqual(requested.status_code, status.HTTP_200_OK, requested.data)
        return record

    def document_requested(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        DocumentRequest.objects.create(
            record=record,
            assignment=RecordAssignment.objects.get(record=record, party=Party.ADVISER),
            party=Party.ADVISER, requested_by=self.adviser, message="The signed form, please.",
        )
        return record

    def one_of_each(self):
        """A record in every state an owner's list can show."""
        return [
            self.make_record(RecordTypeName.THESIS_RESEARCH),
            self.submitted(RecordTypeName.PROPOSAL),
            self.at_parallel_review(),
            self.revision_requested(),
            self.document_requested(),
        ]


class PayloadTests(MyResearchListTestBase):

    def test_a_row_carries_only_what_my_library_shows(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        row = self.mine()[record.pk]

        self.assertEqual(set(row), LIST_FIELDS)
        self.assertEqual(row["record_type_name"], RecordTypeName.THESIS_RESEARCH)
        self.assertEqual(row["adviser_name"], self.adviser.get_full_name())

    def test_the_seat_fields_and_review_blocks_have_left_the_list(self):
        """IR-415's two fields leave as a side effect (comment 10547)."""
        record = self.at_parallel_review()
        row = self.mine()[record.pk]

        for field in ("my_seats", "is_participant", "clearances", "capabilities", "reviews"):
            self.assertNotIn(field, row)

    def test_the_workflow_state_is_the_detail_payloads(self):
        """One derivation: the list never disagrees with Paper View."""
        records = self.one_of_each()
        rows = self.mine()

        for record in records:
            detail = self.detail(record)
            with self.subTest(state=detail["workflow_state"]):
                self.assertEqual(rows[record.pk]["workflow_state"], detail["workflow_state"])
                self.assertEqual(
                    rows[record.pk]["workflow_state_label"], detail["workflow_state_label"],
                )

    def test_every_owner_action_state_is_reported(self):
        """What *Needs my action* and the next-step line read (spec §4.9)."""
        revision = self.revision_requested()
        document = self.document_requested()
        rows = self.mine()

        self.assertEqual(rows[revision.pk]["workflow_state"], "awaiting_resubmission")
        self.assertEqual(rows[document.pk]["workflow_state"], "awaiting_document")


class HolderTests(MyResearchListTestBase):
    """
    Who has each record now, and which offices have cleared it: what My
    Library groups its research by (IR-410, redesigned 2026-10-11). Both come
    from rows the bulk query already reads, so neither is worked out on the
    client.
    """

    def test_a_record_in_parallel_review_is_held_by_the_offices_still_reviewing(self):
        record = self.at_parallel_review()
        row = self.mine()[record.pk]

        self.assertEqual(
            [h["party"] for h in row["holders"]], [Party.IERC, Party.KTTO],
        )
        self.assertEqual([h["label"] for h in row["holders"]], ["IERC", "KTTO"])
        self.assertEqual(
            row["cleared_offices"],
            [{"office": "itso", "label": "ITSO", "preserved": False}],
        )

    def test_a_submitted_record_is_held_by_its_adviser(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        row = self.mine()[record.pk]

        self.assertEqual([h["party"] for h in row["holders"]], [Party.ADVISER])
        self.assertEqual(row["cleared_offices"], [])

    def test_a_draft_is_held_by_nobody(self):
        record = self.make_record(RecordTypeName.THESIS_RESEARCH)
        row = self.mine()[record.pk]

        self.assertEqual(row["holders"], [])
        self.assertEqual(row["cleared_offices"], [])

    def test_a_kept_clearance_agrees_with_record_detail(self):
        """
        The thesis contribution on the card: a clearance that survived a
        resubmission is marked kept, by the same rule Record detail uses. The
        resubmission is stamped directly: what is under test is the list
        agreeing with `clearance_state.is_preserved`, not the act itself
        (`apps/reviews/test_new_version.py` covers that).
        """
        record = self.at_parallel_review()
        record.last_resubmitted_at = timezone.now()
        record.save(update_fields=["last_resubmitted_at"])

        row = self.mine()[record.pk]
        detail = {c["office"]: c for c in self.detail(record)["clearances"]}

        self.assertEqual(row["cleared_offices"][0]["office"], "itso")
        self.assertTrue(row["cleared_offices"][0]["preserved"])
        self.assertEqual(row["cleared_offices"][0]["preserved"], detail["itso"]["preserved"])


class ScopeTests(MyResearchListTestBase):

    def test_only_the_callers_own_records_are_listed(self):
        mine = self.submitted(RecordTypeName.THESIS_RESEARCH)
        theirs = self.make_record(RecordTypeName.THESIS_RESEARCH)
        RecordOwner.objects.filter(record=theirs).update(user=self.stranger)

        rows = self.mine()

        self.assertIn(mine.pk, rows)
        self.assertNotIn(theirs.pk, rows)

    def test_the_pipeline_status_filter_still_narrows(self):
        draft = self.make_record(RecordTypeName.THESIS_RESEARCH)
        in_review = self.submitted(RecordTypeName.THESIS_RESEARCH)

        rows = self.mine({"pipeline_status": PipelineStatus.DRAFT})

        self.assertIn(draft.pk, rows)
        self.assertNotIn(in_review.pk, rows)

    def test_a_co_owned_record_is_listed_once(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        RecordOwner.objects.create(record=record, user=self.stranger, is_primary=False)

        self.client.force_authenticate(self.owner)
        ids = [row["id"] for row in self.client.get(MINE).data]

        self.assertEqual(ids.count(record.pk), 1)

    def test_the_newest_change_comes_first(self):
        older = self.make_record(RecordTypeName.THESIS_RESEARCH)
        newer = self.make_record(RecordTypeName.PROJECT)
        older.title = "Edited later"
        older.save(update_fields=["title", "updated_at"])

        self.client.force_authenticate(self.owner)
        ids = [row["id"] for row in self.client.get(MINE).data]

        self.assertLess(ids.index(older.pk), ids.index(newer.pk))


class QueryCountTests(MyResearchListTestBase):

    def test_the_query_count_does_not_grow_with_the_records(self):
        """
        Settled 2026-10-07 (comment 10547): a flat count, not a ceiling, so
        legitimately adding a field never breaks it. Each round adds one
        record in every state, so every per-record fact is exercised.
        """
        def queries():
            self.client.force_authenticate(self.owner)
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(MINE).status_code, status.HTTP_200_OK)
            return len(ctx)

        self.one_of_each()
        small = queries()
        for _ in range(4):
            self.one_of_each()
        large = queries()

        self.assertEqual(small, large)
