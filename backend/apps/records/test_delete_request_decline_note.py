"""
IR-1099: RDCO declines a delete request with a note, as it does a download
request (IR-688). The requester is told in-app and by email, with the note, and
the queue shows it on the decided row. An approval takes no note.

**Seam: the API.**
"""

from unittest import mock

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.records.models import DOWNLOAD_NOTE_MAX_LENGTH, DeleteRequest, Record
from apps.records.test_delete_request_queue import DELETE_REQUESTS, DeleteRequestFixtures
from core.enums import PipelineStatus, RequestStatus

NOTE = "It is cited by a published paper, so it stays."


class DeclineNoteTests(DeleteRequestFixtures, APITestCase):
    def setUp(self):
        # Email is captured at `send_email_async`: the broker is a real queue.
        patcher = mock.patch("apps.notifications.services.send_email_async")
        self.send_email = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, request, verdict, **data):
        self.client.force_authenticate(self.rdco)
        return self.client.post(f"{DELETE_REQUESTS}{request.pk}/{verdict}/", data, format="json")

    def test_declining_needs_a_note(self):
        request = self.raise_by_deleting(self.published_thesis("no-note"))

        for data in ({}, {"note": ""}, {"note": "   "}, {"note": 7}, {"note": None}):
            with self.subTest(data=data):
                response = self.post(request, "decline", **data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("note", response.data)

        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.record.pipeline_status, PipelineStatus.PENDING_DELETE)
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())
        self.send_email.assert_not_called()

    def test_a_note_over_the_limit_is_refused_and_one_at_the_limit_is_kept(self):
        too_long = self.raise_by_deleting(self.published_thesis("too-long"))
        response = self.post(too_long, "decline", note="x" * (DOWNLOAD_NOTE_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", response.data)
        too_long.refresh_from_db()
        self.assertEqual(too_long.status, RequestStatus.PENDING)

        at_limit = self.raise_by_deleting(self.published_thesis("at-limit"))
        response = self.post(at_limit, "decline", note="x" * DOWNLOAD_NOTE_MAX_LENGTH)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_the_note_is_stored_trimmed_and_the_record_restored(self):
        record = self.published_thesis("stored")
        request = self.raise_by_deleting(record)

        response = self.post(request, "decline", note=f"  {NOTE}  ")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request.refresh_from_db()
        self.assertEqual(
            (request.status, request.rdco_note, request.reviewed_by),
            (RequestStatus.DECLINED, NOTE, self.rdco),
        )
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)

    def test_the_requester_is_told_in_app_and_by_email_with_the_note(self):
        record = self.published_thesis("told")
        request = self.raise_by_deleting(record)

        self.post(request, "decline", note=NOTE)

        notice = Notification.objects.get(recipient=self.owner)
        self.assertIn(NOTE, notice.message)
        self.assertIn("declined", notice.message)
        [call] = self.send_email.call_args_list
        self.assertEqual(call.kwargs["recipient_list"], [self.owner.email])
        self.assertIn(NOTE, call.kwargs["message"])
        self.assertIn(f"/records/{record.pk}", call.kwargs["message"])

    def test_declining_twice_is_refused_and_keeps_the_first_note(self):
        request = self.raise_by_deleting(self.published_thesis("twice"))
        self.post(request, "decline", note=NOTE)

        response = self.post(request, "decline", note="A second thought.")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        request.refresh_from_db()
        self.assertEqual(request.rdco_note, NOTE)

    def test_an_approval_after_a_decline_is_refused_and_removes_nothing(self):
        record = self.published_thesis("decided-first")
        request = self.raise_by_deleting(record)
        self.post(request, "decline", note=NOTE)

        response = self.post(request, "approve")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.DECLINED)
        self.assertFalse(Record.objects.with_deleted().get(pk=record.pk).is_deleted)

    def test_approving_takes_no_note(self):
        request = self.raise_by_deleting(self.published_thesis("approved"))

        response = self.post(request, "approve")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request.refresh_from_db()
        self.assertEqual((request.status, request.rdco_note), (RequestStatus.APPROVED, ""))

    def test_the_queue_carries_the_note_and_an_older_decline_carries_none(self):
        noted = self.raise_by_deleting(self.published_thesis("noted"))
        self.post(noted, "decline", note=NOTE)
        # Declined before notes existed: the column's default, never a value.
        older = self.published_thesis("older")
        DeleteRequest.objects.create(
            record=older, requested_by=self.owner, status=RequestStatus.DECLINED,
            reviewed_by=self.rdco, reviewed_at=timezone.now(),
        )

        self.client.force_authenticate(self.rdco)
        rows = self.client.get(DELETE_REQUESTS, {"status": "decided"}).data["results"]

        self.assertEqual(
            {row["record_title"]: row["rdco_note"] for row in rows},
            {"IR-496 noted": NOTE, "IR-496 older": ""},
        )

    def test_the_note_cannot_be_written_through_the_queue_listing(self):
        request = self.raise_by_deleting(self.published_thesis("read-only"))
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(
            f"{DELETE_REQUESTS}{request.pk}/", {"rdco_note": "sneaked in"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        request.refresh_from_db()
        self.assertEqual(request.rdco_note, "")
