"""
IR-274's two migrations refuse, naming the rows, rather than guess.

`records/0017` narrows `Record.pipeline_status` and refuses while any record --
or any delete request's remembered status -- still holds a removed value.
`reviews/0016` rewrites `rdco_intake` Reviews to `intake` and refuses while an
assignment to the retired Intake is still active. Driven here through their
`RunPython` functions, as `test_intake_retirement.py` drives `reviews/0014`.
"""

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.records.models import DeleteRequest, Record, RecordType
from apps.reviews.models import RecordAssignment, Review
from apps.reviews.workflow_test_helpers import at_the_cutover_schema

records_0017 = import_module("apps.records.migrations.0017_retire_fixed_pipeline_statuses")
reviews_0016 = import_module("apps.reviews.migrations.0016_retire_rdco_intake_stage")


class MigrationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(name="RDCO")
        cls.rdco = User.objects.create_user(email="ir274-rdco@cit.edu", password="TestPass123!", role=role)
        cls.record_type, _ = RecordType.objects.get_or_create(name="Thesis / Research")

    def record(self, status):
        return Record.objects.create(title=f"At {status}", record_type=self.record_type, pipeline_status=status)


class RetiredStatusGateTests(MigrationTestBase):

    def test_a_database_holding_only_current_statuses_passes(self):
        for status in ("draft", "in_review", "published", "approved", "completed", "rejected"):
            self.record(status)
        records_0017.refuse_retired_statuses(apps, None)

    def test_a_retired_status_refuses_and_names_the_record(self):
        held = self.record("itso_review")
        with self.assertRaisesRegex(RuntimeError, rf"\({held.pk}, 'itso_review'\)"):
            records_0017.refuse_retired_statuses(apps, None)

    def test_a_delete_request_remembering_one_refuses_too(self):
        record = self.record("pending_delete")
        request = DeleteRequest.objects.create(
            record=record, requested_by=self.rdco, previous_pipeline_status="declined",
        )
        with self.assertRaisesRegex(RuntimeError, rf"\({request.pk}, 'declined'\)"):
            records_0017.refuse_retired_statuses(apps, None)


class IntakeSpellingTests(MigrationTestBase):

    def test_rdco_intake_reviews_are_rewritten_and_nothing_else_moves(self):
        record = self.record("in_review")
        old = Review.objects.create(record=record, reviewed_by=self.rdco, stage="rdco_intake", status="approved")
        other = Review.objects.create(record=record, reviewed_by=self.rdco, stage="rdco", status="approved")

        reviews_0016.unify_intake_spelling(apps, None)

        old.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((old.stage, old.status, old.reviewed_by_id), ("intake", "approved", self.rdco.pk))
        self.assertEqual(old.get_stage_display(), "Intake (retired)")
        self.assertEqual(other.stage, "rdco")


class ActiveIntakeGateTests(MigrationTestBase):

    def setUp(self):
        # The row this gate refuses is the one IR-274's constraint forbids.
        at_the_cutover_schema()

    def test_closed_intake_history_passes(self):
        record = self.record("in_review")
        RecordAssignment.objects.create(record=record, party="intake", state="withdrawn")
        RecordAssignment.objects.create(record=record, party="intake", state="completed")
        reviews_0016.refuse_active_intake(apps, None)

    def test_an_active_intake_assignment_refuses_and_names_it(self):
        record = self.record("in_review")
        active = RecordAssignment.objects.create(record=record, party="intake")
        with self.assertRaisesRegex(RuntimeError, rf"\({active.pk}, {record.pk}\)"):
            reviews_0016.refuse_active_intake(apps, None)
