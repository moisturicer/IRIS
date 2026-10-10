"""
IR-496: a delete request comes into existence only by deleting a record.

`DELETE /records/<id>/` on accepted work files a `DeleteRequest`, records the
status to restore, and moves the record to `pending_delete`, so RDCO reviews it
before anything is removed. The queue itself is read and decided only; its
direct POST and PATCH are gone (`test_request_visibility.py` asserts the 405s).

**What the retired POST did, pinned in CI before it went** (commit 4c64592,
run 38031335537, all three passing). A request filed through it:

* put nothing on hold -- the record stayed `published` and no previous status
  was recorded;
* on approve, soft-deleted a record nobody had put on hold;
* on decline, answered **400** ("'restore' is not a legal transition from
  'published'") **after** the request row had already been saved as
  `declined`, because the view writes the row before asking the lifecycle and
  does not run in a transaction. The record stayed put, the request said
  declined, and no notification went out.

Those tests went with the route. This file now holds the path that remains,
which `test_workflow_characterisation.py` also covers today -- IR-260 deletes
that file, so the journey is restated here rather than left to it.

**Seam: the API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import DeleteRequest, Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

RECORDS = "/api/v1/records/"
DELETE_REQUESTS = "/api/v1/records/delete-requests/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class DeleteRequestJourneyTests(APITestCase):
    """Raised by deleting the record, then decided by RDCO."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("delq-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("delq-rdco@cit.edu", RoleName.RDCO)

    def published_thesis(self, label):
        record = Record.objects.create(
            title=f"IR-496 {label}",
            abstract=f"Abstract of the {label}.",
            record_type=RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH),
            added_by=self.owner,
            pipeline_status=PipelineStatus.PUBLISHED,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def raise_by_deleting(self, record):
        self.client.force_authenticate(self.owner)
        response = self.client.delete(f"{RECORDS}{record.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        return DeleteRequest.objects.get(record=record)

    def decide(self, request, verdict):
        self.client.force_authenticate(self.rdco)
        response = self.client.post(f"{DELETE_REQUESTS}{request.pk}/{verdict}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request.refresh_from_db()
        return request

    def test_deleting_accepted_work_puts_it_on_hold_and_records_where_it_was(self):
        record = self.published_thesis("held")

        request = self.raise_by_deleting(record)

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PENDING_DELETE)
        self.assertFalse(record.is_deleted)
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.requested_by, self.owner)
        self.assertEqual(request.previous_pipeline_status, PipelineStatus.PUBLISHED)

    def test_approving_it_soft_deletes_the_record(self):
        record = self.published_thesis("approved")
        request = self.raise_by_deleting(record)

        request = self.decide(request, "approve")

        self.assertEqual(request.status, RequestStatus.APPROVED)
        self.assertEqual(request.reviewed_by, self.rdco)
        self.assertTrue(Record.objects.with_deleted().get(pk=record.pk).is_deleted)

    def test_declining_it_restores_the_previous_status(self):
        record = self.published_thesis("declined")
        request = self.raise_by_deleting(record)

        request = self.decide(request, "decline")

        self.assertEqual(request.status, RequestStatus.DECLINED)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        self.assertFalse(record.is_deleted)
