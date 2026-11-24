"""
Held uploads and *Request changes* (ADR-022 Amendment 8, IR-1322).

An owner's upload to a submitted Record is held until they send it: with
*Submit new version*, or *Submit added documents*
(`POST /records/<id>/documents/send/`). Until then it is the owners' alone,
answers no request and can be deleted by them. A reviewer's *Request changes*
may ask for a revision and documents in one act, or for documents alone.

**Seam: the HTTP API**, except the owner's upload, which is made through
`_store_slot_upload` (what both upload routes call) because the PDF check only
runs on Linux and these tests are about what happens after the file is stored.
`test_document_requests` covers the upload routes themselves.
"""

from django.db import transaction
from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest, DocumentRequestItem, RecordUpload
from apps.documents.views import _store_slot_upload
from apps.notifications.models import Notification
from apps.records.models import RecordVersionDocument
from apps.reviews.models import RecordAssignment, ResubmissionRequest, ReviewRound
from apps.reviews.submitter_status import waiting_on_you
from core.enums import DocumentRequestItemState, DocumentRequestState, ResubmissionRequestState

from .test_document_requests import DocumentRequestTestBase, pdf

UPLOADS = "/api/v1/documents/uploads/"


class HeldUploadTestBase(DocumentRequestTestBase):

    def stored(self, record, slot, user=None):
        """`user` (the owner) uploads into `slot`, as both upload routes do."""
        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            return _store_slot_upload(record, slot, pdf(), user or self.owner)

    def send(self, record, user=None):
        self.client.force_authenticate(user or self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("record-send-documents", args=[record.pk]), format="json")

    def slot_uploads(self, record, viewer):
        """Every upload id the Documents tab's slot listing shows `viewer`."""
        self.client.force_authenticate(viewer)
        response = self.client.get(reverse("record-slot-list", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {u["id"]: u for slot in response.data for u in slot["uploads"]}

    def listed_uploads(self, record, viewer):
        self.client.force_authenticate(viewer)
        response = self.client.get(UPLOADS, {"record": record.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return {u["id"] for u in rows}

    def open_seat(self, record, actor):
        assignment = RecordAssignment.objects.get(
            record=record, party=actor.role.name.lower(), state="active",
        )
        seat = assignment.seats.get(reviewer=actor)
        self.client.force_authenticate(actor)
        opened = self.client.post(f"/api/v1/seats/{seat.pk}/open/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)

    def finish(self, record, actor, **body):
        self.client.force_authenticate(actor)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("record-finish-review", args=[record.pk]),
                {"summary": "Please revise.", **body}, format="json",
            )

    def fulfilment_notices(self, user):
        """An office hears as a role broadcast; the Adviser directly."""
        from django.db.models import Q

        return Notification.objects.filter(
            Q(recipient=user) | Q(broadcast_to_role=user.role),
            notif_type__name="Document Request Fulfilled",
        )


class AnUploadIsHeldTests(HeldUploadTestBase):

    def test_an_owners_upload_to_a_submitted_record_is_held_and_theirs_alone(self):
        record = self.at_parallel_review()
        upload = self.stored(record, self.slot(record, "Ethics Clearance"))

        self.assertTrue(upload.held)
        self.assertTrue(self.slot_uploads(record, self.owner)[upload.pk]["held"])
        self.assertIn(upload.pk, self.listed_uploads(record, self.owner))
        for reviewer in (self.ierc, self.adviser, self.rdco):
            with self.subTest(reviewer=reviewer.email):
                self.assertNotIn(upload.pk, self.slot_uploads(record, reviewer))
                self.assertNotIn(upload.pk, self.listed_uploads(record, reviewer))
                self.client.force_authenticate(reviewer)
                download = self.client.get(reverse("record-upload-download", args=[upload.pk]))
                # As if it did not exist, not a 403 that confirms it does.
                self.assertEqual(download.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_office_upload_is_sent_at_once(self):
        record = self.at_parallel_review()
        upload = self.stored(record, self.slot(record, "Ethics Clearance"), user=self.ierc)

        self.assertFalse(upload.held)
        self.assertIn(upload.pk, self.slot_uploads(record, self.ierc))

    def test_a_held_upload_answers_no_request_and_tells_nobody(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}])

        self.stored(record, ethics)

        [item] = data["items"]
        self.assertEqual(DocumentRequestItem.objects.get(pk=item["id"]).state, DocumentRequestItemState.MISSING)
        self.assertEqual(DocumentRequest.objects.get(pk=data["id"]).state, DocumentRequestState.OPEN)
        self.assertFalse(self.fulfilment_notices(self.ierc).exists())

    def test_the_owner_deletes_a_held_first_version_but_not_one_that_was_sent(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        held = self.stored(record, ethics)
        self.client.force_authenticate(self.owner)

        deleted = self.client.delete(reverse("record-upload-delete", args=[held.pk]))

        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RecordUpload.objects.filter(pk=held.pk).exists())

        self.requested(record, self.ierc, [{"slot": ethics.pk}])
        answered = self.stored(record, ethics)
        self.assertEqual(self.send(record).status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.owner)
        refused = self.client.delete(reverse("record-upload-delete", args=[answered.pk]))
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_reviewer_cannot_delete_a_held_upload_it_cannot_see(self):
        record = self.at_parallel_review()
        held = self.stored(record, self.slot(record, "Ethics Clearance"))
        self.client.force_authenticate(self.ierc)

        response = self.client.delete(reverse("record-upload-delete", args=[held.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(RecordUpload.objects.filter(pk=held.pk).exists())


class SubmitAddedDocumentsTests(HeldUploadTestBase):

    def test_sending_answers_the_request_and_tells_the_party_once(self):
        record = self.at_parallel_review()
        ethics, consent = self.slot(record, "Ethics Clearance"), self.slot(record, "Consent Paper")
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}, {"slot": consent.pk}])
        first, second = self.stored(record, ethics), self.stored(record, consent)
        before = self.fulfilment_notices(self.ierc).count()

        response = self.send(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"sent": 2, "requests_fulfilled": 1})
        self.assertEqual(DocumentRequest.objects.get(pk=data["id"]).state, DocumentRequestState.FULFILLED)
        self.assertEqual(
            set(DocumentRequestItem.objects.filter(request_id=data["id"]).values_list("upload_id", flat=True)),
            {first.pk, second.pk},
        )
        self.assertEqual(self.fulfilment_notices(self.ierc).count() - before, 1)
        self.assertTrue({first.pk, second.pk} <= set(self.slot_uploads(record, self.ierc)))

    def test_the_newest_upload_in_a_slot_answers_it(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}])
        self.stored(record, ethics)
        newer = self.stored(record, ethics)

        self.send(record)

        [item] = data["items"]
        self.assertEqual(DocumentRequestItem.objects.get(pk=item["id"]).upload_id, newer.pk)

    def test_an_other_item_is_answered_through_its_own_slot(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Signed consent forms"}])
        [item] = data["items"]
        from apps.documents.requests import resolve_item_for_upload

        with transaction.atomic():
            _, adhoc = resolve_item_for_upload(record, item["id"])
        upload = self.stored(record, adhoc)

        self.send(record)

        self.assertEqual(DocumentRequestItem.objects.get(pk=item["id"]).upload_id, upload.pk)
        self.assertEqual(DocumentRequest.objects.get(pk=data["id"]).state, DocumentRequestState.FULFILLED)

    def test_a_file_sent_before_the_request_does_not_answer_it(self):
        record = self.at_parallel_review()
        ethics, consent = self.slot(record, "Ethics Clearance"), self.slot(record, "Consent Paper")
        self.stored(record, ethics)
        self.send(record)
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}])
        self.stored(record, consent)

        self.send(record)

        [item] = data["items"]
        self.assertEqual(DocumentRequestItem.objects.get(pk=item["id"]).state, DocumentRequestItemState.MISSING)

    def test_nothing_held_is_refused(self):
        record = self.at_parallel_review()

        response = self.send(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_an_owner_may_send(self):
        record = self.at_parallel_review()
        self.stored(record, self.slot(record, "Ethics Clearance"))

        self.assertEqual(self.send(record, user=self.ierc).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.send(record, user=self.stranger).status_code, status.HTTP_404_NOT_FOUND)

    def test_an_open_revision_sends_with_the_new_version_instead(self):
        record = self.at_parallel_review()
        self.open_seat(record, self.ierc)
        self.assertEqual(self.finish(record, self.ierc, verdict="request_revision").status_code, status.HTTP_200_OK)
        held = self.stored(record, self.slot(record, "Ethics Clearance"))

        self.assertEqual(self.send(record).status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.owner)
        submitted = self.client.post(reverse("record-new-version", args=[record.pk]), format="json")

        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        held.refresh_from_db()
        self.assertFalse(held.held)
        # The version it was sent with names it (ADR-058 §2).
        self.assertTrue(RecordVersionDocument.objects.filter(upload=held).exists())


class RequestChangesTests(HeldUploadTestBase):

    def test_one_act_asks_for_a_revision_and_documents_from_the_same_party(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        self.open_seat(record, self.ierc)

        response = self.finish(
            record, self.ierc, verdict="request_revision", documents=[{"slot": ethics.pk}],
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(ResubmissionRequest.objects.filter(
            record=record, party="ierc", state=ResubmissionRequestState.OPEN).exists())
        request = DocumentRequest.objects.get(record=record, party="ierc")
        self.assertEqual(request.state, DocumentRequestState.OPEN)
        self.assertEqual(request.message, "Please revise.")
        self.assertEqual(list(request.items.values_list("slot_id", flat=True)), [ethics.pk])

    def test_documents_alone_open_no_revision(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        self.open_seat(record, self.ierc)

        response = self.finish(
            record, self.ierc, verdict="request_revision", new_version=False,
            documents=[{"slot": ethics.pk}],
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(ResubmissionRequest.objects.filter(record=record).exists())
        self.assertTrue(DocumentRequest.objects.filter(record=record, party="ierc", state="open").exists())
        self.assertEqual(ReviewRound.objects.get(record=record, party="ierc").verdict, "comment_only")

    def test_no_new_version_and_no_documents_is_refused_and_changes_nothing(self):
        record = self.at_parallel_review()
        self.open_seat(record, self.ierc)

        response = self.finish(record, self.ierc, verdict="request_revision", new_version=False)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ReviewRound.objects.filter(record=record, party="ierc").exists())
        self.assertFalse(DocumentRequest.objects.filter(record=record).exists())

    def test_a_document_off_the_picklist_refuses_the_whole_act(self):
        record = self.at_parallel_review()
        self.open_seat(record, self.ierc)

        response = self.finish(record, self.ierc, verdict="request_revision", documents=[{"slot": 999999}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ResubmissionRequest.objects.filter(record=record).exists())
        self.assertFalse(DocumentRequest.objects.filter(record=record).exists())

    def test_only_request_changes_asks_for_documents(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        self.open_seat(record, self.ierc)

        response = self.finish(record, self.ierc, verdict="comment_only", documents=[{"slot": ethics.pk}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DocumentRequest.objects.filter(record=record).exists())


class OneItemPerPartyTests(HeldUploadTestBase):

    def test_a_partys_revision_and_documents_are_one_item(self):
        items = waiting_on_you(
            workflow_state="awaiting_resubmission",
            revision_parties=["ierc"], document_parties=["ierc", "adviser"],
        )

        self.assertEqual(
            [(i["party"], i["kind"], i["label"]) for i in items],
            [("adviser", "document", "Changes requested by Adviser"),
             ("ierc", "revision", "Changes requested by IERC")],
        )
