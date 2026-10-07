"""
`manage.py enter_new_model` (IR-261, decided 2026-10-08): development only,
the same rules as `routing.enter_at_adviser`, and no way past `DEBUG` off.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, ReviewerSeat
from core.enums import PipelineStatus, RecordTypeName, RoleName

from apps.reviews.test_workflow_characterisation import make_user


class EnterNewModelCommandTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("enm-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("enm-adviser@cit.edu", RoleName.ADVISER)

    def draft(self, **extra):
        record = Record.objects.create(
            title="A draft to demo routing on",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            added_by=self.owner,
            pipeline_status=PipelineStatus.DRAFT,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    @override_settings(DEBUG=True)
    def test_it_enters_a_draft_at_its_adviser(self):
        record = self.draft(adviser=self.adviser)

        call_command("enter_new_model", record.pk, stdout=StringIO())

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertEqual(
            list(RecordAssignment.objects.filter(record=record).values_list("party", "state")),
            [("adviser", "active")],
        )
        self.assertTrue(
            ReviewerSeat.objects.filter(assignment__record=record, reviewer=self.adviser).exists()
        )

    @override_settings(DEBUG=False)
    def test_it_refuses_with_debug_off_and_has_no_force(self):
        record = self.draft(adviser=self.adviser)

        with self.assertRaises(CommandError):
            call_command("enter_new_model", record.pk, stdout=StringIO())
        with self.assertRaises(TypeError):
            call_command("enter_new_model", record.pk, force=True, stdout=StringIO())

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)

    @override_settings(DEBUG=True)
    def test_it_applies_the_entry_rules(self):
        no_adviser = self.draft()
        with self.assertRaises(CommandError):
            call_command("enter_new_model", no_adviser.pk, stdout=StringIO())

        with self.assertRaises(CommandError):
            call_command("enter_new_model", 999999, stdout=StringIO())
