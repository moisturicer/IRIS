"""
Embargo reminders (ADR-052 decision 9, IR-814).

On an embargo's review date IRIS tells the owners and the Adviser in-app, then
every 5 working days until someone extends or releases it. Three things are
pinned hardest. Each reminder is sent once, whatever the beat does. A reminder
changes nothing: the paper stays under embargo and refused. And nobody is told
about a paper they can't see.
"""

from datetime import date, datetime, time
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.ai.policy.disclosure import Reason
from apps.ai.policy.records import decision_for_record
from apps.notifications.models import Notification
from apps.reviews.models import Holiday
from core.enums import EmbargoState, PipelineStatus, RecordTypeName, RoleName

from . import embargo, embargo_reminders
from .embargo_reminders import run_embargo_reminders
from .models import Record, RecordOwner, RecordType
from .tests import make_user

MANILA = ZoneInfo("Asia/Manila")
REVIEW_DATE = date(2026, 11, 2)  # a Monday


def on(day):
    """08:00 in Manila on `day`, when the beat runs."""
    return datetime.combine(day, time(8, 0), tzinfo=MANILA)


class EmbargoReminderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.record_type = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        cls.owner = make_user("remind-owner@cit.edu", RoleName.STUDENT)
        cls.co_owner = make_user("remind-co-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("remind-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = make_user("remind-rdco@cit.edu", RoleName.RDCO)

    def _paper(self, status_=PipelineStatus.PUBLISHED, *, until=REVIEW_DATE, released=False):
        now = timezone.now()
        stamps = {
            "embargo_date_set_at": now, "embargo_date_set_by": self.adviser, "embargoed_until": until,
            "dpa_accepted_at": now, "dpa_accepted_by": self.owner,
        }
        if released:
            stamps.update(is_embargoed=False, embargo_released_at=now, embargo_released_by=self.adviser)
        record = Record.objects.create(
            title="A held paper", abstract="An abstract long enough to read.",
            record_type=self.record_type, added_by=self.owner, adviser=self.adviser,
            pipeline_status=status_, **stamps,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        RecordOwner.objects.create(record=record, user=self.co_owner, is_primary=False)
        return record

    def _told(self, record):
        """Who has been reminded about `record`, as {email: count}."""
        notes = Notification.objects.filter(record=record, notif_type__name=embargo_reminders.TYPE_NAME)
        counts = {}
        for note in notes:
            counts[note.recipient.email] = counts.get(note.recipient.email, 0) + 1
        return counts

    EVERYONE_ONCE = {"remind-owner@cit.edu": 1, "remind-co-owner@cit.edu": 1, "remind-adviser@cit.edu": 1}


class WhenRemindersGoOutTests(EmbargoReminderTests):
    def test_nothing_before_the_date(self):
        record = self._paper()

        run_embargo_reminders(on(date(2026, 11, 1)))

        self.assertEqual(self._told(record), {})

    def test_the_owners_and_the_adviser_are_told_on_the_date_and_nobody_else(self):
        record = self._paper()

        run_embargo_reminders(on(REVIEW_DATE))

        self.assertEqual(self._told(record), self.EVERYONE_ONCE)
        note = Notification.objects.filter(record=record).first()
        self.assertIn("A held paper", note.message)
        self.assertIn("until someone extends or releases it", note.message)

    def test_a_date_on_a_weekend_is_reminded_on_the_day(self):
        record = self._paper(until=date(2026, 11, 7))  # a Saturday

        run_embargo_reminders(on(date(2026, 11, 7)))

        self.assertEqual(self._told(record), self.EVERYONE_ONCE)

    def test_then_every_5_working_days(self):
        record = self._paper()
        for day in (REVIEW_DATE, date(2026, 11, 3), date(2026, 11, 6), date(2026, 11, 8)):
            run_embargo_reminders(on(day))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 1)

        run_embargo_reminders(on(date(2026, 11, 9)))  # 5 working days on
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 2)

        run_embargo_reminders(on(date(2026, 11, 16)))  # 10
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 3)

    def test_a_holiday_is_not_a_working_day(self):
        Holiday.objects.create(date=date(2026, 11, 4), name="A holiday")
        record = self._paper()
        run_embargo_reminders(on(REVIEW_DATE))

        run_embargo_reminders(on(date(2026, 11, 9)))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 1)

        run_embargo_reminders(on(date(2026, 11, 10)))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 2)

    def test_a_later_reminder_says_how_long_it_has_waited(self):
        record = self._paper()
        run_embargo_reminders(on(date(2026, 11, 9)))

        note = Notification.objects.filter(record=record, recipient=self.owner).get()
        self.assertIn("5 working days ago", note.message)


class SentOnceTests(EmbargoReminderTests):
    def test_a_rerun_sends_nothing_more(self):
        record = self._paper()

        run_embargo_reminders(on(REVIEW_DATE))
        run_embargo_reminders(on(REVIEW_DATE))
        run_embargo_reminders(on(date(2026, 11, 3)))

        self.assertEqual(self._told(record), self.EVERYONE_ONCE)

    def test_after_downtime_only_the_latest_reminder_is_sent(self):
        record = self._paper()

        run_embargo_reminders(on(date(2026, 11, 20)))  # 14 working days on: the third reminder

        self.assertEqual(self._told(record), self.EVERYONE_ONCE)
        note = Notification.objects.filter(record=record, recipient=self.owner).get()
        self.assertIn("14 working days ago", note.message)

    def test_extending_starts_again_from_the_new_date(self):
        record = self._paper()
        run_embargo_reminders(on(REVIEW_DATE))

        embargo.set_embargo(record, date(2026, 12, 1), actor=self.adviser)
        run_embargo_reminders(on(date(2026, 11, 9)))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 1)

        run_embargo_reminders(on(date(2026, 12, 1)))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 2)

    def test_holding_a_released_paper_again_with_the_same_date_starts_again(self):
        record = self._paper()
        run_embargo_reminders(on(REVIEW_DATE))
        embargo.release_embargo(record, actor=self.adviser)
        embargo.set_embargo(record, REVIEW_DATE, actor=self.owner)

        run_embargo_reminders(on(date(2026, 11, 3)))

        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 2)

    def test_releasing_stops_them(self):
        record = self._paper()
        run_embargo_reminders(on(REVIEW_DATE))

        embargo.release_embargo(record, actor=self.adviser)
        run_embargo_reminders(on(date(2026, 11, 9)))

        self.assertEqual(self._told(record), self.EVERYONE_ONCE)


class WhichPapersTests(EmbargoReminderTests):
    def test_any_submitted_status_is_reminded(self):
        for status_ in (PipelineStatus.IN_REVIEW, PipelineStatus.COMPLETED, PipelineStatus.REJECTED):
            with self.subTest(status=status_):
                record = self._paper(status_)

                run_embargo_reminders(on(REVIEW_DATE))

                self.assertEqual(self._told(record), self.EVERYONE_ONCE)

    def test_drafts_released_and_deleted_papers_are_not(self):
        draft = self._paper(PipelineStatus.DRAFT)
        released = self._paper(released=True)
        deleted = self._paper()
        Record.objects.filter(pk=deleted.pk).update(is_deleted=True)

        run_embargo_reminders(on(REVIEW_DATE))

        for record in (draft, released, deleted):
            self.assertEqual(self._told(record), {})


class WhoIsToldTests(EmbargoReminderTests):
    def test_an_inactive_owner_is_not_told(self):
        record = self._paper()
        type(self.co_owner).objects.filter(pk=self.co_owner.pk).update(is_active=False)

        run_embargo_reminders(on(REVIEW_DATE))

        self.assertNotIn("remind-co-owner@cit.edu", self._told(record))

    def test_without_an_adviser_only_the_owners_are_told(self):
        record = self._paper()
        Record.objects.filter(pk=record.pk).update(adviser=None)

        run_embargo_reminders(on(REVIEW_DATE))

        self.assertEqual(set(self._told(record)), {"remind-owner@cit.edu", "remind-co-owner@cit.edu"})

    def test_everyone_is_checked_against_visibility_before_the_paper_is_named(self):
        record = self._paper()
        real = Record.objects.visible_to

        def visible_to(user):
            return Record.objects.none() if user == self.co_owner else real(user)

        with mock.patch.object(type(Record.objects), "visible_to", side_effect=visible_to):
            run_embargo_reminders(on(REVIEW_DATE))

        self.assertEqual(set(self._told(record)), {"remind-owner@cit.edu", "remind-adviser@cit.edu"})


class ChangesNothingTests(EmbargoReminderTests):
    def test_the_paper_stays_under_embargo_and_refused_after_every_reminder(self):
        record = self._paper()
        for day in (REVIEW_DATE, date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)):
            run_embargo_reminders(on(day))
            record.refresh_from_db()
            self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
            self.assertEqual(record.embargoed_until, REVIEW_DATE)
            self.assertEqual(decision_for_record(record).reasons, (Reason.EMBARGOED,))
        self.assertEqual(self._told(record)["remind-owner@cit.edu"], 4)


class FailureTests(EmbargoReminderTests):
    def test_a_failed_paper_is_logged_and_the_batch_carries_on(self):
        broken, fine = self._paper(), self._paper()
        real = embargo_reminders._send

        def send(record_id, *args, **kwargs):
            if record_id == broken.pk:
                raise RuntimeError("boom")
            return real(record_id, *args, **kwargs)

        with mock.patch.object(embargo_reminders, "_send", side_effect=send), \
                self.assertLogs("apps.records.embargo_reminders", level="ERROR") as logs:
            run_embargo_reminders(on(REVIEW_DATE))

        self.assertEqual(self._told(fine), self.EVERYONE_ONCE)
        self.assertIn(str(broken.pk), "".join(logs.output))


class FailedNoticeTests(EmbargoReminderTests):
    def test_one_recipient_failing_is_logged_and_the_others_are_still_told(self):
        record = self._paper()
        real = Notification.objects.create

        def create(**kwargs):
            if kwargs.get("recipient") == self.co_owner:
                raise RuntimeError("boom")
            return real(**kwargs)

        with mock.patch.object(Notification.objects, "create", side_effect=create),                 self.assertLogs("apps.notifications", level="WARNING"):
            run_embargo_reminders(on(REVIEW_DATE))

        self.assertEqual(set(self._told(record)), {"remind-owner@cit.edu", "remind-adviser@cit.edu"})


class ScheduleTests(TestCase):
    def test_beat_runs_it_daily_at_8_in_manila(self):
        entry = settings.CELERY_BEAT_SCHEDULE["embargo-reminders"]

        self.assertEqual(entry["task"], "apps.records.tasks.send_embargo_reminders")
        # Celery runs on UTC here, and Manila is UTC+8 with no daylight saving.
        self.assertEqual(entry["schedule"].hour, {0})
        self.assertEqual(entry["schedule"].minute, {0})

    def test_the_task_runs_the_reminders(self):
        from .tasks import send_embargo_reminders

        with mock.patch("apps.records.tasks.run_embargo_reminders", return_value=3) as run:
            self.assertEqual(send_embargo_reminders(), 3)
        run.assert_called_once_with()
