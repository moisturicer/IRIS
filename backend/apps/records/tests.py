"""
Tests for apps.records.

No pytest is configured for this repo (backend/requirements/development.txt
says so explicitly) -- these use Django's own django.test.TestCase /
rest_framework.test.APITestCase, which need no extra setup. Run with:

    docker compose exec -T backend python manage.py test apps.records
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from .models import Record, RecordOwner, RecordType


def make_user(email, role_name=None, **extra):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, is_verified=True, **extra,
    )


class SubmitOwnershipTests(APITestCase):
    """
    RecordViewSet.submit() must be owner-or-staff only.

    Found while wiring the Submit Disclosure wizard: get_permissions() listed
    "submit" nowhere, so it fell through to the bare IsAuthenticated() default --
    despite the action's own docstring/comment claiming IsOwnerOrStaff applied.
    Any authenticated user could POST /records/<id>/submit/ on someone else's
    draft and push it into the review pipeline.
    """

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner   = make_user("owner@cit.edu", "Student")
        self.other   = make_user("other@cit.edu", "Student")
        self.rdco    = make_user("rdco@cit.edu", "RDCO")

        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status="draft",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _submit(self):
        return self.client.post(reverse("record-submit", args=[self.record.id]))

    def test_owner_can_submit_own_draft(self):
        self.client.force_authenticate(self.owner)
        response = self._submit()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, "rdco_intake")

    def test_staff_can_submit_someone_elses_draft(self):
        self.client.force_authenticate(self.rdco)
        response = self._submit()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_non_owner_non_staff_cannot_submit_someone_elses_draft(self):
        self.client.force_authenticate(self.other)
        response = self._submit()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, "draft")

    def test_anonymous_cannot_submit(self):
        response = self._submit()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TagsPermissionTests(APITestCase):
    """
    RecordViewSet.tags() docstring says "Staff ... may update IP classification
    flags ... on any record" -- but "tags" was, like "submit", absent from
    get_permissions(), so it fell through to the bare IsAuthenticated() default.
    Any authenticated user -- including one who does not own the record --
    could set is_ip / ip_type / for_commercialization / community_extension on
    someone else's record. Same root cause as SubmitOwnershipTests: this class's
    get_permissions() is a full override with no super() fallback, so the
    permission_classes kwarg on the @action decorator itself was dead code.
    """

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner  = make_user("owner2@cit.edu", "Student")
        self.other  = make_user("other2@cit.edu", "Student")
        self.ktto   = make_user("ktto2@cit.edu", "KTTO")

        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status="published",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _patch_tags(self, **data):
        return self.client.patch(reverse("record-tags", args=[self.record.id]), data, format="json")

    def test_staff_can_set_tags(self):
        self.client.force_authenticate(self.ktto)
        response = self._patch_tags(is_ip=True, ip_type="patent")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertTrue(self.record.is_ip)
        self.assertEqual(self.record.ip_type, "patent")

    def test_owner_cannot_set_tags(self):
        """Owning the record is not enough -- only staff may classify IP."""
        self.client.force_authenticate(self.owner)
        response = self._patch_tags(is_ip=True)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_non_staff_non_owner_cannot_set_tags(self):
        self.client.force_authenticate(self.other)
        response = self._patch_tags(is_ip=True)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.record.refresh_from_db()
        self.assertFalse(self.record.is_ip)

    def test_anonymous_cannot_set_tags(self):
        response = self._patch_tags(is_ip=True)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
