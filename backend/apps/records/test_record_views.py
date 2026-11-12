"""
IR-369: a paper's views count each account once.

The rule (decided 2026-10-31, CONTEXT.md **View**): a view is one account's
first opening of a published paper. Opening it again never adds one, only
published papers count, and the paper's owners never count.

**Seam: the API.** Paper View posts `increment_access` on every load, and the
response carries the count the page shows; the count is read back through the
same response and the Discover list, never from the table that holds it.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from time import monotonic, sleep
from unittest.mock import patch

from django.db import connection, transaction
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus, RoleName


def person(email, role_name=RoleName.STUDENT):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


def paper(owner, status=PipelineStatus.PUBLISHED, title="A paper", adviser=None):
    record = Record.objects.create(title=title, pipeline_status=status, adviser=adviser)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


def open_url(record):
    return f"/api/v1/records/{record.pk}/increment_access/"


class OneViewPerAccountTests(APITestCase):
    def setUp(self):
        self.owner = person("views-owner@cit.edu")
        self.reader = person("views-reader@cit.edu")
        self.other = person("views-other@cit.edu")
        self.record = paper(self.owner)

    def open_as(self, user, record=None):
        self.client.force_authenticate(user)
        response = self.client.post(open_url(record or self.record))
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["access_count"]

    def test_one_account_opening_a_paper_many_times_is_one_view(self):
        self.assertEqual(self.open_as(self.reader), 1)
        self.assertEqual(self.open_as(self.reader), 1)
        self.assertEqual(self.open_as(self.reader), 1)

    def test_a_different_account_adds_one_more(self):
        self.open_as(self.reader)
        self.assertEqual(self.open_as(self.other), 2)

    def test_an_owner_opening_their_own_paper_never_counts(self):
        co_owner = person("views-co-owner@cit.edu")
        RecordOwner.objects.create(record=self.record, user=co_owner)

        self.assertEqual(self.open_as(self.owner), 0)
        self.assertEqual(self.open_as(co_owner), 0)
        self.assertEqual(self.open_as(self.reader), 1)

    def test_an_unpublished_paper_answers_its_count_and_never_counts(self):
        adviser = person("views-adviser@cit.edu", RoleName.ADVISER)
        rdco = person("views-rdco@cit.edu", RoleName.RDCO)
        draft = paper(self.owner, PipelineStatus.IN_REVIEW, "Under review", adviser=adviser)

        self.assertEqual(self.open_as(adviser, draft), 0)
        self.assertEqual(self.open_as(rdco, draft), 0)

    def test_the_adviser_and_office_staff_count_on_a_published_paper(self):
        adviser = person("views-adviser@cit.edu", RoleName.ADVISER)
        rdco = person("views-rdco@cit.edu", RoleName.RDCO)
        self.record.adviser = adviser
        self.record.save(update_fields=["adviser"])

        self.assertEqual(self.open_as(adviser), 1)
        self.assertEqual(self.open_as(rdco), 2)

    def test_no_response_says_who_viewed_a_paper(self):
        self.open_as(self.reader)
        self.client.force_authenticate(self.owner)
        for url in (f"/api/v1/records/{self.record.pk}/", "/api/v1/records/", "/api/v1/records/mine/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                body = response.content.decode()
                self.assertNotIn(self.reader.email, body)
                self.assertNotIn('"viewed_by"', body)
                self.assertNotIn('"views":[', body)

    def test_deleting_a_paper_deletes_who_viewed_it(self):
        from apps.records.models import RecordView

        self.open_as(self.reader)
        self.record.delete()
        self.assertFalse(RecordView.objects.filter(user=self.reader).exists())

    def test_an_approved_deletion_deletes_who_viewed_it(self):
        """Approving a delete request is the final deletion: the paper is
        removed, never restored (`DeleteRequestViewSet.approve`)."""
        from apps.records.models import RecordView
        from apps.records.services import soft_delete_record

        self.open_as(self.reader)
        soft_delete_record(self.record, deleted_by=person("views-deleter@cit.edu", RoleName.RDCO))
        self.assertFalse(RecordView.objects.filter(user=self.reader).exists())

    def test_a_paper_the_account_cannot_see_is_still_a_404(self):
        draft = paper(self.owner, PipelineStatus.DRAFT, "Hidden draft")
        self.client.force_authenticate(self.reader)

        response = self.client.post(open_url(draft))

        self.assertEqual(response.status_code, 404)
        missing = self.client.post("/api/v1/records/999999/increment_access/")
        self.assertEqual(response.content, missing.content)


AT = datetime(2026, 11, 12, 9, tzinfo=dt_timezone.utc)


class AccessAuditTests(APITestCase):
    """`ACCESS` events, read through the audit log the System Admin uses."""

    def setUp(self):
        self.owner = person("audit-owner@cit.edu")
        self.reader = person("audit-reader@cit.edu")
        self.admin = person("audit-admin@cit.edu", RoleName.SYSTEM_ADMIN)
        self.record = paper(self.owner)

    def open_at(self, user, when, record=None):
        with patch("django.utils.timezone.now", return_value=when):
            self.client.force_authenticate(user)
            response = self.client.post(open_url(record or self.record))
        self.assertEqual(response.status_code, 200, response.content)

    def access_events(self, user, record=None):
        self.client.force_authenticate(self.admin)
        listed = self.client.get("/api/v1/audit/", {
            "event_type": "ACCESS", "record": (record or self.record).pk, "user": user.pk,
        })
        self.assertEqual(listed.status_code, 200, listed.content)
        return listed.data["count"]

    def test_reloads_within_a_day_write_one_access_event(self):
        for minutes in (0, 1, 30, 60 * 23):
            self.open_at(self.reader, AT + timedelta(minutes=minutes))
        self.assertEqual(self.access_events(self.reader), 1)

    def test_a_return_visit_after_24_hours_writes_another(self):
        self.open_at(self.reader, AT)
        self.open_at(self.reader, AT + timedelta(hours=24, minutes=1))
        self.assertEqual(self.access_events(self.reader), 2)

    def test_the_window_rolls_from_the_last_event_not_the_calendar_day(self):
        self.open_at(self.reader, AT.replace(hour=23))
        self.open_at(self.reader, AT.replace(hour=23) + timedelta(hours=2))
        self.assertEqual(self.access_events(self.reader), 1)

    def test_openings_that_never_count_are_still_audited_once_a_day(self):
        draft = paper(self.owner, PipelineStatus.IN_REVIEW, "In review")
        self.open_at(self.owner, AT)
        self.open_at(self.owner, AT + timedelta(minutes=5))
        self.open_at(self.owner, AT, record=draft)
        self.open_at(self.owner, AT + timedelta(minutes=5), record=draft)
        self.assertEqual(self.access_events(self.owner), 1)
        self.assertEqual(self.access_events(self.owner, draft), 1)


RACE = "ir369_view_race"


class SimultaneousOpeningTests(APITransactionTestCase):
    """Two openings held at the same point, then released together.

    The test holds the paper's row, which every opening must reach (its view
    row references the paper), until both requests are waiting on it. They
    then race exactly where a lost or double count would happen.
    """

    def setUp(self):
        self.owner = person("race-owner@cit.edu")
        self.record = paper(self.owner)

    def open_together(self, first, second):
        def open_on_another_connection(user):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET application_name = '{RACE}'")
                    cursor.execute("SET lock_timeout = '15s'")
                client = APIClient()
                client.force_authenticate(user)
                return client.post(open_url(self.record))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            with transaction.atomic():
                Record.objects.select_for_update().get(pk=self.record.pk)
                pending = [pool.submit(open_on_another_connection, u) for u in (first, second)]
                deadline = monotonic() + 10
                waiting = 0
                while monotonic() < deadline and waiting < 2:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE application_name = %s AND wait_event_type = 'Lock'",
                            [RACE],
                        )
                        waiting = cursor.fetchone()[0]
                    sleep(0.02)
                self.assertEqual(waiting, 2, "both openings must be waiting on the paper")
            responses = [p.result(timeout=20) for p in pending]
        for response in responses:
            self.assertEqual(response.status_code, 200, response.content)

    def views_now(self):
        reader = person(f"race-check-{monotonic()}@cit.edu")
        self.client.force_authenticate(reader)
        return self.client.post(open_url(self.record)).data["access_count"] - 1

    def test_two_accounts_opening_at_the_same_moment_both_count(self):
        self.open_together(person("race-a@cit.edu"), person("race-b@cit.edu"))
        self.assertEqual(self.views_now(), 2)

    def test_one_account_opening_twice_at_the_same_moment_counts_once(self):
        reader = person("race-same@cit.edu")
        self.open_together(reader, reader)
        self.assertEqual(self.views_now(), 1)

    def test_one_account_opening_twice_at_the_same_moment_is_audited_once(self):
        reader = person("race-audit@cit.edu")
        admin = person("race-admin@cit.edu", RoleName.SYSTEM_ADMIN)
        self.open_together(reader, reader)

        self.client.force_authenticate(admin)
        listed = self.client.get("/api/v1/audit/", {
            "event_type": "ACCESS", "record": self.record.pk, "user": reader.pk,
        })
        self.assertEqual(listed.data["count"], 1)


class TrendingTests(APITestCase):
    """Discover's orderings: Trending is views gained in the last 30 days,
    then all-time views, then newest; Most Viewed is all-time views."""

    NOW = datetime(2026, 11, 12, 9, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.owner = person("trend-owner@cit.edu")
        self.viewer = person("trend-viewer@cit.edu")
        self.readers = [person(f"trend-reader-{i}@cit.edu") for i in range(3)]
        self.old = self.paper_at("Viewed long ago", days_ago=200)
        self.rising = self.paper_at("Rising", days_ago=100)
        self.steady = self.paper_at("One recent view", days_ago=90)
        self.quiet_older = self.paper_at("Quiet, older", days_ago=60)
        self.quiet_newer = self.paper_at("Quiet, newer", days_ago=50)

        self.view(self.old, self.readers, days_ago=40)
        self.view(self.rising, self.readers[:2], days_ago=3)
        self.view(self.steady, self.readers[:1], days_ago=29)

    def paper_at(self, title, days_ago):
        with patch("django.utils.timezone.now", return_value=self.NOW - timedelta(days=days_ago)):
            return paper(self.owner, title=title)

    def view(self, record, readers, days_ago):
        with patch("django.utils.timezone.now", return_value=self.NOW - timedelta(days=days_ago)):
            for reader in readers:
                self.client.force_authenticate(reader)
                self.assertEqual(self.client.post(open_url(record)).status_code, 200)

    def listed(self, ordering):
        self.client.force_authenticate(self.viewer)
        with patch("django.utils.timezone.now", return_value=self.NOW):
            response = self.client.get("/api/v1/records/", {"ordering": ordering})
        self.assertEqual(response.status_code, 200, response.content)
        return [row["title"] for row in response.data["results"]]

    def test_trending_orders_by_recent_views_then_all_time_then_newest(self):
        self.assertEqual(self.listed("trending"), [
            "Rising", "One recent view", "Viewed long ago", "Quiet, newer", "Quiet, older",
        ])

    def test_most_viewed_orders_by_all_time_views(self):
        self.assertEqual(self.listed("-access_count")[:3], ["Viewed long ago", "Rising", "One recent view"])


class RebuildFromAccessHistoryTests(APITestCase):
    """The one-time recount in migration 0040, run on crafted `ACCESS` history.

    One view per distinct non-owner account per published paper, dated by that
    account's earliest opening after publication where a publication date is
    recorded (a `PUBLISHED` audit event, IR-144; earlier papers have none).
    """

    T0 = datetime(2026, 10, 1, 9, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.owner = person("rebuild-owner@cit.edu")
        self.first = person("rebuild-first@cit.edu")
        self.second = person("rebuild-second@cit.edu")
        self.gone = person("rebuild-gone@cit.edu")
        self.gone.deleted_at = self.T0
        self.gone.save(update_fields=["deleted_at"])

    def event(self, event_type, user, record, when):
        from apps.audit.models import AuditEvent

        with patch("django.utils.timezone.now", return_value=when):
            AuditEvent.objects.create(event_type=event_type, user=user, record=record)

    def rebuild(self):
        from importlib import import_module

        from django.apps import apps

        import_module("apps.records.migrations.0040_rebuild_record_views").rebuild_views(apps, None)

    def views_of(self, record):
        record.refresh_from_db()
        return record.access_count

    def test_counts_each_non_owner_account_once_after_publication(self):
        published = paper(self.owner, title="Published")
        Record.objects.filter(pk=published.pk).update(access_count=99)
        self.event("PUBLISHED", self.owner, published, self.T0)
        self.event("ACCESS", self.first, published, self.T0 - timedelta(days=5))
        self.event("ACCESS", self.first, published, self.T0 + timedelta(days=2))
        self.event("ACCESS", self.first, published, self.T0 + timedelta(days=10))
        self.event("ACCESS", self.second, published, self.T0 + timedelta(days=1))
        self.event("ACCESS", self.owner, published, self.T0 + timedelta(days=3))
        self.event("ACCESS", self.gone, published, self.T0 + timedelta(days=4))
        self.event("ACCESS", None, published, self.T0 + timedelta(days=4))

        self.rebuild()

        # Rule change, decided 2026-11-12 by Hermoine Zozobrado: a deleted
        # account's view stays in the count, as it does when an account is
        # deleted after viewing. Its row is never stored.
        self.assertEqual(self.views_of(published), 3)

    def test_a_deleted_account_is_counted_but_not_remembered(self):
        from apps.records.models import RecordView

        published = paper(self.owner, title="Published")
        self.event("ACCESS", self.gone, published, self.T0)

        self.rebuild()

        self.assertEqual(self.views_of(published), 1)
        self.assertFalse(RecordView.objects.filter(user=self.gone).exists())

    def test_a_published_paper_awaiting_deletion_keeps_its_views(self):
        from apps.records.models import DeleteRequest

        waiting = paper(self.owner, PipelineStatus.PENDING_DELETE, title="Awaiting deletion")
        DeleteRequest.objects.create(
            record=waiting, requested_by=self.owner, status="pending",
            previous_pipeline_status=PipelineStatus.PUBLISHED,
        )
        self.event("ACCESS", self.first, waiting, self.T0)

        self.rebuild()

        self.assertEqual(self.views_of(waiting), 1)

    def test_a_paper_whose_deletion_was_approved_has_no_views(self):
        from apps.records.models import RecordView

        gone = paper(self.owner, PipelineStatus.PENDING_DELETE, title="Deleted")
        Record._base_manager.filter(pk=gone.pk).update(is_deleted=True)
        self.event("ACCESS", self.first, gone, self.T0)

        self.rebuild()

        self.assertFalse(RecordView.objects.filter(record=gone).exists())

    def test_a_view_is_dated_by_the_first_opening_after_publication(self):
        from apps.records.models import RecordView

        published = paper(self.owner, title="Published")
        self.event("PUBLISHED", self.owner, published, self.T0)
        self.event("ACCESS", self.first, published, self.T0 - timedelta(days=5))
        self.event("ACCESS", self.first, published, self.T0 + timedelta(days=2))

        self.rebuild()

        self.assertEqual(
            RecordView.objects.get(record=published, user=self.first).viewed_at,
            self.T0 + timedelta(days=2),
        )

    def test_without_a_publication_date_every_opening_counts_from_the_first(self):
        from apps.records.models import RecordView

        older = paper(self.owner, title="Published before IR-144")
        self.event("ACCESS", self.first, older, self.T0 - timedelta(days=100))
        self.event("ACCESS", self.first, older, self.T0)

        self.rebuild()

        self.assertEqual(self.views_of(older), 1)
        self.assertEqual(
            RecordView.objects.get(record=older, user=self.first).viewed_at,
            self.T0 - timedelta(days=100),
        )

    def test_a_paper_that_is_not_published_has_no_views(self):
        in_review = paper(self.owner, PipelineStatus.IN_REVIEW, "In review")
        Record.objects.filter(pk=in_review.pk).update(access_count=57)
        self.event("ACCESS", self.first, in_review, self.T0)

        self.rebuild()

        self.assertEqual(self.views_of(in_review), 0)

    def test_an_account_counted_by_the_rebuild_is_not_counted_again(self):
        published = paper(self.owner, title="Published")
        self.event("ACCESS", self.first, published, self.T0)
        self.rebuild()

        self.client.force_authenticate(self.first)
        response = self.client.post(open_url(published))

        self.assertEqual(response.data["access_count"], 1)
