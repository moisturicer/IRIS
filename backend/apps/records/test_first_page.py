"""GET /records/<id>/first-page/ and the drawing behind it (IR-1241).

A Discover row's thumbnail used to download the whole manuscript and write a
`DOWNLOAD` audit event. The endpoint reads the paper as the paper is read
(`visible_to`, the served file), never parses it in the request, and audits
nothing. The real sandbox child is tested in
`documents/pdf_evidence/tests/test_first_page.py`.
"""

import hashlib
import uuid
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.records import first_page
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus, RoleName

PDF = b"%PDF-1.7 fake bytes"
SHA = hashlib.sha256(PDF).hexdigest()
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 fake image"


def _pdf():
    return SimpleUploadedFile("thesis.pdf", PDF, content_type="application/pdf")


class FirstPageEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("fp-owner@cit.edu", RoleName.STUDENT)
        self.adviser = make_user("fp-adviser@cit.edu", RoleName.ADVISER)
        self.staff = make_user("fp-rdco@cit.edu", RoleName.RDCO)
        self.stranger = make_user("fp-stranger@cit.edu", RoleName.STUDENT)
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=record_type, added_by=self.owner,
            pipeline_status=PipelineStatus.IN_REVIEW, adviser=self.adviser,
            abstract_file=_pdf(), manuscript_revision=uuid.uuid4(), manuscript_sha256=SHA,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        queue = mock.patch("apps.records.tasks.draw_first_page.delay")
        self.delay = queue.start()
        self.addCleanup(queue.stop)

    def _get(self, user, record_id=None):
        self.client.force_authenticate(user)
        return self.client.get(reverse("record-first-page", args=[record_id or self.record.id]))

    def test_a_drawn_page_is_served_to_everyone_who_may_read_the_paper(self):
        cache.set(first_page.key("image", SHA), WEBP)
        for reader in (self.owner, self.adviser, self.staff):
            with self.subTest(reader=reader.email):
                response = self._get(reader)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.content, WEBP)
                self.assertEqual(response["Content-Type"], "image/webp")
        self.delay.assert_not_called()

    def test_the_image_is_never_cached_or_sniffed_as_something_else(self):
        cache.set(first_page.key("image", SHA), WEBP)
        response = self._get(self.owner)

        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Disposition"], "inline")

    def test_an_unrelated_reader_gets_the_404_of_a_missing_record(self):
        cache.set(first_page.key("image", SHA), WEBP)
        refused = self._get(self.stranger)
        missing = self._get(self.stranger, record_id=self.record.id + 10_000)

        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(refused.data, missing.data)
        self.delay.assert_not_called()

    def test_a_record_with_no_manuscript_says_so(self):
        Record.objects.filter(pk=self.record.pk).update(abstract_file="", manuscript_sha256="")
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "no_manuscript")
        self.delay.assert_not_called()

    def test_a_manuscript_with_no_fingerprint_is_unavailable_and_is_not_read(self):
        Record.objects.filter(pk=self.record.pk).update(manuscript_sha256="")
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "first_page_unavailable")
        self.delay.assert_not_called()

    def test_an_undrawn_page_is_queued_once_however_many_ask(self):
        first, second = self._get(self.owner), self._get(self.adviser)

        for response in (first, second):
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            self.assertEqual(response.data["code"], "first_page_pending")
        self.delay.assert_called_once_with(self.record.pk, self.owner.pk, SHA)

    def test_a_failed_drawing_is_unavailable_and_not_queued_again(self):
        cache.set(first_page.key("failed", SHA), "unreadable")
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "first_page_unavailable")
        self.delay.assert_not_called()

    def test_when_the_queue_is_down_the_next_request_tries_again(self):
        self.delay.side_effect = [ConnectionError("broker down"), None]
        self.assertEqual(self._get(self.owner).status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self._get(self.owner).status_code, status.HTTP_202_ACCEPTED)

        self.assertEqual(self.delay.call_count, 2)

    def test_a_new_manuscript_version_is_not_shown_the_old_image(self):
        cache.set(first_page.key("image", SHA), WEBP)
        Record.objects.filter(pk=self.record.pk).update(manuscript_sha256="b" * 64)
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.delay.assert_called_once_with(self.record.pk, self.owner.pk, "b" * 64)

    def test_each_reader_sees_the_image_of_the_file_they_are_served(self):
        """An owner's unsubmitted file and everyone else's submitted one
        (`served_manuscript_identity`) are two images, never mixed."""
        cache.set(first_page.key("image", "o" * 64), b"RIFF\x00\x00\x00\x00WEBPowner")
        cache.set(first_page.key("image", "s" * 64), b"RIFF\x00\x00\x00\x00WEBPsubmitted")

        def identity(record, user):
            return (None, "o" * 64 if user == self.owner else "s" * 64)

        with mock.patch("apps.records.versions.served_manuscript_identity", identity):
            self.assertTrue(self._get(self.owner).content.endswith(b"owner"))
            self.assertTrue(self._get(self.staff).content.endswith(b"submitted"))

    def test_no_request_writes_an_audit_event(self):
        before = AuditEvent.objects.count()
        self._get(self.owner)  # 202
        cache.set(first_page.key("image", SHA), WEBP)
        self._get(self.owner)  # 200

        self.assertEqual(AuditEvent.objects.count(), before)


class DrawTests(APITestCase):
    """`first_page.draw`, the task's body, with the sandbox child faked."""

    def setUp(self):
        cache.clear()
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("draw-owner@cit.edu", RoleName.STUDENT)
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=record_type, added_by=self.owner,
            pipeline_status=PipelineStatus.IN_REVIEW, adviser=make_user("draw-adviser@cit.edu", RoleName.ADVISER),
            abstract_file=_pdf(), manuscript_revision=uuid.uuid4(), manuscript_sha256=SHA,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        cache.set(first_page.key("drawing", SHA), True)

    def _draw(self, sha=SHA):
        return first_page.draw(self.record.pk, self.owner.pk, sha)

    def test_a_drawn_page_is_stored_by_the_file_hash_and_the_marker_cleared(self):
        with mock.patch.object(first_page, "render", return_value=(WEBP, "")) as render:
            self.assertEqual(self._draw(), first_page.READY)

        render.assert_called_once_with(PDF)
        self.assertEqual(cache.get(first_page.key("image", SHA)), WEBP)
        self.assertIsNone(cache.get(first_page.key("drawing", SHA)))

    def test_a_failed_drawing_is_remembered(self):
        with mock.patch.object(first_page, "render", return_value=(None, "encrypted")):
            self.assertEqual(self._draw(), "encrypted")

        self.assertEqual(cache.get(first_page.key("failed", SHA)), "encrypted")
        self.assertIsNone(cache.get(first_page.key("image", SHA)))
        self.assertIsNone(cache.get(first_page.key("drawing", SHA)))

    def test_a_file_replaced_since_it_was_asked_for_is_not_drawn_under_the_old_hash(self):
        with mock.patch.object(first_page, "render") as render:
            self.assertEqual(self._draw(sha="c" * 64), "changed")

        render.assert_not_called()
        self.assertIsNone(cache.get(first_page.key("image", "c" * 64)))
        self.assertIsNone(cache.get(first_page.key("failed", "c" * 64)))

    def test_a_file_missing_from_storage_is_remembered_as_failed(self):
        with mock.patch("django.db.models.fields.files.FieldFile.open", side_effect=FileNotFoundError):
            self.assertEqual(self._draw(), "missing_file")

        self.assertEqual(cache.get(first_page.key("failed", SHA)), "missing_file")

    def test_a_deleted_record_draws_nothing(self):
        self.assertEqual(first_page.draw(self.record.pk + 10_000, self.owner.pk, SHA), "gone")
        self.assertIsNone(cache.get(first_page.key("drawing", SHA)))


def test_the_drawing_runs_on_the_extraction_worker():
    """With the other PDF work, on the worker built for it, never `default`."""
    assert settings.CELERY_TASK_ROUTES["apps.records.tasks.draw_first_page"] == {"queue": "extraction"}


def test_only_a_webp_is_accepted_from_the_child():
    assert first_page.is_webp(WEBP)
    assert not first_page.is_webp(b"\x89PNG\r\n\x1a\n not webp at all")
    assert not first_page.is_webp(b"RIFF")
