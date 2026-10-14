"""
Tests for apps.accounts.

No pytest is configured for this repo -- these use rest_framework's APITestCase.
Run with:

    docker compose exec -T backend python manage.py test apps.accounts.tests
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import (
    AdviserProfile, Course, Role, RoleRequest, StudentProfile, User,
)
from core.enums import RequestStatus


def make_user(email, role_name=None, **extra):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    # setdefault, not a literal: create_user passes **extra straight through to
    # the model, so a caller overriding is_verified would collide with it.
    extra.setdefault("is_verified", True)
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, **extra,
    )


class SelfProfileUpdateTests(APITestCase):
    """
    MeView is a RetrieveUpdateAPIView open to any authenticated user, so what it
    lets a user write to themselves is a security boundary, not a form detail.
    """

    def setUp(self):
        self.user = make_user("student@cit.edu", "Student")
        self.url  = reverse("user-me")
        self.client.force_authenticate(self.user)

    def test_user_cannot_change_their_own_email(self):
        """
        Regression: `email` was writable here.

        It is USERNAME_FIELD -- the login identifier -- and the system leans on
        institutional identity for authorship, clearance attribution and
        citations. Before the fix this PATCH returned 200 and the address became
        attacker@gmail.com while `is_verified` stayed True, moving the account
        off CIT-U identity entirely.
        """
        response = self.client.patch(
            self.url, {"email": "attacker@gmail.com"}, format="json",
        )
        # DRF silently ignores read-only fields rather than erroring, so the
        # assertion that matters is the stored value, not the status code.
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "student@cit.edu")
        self.assertEqual(response.data["email"], "student@cit.edu")

    def test_verification_and_role_cannot_be_self_granted(self):
        other_role = Role.objects.get_or_create(name="RDCO")[0]
        unverified = make_user("new@cit.edu", "Student", is_verified=False)
        self.client.force_authenticate(unverified)

        self.client.patch(
            self.url,
            {"is_verified": True, "is_staff": True, "role": other_role.pk, "consent_given": True},
            format="json",
        )
        unverified.refresh_from_db()
        self.assertFalse(unverified.is_verified)
        self.assertFalse(unverified.is_staff)
        self.assertFalse(unverified.consent_given)
        self.assertEqual(unverified.role.name, "Student")

    def test_user_can_change_their_own_name(self):
        """The fields the profile screen is actually for must still be writable."""
        response = self.client.patch(
            self.url,
            {"first_name": "Juan", "middle_initial": "P", "last_name": "Dela Cruz"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), "Juan P Dela Cruz")

    def test_anonymous_cannot_read_or_write_me(self):
        self.client.force_authenticate(None)
        self.assertIn(
            self.client.get(self.url).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class AffiliationDisplayTests(APITestCase):
    """
    Affiliation is read-only and reaches a student and an adviser by different
    routes, which is exactly why the profile screen cannot offer one editable
    "College / Department" dropdown for both.
    """

    def setUp(self):
        # Reuse the rows seeded by accounts/0003 rather than creating new ones.
        # That migration inserts College/Department/Course with **explicit ids**,
        # which leaves the Postgres identity sequence at 1 while rows already
        # occupy 1..N -- so a plain College.objects.create() here raises
        # IntegrityError "duplicate key value violates accounts_college_pkey".
        # Reusing the seed data is both realistic and immune to that.
        self.course     = Course.objects.select_related("department__college").first()
        self.assertIsNotNone(self.course, "accounts/0003 should have seeded courses")
        self.department = self.course.department
        self.college    = self.department.college
        self.url        = reverse("user-me")

    def test_student_college_is_derived_through_course(self):
        student = make_user("s@cit.edu", "Student")
        StudentProfile.objects.create(user=student, course=self.course)
        self.client.force_authenticate(student)

        data = self.client.get(self.url).data
        self.assertEqual(data["college_name"],    self.college.name)
        self.assertEqual(data["department_name"], self.department.name)
        self.assertEqual(data["course_name"],     self.course.name)

    def test_adviser_college_comes_from_the_adviser_profile(self):
        adviser = make_user("a@cit.edu", "Adviser")
        AdviserProfile.objects.create(user=adviser, college=self.college, department=self.department)
        self.client.force_authenticate(adviser)

        data = self.client.get(self.url).data
        self.assertEqual(data["college_name"],    self.college.name)
        self.assertEqual(data["department_name"], self.department.name)
        self.assertEqual(data["course_name"],     "")

    def test_user_with_no_profile_gets_blanks_not_an_error(self):
        self.client.force_authenticate(make_user("bare@cit.edu", "RDCO"))
        data = self.client.get(self.url).data
        self.assertEqual(data["college_name"], "")
        self.assertEqual(data["department_name"], "")

    def test_affiliation_cannot_be_written(self):
        student = make_user("s2@cit.edu", "Student")
        StudentProfile.objects.create(user=student, course=self.course)
        self.client.force_authenticate(student)

        self.client.patch(self.url, {"college_name": "Somewhere Else"}, format="json")
        self.assertEqual(self.client.get(self.url).data["college_name"], self.college.name)


class OwnRoleRequestTests(APITestCase):
    """
    `role_request` on `/users/me/` (IR-537) is what lets the pending screen tell
    an applicant still waiting from one RDCO has declined. Before it, both saw
    "Account Pending Approval" indefinitely.
    """

    def setUp(self):
        self.url     = reverse("user-me")
        self.student = Role.objects.get_or_create(name="Student")[0]

    def _file_request(self, user, status_=RequestStatus.PENDING, role=None):
        return RoleRequest.objects.create(
            user=user, requested_role=role or self.student, status=status_,
        )

    def _role_request(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["role_request"]

    def test_pending_request_reports_pending_and_the_role(self):
        applicant = make_user("applicant@cit.edu")
        self._file_request(applicant)

        self.assertEqual(
            self._role_request(applicant),
            {"status": "pending", "requested_role": "Student"},
        )

    def test_declined_request_reports_declined(self):
        applicant = make_user("declined@cit.edu")
        self._file_request(applicant, RequestStatus.DECLINED)

        self.assertEqual(
            self._role_request(applicant),
            {"status": "declined", "requested_role": "Student"},
        )

    def test_the_latest_request_is_the_one_reported(self):
        applicant = make_user("twice@cit.edu")
        adviser   = Role.objects.get_or_create(name="Adviser")[0]
        self._file_request(applicant, RequestStatus.DECLINED)
        self._file_request(applicant, RequestStatus.PENDING, role=adviser)

        self.assertEqual(
            self._role_request(applicant),
            {"status": "pending", "requested_role": "Adviser"},
        )

    def test_user_with_an_approved_role_gets_null(self):
        member = make_user("member@cit.edu", "Student")
        self._file_request(member, RequestStatus.APPROVED)

        self.assertIsNone(self._role_request(member))

    def test_user_with_a_role_gets_null_even_beside_an_older_pending_request(self):
        member = make_user("assigned@cit.edu", "Student")
        self._file_request(member, RequestStatus.PENDING)

        self.assertIsNone(self._role_request(member))

    def test_user_with_no_request_gets_null(self):
        self.assertIsNone(self._role_request(make_user("norequest@cit.edu")))

    def test_sign_in_carries_it_too(self):
        applicant = make_user("signin@cit.edu")
        self._file_request(applicant)

        response = self.client.post(
            reverse("auth-login"),
            {"email": "signin@cit.edu", "password": "pw12345!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["user"]["role_request"],
            {"status": "pending", "requested_role": "Student"},
        )

    def test_the_field_cannot_be_written(self):
        applicant = make_user("writer@cit.edu")
        request   = self._file_request(applicant, RequestStatus.DECLINED)
        self.client.force_authenticate(applicant)

        response = self.client.patch(
            self.url,
            {"role_request": {"status": "pending", "requested_role": "RDCO"}},
            format="json",
        )
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.DECLINED)
        self.assertEqual(request.requested_role, self.student)
        self.assertEqual(
            response.data["role_request"],
            {"status": "declined", "requested_role": "Student"},
        )
