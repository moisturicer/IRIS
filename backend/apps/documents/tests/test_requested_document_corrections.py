"""
An owner reads, replaces and removes a requested document they uploaded,
until the party that asked has decided it (ADR-022 §Amendment 8).

**Seam: the HTTP API.** The PDF safety check runs only on Linux and is not what
these are about, so it is switched off around the uploads.
"""

from unittest import mock

from rest_framework import status

from apps.audit.models import AuditEvent
from apps.documents.models import DocumentRequestItem, RecordUpload, UploadSlot
from apps.records.models import Record, RecordOwner
from apps.reviews.models import RecordAssignment
from core.enums import AssignmentState, PipelineStatus

from .test_document_request_decisions import DecisionTestBase, REASON
from .test_document_requests import SUBMIT_DOCUMENT, pdf


class CorrectionTestBase(DecisionTestBase):

    def setUp(self):
        super().setUp()
        for check in ("pdf_upload_problem", "upload_problem"):
            patcher = mock.patch(f"apps.documents.views.{check}", return_value=None)
            patcher.start()
            self.addCleanup(patcher.stop)

    def item(self, item_id):
        return DocumentRequestItem.objects.get(pk=item_id)

    def replace(self, record, item_id, upload_id, as_user=None):
        return self.upload_against(record, item_id, uploader=as_user, replaces=upload_id)

    def remove(self, item_id, upload_id, as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.delete(
                f"/api/v1/document-request-items/{item_id}/upload/?upload={upload_id}"
            )

    def can_replace(self, record, viewer=None):
        [request] = self.listed(record, viewer)
        return [item["can_replace"] for item in request["items"]]

    def uploaded_once(self):
        record, request_id, item_id = self.one_item_uploaded()
        return record, request_id, item_id, self.item(item_id).upload_id

    def one_file_for_two(self):
        """IERC asked twice for one slot, and one slot upload answered both."""
        record = self.at_parallel_review()
        slot = self.slot(record, "Ethics Clearance")
        first = self.requested(record, self.ierc, [{"slot": slot.pk}])["items"][0]["id"]
        second = self.requested(record, self.ierc, [{"slot": slot.pk}])["items"][0]["id"]
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            SUBMIT_DOCUMENT, {"record": record.pk, "slot": slot.pk, "file": pdf()}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return record, first, second, self.item(first).upload_id


class ReplaceTests(CorrectionTestBase):

    def test_the_new_file_takes_its_place_and_the_request_stays_fulfilled(self):
        record, request_id, item_id, first = self.uploaded_once()

        response = self.replace(record, item_id, first)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        item = self.item(item_id)
        self.assertEqual((item.state, item.upload.version), ("uploaded", 2))
        self.assertFalse(RecordUpload.objects.filter(pk=first).exists())
        self.assertEqual(self.request_state(request_id), "fulfilled")
        self.assertTrue(
            AuditEvent.objects.filter(event_type="DOCUMENT_REQUEST_REPLACED", record=record).exists()
        )

    def test_without_saying_what_it_replaces_an_upload_is_still_refused(self):
        record, _, item_id, _ = self.uploaded_once()

        response = self.upload_against(record, item_id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_file_replaced_meanwhile_is_not_overwritten(self):
        record, _, item_id, first = self.uploaded_once()
        self.replace(record, item_id, first)

        response = self.replace(record, item_id, first)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("changed", response.data["detail"])
        self.assertEqual(RecordUpload.objects.filter(record=record).count(), 1)

    def test_an_accepted_document_stays_as_it_is(self):
        record, _, item_id, first = self.uploaded_once()
        self.decided(item_id, self.ierc, "accept")

        for response in (self.replace(record, item_id, first), self.remove(item_id, first)):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("accepted", response.data["detail"])
        self.assertEqual(self.item(item_id).upload_id, first)

    def test_a_party_that_no_longer_has_the_paper_closes_it(self):
        record, _, item_id, first = self.uploaded_once()
        RecordAssignment.objects.filter(record=record, party="ierc").update(
            state=AssignmentState.COMPLETED,
        )

        self.assertEqual(self.can_replace(record), [False])
        self.assertEqual(self.remove(item_id, first).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.replace(record, item_id, first).status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_a_verdict_on_the_replaced_file_does_not_land_on_the_new_one(self):
        record, _, item_id, first = self.uploaded_once()
        self.replace(record, item_id, first)
        self.client.force_authenticate(self.ierc)

        for body in ({"action": "accept"}, {"action": "reject", "reason": REASON}):
            response = self.client.patch(
                self.item_url(item_id), {**body, "upload": first}, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("replaced", response.data["detail"])
        self.assertEqual(self.item_state(item_id), "uploaded")

        latest = self.item(item_id).upload_id
        response = self.client.patch(
            self.item_url(item_id), {"action": "accept", "upload": latest}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_one_file_answering_two_requests_is_replaced_for_both(self):
        record, first_item, second_item, upload = self.one_file_for_two()

        response = self.replace(record, first_item, upload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.item(first_item).upload_id, self.item(second_item).upload_id)
        self.assertNotEqual(self.item(first_item).upload_id, upload)


class RemoveTests(CorrectionTestBase):

    def test_the_document_is_asked_for_again_and_the_file_is_gone(self):
        record, _, item_id, upload = self.uploaded_once()
        file = RecordUpload.objects.get(pk=upload).file
        storage, name = file.storage, file.name
        self.assertTrue(storage.exists(name))

        response = self.remove(item_id, upload)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["state"], "open")
        self.assertEqual(response.data["items"][0]["state"], "missing")
        self.assertEqual(self.detail(record)["workflow_state"], "awaiting_document")
        self.assertFalse(RecordUpload.objects.filter(pk=upload).exists())
        self.assertFalse(storage.exists(name))
        # The "Other" document's own slot goes with its last file.
        self.assertFalse(UploadSlot.objects.filter(record=record).exists())
        self.assertTrue(
            AuditEvent.objects.filter(event_type="DOCUMENT_REQUEST_REMOVED", record=record).exists()
        )

    def test_it_can_be_uploaded_again(self):
        record, request_id, item_id, upload = self.uploaded_once()
        self.remove(item_id, upload)

        self.uploaded(record, item_id)

        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_a_rejected_file_keeps_its_history_when_its_replacement_is_removed(self):
        record, _, item_id, first = self.uploaded_once()
        self.decided(item_id, self.ierc, "reject", REASON)
        self.uploaded(record, item_id)

        self.remove(item_id, self.item(item_id).upload_id)

        self.assertEqual(self.item(item_id).rejection_reason, REASON)
        self.assertEqual(
            list(RecordUpload.objects.filter(record=record).values_list("pk", flat=True)), [first],
        )

    def test_a_file_another_request_accepted_is_taken_back_but_kept(self):
        record, first_item, second_item, upload = self.one_file_for_two()
        self.decided(first_item, self.ierc, "accept")

        response = self.remove(second_item, upload)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.item(first_item).upload_id, upload)
        self.assertEqual(self.item_state(second_item), "missing")
        self.assertTrue(RecordUpload.objects.filter(pk=upload).exists())

    def test_a_missing_document_has_nothing_to_remove(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]

        for upload in ("", 1, "x"):
            with self.subTest(upload=upload):
                self.assertEqual(
                    self.remove(item["id"], upload).status_code, status.HTTP_400_BAD_REQUEST,
                )

    def test_a_withdrawn_request_is_left_alone(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        item_id = data["items"][0]["id"]
        self.uploaded(record, item_id)
        self.withdraw(data["id"], self.ierc)

        response = self.remove(item_id, self.item(item_id).upload_id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.item_state(item_id), "uploaded")


class WhoTests(CorrectionTestBase):

    def test_only_an_owner_replaces_or_removes(self):
        record, _, item_id, upload = self.uploaded_once()

        for user in (self.ierc, self.itso, self.adviser):
            with self.subTest(user=user.email):
                self.assertEqual(
                    self.remove(item_id, upload, as_user=user).status_code, status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.replace(record, item_id, upload, as_user=user).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
        self.assertEqual(self.item(item_id).upload_id, upload)

    def test_a_co_owner_may(self):
        record, _, item_id, upload = self.uploaded_once()
        RecordOwner.objects.create(record=record, user=self.stranger, is_primary=False)

        self.assertEqual(
            self.remove(item_id, upload, as_user=self.stranger).status_code, status.HTTP_200_OK,
        )

    def test_a_hidden_record_reads_as_missing_and_a_published_one_refuses(self):
        record, _, item_id, upload = self.uploaded_once()
        self.assertEqual(
            self.remove(item_id, upload, as_user=self.stranger).status_code, status.HTTP_404_NOT_FOUND,
        )
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        self.assertEqual(
            self.remove(item_id, upload, as_user=self.stranger).status_code, status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.remove(999999, upload).status_code, status.HTTP_404_NOT_FOUND)

    def test_the_owner_is_offered_it_until_it_is_decided_and_the_reviewer_never(self):
        record, _, item_id, _ = self.uploaded_once()

        self.assertEqual(self.can_replace(record), [True])
        self.assertEqual(self.can_replace(record, self.ierc), [False])
        self.decided(item_id, self.ierc, "accept")
        self.assertEqual(self.can_replace(record), [False])
