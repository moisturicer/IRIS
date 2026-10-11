from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User

from .models import Record, RecordOwner


class ResetDemoRecordsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="reset-test@example.com",
            password="pw12345!",
            first_name="Reset",
            last_name="Test",
        )
        self.demo = Record.objects.create(
            title="[DEMO] Old workflow fixture", added_by=self.user
        )
        RecordOwner.objects.create(record=self.demo, user=self.user)
        self.real_record = Record.objects.create(
            title="Community irrigation research", added_by=self.user
        )

    def test_default_run_previews_without_deleting(self):
        output = StringIO()

        call_command("reset_demo_records", stdout=output)

        self.assertIn("[DEMO] Old workflow fixture", output.getvalue())
        self.assertIn("Preview only", output.getvalue())
        self.assertTrue(Record.objects.filter(pk=self.demo.pk).exists())

    @override_settings(DEBUG=True)
    def test_execute_deletes_demo_records_and_cascades_linked_rows(self):
        call_command("reset_demo_records", execute=True, stdout=StringIO())

        self.assertFalse(Record.objects.filter(pk=self.demo.pk).exists())
        self.assertFalse(RecordOwner.objects.filter(record_id=self.demo.pk).exists())
        self.assertTrue(Record.objects.filter(pk=self.real_record.pk).exists())

    @override_settings(DEBUG=False)
    def test_execute_refuses_when_debug_is_off(self):
        with self.assertRaisesMessage(CommandError, "DEBUG is off"):
            call_command("reset_demo_records", execute=True, stdout=StringIO())

        self.assertTrue(Record.objects.filter(pk=self.demo.pk).exists())

    @override_settings(DEBUG=False)
    def test_preview_is_safe_when_debug_is_off(self):
        call_command("reset_demo_records", stdout=StringIO())

        self.assertTrue(Record.objects.filter(pk=self.demo.pk).exists())
