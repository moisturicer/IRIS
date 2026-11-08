"""
IR-795: before the System Admin saves a retention period, the Retention page
asks how many items it would erase (ADR-051 decision 19).

**Seam: `GET /settings/<key>/erasure-preview/?days=N` and `retention.preview`.**
The count comes from the same query the eraser runs, so the tests check it
against what `run_retention` then erases, and that asking erases nothing.
"""

from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import SystemSetting
from apps.audit import retention
from apps.audit.models import AuditEvent
from apps.audit.retention import RetentionType, run_retention
from apps.records.models import DownloadRequest, Record, RecordType
from apps.records.retention import SETTING_KEY, TYPE_KEY
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

from .test_retention import RDCO_NOTE, READER_NOTE, _user, set_period


class ErasurePreviewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sysadmin = _user("preview-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.rdco = _user("preview-rdco@cit.edu", RoleName.RDCO)
        cls.reader = _user("preview-reader@cit.edu", RoleName.STUDENT)
        cls.record = Record.objects.create(
            title="A published thesis",
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            pipeline_status=PipelineStatus.PUBLISHED,
        )
        cls.url = f"/api/v1/settings/{SETTING_KEY}/erasure-preview/"

    def setUp(self):
        self.client.force_authenticate(self.sysadmin)

    def request(self, *, age, status=RequestStatus.DECLINED):
        made = DownloadRequest.objects.create(
            record=self.record, requested_by=self.reader, status=status,
            note=READER_NOTE, rdco_note=RDCO_NOTE,
        )
        DownloadRequest.objects.filter(pk=made.pk).update(created_at=timezone.now() - age)
        return made

    def preview(self, days):
        return self.client.get(self.url, {"days": days})

    def test_it_counts_what_a_run_would_erase_and_erases_nothing(self):
        self.request(age=timedelta(days=100))
        self.request(age=timedelta(days=50))
        self.request(age=timedelta(days=10))
        self.request(age=timedelta(days=100), status=RequestStatus.PENDING)

        response = self.preview("30")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"key": SETTING_KEY, "days": 30, "count": 2})
        self.assertEqual(DownloadRequest.objects.exclude(note="").count(), 4)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.RETENTION_CLEANUP_RUN).exists())
        self.assertEqual(SystemSetting.objects.get(key=SETTING_KEY).value, "")

    def test_the_count_matches_what_the_run_then_erases(self):
        for days in (5, 40, 70, 400):
            self.request(age=timedelta(days=days))
        for period in ("1", "60", "365", "1000"):
            with self.subTest(period=period):
                previewed = self.preview(period).json()["count"]
                set_period(period)
                self.assertEqual(run_retention()[TYPE_KEY], previewed)
                # Put the notes back for the next period.
                DownloadRequest.objects.update(note=READER_NOTE, rdco_note=RDCO_NOTE)

    def test_a_blank_period_previews_nothing(self):
        self.request(age=timedelta(days=1000))

        for days in ("", "  "):
            with self.subTest(days=days):
                response = self.preview(days)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"key": SETTING_KEY, "days": None, "count": 0})

    def test_a_period_that_is_not_whole_days_is_refused_against_its_field(self):
        for days in ("abc", "0", "-1", "1.5"):
            with self.subTest(days=days):
                response = self.preview(days)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"days": ["Enter a whole number of days, or leave it blank to erase nothing."]},
                )

    def test_a_missing_period_is_refused(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("days", response.json())

    def test_a_setting_that_is_not_a_retention_period_is_not_found(self):
        SystemSetting.objects.get_or_create(key="preview.not_retention", defaults={"value": "1"})

        for key in ("preview.not_retention", "no.such.key"):
            with self.subTest(key=key):
                response = self.client.get(f"/api/v1/settings/{key}/erasure-preview/", {"days": "30"})
                self.assertEqual(response.status_code, 404)

    def test_a_type_that_cannot_count_says_so(self):
        uncountable = RetentionType(key="zz_uncounted", setting_key="retention.zz_uncounted_days",
                                    erase=lambda cutoff: 0)
        with mock.patch.dict(retention._REGISTRY, {uncountable.key: uncountable}):
            response = self.client.get(
                f"/api/v1/settings/{uncountable.setting_key}/erasure-preview/", {"days": "30"},
            )

        self.assertEqual(response.status_code, 501)

    def test_only_the_system_admin_may_ask(self):
        self.client.force_authenticate(self.rdco)
        self.assertEqual(self.preview("30").status_code, 403)

        self.client.force_authenticate(None)
        self.assertEqual(self.preview("30").status_code, 401)
