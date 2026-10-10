"""IR-260: intake retirement preserves history and refuses to guess an Adviser."""

from importlib import import_module
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.documents.models import DocumentRequest
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import (
    RecordAssignment, ResubmissionRequest, Review, ReviewerSeat, RoutingEvent,
)


retire_intake = import_module(
    "apps.reviews.migrations.0014_retire_intake_assignments"
).retire_intake


class IntakeRetirementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def user(email, role_name):
            role, _ = Role.objects.get_or_create(name=role_name)
            return User.objects.create_user(email=email, password="TestPass123!", role=role)

        cls.owner = user("ir260-owner@cit.edu", "Student")
        cls.adviser = user("ir260-adviser@cit.edu", "Adviser")
        cls.rdco = user("ir260-rdco@cit.edu", "RDCO")
        cls.record_type, _ = RecordType.objects.get_or_create(name="Thesis / Research")

    def intake_record(self, title, adviser=None):
        record = Record.objects.create(
            title=title, record_type=self.record_type, added_by=self.owner,
            adviser=adviser, pipeline_status="rdco_intake",
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        assignment = RecordAssignment.objects.create(record=record, party="intake")
        return record, assignment

    def test_named_adviser_receives_entry_seat_and_intake_history_stays(self):
        record, intake = self.intake_record("With adviser", self.adviser)
        old_review = Review.objects.create(
            record=record, reviewed_by=self.rdco, stage="rdco_intake",
            status="approved", assignment=intake,
        )

        retire_intake(apps, None)
        retire_intake(apps, None)

        record.refresh_from_db()
        intake.refresh_from_db()
        old_review.refresh_from_db()
        self.assertEqual(record.pipeline_status, "in_review")
        self.assertEqual((intake.state, intake.reason), ("withdrawn", "ADR-032: intake retired"))
        self.assertEqual(old_review.stage, "rdco_intake")
        adviser = RecordAssignment.objects.get(record=record, party="adviser", state="active")
        self.assertEqual(ReviewerSeat.objects.get(assignment=adviser).reviewer, self.adviser)
        self.assertEqual(RoutingEvent.objects.filter(record=record, to_party="adviser").count(), 1)

    def test_missing_or_self_adviser_blocks_cutover_and_is_listed(self):
        missing, missing_intake = self.intake_record("No adviser")
        self_owned, self_intake = self.intake_record("Own adviser", self.owner)

        with self.assertRaisesRegex(RuntimeError, "Record ids:.*" + str(missing.pk)):
            retire_intake(apps, None)

        missing.refresh_from_db()
        self_owned.refresh_from_db()
        self.assertEqual(missing.pipeline_status, "rdco_intake")
        self.assertEqual(self_owned.pipeline_status, "rdco_intake")
        self.assertEqual(RecordAssignment.objects.get(pk=missing_intake.pk).state, "active")
        self.assertEqual(RecordAssignment.objects.get(pk=self_intake.pk).state, "active")
        output = StringIO()
        call_command("list_unassigned_intake", stdout=output)
        self.assertIn("No adviser\tno adviser", output.getvalue())
        self.assertIn("Own adviser\tadviser is an owner", output.getvalue())

    def test_conflicting_active_assignment_fails_without_partial_cutover(self):
        record, intake = self.intake_record("Conflicting holder", self.adviser)
        RecordAssignment.objects.create(record=record, party="itso")

        with self.assertRaisesRegex(RuntimeError, f"Record ids: {record.pk}"):
            retire_intake(apps, None)

        record.refresh_from_db()
        intake.refresh_from_db()
        self.assertEqual(record.pipeline_status, "rdco_intake")
        self.assertEqual(intake.state, "active")
        self.assertFalse(RecordAssignment.objects.filter(record=record, party="adviser").exists())

    def test_declined_intake_work_and_its_requests_are_retired_as_history(self):
        record, intake = self.intake_record("Intake asked for changes", self.adviser)
        record.pipeline_status = "declined"
        record.save(update_fields=["pipeline_status"])
        review = Review.objects.create(
            record=record, reviewed_by=self.rdco, stage="rdco_intake",
            status="declined", comment="Revise the manuscript.", assignment=intake,
        )
        revision = ResubmissionRequest.objects.create(
            record=record, party="intake", assignment=intake, review=review,
            requested_by=self.rdco, reason=review.comment,
        )
        document = DocumentRequest.objects.create(
            record=record, party="intake", assignment=intake,
            requested_by=self.rdco, message="Attach the evidence.",
        )

        retire_intake(apps, None)

        record.refresh_from_db()
        revision.refresh_from_db()
        document.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(record.pipeline_status, "in_review")
        self.assertEqual(revision.state, "withdrawn")
        self.assertEqual(document.state, "withdrawn")
        self.assertIsNotNone(revision.resolved_at)
        self.assertIsNotNone(document.closed_at)
        self.assertEqual((review.stage, review.status), ("rdco_intake", "declined"))

    def test_all_legacy_in_flight_statuses_move_after_preflight(self):
        statuses = ("adviser_review", "itso_review", "parallel_review", "rdco_review")
        for status in statuses:
            with self.subTest(status=status):
                record = Record.objects.create(
                    title=status, record_type=self.record_type, added_by=self.owner,
                    adviser=self.adviser, pipeline_status=status,
                )
                RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
                if status == "adviser_review":
                    RecordAssignment.objects.create(record=record, party="adviser")
                elif status == "rdco_review":
                    RecordAssignment.objects.create(record=record, party="rdco")
                    RecordAssignment.objects.create(
                        record=record, party="intake", state="completed",
                    )
                else:
                    from apps.reviews.models import RecordClearance
                    RecordClearance.objects.create(record=record, office="itso", status="pending")
                    RecordAssignment.objects.create(record=record, party="itso")
                    RecordAssignment.objects.create(
                        record=record, party="intake", state="completed",
                    )
        retire_intake(apps, None)
        self.assertFalse(Record.objects.filter(pipeline_status__in=statuses).exists())
        self.assertEqual(Record.objects.filter(pipeline_status="in_review").count(), 4)

    def test_preflight_lists_every_bad_id_before_any_write(self):
        first, first_intake = self.intake_record("Missing adviser")
        second, second_intake = self.intake_record("Wrong holders", self.adviser)
        RecordAssignment.objects.create(record=second, party="itso")

        with self.assertRaises(RuntimeError) as caught:
            retire_intake(apps, None)

        self.assertIn(str(first.pk), str(caught.exception))
        self.assertIn(str(second.pk), str(caught.exception))
        self.assertEqual(RecordAssignment.objects.get(pk=first_intake.pk).state, "active")
        self.assertEqual(RecordAssignment.objects.get(pk=second_intake.pk).state, "active")
