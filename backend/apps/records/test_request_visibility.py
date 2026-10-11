"""
IR-316: download requests honour the visibility predicate; delete requests take no record id.

`POST /records/download-requests/` and `POST /records/delete-requests/` took a
`record` id resolved against **every** Record. A record the caller cannot read
-- an approved Proposal is private since IR-264 -- was therefore answered
differently from an id that does not exist, which confirms the private record
exists. A successful request also put its title in RDCO's queue.

**The refusal is the missing-record refusal, byte for byte.** The `record`
field resolves through `Record.objects.visible_to(user)`, so an unreadable id
fails the same field validation, with the same code and the same message, as an
id no record has. A 403 here would be the oracle this ticket closes.

**Delete requests no longer take a record id at all (IR-496).** IR-316 gated
`POST /records/delete-requests/` and its PATCH; IR-496 retired both, because a
request filed that way skipped the `request_delete` transition. The tests that
asserted IR-316's gate are replaced, **deliberately**, by
`DeleteRequestWriteRouteTests` below: every role gets a 405 and nothing is
written. A delete request is raised by `DELETE /records/<id>/`; see
`test_delete_request_queue.py`.

**Seam: the API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.notifications.models import Notification
from apps.records.models import (
    DeleteRequest,
    DownloadRequest,
    Record,
    RecordOwner,
    RecordType,
)
from core.enums import PipelineStatus, RecordTypeName, RoleName, RequestStatus

DOWNLOAD_REQUESTS = "/api/v1/records/download-requests/"
DELETE_REQUESTS = "/api/v1/records/delete-requests/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class RequestVisibilityFixtures(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("req-owner@cit.edu", RoleName.STUDENT)
        cls.stranger = _user("req-stranger@cit.edu", RoleName.STUDENT)
        cls.adviser = _user("req-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = _user("req-rdco@cit.edu", RoleName.RDCO)

        cls.approved_proposal = cls.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.APPROVED, "approved proposal"
        )
        cls.published_thesis = cls.make_record(
            RecordTypeName.THESIS_RESEARCH, PipelineStatus.PUBLISHED, "published thesis"
        )
        # An id no record has, soft-deleted ones included. Its digit count
        # need not match the real id's: the message is compared with the id
        # substituted out.
        cls.missing_id = Record.objects.with_deleted().order_by("-pk").first().pk + 1000

    @classmethod
    def make_record(cls, type_name, pipeline_status, label):
        record = Record.objects.create(
            title=f"IR-316 {label}",
            abstract=f"Abstract of the {label}.",
            record_type=RecordType.objects.get(name=type_name),
            added_by=cls.owner,
            adviser=cls.adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=cls.owner, is_primary=True)
        return record

    def post_as(self, user, url, payload):
        self.client.force_authenticate(user)
        return self.client.post(url, payload, format="json")

    def assert_refused_as_missing(self, url, user, record, extra=None):
        """`record` is refused exactly as an id no record has is refused."""
        payload = {**(extra or {})}

        unreadable = self.post_as(user, url, {**payload, "record": record.pk})
        missing = self.post_as(user, url, {**payload, "record": self.missing_id})

        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST, missing.data)
        self.assertEqual(unreadable.status_code, missing.status_code, unreadable.data)
        self.assertEqual(set(unreadable.data), {"record"}, unreadable.data)
        self.assertEqual(set(missing.data), {"record"}, missing.data)
        self.assertEqual(
            [e.code for e in unreadable.data["record"]],
            [e.code for e in missing.data["record"]],
        )
        # The message names the id the caller sent and nothing else, so with
        # the id swapped the two bodies are identical.
        self.assertEqual(
            [str(e).replace(str(record.pk), "<id>") for e in unreadable.data["record"]],
            [str(e).replace(str(self.missing_id), "<id>") for e in missing.data["record"]],
        )


class DownloadRequestVisibilityTests(RequestVisibilityFixtures):

    def test_a_stranger_is_refused_a_private_proposal_as_if_it_did_not_exist(self):
        self.assert_refused_as_missing(DOWNLOAD_REQUESTS, self.stranger, self.approved_proposal)

    def test_a_refused_request_creates_nothing_and_notifies_nobody(self):
        notifications = Notification.objects.count()

        self.post_as(self.stranger, DOWNLOAD_REQUESTS, {"record": self.approved_proposal.pk})

        self.assertFalse(DownloadRequest.objects.exists())
        self.assertEqual(Notification.objects.count(), notifications)

    def test_anyone_may_request_a_published_record(self):
        response = self.post_as(
            self.stranger, DOWNLOAD_REQUESTS, {"record": self.published_thesis.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            DownloadRequest.objects.filter(
                record=self.published_thesis, requested_by=self.stranger
            ).exists()
        )

    def test_an_owner_may_request_their_own_private_proposal(self):
        response = self.post_as(
            self.owner, DOWNLOAD_REQUESTS, {"record": self.approved_proposal.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_a_request_is_created_pending_whatever_status_is_sent(self):
        response = self.post_as(
            self.stranger,
            DOWNLOAD_REQUESTS,
            {"record": self.published_thesis.pk, "status": RequestStatus.APPROVED},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            DownloadRequest.objects.get(requested_by=self.stranger).status,
            RequestStatus.PENDING,
        )


class DeleteRequestWriteRouteTests(RequestVisibilityFixtures):
    """
    The delete-request queue has no write routes (IR-496). Replaces IR-316's
    create and PATCH tests on purpose: the routes they gated are gone.
    """

    def every_role(self):
        return {
            "owner": self.owner,
            "stranger": self.stranger,
            "adviser": self.adviser,
            "itso": _user("req-itso@cit.edu", RoleName.ITSO),
            "rdco": self.rdco,
        }

    def test_post_is_not_allowed_for_any_role(self):
        for name, user in self.every_role().items():
            with self.subTest(role=name):
                response = self.post_as(
                    user, DELETE_REQUESTS, {"record": self.published_thesis.pk, "reason": "x"}
                )

                self.assertEqual(
                    response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, response.data
                )
        self.assertFalse(DeleteRequest.objects.exists())

    def test_patch_is_not_allowed_for_any_role_and_changes_nothing(self):
        pending = DeleteRequest.objects.create(
            record=self.approved_proposal, requested_by=self.owner, reason="mine"
        )

        for name, user in self.every_role().items():
            with self.subTest(role=name):
                self.client.force_authenticate(user)
                response = self.client.patch(
                    f"{DELETE_REQUESTS}{pending.pk}/",
                    {"record": self.published_thesis.pk, "status": RequestStatus.APPROVED},
                    format="json",
                )

                self.assertEqual(
                    response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, response.data
                )

        pending.refresh_from_db()
        self.assertEqual(pending.record, self.approved_proposal)
        self.assertEqual(pending.status, RequestStatus.PENDING)
