"""
A reviewer requests a document and the owner uploads it (IR-262, ADR-022).

ADR-022 §3: a reviewer who holds a Record asks the owner for specific
documents. The Record stays in review. No clearance resets, no assignment
closes, `pipeline_status` does not move, and the owner does not resubmit. They
upload against each requested item, and once every item has a file the request
is fulfilled and the requesting party is told.

**Seam: the HTTP API** (IR-255's confirmed seam). Records are driven through
the real submit and review endpoints, so the assignments a request is checked
against are the ones IR-257 dual-writes. Uploads go through the existing
`/documents/submit/` endpoint, because ADR-022 adds no second upload path.

Accepting, rejecting and withdrawing (ADR-022 §3.4, §4), and the rule that
only the owner fulfils, are IR-263's: `test_document_request_decisions.py`.
A decision closing open requests (§3) is IR-270's.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest, RecordUpload, UploadSlot
from apps.notifications.models import Notification
from apps.records.test_tracker import TrackerTestBase
from apps.reviews.models import RecordAssignment
from core.enums import RecordTypeName

SUBMIT_DOCUMENT = "/api/v1/documents/submit/"
SLOTS = "/api/v1/documents/slots/"


def pdf(name="evidence.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 requested", content_type="application/pdf")


class DocumentRequestTestBase(TrackerTestBase):

    def slot(self, record, name):
        return UploadSlot.objects.get_or_create(
            name=name, record_type=record.record_type, record=None,
        )[0]

    def requests_url(self, record):
        return reverse("record-document-requests", args=[record.pk])

    def request_documents(self, record, actor, items, message="Please send this.", **extra):
        self.client.force_authenticate(actor)
        return self.client.post(
            self.requests_url(record),
            {"message": message, "items": items, **extra},
            format="json",
        )

    def requested(self, record, actor, items, **extra):
        response = self.request_documents(record, actor, items, **extra)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def listed(self, record, viewer=None):
        self.client.force_authenticate(viewer or self.owner)
        response = self.client.get(self.requests_url(record))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def upload_against(self, record, item_id, uploader=None, **extra):
        self.client.force_authenticate(uploader or self.owner)
        # The fulfilment notice is sent on commit; a TestCase never commits.
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                SUBMIT_DOCUMENT,
                {"record": record.pk, "request_item": item_id, "file": pdf(), **extra},
                format="multipart",
            )

    def uploaded(self, record, item_id):
        response = self.upload_against(record, item_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def snapshot(self, record):
        record.refresh_from_db()
        return {
            "pipeline_status": record.pipeline_status,
            "clearances": sorted(record.clearances.values_list("office", "status")),
            "assignments": sorted(
                RecordAssignment.objects.filter(record=record)
                .values_list("party", "state", "closed_at")
            ),
        }


class RequestReachesTheOwnerTests(DocumentRequestTestBase):

    def test_ierc_request_is_listed_for_the_owner_naming_ierc_with_its_message(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")

        self.requested(
            record, self.ierc, [{"slot": ethics.pk}],
            message="The signed consent forms are missing.",
        )

        [request] = self.listed(record, self.owner)
        self.assertEqual(request["party"], "ierc")
        self.assertEqual(request["label"], "IERC")
        self.assertEqual(request["state"], "open")
        self.assertEqual(request["message"], "The signed consent forms are missing.")
        [item] = request["items"]
        self.assertEqual(item["label"], "Ethics Clearance")
        self.assertEqual(item["slot"], ethics.pk)
        self.assertEqual(item["state"], "missing")
        self.assertIsNone(item["upload"])

    def test_the_owner_is_notified(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")

        self.requested(record, self.ierc, [{"slot": ethics.pk}])

        notice = Notification.objects.filter(recipient=self.owner, record=record).latest("created_at")
        self.assertIn("IERC", notice.message)
        self.assertIn("Ethics Clearance", notice.message)

    def test_an_other_item_carries_its_free_text_label_and_no_slot(self):
        record = self.at_parallel_review()

        data = self.requested(record, self.ierc, [{"label": "Rescanned consent form"}])

        [item] = data["items"]
        self.assertIsNone(item["slot"])
        self.assertEqual(item["label"], "Rescanned consent form")

    def test_the_message_is_returned_exactly_as_written(self):
        # ADR-022 §Security: shown as text, never rendered as markup. The API's
        # part is to hand it back untouched rather than escape or strip it.
        record = self.at_parallel_review()
        message = "<b>Bold</b> & <script>alert(1)</script>"

        self.requested(record, self.ierc, [{"label": "Form"}], message=message)

        self.assertEqual(self.listed(record)[0]["message"], message)


class IntakeCanRequestTests(DocumentRequestTestBase):

    def test_intake_creates_a_request_on_a_new_submission(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH, requested_itso=True)

        data = self.requested(record, self.rdco, [{"label": "Endorsement sheet"}])

        self.assertEqual(data["party"], "intake")

    def test_intake_reads_intake_to_the_owner(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH, requested_itso=True)
        self.requested(record, self.rdco, [{"label": "Endorsement sheet"}])

        self.assertEqual(self.listed(record, self.owner)[0]["label"], "Intake")
        self.assertEqual(self.listed(record, self.rdco)[0]["label"], "Intake & Triage")


class UploadsFulfilTheRequestTests(DocumentRequestTestBase):

    def test_an_upload_marks_its_item_uploaded_and_leaves_the_request_open(self):
        record = self.at_parallel_review()
        data = self.requested(
            record, self.ierc,
            [{"slot": self.slot(record, "Ethics Clearance").pk}, {"label": "Consent form"}],
        )
        first, second = data["items"]

        self.uploaded(record, first["id"])

        [request] = self.listed(record)
        self.assertEqual(request["state"], "open")
        self.assertEqual(request["items"][0]["state"], "uploaded")
        self.assertIsNotNone(request["items"][0]["upload"])
        self.assertEqual(request["items"][1]["state"], "missing")

    def test_the_last_upload_fulfils_the_request_and_notifies_ierc(self):
        record = self.at_parallel_review()
        data = self.requested(
            record, self.ierc,
            [{"slot": self.slot(record, "Ethics Clearance").pk}, {"label": "Consent form"}],
        )
        # The same filter on both sides (IR-263): this Record's IERC broadcasts.
        notices = Notification.objects.filter(broadcast_to_role=self.ierc.role, record=record)
        before = notices.count()

        for item in data["items"]:
            self.uploaded(record, item["id"])

        [request] = self.listed(record)
        self.assertEqual(request["state"], "fulfilled")
        self.assertIsNotNone(request["closed_at"])
        self.assertEqual(notices.count(), before + 1)
        self.assertIn("uploaded", notices.latest("created_at").message)

    def test_a_slot_item_lands_in_that_slot(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        [item] = self.requested(record, self.ierc, [{"slot": ethics.pk}])["items"]

        self.uploaded(record, item["id"])

        self.assertTrue(RecordUpload.objects.filter(record=record, slot=ethics).exists())

    def test_an_other_item_lands_in_a_slot_of_its_own_that_no_other_record_sees(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]

        self.uploaded(record, item["id"])

        upload = RecordUpload.objects.get(record=record, slot__name="Consent form")
        self.assertEqual(upload.slot.record_id, record.pk)
        # The ad-hoc slot is this record's alone: it is not on the type's list.
        self.client.force_authenticate(self.owner)
        listed = self.client.get(SLOTS, {"record_type": record.record_type_id}).data
        names = [s["name"] for s in listed.get("results", listed)]
        self.assertNotIn("Consent form", names)

    def test_the_slot_is_taken_from_the_item_and_a_contradicting_slot_is_refused(self):
        record = self.at_parallel_review()
        [item] = self.requested(
            record, self.ierc, [{"slot": self.slot(record, "Ethics Clearance").pk}]
        )["items"]

        response = self.upload_against(
            record, item["id"], slot=self.slot(record, "Patent Draft").pk
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_item_from_another_record_is_refused(self):
        record = self.at_parallel_review()
        other = self.at_parallel_review()
        [item] = self.requested(other, self.ierc, [{"label": "Consent form"}])["items"]

        response = self.upload_against(record, item["id"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_another_records_ad_hoc_slot_takes_no_upload_through_either_endpoint(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]
        self.uploaded(record, item["id"])
        adhoc = UploadSlot.objects.get(record=record)
        # The same owner, so authorization passes and only the slot is wrong.
        other = self.at_parallel_review()

        self.client.force_authenticate(self.owner)
        for endpoint in (SUBMIT_DOCUMENT, "/api/v1/documents/uploads/create/"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    endpoint, {"record": other.pk, "slot": adhoc.pk, "file": pdf()},
                    format="multipart",
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(RecordUpload.objects.filter(record=other).exists())

    def test_an_item_on_a_fulfilled_request_takes_no_more_uploads(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]
        self.uploaded(record, item["id"])

        response = self.upload_against(record, item["id"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NothingElseChangesTests(DocumentRequestTestBase):

    def test_opening_and_fulfilling_a_request_moves_no_status_clearance_or_assignment(self):
        record = self.at_parallel_review()
        before = self.snapshot(record)

        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]
        self.assertEqual(self.snapshot(record), before)

        self.uploaded(record, item["id"])
        self.assertEqual(self.snapshot(record), before)

    def test_another_office_can_clear_while_the_request_is_open(self):
        record = self.at_parallel_review()
        self.requested(record, self.ierc, [{"label": "Consent form"}])

        self.review(record, self.ktto, "approved", "No commercial concerns.")

        self.assertEqual(record.clearances.get(office="ktto").status, "cleared")


class WorkflowStateTests(DocumentRequestTestBase):

    def test_an_open_request_makes_the_record_awaiting_document(self):
        record = self.at_parallel_review()
        self.requested(record, self.ierc, [{"label": "Consent form"}])

        self.assertEqual(self.detail(record)["workflow_state"], "awaiting_document")
        tracker = self.tracker_ok(record)
        self.assertEqual(tracker["workflow_state"], "awaiting_document")

    def test_the_tracker_lists_the_request_and_flags_the_waiting_party(self):
        record = self.at_parallel_review()
        self.requested(record, self.ierc, [{"label": "Consent form"}], message="Rescan it.")

        tracker = self.tracker_ok(record)

        [request] = tracker["document_requests"]
        self.assertEqual(request["party"], "ierc")
        self.assertEqual(request["message"], "Rescan it.")
        rows = {row["party"]: row for row in tracker["parties"]}
        self.assertTrue(rows["ierc"]["awaiting_document"])
        self.assertFalse(rows["ktto"]["awaiting_document"])

    def test_a_fulfilled_request_no_longer_holds_the_record(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]

        self.uploaded(record, item["id"])

        self.assertEqual(self.detail(record)["workflow_state"], "in_review")
        rows = {row["party"]: row for row in self.tracker_ok(record)["parties"]}
        self.assertFalse(rows["ierc"]["awaiting_document"])

    def test_detail_says_which_parties_the_viewer_may_request_as(self):
        record = self.at_parallel_review()

        self.assertEqual(self.detail(record, self.ierc)["can_request_document"], ["ierc"])
        self.assertEqual(self.detail(record, self.owner)["can_request_document"], [])


class AccessTests(DocumentRequestTestBase):

    def test_an_office_that_does_not_hold_the_record_cannot_request(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH, requested_itso=True)

        response = self.request_documents(record, self.ierc, [{"label": "Consent form"}])

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DocumentRequest.objects.exists())

    def test_the_owner_cannot_request_from_themselves(self):
        record = self.at_parallel_review()

        response = self.request_documents(record, self.owner, [{"label": "Consent form"}])

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_party_the_user_cannot_staff_is_refused(self):
        record = self.at_parallel_review()

        response = self.request_documents(
            record, self.ierc, [{"label": "Consent form"}], party="ktto"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_user_without_access_gets_404_on_both_list_and_create(self):
        record = self.at_parallel_review()
        self.requested(record, self.ierc, [{"label": "Consent form"}])

        self.client.force_authenticate(self.stranger)
        self.assertEqual(
            self.client.get(self.requests_url(record)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        response = self.request_documents(record, self.stranger, [{"label": "Other"}])
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_stranger_cannot_upload_against_an_item(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]

        response = self.upload_against(record, item["id"], uploader=self.stranger)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.listed(record)[0]["items"][0]["state"], "missing")


class ValidationTests(DocumentRequestTestBase):

    def test_a_request_needs_at_least_one_item(self):
        record = self.at_parallel_review()

        response = self.request_documents(record, self.ierc, [])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_request_needs_a_message(self):
        record = self.at_parallel_review()

        response = self.request_documents(record, self.ierc, [{"label": "Form"}], message="  ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_slot_from_another_record_type_is_refused(self):
        record = self.at_parallel_review()
        proposal_slot = UploadSlot.objects.filter(
            record_type__name=RecordTypeName.PROPOSAL
        ).first() or UploadSlot.objects.create(
            name="NDA", record_type=self.make_record(RecordTypeName.PROPOSAL).record_type
        )

        response = self.request_documents(record, self.ierc, [{"slot": proposal_slot.pk}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_blank_slot_beside_a_label_is_an_other_item(self):
        # Kept when input moved onto a serializer (IR-263).
        record = self.at_parallel_review()

        data = self.requested(record, self.ierc, [{"slot": "", "label": "Consent form"}])

        self.assertIsNone(data["items"][0]["slot"])
        self.assertEqual(data["items"][0]["label"], "Consent form")

    def test_a_slot_that_is_not_an_id_is_refused_as_not_on_the_picklist(self):
        record = self.at_parallel_review()

        response = self.request_documents(record, self.ierc, [{"slot": "ethics"}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "That document is not one this record type can be asked for.",
        )

    def test_an_item_needs_a_slot_or_a_label(self):
        record = self.at_parallel_review()

        response = self.request_documents(record, self.ierc, [{"label": "   "}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PicklistTests(DocumentRequestTestBase):

    def test_the_picklist_is_the_record_types_slots(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")

        self.client.force_authenticate(self.ierc)
        response = self.client.get(reverse("record-document-request-slots", args=[record.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn({"id": ethics.pk, "name": "Ethics Clearance"}, response.data)

    def test_the_picklist_is_404_to_a_user_without_access(self):
        record = self.at_parallel_review()

        self.client.force_authenticate(self.stranger)
        response = self.client.get(reverse("record-document-request-slots", args=[record.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
