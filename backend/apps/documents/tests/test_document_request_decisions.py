"""
The requesting party withdraws (IR-263, ADR-022 §4).

§4: the requesting party may withdraw an open request; it closes and stays in
the history. It no longer accepts or rejects an upload: a sent document is
supplied (ADR-022 Amendment 10, IR-1338), so the Accept and Reject tests that
were here are gone with `PATCH /document-request-items/<id>/`. A rejection made
before then is still on file, and the tests that read one set it up directly.

§Amendment 2: the requesting party cannot fulfil its own request. Only the
Record's owners answer an item, so a staff upload against a `request_item` is
a 403 even though `authorize_record_documents` admits every office.

§Amendment 4 and 5, settled 2026-09-24: a caller who cannot see the Record,
or names an id that does not exist, gets a 404. A caller who can see the
Record but may not read its request data (`may_read_requests`) gets a 403 --
the 404 is never used to hide request authorization on a visible Record. A
reader who is not the requesting party gets a 403 as well.

**Seam: the HTTP API**, as for IR-262 and IR-349.
"""

import json

from rest_framework import status

from apps.documents.models import DocumentRequest, DocumentRequestItem, RecordUpload
from apps.notifications.models import Notification
from apps.records.models import Record
from apps.reviews.models import RecordAssignment
from core.enums import PipelineStatus, RecordTypeName

from .test_document_requests import DocumentRequestTestBase, SUBMIT_DOCUMENT, pdf

REASON = "The scan is unreadable; please rescan at 300 dpi."


class DecisionTestBase(DocumentRequestTestBase):

    def request_url(self, request_id):
        return f"/api/v1/document-requests/{request_id}/"

    def rejected_before(self, item_id, reason=REASON):
        """
        An item the requesting party rejected before IR-1338, as it stays on
        file: back to `missing` with its reason, and its request open again.
        """
        item = DocumentRequestItem.objects.get(pk=item_id)
        DocumentRequestItem.objects.filter(pk=item_id).update(
            state="missing", upload=None, rejection_reason=reason,
        )
        DocumentRequest.objects.filter(pk=item.request_id).update(state="open", closed_at=None)

    def withdraw(self, request_id, actor):
        self.client.force_authenticate(actor)
        return self.client.patch(
            self.request_url(request_id), {"action": "withdraw"}, format="json"
        )

    def one_item_uploaded(self, record=None):
        """IERC asked for one document and the owner uploaded it: fulfilled."""
        record = record or self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])
        [item] = data["items"]
        self.uploaded(record, item["id"])
        return record, data["id"], item["id"]

    def item_state(self, item_id):
        return DocumentRequestItem.objects.get(pk=item_id).state

    def request_state(self, request_id):
        return DocumentRequest.objects.get(pk=request_id).state


class WithdrawTests(DecisionTestBase):

    def test_withdrawing_closes_the_request_and_keeps_it_in_the_history(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])

        response = self.withdraw(data["id"], self.ierc)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["state"], "withdrawn")
        self.assertIsNotNone(response.data["closed_at"])
        [request] = self.tracker_ok(record)["document_requests"]
        self.assertEqual(request["state"], "withdrawn")
        self.assertEqual(self.detail(record)["workflow_state"], "in_review")

    def test_a_withdrawal_carries_no_reason_field(self):
        # IR-263 adds no withdrawal reason; IR-270 defines any it needs.
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])

        response = self.withdraw(data["id"], self.ierc)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn("withdrawal_reason", response.data)

    def test_only_an_open_request_can_be_withdrawn(self):
        _, request_id, _ = self.one_item_uploaded()

        response = self.withdraw(request_id, self.ierc)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_a_withdrawn_request_takes_no_uploads(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        first, second = data["items"]
        self.uploaded(record, first["id"])
        self.assertEqual(self.withdraw(data["id"], self.ierc).status_code, status.HTTP_200_OK)

        self.assertEqual(
            self.upload_against(record, second["id"]).status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_an_unknown_action_is_refused(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])

        self.client.force_authenticate(self.ierc)
        response = self.client.patch(
            self.request_url(data["id"]), {"action": "close"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.request_state(data["id"]), "open")


class OnlyTheRequestingPartyTests(DecisionTestBase):
    """Anyone who may read the request but is not its party: 403, and nothing moves."""

    def test_the_owner_and_other_parties_may_not_withdraw(self):
        record, request_id, item_id = self.one_item_uploaded()
        # All three may read the request (IR-349): the owner, ITSO (held and
        # cleared), KTTO (holds now). None of them asked.
        for actor in (self.owner, self.itso, self.ktto):
            with self.subTest(actor=actor.email):
                response = self.withdraw(request_id, actor)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(self.item_state(item_id), "uploaded")
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_the_party_is_what_counts_not_the_person(self):
        """
        Another IERC reviewer withdraws a request a colleague made: it is
        IERC's, not theirs. Changed deliberately by IR-1226 (ADR-022
        Amendment 7): they act once seated on IERC's review. An unseated
        IERC member no longer does. (By IR-1338 it withdraws: the
        Accept it was shown with is gone.)
        """
        from apps.documents.tests.test_record_document_authorization import seat_on
        from apps.records.test_tracker import make_user
        from core.enums import RoleName

        colleague = make_user("tracker-ierc-2@cit.edu", RoleName.IERC)
        record = self.at_parallel_review()
        request_id = self.requested(record, self.ierc, [{"label": "Consent form"}])["id"]
        self.assertEqual(self.withdraw(request_id, colleague).status_code, status.HTTP_403_FORBIDDEN)

        seat_on(RecordAssignment.objects.get(record=record, party="ierc", state="active"), colleague)
        self.assertEqual(self.withdraw(request_id, colleague).status_code, status.HTTP_200_OK)

        self.assertEqual(self.request_state(request_id), "withdrawn")

    def test_can_manage_is_true_only_for_the_requesting_party(self):
        record, _, _ = self.one_item_uploaded()

        self.assertIs(self.listed(record, self.ierc)[0]["can_manage"], True)
        self.assertIs(self.listed(record, self.owner)[0]["can_manage"], False)
        self.assertIs(self.listed(record, self.ktto)[0]["can_manage"], False)
        [request] = self.tracker_ok(record, self.ierc)["document_requests"]
        self.assertIs(request["can_manage"], True)


class RefusalTests(DecisionTestBase):
    """
    ADR-022 §Amendment 4, settled 2026-09-24. 404 only when the Record (or the
    id) cannot be seen at all; a visible Record whose request data the caller
    may not read is a 403, never hidden behind a 404.
    """

    def assert_refused(self, actor, request_id, item_id, code):
        withdrawn = self.withdraw(request_id, actor)
        self.assertEqual(withdrawn.status_code, code)
        return (withdrawn,)

    def test_a_user_who_cannot_see_the_record_gets_404(self):
        _, request_id, item_id = self.one_item_uploaded()

        self.assert_refused(self.stranger, request_id, item_id, status.HTTP_404_NOT_FOUND)

    def test_an_id_that_does_not_exist_gets_404(self):
        self.assert_refused(self.ierc, 999999, 999999, status.HTTP_404_NOT_FOUND)

    def test_a_reader_of_a_published_record_gets_403_and_learns_nothing(self):
        record, request_id, item_id = self.one_item_uploaded()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        for response in self.assert_refused(
            self.stranger, request_id, item_id, status.HTTP_403_FORBIDDEN
        ):
            self.assertNotIn("Consent form", json.dumps(response.data))
        self.assertEqual(self.item_state(item_id), "uploaded")
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_an_office_that_took_no_part_gets_403(self):
        # KTTO was never requested, so it may see the Record but not its requests.
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True, requested_ierc=True,
        )
        self.route_requested(record)
        self.review(record, self.itso, "approved", "No patent concerns.")
        _, request_id, item_id = self.one_item_uploaded(record)

        self.assert_refused(self.ktto, request_id, item_id, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.item_state(item_id), "uploaded")

    def test_read_access_does_not_grant_decision_authority(self):
        # Public readers cannot see requests; the Adviser participated and
        # may read them, but only the requesting office may decide or withdraw.
        record, request_id, item_id = self.one_item_uploaded()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        for viewer in (self.stranger, self.other_adviser):
            with self.subTest(viewer=viewer.email):
                self.client.force_authenticate(viewer)
                listed = self.client.get(self.requests_url(record)).status_code
                self.assertEqual(listed, status.HTTP_403_FORBIDDEN)
                self.assert_refused(viewer, request_id, item_id, listed)

        self.client.force_authenticate(self.adviser)
        self.assertEqual(self.client.get(self.requests_url(record)).status_code, 200)
        self.assert_refused(self.adviser, request_id, item_id, status.HTTP_403_FORBIDDEN)


class DecisionDataIsInternalTests(DecisionTestBase):
    """IR-349's predicate covers what this ticket adds (ADR-022 §Amendment 5)."""

    def test_a_public_reader_never_sees_a_reject_reason_or_a_withdrawal(self):
        record = self.at_parallel_review()
        rejected = self.requested(record, self.ierc, [{"label": "Consent form"}])
        self.uploaded(record, rejected["items"][0]["id"])
        self.rejected_before(rejected["items"][0]["id"])
        withdrawn = self.requested(record, self.ierc, [{"label": "Protocol"}])
        self.withdraw(withdrawn["id"], self.ierc)
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        self.client.force_authenticate(self.stranger)
        listed = self.client.get(self.requests_url(record))
        self.assertEqual(listed.status_code, status.HTTP_403_FORBIDDEN)
        tracker = json.dumps(self.tracker_ok(record, self.stranger))
        for secret in (REASON, "rejection_reason", "Protocol"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, json.dumps(listed.data))
                self.assertNotIn(secret, tracker)


class RejectedThenSlotUploadTests(DecisionTestBase):
    """IR-346 on IR-263: a rejected item is missing again, so a slot upload answers it."""

    def test_an_owner_slot_upload_answers_a_rejected_item_again(self):
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}])
        [item] = data["items"]
        self.uploaded(record, item["id"])
        self.rejected_before(item["id"])
        self.assertEqual(self.request_state(data["id"]), "open")

        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                SUBMIT_DOCUMENT, {"record": record.pk, "slot": ethics.pk, "file": pdf()},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # Held until the owner sends it (ADR-022 Amendment 8, IR-1322).
        self.assertEqual(self.item_state(item["id"]), "missing")
        self.send_what_is_held(record, self.owner, response)
        self.assertEqual(self.item_state(item["id"]), "uploaded")
        self.assertEqual(self.request_state(data["id"]), "fulfilled")
        self.assertEqual(
            DocumentRequestItem.objects.get(pk=item["id"]).upload_id,
            response.data["upload"]["id"],
        )


class OnlyTheOwnerFulfilsTests(DecisionTestBase):
    """ADR-022 §Amendment 2: an upload against an item is the owner's to make."""

    def test_the_requesting_office_cannot_answer_its_own_request(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])
        [item] = data["items"]
        notices_before = Notification.objects.count()

        response = self.upload_against(record, item["id"], uploader=self.ierc)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.item_state(item["id"]), "missing")
        self.assertEqual(self.request_state(data["id"]), "open")
        self.assertFalse(RecordUpload.objects.filter(record=record).exists())
        self.assertEqual(Notification.objects.count(), notices_before)

    def test_no_other_staff_member_can_answer_it_either(self):
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]

        for uploader in (self.ktto, self.rdco, self.itso):
            with self.subTest(uploader=uploader.email):
                response = self.upload_against(record, item["id"], uploader=uploader)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.item_state(item["id"]), "missing")

    def test_staff_may_still_upload_an_ordinary_file(self):
        record = self.at_parallel_review()
        [item] = self.requested(
            record, self.ierc, [{"slot": self.slot(record, "Ethics Clearance").pk}]
        )["items"]

        self.client.force_authenticate(self.ierc)
        response = self.client.post(
            SUBMIT_DOCUMENT,
            {"record": record.pk, "slot": item["slot"], "file": pdf()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # A slot upload does not answer the request (that is IR-346, owner-only).
        self.assertEqual(self.item_state(item["id"]), "missing")
