"""
IR-794: a daily job erases personal data past the retention period the System
Admin sets (ADR-051 decision 19).

The clock is frozen by passing `now` to `run_retention`, so no test depends on
the day it runs. Download notes are the one registered type; a stand-in type
shows that a later one needs no new job.

**Seam: `run_retention` and the settings API.**
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.accounts.models import Role, SystemSetting, User
from apps.audit import retention
from apps.audit.models import AuditEvent
from apps.audit.retention import RetentionType, run_retention
from apps.records.models import DownloadRequest, Record, RecordType
from apps.records.retention import SETTING_KEY, TYPE_KEY
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=dt_timezone.utc)
DAYS = 30
READER_NOTE = "I am citing its survey method in my own thesis."
RDCO_NOTE = "The paper is under embargo for a patent filing."


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


def set_period(value, key=SETTING_KEY):
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value})


class RetentionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = _user("retain-reader@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("retain-rdco@cit.edu", RoleName.RDCO)
        cls.record = Record.objects.create(
            title="A published thesis",
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            pipeline_status=PipelineStatus.PUBLISHED,
        )

    def request(self, *, age, status=RequestStatus.DECLINED, **fields):
        """A request whose last activity was `age` ago. `created_at` is set by the database clock."""
        when = NOW - age
        fields = {"note": READER_NOTE, "rdco_note": RDCO_NOTE, **fields}
        made = DownloadRequest.objects.create(
            record=self.record, requested_by=self.reader, status=status, **fields,
        )
        DownloadRequest.objects.filter(pk=made.pk).update(created_at=when)
        made.refresh_from_db()
        return made

    def notes(self, made):
        made.refresh_from_db()
        return made.note, made.rdco_note

    def last_event(self):
        return AuditEvent.objects.filter(event_type=AuditEvent.RETENTION_CLEANUP_RUN).first()


class SettingsAreCreatedBlankTests(RetentionTestCase):
    def test_every_registered_type_has_a_blank_setting_from_the_migrations(self):
        types = retention.registered_types()
        self.assertIn(TYPE_KEY, [t.key for t in types])
        for retention_type in types:
            with self.subTest(type=retention_type.key):
                setting = SystemSetting.objects.get(key=retention_type.setting_key)
                self.assertEqual(setting.value, "")

    def test_no_period_has_a_default_in_code(self):
        # A fresh database erases nothing: the key exists, blank, and the job honours that.
        old = self.request(age=timedelta(days=100_000))

        counts = run_retention(NOW)

        self.assertEqual(counts, {TYPE_KEY: 0})
        self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))


class PeriodTests(RetentionTestCase):
    def test_a_blank_period_erases_nothing(self):
        set_period("")
        old = self.request(age=timedelta(days=5_000))

        counts = run_retention(NOW)

        self.assertEqual(counts, {TYPE_KEY: 0})
        self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))

    def test_a_missing_setting_erases_nothing(self):
        SystemSetting.objects.filter(key=SETTING_KEY).delete()
        old = self.request(age=timedelta(days=5_000))

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 0})
        self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))

    def test_a_period_that_is_not_a_positive_whole_number_erases_nothing(self):
        old = self.request(age=timedelta(days=5_000))
        for value in ("abc", "0", "-5", "30.5", "30 days", "٣٠"):
            with self.subTest(value=value):
                set_period(value)

                with self.assertLogs("apps.audit.retention", level="WARNING"):
                    counts = run_retention(NOW)

                self.assertEqual(counts, {TYPE_KEY: 0})
                self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))

    def test_surrounding_spaces_do_not_change_the_period(self):
        set_period(f"  {DAYS}  ")
        old = self.request(age=timedelta(days=DAYS, seconds=1))

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 1})
        self.assertEqual(self.notes(old), ("", ""))

    def test_a_longer_period_keeps_what_a_shorter_one_would_erase(self):
        made = self.request(age=timedelta(days=45))

        set_period("60")
        self.assertEqual(run_retention(NOW), {TYPE_KEY: 0})
        self.assertEqual(self.notes(made), (READER_NOTE, RDCO_NOTE))

        set_period("30")
        self.assertEqual(run_retention(NOW), {TYPE_KEY: 1})
        self.assertEqual(self.notes(made), ("", ""))


class DownloadNotesTests(RetentionTestCase):
    def setUp(self):
        set_period(str(DAYS))

    def test_the_boundary_day_is_kept_and_a_second_past_it_is_erased(self):
        on_the_day = self.request(age=timedelta(days=DAYS))
        a_second_past = self.request(age=timedelta(days=DAYS, seconds=1))
        a_second_short = self.request(age=timedelta(days=DAYS) - timedelta(seconds=1))

        counts = run_retention(NOW)

        self.assertEqual(counts, {TYPE_KEY: 1})
        self.assertEqual(self.notes(on_the_day), (READER_NOTE, RDCO_NOTE))
        self.assertEqual(self.notes(a_second_short), (READER_NOTE, RDCO_NOTE))
        self.assertEqual(self.notes(a_second_past), ("", ""))

    def test_only_the_text_goes_the_request_stays_as_it_was(self):
        old = self.request(
            age=timedelta(days=90), reviewed_by=self.rdco,
            reviewed_at=NOW - timedelta(days=90),
        )

        run_retention(NOW)

        old.refresh_from_db()
        self.assertEqual((old.note, old.rdco_note), ("", ""))
        self.assertEqual(old.status, RequestStatus.DECLINED)
        self.assertEqual(old.requested_by, self.reader)
        self.assertEqual(old.reviewed_by, self.rdco)
        self.assertEqual(old.record, self.record)
        self.assertEqual(old.reviewed_at, NOW - timedelta(days=90))

    def test_a_pending_request_is_never_touched(self):
        waiting = self.request(age=timedelta(days=500), status=RequestStatus.PENDING)

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 0})
        self.assertEqual(self.notes(waiting), (READER_NOTE, RDCO_NOTE))

    def test_age_runs_from_the_latest_thing_that_happened_to_the_request(self):
        decided_recently = self.request(
            age=timedelta(days=400), status=RequestStatus.APPROVED,
            reviewed_at=NOW - timedelta(days=3),
            grant_expires_at=NOW + timedelta(days=27),
        )
        grant_still_running = self.request(
            age=timedelta(days=400), status=RequestStatus.APPROVED,
            reviewed_at=NOW - timedelta(days=400),
            grant_expires_at=NOW + timedelta(days=1),
        )
        revoked_recently = self.request(
            age=timedelta(days=400), status=RequestStatus.REVOKED,
            reviewed_at=NOW - timedelta(days=400), revoked_at=NOW - timedelta(days=2),
        )
        revoked_with_a_grant_that_would_have_run_on = self.request(
            age=timedelta(days=400), status=RequestStatus.REVOKED,
            reviewed_at=NOW - timedelta(days=400), revoked_at=NOW - timedelta(days=399),
            grant_expires_at=NOW + timedelta(days=200),
        )
        cancelled_long_ago = self.request(
            age=timedelta(days=400), status=RequestStatus.CANCELLED,
            cancelled_at=NOW - timedelta(days=399),
        )

        counts = run_retention(NOW)

        self.assertEqual(counts, {TYPE_KEY: 2})
        for kept in (decided_recently, grant_still_running, revoked_recently):
            self.assertEqual(self.notes(kept), (READER_NOTE, RDCO_NOTE))
        self.assertEqual(self.notes(cancelled_long_ago), ("", ""))
        # Its grant ended when it was revoked, not on the date it once carried.
        self.assertEqual(self.notes(revoked_with_a_grant_that_would_have_run_on), ("", ""))

    def test_a_request_with_only_one_note_is_counted_once_and_a_blank_one_not_at_all(self):
        only_reader = self.request(age=timedelta(days=90), rdco_note="")
        already_blank = self.request(age=timedelta(days=90), note="", rdco_note="")

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 1})
        self.assertEqual(self.notes(only_reader), ("", ""))
        self.assertEqual(self.notes(already_blank), ("", ""))


class SafeToRepeatTests(RetentionTestCase):
    def setUp(self):
        set_period(str(DAYS))

    def test_a_second_run_finds_nothing_and_changes_nothing(self):
        old = self.request(age=timedelta(days=90))
        fresh = self.request(age=timedelta(days=1))

        first = run_retention(NOW)
        second = run_retention(NOW)
        third = run_retention(NOW + timedelta(hours=1))

        self.assertEqual((first, second, third), ({TYPE_KEY: 1}, {TYPE_KEY: 0}, {TYPE_KEY: 0}))
        self.assertEqual(self.notes(old), ("", ""))
        self.assertEqual(self.notes(fresh), (READER_NOTE, RDCO_NOTE))

    def test_the_next_day_erases_what_has_since_come_due(self):
        due_tomorrow = self.request(age=timedelta(days=DAYS) - timedelta(hours=1))

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 0})
        self.assertEqual(run_retention(NOW + timedelta(days=1)), {TYPE_KEY: 1})
        self.assertEqual(self.notes(due_tomorrow), ("", ""))

    def test_an_interrupted_run_erases_nothing_and_the_next_one_does_it_all(self):
        old = self.request(age=timedelta(days=90))

        def explode(cutoff):
            raise RuntimeError("worker killed")

        broken = RetentionType(key="zz_broken", setting_key="retention.zz_broken_days", erase=explode)
        set_period("30", key=broken.setting_key)
        with mock.patch.dict(retention._REGISTRY, {broken.key: broken}):
            with self.assertRaises(RuntimeError):
                run_retention(NOW)

        # The download notes ran first and were rolled back with the rest, event included.
        self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))
        self.assertIsNone(self.last_event())

        self.assertEqual(run_retention(NOW), {TYPE_KEY: 1})
        self.assertEqual(self.notes(old), ("", ""))


class AuditFailureTests(RetentionTestCase):
    def test_a_run_whose_event_cannot_be_written_erases_nothing(self):
        set_period(str(DAYS))
        old = self.request(age=timedelta(days=90))

        with mock.patch.object(AuditEvent.objects, "create", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                run_retention(NOW)

        self.assertEqual(self.notes(old), (READER_NOTE, RDCO_NOTE))


class AuditTests(RetentionTestCase):
    def setUp(self):
        set_period(str(DAYS))

    def test_a_run_writes_one_event_with_counts_and_no_personal_data(self):
        self.request(age=timedelta(days=90))
        self.request(age=timedelta(days=60))

        run_retention(NOW)

        event = self.last_event()
        self.assertEqual(AuditEvent.objects.filter(event_type=AuditEvent.RETENTION_CLEANUP_RUN).count(), 1)
        self.assertIsNone(event.user_id)
        self.assertIsNone(event.record_id)
        self.assertEqual(event.metadata, {"counts": {TYPE_KEY: 2}})
        stored = repr(event.metadata)
        for text in (READER_NOTE, RDCO_NOTE, self.reader.email, self.record.title):
            self.assertNotIn(text, stored)

    def test_a_run_that_erases_nothing_still_says_so(self):
        run_retention(NOW)
        run_retention(NOW)

        events = AuditEvent.objects.filter(event_type=AuditEvent.RETENTION_CLEANUP_RUN)
        self.assertEqual([e.metadata for e in events], [{"counts": {TYPE_KEY: 0}}] * 2)

    def test_the_job_never_updates_or_deletes_an_audit_row(self):
        # Audit rows are insert-only at the database (IR-166). This proves the job
        # does not even try, rather than relying on the trigger to refuse it.
        self.request(age=timedelta(days=90))
        AuditEvent.objects.create(
            event_type=AuditEvent.DOWNLOAD, user=self.reader, record=self.record,
            metadata={"note": READER_NOTE},
        )
        before = list(AuditEvent.objects.order_by("pk").values())

        with CaptureQueriesContext(connection) as queries:
            run_retention(NOW)

        for query in queries.captured_queries:
            sql = query["sql"].lstrip().upper()
            if "AUDIT_AUDITEVENT" in sql:
                self.assertTrue(sql.startswith(("INSERT", "SELECT", "SAVEPOINT", "RELEASE")), query["sql"])
        after = list(AuditEvent.objects.exclude(event_type=AuditEvent.RETENTION_CLEANUP_RUN).order_by("pk").values())
        self.assertEqual(after, before)


class RegistrationTests(RetentionTestCase):
    def test_a_new_type_is_erased_by_the_same_job_under_its_own_period(self):
        seen = []
        extra = RetentionType(
            key="comment_text", setting_key="retention.comment_text_days",
            erase=lambda cutoff: seen.append(cutoff) or 7,
        )
        set_period("30")
        set_period("10", key=extra.setting_key)

        with mock.patch.dict(retention._REGISTRY, {extra.key: extra}):
            counts = run_retention(NOW)

        self.assertEqual(counts, {TYPE_KEY: 0, "comment_text": 7})
        self.assertEqual(seen, [NOW - timedelta(days=10)])
        self.assertEqual(self.last_event().metadata, {"counts": {TYPE_KEY: 0, "comment_text": 7}})

    def test_a_new_type_with_a_blank_period_is_left_alone(self):
        extra = RetentionType(key="comment_text", setting_key="retention.comment_text_days",
                              erase=mock.Mock(return_value=9))
        set_period("30")

        with mock.patch.dict(retention._REGISTRY, {extra.key: extra}):
            counts = run_retention(NOW)

        extra.erase.assert_not_called()
        self.assertEqual(counts["comment_text"], 0)

    def test_two_types_cannot_share_a_period(self):
        clash = RetentionType(key="other", setting_key=SETTING_KEY, erase=lambda cutoff: 0)
        with self.assertRaises(ValueError):
            retention.register(clash)

    def test_a_key_cannot_be_registered_twice_with_different_behaviour(self):
        clash = RetentionType(key=TYPE_KEY, setting_key="retention.other_days", erase=lambda cutoff: 0)
        with self.assertRaises(ValueError):
            retention.register(clash)


class ScheduleTests(TestCase):
    def test_beat_runs_it_daily_at_3_in_manila(self):
        entry = settings.CELERY_BEAT_SCHEDULE["retention-cleanup"]

        self.assertEqual(entry["task"], "apps.audit.tasks.erase_expired_personal_data")
        # Celery's clock is Manila's (CELERY_TIMEZONE = TIME_ZONE), so the hour is
        # Manila's. It said {19} on the belief that Celery ran on UTC, which made
        # the cleanup run at 19:00 Manila (IR-1019).
        from config.celery import app
        self.assertEqual(str(app.timezone), "Asia/Manila")
        self.assertEqual(entry["schedule"].hour, {3})
        self.assertEqual(entry["schedule"].minute, {0})

    def test_the_task_runs_the_cleanup(self):
        from apps.audit.tasks import erase_expired_personal_data

        with mock.patch("apps.audit.tasks.run_retention", return_value={TYPE_KEY: 3}) as run:
            self.assertEqual(erase_expired_personal_data(), {TYPE_KEY: 3})
        run.assert_called_once_with()


class SettingsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sysadmin = _user("retain-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.rdco = _user("retain-api-rdco@cit.edu", RoleName.RDCO)
        cls.url = f"/api/v1/settings/{SETTING_KEY}/"

    def test_the_system_admin_sets_a_period_and_the_change_is_audited(self):
        self.client.force_authenticate(self.sysadmin)

        response = self.client.patch(self.url, {"value": "365"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSetting.objects.get(key=SETTING_KEY).value, "365")
        event = AuditEvent.objects.get(event_type=AuditEvent.SYSTEM_SETTING_CHANGED)
        self.assertEqual(
            event.metadata, {"key": SETTING_KEY, "old_value": "", "new_value": "365"},
        )

    def test_a_period_can_be_cleared_to_erase_nothing_again(self):
        set_period("365")
        self.client.force_authenticate(self.sysadmin)

        response = self.client.patch(self.url, {"value": ""}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSetting.objects.get(key=SETTING_KEY).value, "")

    def test_a_period_that_is_not_whole_days_is_refused_and_changes_nothing(self):
        set_period("365")
        self.client.force_authenticate(self.sysadmin)
        for value in ("abc", "0", "-1", "1.5", "one year"):
            with self.subTest(value=value):
                response = self.client.patch(self.url, {"value": value}, format="json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(SystemSetting.objects.get(key=SETTING_KEY).value, "365")
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.SYSTEM_SETTING_CHANGED).exists())

    def test_rdco_cannot_set_a_period(self):
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(self.url, {"value": "30"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(SystemSetting.objects.get(key=SETTING_KEY).value, "")
