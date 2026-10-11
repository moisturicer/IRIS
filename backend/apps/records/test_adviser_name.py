"""
IR-472: the Record detail names its adviser, for Paper View's byline.

`GET /records/<id>/` carried `adviser` as an id only, so the byline showed no
adviser rather than invent one. `adviser_name` is the adviser's full name,
falling back to their email the way `requested_by_name` does, and null when
the record names no adviser.

**No new disclosure path.** The name rides on the record's own visibility:
a viewer who may not read the record gets the same 404 as for an id no record
has (IR-153), and that 404 carries no name.

**Seam: the API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName


def _user(email, role_name, first_name="Test", last_name="User"):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name=first_name,
        last_name=last_name, role=role, is_verified=True,
    )


def _detail(record_id):
    return f"/api/v1/records/{record_id}/"


class AdviserNameTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("name-owner@cit.edu", RoleName.STUDENT)
        cls.stranger = _user("name-stranger@cit.edu", RoleName.STUDENT)
        cls.adviser = _user(
            "name-adviser@cit.edu", RoleName.ADVISER, first_name="Maria", last_name="Santos"
        )
        cls.nameless_adviser = _user(
            "nameless-adviser@cit.edu", RoleName.ADVISER, first_name="", last_name=""
        )

        cls.advised = cls.make_record(
            RecordTypeName.THESIS_RESEARCH, PipelineStatus.PUBLISHED, "advised", cls.adviser
        )
        cls.unadvised = cls.make_record(
            RecordTypeName.THESIS_RESEARCH, PipelineStatus.PUBLISHED, "unadvised", None
        )
        cls.nameless = cls.make_record(
            RecordTypeName.THESIS_RESEARCH, PipelineStatus.PUBLISHED, "nameless", cls.nameless_adviser
        )
        # Private since IR-264: readable by its owner and adviser, nobody else.
        cls.private_proposal = cls.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.APPROVED, "private proposal", cls.adviser
        )
        cls.missing_id = Record.objects.with_deleted().order_by("-pk").first().pk + 1000

    @classmethod
    def make_record(cls, type_name, pipeline_status, label, adviser):
        record = Record.objects.create(
            title=f"IR-472 {label}",
            abstract=f"Abstract of the {label}.",
            record_type=RecordType.objects.get(name=type_name),
            added_by=cls.owner,
            adviser=adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=cls.owner, is_primary=True)
        return record

    def get_as(self, user, record_id):
        self.client.force_authenticate(user)
        return self.client.get(_detail(record_id))

    def test_a_record_with_an_adviser_names_them(self):
        response = self.get_as(self.stranger, self.advised.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["adviser_name"], "Maria Santos")
        self.assertEqual(response.data["adviser"], self.adviser.pk)

    def test_a_record_without_an_adviser_names_none(self):
        response = self.get_as(self.stranger, self.unadvised.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data["adviser_name"])

    def test_an_adviser_with_no_name_on_file_is_named_by_email(self):
        response = self.get_as(self.stranger, self.nameless.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["adviser_name"], "nameless-adviser@cit.edu")

    def test_the_owner_of_a_private_record_sees_its_adviser(self):
        response = self.get_as(self.owner, self.private_proposal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["adviser_name"], "Maria Santos")

    def test_a_viewer_who_cannot_read_the_record_gets_the_missing_record_404(self):
        unreadable = self.get_as(self.stranger, self.private_proposal.pk)
        missing = self.get_as(self.stranger, self.missing_id)

        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unreadable.status_code, missing.status_code)
        self.assertEqual(unreadable.data, missing.data)
        self.assertNotIn("Maria Santos", unreadable.content.decode())

    def test_the_list_payload_does_not_carry_the_name(self):
        self.client.force_authenticate(self.stranger)
        response = self.client.get("/api/v1/records/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        results = response.data.get("results", response.data)
        self.assertTrue(results)
        self.assertTrue(all("adviser_name" not in row for row in results))
