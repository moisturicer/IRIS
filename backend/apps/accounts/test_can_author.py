"""
`can_author` on the signed-in user's own payload (IR-1096).

The client shows Publish, and My Library's research tabs, only when the server
says the user can author. The flag is `core.permissions.can_author`, the same
predicate `IsAuthor` enforces on `POST /records/`, so what the page offers and
what the API accepts cannot drift apart.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from apps.accounts.serializers import AdviserOptionSerializer, UserSerializer
from apps.accounts.tests import make_user
from core.permissions import IsAuthor, can_author

AUTHORS = ["Student", "Adviser"]
NON_AUTHORS = ["RDCO", "ITSO", "IERC", "KTTO", "System Admin"]


class CanAuthorPayloadTests(APITestCase):
    def me(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("user-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_a_student_and_an_adviser_can_author(self):
        for role in AUTHORS:
            with self.subTest(role=role):
                user = make_user(f"{role.lower()}@cit.edu", role)
                self.assertIs(self.me(user)["can_author"], True)

    def test_no_office_rdco_or_system_admin_can_author(self):
        for role in NON_AUTHORS:
            with self.subTest(role=role):
                user = make_user(f"{role.lower().replace(' ', '')}@cit.edu", role)
                self.assertIs(self.me(user)["can_author"], False)

    def test_an_account_with_no_role_yet_cannot_author(self):
        self.assertIs(self.me(make_user("new@cit.edu"))["can_author"], False)

    def test_an_office_coordinator_still_cannot_author(self):
        user = make_user("coord@cit.edu", "ITSO", is_office_coordinator=True)
        self.assertIs(self.me(user)["can_author"], False)

    def test_sign_in_carries_it(self):
        make_user("sign@cit.edu", "Student")
        response = self.client.post(
            reverse("auth-login"), {"email": "sign@cit.edu", "password": "pw12345!"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(response.data["user"]["can_author"], True)

    def test_other_users_payloads_never_carry_it(self):
        student = make_user("someone@cit.edu", "Student")
        self.assertNotIn("can_author", UserSerializer(student).data)
        adviser = make_user("adv@cit.edu", "Adviser")
        self.assertNotIn("can_author", AdviserOptionSerializer(adviser).data)

    def test_it_is_read_only(self):
        user = make_user("ro@cit.edu", "ITSO")
        self.client.force_authenticate(user)
        response = self.client.patch(reverse("user-me"), {"can_author": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIs(response.data["can_author"], False)


class CanAuthorMatchesTheGateTests(APITestCase):
    """The flag and `IsAuthor` are one rule: no role is offered what the API refuses."""

    def test_the_flag_and_the_permission_agree_for_every_role(self):
        request = APIRequestFactory().post("/records/")
        for role in [*AUTHORS, *NON_AUTHORS, None]:
            with self.subTest(role=role):
                user = make_user(f"gate-{(role or 'none').lower().replace(' ', '')}@cit.edu", role)
                request.user = user
                self.assertEqual(can_author(user), IsAuthor().has_permission(request, None))
