"""IR-260: ADR-032's five public API paths start from migrated legacy data."""

from importlib import import_module

from django.apps import apps
from django.urls import reverse
from django.utils import timezone

from apps.records import versions
from apps.records.models import RecordVersion
from apps.reviews import seats
from apps.reviews.models import RecordAssignment, RecordClearance, Review, ReviewerSeat
from core.enums import RecordTypeName, VersionCause

from .test_decisions import DecisionTestBase
from .workflow_test_helpers import at_the_cutover_schema


retire_intake = import_module(
    "apps.reviews.migrations.0014_retire_intake_assignments"
).retire_intake


class MigratedApiJourneys(DecisionTestBase):
    def setUp(self):
        super().setUp()
        # Active intake assignments are what 0014 retires; IR-274 forbids them.
        at_the_cutover_schema()

    def migrated(self, type_name):
        record = self.make_record(type_name)
        if type_name == RecordTypeName.PROPOSAL:
            record.pipeline_status = "adviser_review"
            party = "adviser"
        else:
            record.pipeline_status = "rdco_intake"
            party = "intake"
        record.save(update_fields=["pipeline_status"])
        assignment = RecordAssignment.objects.create(record=record, party=party)
        if party == "adviser":
            ReviewerSeat.objects.create(
                assignment=assignment, reviewer=self.adviser, source="entry",
                assigned_at=timezone.now(),
            )
        versions.write_version(record, self.owner, VersionCause.SUBMISSION)
        retire_intake(apps, None)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, "in_review")
        self.adviser_seat(record)
        return record

    def new_version(self, record):
        self.client.force_authenticate(self.owner)
        edited = self.client.patch(
            reverse("record-detail", args=[record.pk]),
            {"abstract": "Revised evidence and methods after reviewer feedback. " * 2},
            format="json",
        )
        self.assertEqual(edited.status_code, 200, edited.data)
        response = self.post(reverse("record-new-version", args=[record.pk]), self.owner, {})
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_proposal_revise_v2_accept(self):
        record = self.migrated(RecordTypeName.PROPOSAL)
        self.asked(record, self.adviser)
        self.new_version(record)
        self.assertEqual(RecordVersion.objects.filter(record=record).latest("number").number, 2)
        self.decided(record, self.adviser, "accept")
        self.assertEqual(record.pipeline_status, "approved")

    def test_proposal_reject(self):
        record = self.migrated(RecordTypeName.PROPOSAL)
        self.decided(record, self.adviser, "reject", "The proposal duplicates existing work.")
        self.assertEqual(record.pipeline_status, "rejected")

    def test_thesis_adviser_only_publish(self):
        record = self.migrated(RecordTypeName.THESIS_RESEARCH)
        self.decided(record, self.adviser, "publish")
        self.assertEqual(record.pipeline_status, "published")

    def test_thesis_itso_ierc_revision_preserves_itso(self):
        record = self.migrated(RecordTypeName.THESIS_RESEARCH)
        self.accepted_to(record, "itso", "ierc")
        self.opened_seat(record, "itso", self.itso)
        self.opened_seat(record, "ierc", self.ierc)
        self.cleared(record, self.itso)
        self.asked(record, self.ierc)
        self.new_version(record)
        self.assertEqual(RecordClearance.objects.get(record=record, office="itso").status, "cleared")
        self.assertEqual(RecordVersion.objects.filter(record=record).latest("number").number, 2)

    def test_project_ktto_rdco_keep_unlisted(self):
        record = self.migrated(RecordTypeName.PROJECT)
        self.accepted_to(record, "ktto")
        self.opened_seat(record, "ktto", self.ktto)
        self.cleared(record, self.ktto)
        assignment = RecordAssignment.objects.get(record=record, party="rdco", state="active")
        seats.open_review(seats.claim(assignment, self.rdco), self.rdco)
        self.decided(record, self.rdco, "keep_unlisted")
        self.assertEqual(record.pipeline_status, "completed")

    def test_retired_review_and_resubmit_endpoints_write_nothing(self):
        record = self.migrated(RecordTypeName.THESIS_RESEARCH)
        review_count = Review.objects.filter(record=record).count()
        old_review = self.post(
            "/api/v1/reviews/submit/", self.adviser,
            {"record_id": record.pk, "status": "approved", "comment": "Old form"},
        )
        old_resubmit = self.post(
            "/api/v1/reviews/resubmit/", self.owner, {"record_id": record.pk},
        )
        self.assertEqual((old_review.status_code, old_resubmit.status_code), (410, 410))
        self.assertEqual(Review.objects.filter(record=record).count(), review_count)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, "in_review")
