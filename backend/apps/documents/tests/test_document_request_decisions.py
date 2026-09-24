"""
The requesting party accepts, rejects or withdraws (IR-263, ADR-022 §3.4, §4).

ADR-022 §3.4: the party that asked for documents decides whether each upload
satisfies it. A rejected item goes back to `missing` with a reason, the
request reopens and the owner is told. Accepting marks the item `accepted`.
§4: the requesting party may withdraw an open request; it closes and stays in
the history.

§Amendment 2: the requesting party cannot fulfil its own request. Only the
Record's owners answer an item, so a staff upload against a `request_item` is
a 403 even though `authorize_record_documents` admits every office.

§Amendment 4 and 5: the decision routes follow the refusal convention. A
caller who cannot see the Record, or may not read its request data
(`may_read_requests`), gets a 404 -- the request is an object they cannot see.
A caller who can read it but is not the requesting party gets a 403.

**Seam: the HTTP API**, as for IR-262 and IR-349.
"""

import json

from rest_framework import status

from apps.documents.models import DocumentRequest, DocumentRequestItem, RecordUpload
from apps.notifications.models import Notification
from apps.records.models import Record
from core.enums import PipelineStatus, RecordTypeName

from .test_document_requests import DocumentRequestTestBase, SUBMIT_DOCUMENT, pdf

REASON = "The scan is unreadable; please rescan at 300 dpi."


class DecisionTestBase(DocumentRequestTestBase):

    def item_url(self, item_id):
        return f"/api/v1/document-request-items/{item_id}/"

    def request_url(self, request_id):
        return f"/api/v1/document-requests/{request_id}/"

    def decide(self, item_id, actor, action, reason=None):
        self.client.force_authenticate(actor)
        body = {"action": action}
        if reason is not None:
            body["reason"] = reason
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.patch(self.item_url(item_id), body, format="json")

    def decided(self, item_id, actor, action, reason=None):
        response = self.decide(item_id, actor, action, reason)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def withdraw(self, request_id, actor, reason=None):
        self.client.force_authenticate(actor)
        body = {"action": "withdraw"}
        if reason is not None:
            body["reason"] = reason
        return self.client.patch(self.request_url(request_id), body, format="json")

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


class RejectTests(DecisionTestBase):

    def test_a_rejected_item_goes_back_to_missing_and_the_request_reopens(self):
        record, request_id, item_id = self.one_item_uploaded()
        self.assertEqual(self.request_state(request_id), "fulfilled")

        data = self.decided(item_id, self.ierc, "reject", REASON)

        self.assertEqual(data["state"], "open")
        self.assertIsNone(data["closed_at"])
        [item] = data["items"]
        self.assertEqual(item["state"], "missing")
        self.assertEqual(item["rejection_reason"], REASON)
        self.assertIsNone(item["upload"])
        self.assertEqual(self.detail(record)["workflow_state"], "awaiting_document")

    def test_the_owner_sees_the_reason_in_the_list(self):
        record, _, item_id = self.one_item_uploaded()

        self.decided(item_id, self.ierc, "reject", REASON)

        [request] = self.listed(record, self.owner)
        self.assertEqual(request["state"], "open")
        self.assertEqual(request["items"][0]["rejection_reason"], REASON)

    def test_the_owner_is_notified_with_the_reason(self):
        record, _, item_id = self.one_item_uploaded()
        before = Notification.objects.filter(recipient=self.owner, record=record).count()

        self.decided(item_id, self.ierc, "reject", REASON)

        notices = Notification.objects.filter(recipient=self.owner, record=record)
        self.assertEqual(notices.count(), before + 1)
        notice = notices.latest("created_at")
        self.assertIn("Consent form", notice.message)
        self.assertIn(REASON, notice.message)
        self.assertEqual(notice.notif_type.name, "Document Rejected")

    def test_the_rejected_file_stays_on_the_record(self):
        # The item forgets the upload; the file version itself is not deleted.
        record, _, item_id = self.one_item_uploaded()

        self.decided(item_id, self.ierc, "reject", REASON)

        self.assertTrue(RecordUpload.objects.filter(record=record).exists())

    def test_the_owner_can_upload_again_and_the_request_is_fulfilled_again(self):
        record, request_id, item_id = self.one_item_uploaded()
        self.decided(item_id, self.ierc, "reject", REASON)

        self.uploaded(record, item_id)

        self.assertEqual(self.item_state(item_id), "uploaded")
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_a_rejection_needs_a_reason(self):
        _, _, item_id = self.one_item_uploaded()

        for reason in (None, "", "   "):
            with self.subTest(reason=reason):
                response = self.decide(item_id, self.ierc, "reject", reason)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.item_state(item_id), "uploaded")

    def test_rejecting_one_item_of_an_open_request_leaves_the_rest_alone(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        first, second = data["items"]
        self.uploaded(record, first["id"])

        data = self.decided(first["id"], self.ierc, "reject", REASON)

        self.assertEqual(data["state"], "open")
        self.assertEqual([i["state"] for i in data["items"]], ["missing", "missing"])
        self.assertIsNone(data["items"][1]["rejection_reason"])


class AcceptTests(DecisionTestBase):

    def test_accepting_every_item_closes_the_request_and_the_tracker_shows_accepted(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        for item in data["items"]:
            self.uploaded(record, item["id"])

        for item in data["items"]:
            self.decided(item["id"], self.ierc, "accept")

        [request] = self.tracker_ok(record, self.ierc)["document_requests"]
        self.assertEqual(request["state"], "fulfilled")
        self.assertIsNotNone(request["closed_at"])
        self.assertEqual([i["state"] for i in request["items"]], ["accepted", "accepted"])
        self.assertEqual(self.detail(record)["workflow_state"], "in_review")

    def test_accepting_one_item_of_an_open_request_leaves_it_open(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        first, _ = data["items"]
        self.uploaded(record, first["id"])

        data = self.decided(first["id"], self.ierc, "accept")

        self.assertEqual(data["state"], "open")
        self.assertEqual([i["state"] for i in data["items"]], ["accepted", "missing"])

    def test_only_an_uploaded_item_can_be_decided(self):
        record = self.at_parallel_review()
        [missing] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]
        _, _, accepted = self.one_item_uploaded()
        self.decided(accepted, self.ierc, "accept")

        for item_id, action in (
            (missing["id"], "accept"), (missing["id"], "reject"), (accepted, "reject"),
        ):
            with self.subTest(item=item_id, action=action):
                response = self.decide(item_id, self.ierc, action, REASON)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unknown_action_is_refused(self):
        _, _, item_id = self.one_item_uploaded()

        response = self.decide(item_id, self.ierc, "approve")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.item_state(item_id), "uploaded")


class WithdrawTests(DecisionTestBase):

    def test_withdrawing_closes_the_request_and_keeps_it_in_the_history(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])

        response = self.withdraw(data["id"], self.ierc, "Found it in the appendix.")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["state"], "withdrawn")
        self.assertIsNotNone(response.data["closed_at"])
        self.assertEqual(response.data["withdrawal_reason"], "Found it in the appendix.")
        [request] = self.tracker_ok(record)["document_requests"]
        self.assertEqual(request["state"], "withdrawn")
        self.assertEqual(self.detail(record)["workflow_state"], "in_review")

    def test_a_reason_is_optional(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])

        response = self.withdraw(data["id"], self.ierc)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data["withdrawal_reason"])

    def test_only_an_open_request_can_be_withdrawn(self):
        _, request_id, _ = self.one_item_uploaded()

        response = self.withdraw(request_id, self.ierc)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_a_withdrawn_request_takes_no_uploads_and_no_decisions(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}, {"label": "Protocol"}])
        first, second = data["items"]
        self.uploaded(record, first["id"])
        self.assertEqual(self.withdraw(data["id"], self.ierc).status_code, status.HTTP_200_OK)

        self.assertEqual(
            self.upload_against(record, second["id"]).status_code, status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(
            self.decide(first["id"], self.ierc, "accept").status_code,
            status.HTTP_400_BAD_REQUEST,
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

    def test_the_owner_and_other_parties_are_refused_on_every_action(self):
        record, request_id, item_id = self.one_item_uploaded()
        # All three may read the request (IR-349): the owner, ITSO (held and
        # cleared), KTTO (holds now). None of them asked.
        for actor in (self.owner, self.itso, self.ktto):
            with self.subTest(actor=actor.email):
                for action in ("accept", "reject"):
                    response = self.decide(item_id, actor, action, REASON)
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                response = self.withdraw(request_id, actor)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(self.item_state(item_id), "uploaded")
        self.assertEqual(self.request_state(request_id), "fulfilled")

    def test_the_party_is_what_counts_not_the_person(self):
        # Any IERC staffer may act for IERC, as on every other IERC action.
        from apps.records.test_tracker import make_user
        from core.enums import RoleName

        colleague = make_user("tracker-ierc-2@cit.edu", RoleName.IERC)
        _, _, item_id = self.one_item_uploaded()

        self.decided(item_id, colleague, "accept")

        self.assertEqual(self.item_state(item_id), "accepted")

    def test_can_manage_is_true_only_for_the_requesting_party(self):
        record, _, _ = self.one_item_uploaded()

        self.assertIs(self.listed(record, self.ierc)[0]["can_manage"], True)
        self.assertIs(self.listed(record, self.owner)[0]["can_manage"], False)
        self.assertIs(self.listed(record, self.ktto)[0]["can_manage"], False)
        [request] = self.tracker_ok(record, self.ierc)["document_requests"]
        self.assertIs(request["can_manage"], True)


class NotFoundTests(DecisionTestBase):
    """A request the caller cannot see is indistinguishable from a missing one."""

    def assert_not_found(self, actor, request_id, item_id):
        self.assertEqual(
            self.decide(item_id, actor, "accept").status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(
            self.withdraw(request_id, actor).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_a_user_who_cannot_see_the_record(self):
        _, request_id, item_id = self.one_item_uploaded()

        self.assert_not_found(self.stranger, request_id, item_id)

    def test_a_reader_of_a_published_record(self):
        record, request_id, item_id = self.one_item_uploaded()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        self.assert_not_found(self.stranger, request_id, item_id)

    def test_an_office_that_took_no_part(self):
        # KTTO was never requested, so it may see the Record but not its requests.
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True, requested_ierc=True,
        )
        self.review(record, self.rdco, "approved", "Needs ITSO and IERC.")
        self.review(record, self.itso, "approved", "No patent concerns.")
        _, request_id, item_id = self.one_item_uploaded(record)

        self.assert_not_found(self.ktto, request_id, item_id)
        self.assertEqual(self.item_state(item_id), "uploaded")

    def test_an_id_that_does_not_exist(self):
        self.assert_not_found(self.ierc, 999999, 999999)


class DecisionDataIsInternalTests(DecisionTestBase):
    """IR-349's predicate covers what this ticket adds (ADR-022 §Amendment 5)."""

    def test_a_public_reader_never_sees_a_reject_or_withdrawal_reason(self):
        record = self.at_parallel_review()
        rejected = self.requested(record, self.ierc, [{"label": "Consent form"}])
        self.uploaded(record, rejected["items"][0]["id"])
        self.decided(rejected["items"][0]["id"], self.ierc, "reject", REASON)
        withdrawn = self.requested(record, self.ierc, [{"label": "Protocol"}])
        self.withdraw(withdrawn["id"], self.ierc, "No longer needed, thanks.")
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        self.client.force_authenticate(self.stranger)
        listed = self.client.get(self.requests_url(record))
        self.assertEqual(listed.status_code, status.HTTP_403_FORBIDDEN)
        tracker = json.dumps(self.tracker_ok(record, self.stranger))
        for secret in (REASON, "No longer needed, thanks.", "rejection_reason", "withdrawal_reason"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, json.dumps(listed.data))
                self.assertNotIn(secret, tracker)


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
