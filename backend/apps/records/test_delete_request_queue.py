"""
IR-496: a delete request comes into existence only by deleting a record.

**Characterisation, pinned before the route goes.** `POST /records/delete-requests/`
files a `DeleteRequest` without the `request_delete` transition, so the record
stays where it is and no previous status is recorded. This class pins what
deciding such a request does today, so the PR that retires the route can say
what the route was doing rather than guess.

**Seam: the API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import DeleteRequest, Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

DELETE_REQUESTS = "/api/v1/records/delete-requests/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class DeleteRequestFixtures(APITestCase):

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

    def as_user(self, user):
        self.client.force_authenticate(user)


class OldPostRouteCharacterisation(DeleteRequestFixtures):
    """What a request filed through the old POST did once RDCO decided it."""

    def file_through_old_post(self, record):
        self.as_user(self.owner)
        response = self.client.post(
            DELETE_REQUESTS, {"record": record.pk, "reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return DeleteRequest.objects.get(record=record)

    def test_the_old_post_puts_nothing_on_hold(self):
        record = self.published_thesis("not held")

        request = self.file_through_old_post(record)

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        self.assertEqual(request.previous_pipeline_status, "")

    def test_declining_it_refuses_but_leaves_the_request_declined(self):
        record = self.published_thesis("stranded decline")
        request = self.file_through_old_post(record)

        self.as_user(self.rdco)
        response = self.client.post(f"{DELETE_REQUESTS}{request.pk}/decline/")

        # Refused by the lifecycle: there is no restore edge out of published.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("restore", str(response.data))
        # ...after the request row was already written as declined.
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.DECLINED)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)

    def test_approving_it_deletes_a_record_that_was_never_held(self):
        record = self.published_thesis("deleted unheld")
        request = self.file_through_old_post(record)

        self.as_user(self.rdco)
        response = self.client.post(f"{DELETE_REQUESTS}{request.pk}/approve/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(Record.objects.with_deleted().get(pk=record.pk).is_deleted)
