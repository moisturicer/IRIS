""""Don't show tours again" (IR-1349, AC 5).

`PUT /users/me/tours-off/` is the one write: a JSON boolean, for the signed-in
account, touching `tours_off` alone. It is read on the person's own
`/users/me/` and in their data export, never on the administrators' list.
"""
import json

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.accounts.tests import make_user
from core.enums import RoleName

ME = "/api/v1/users/me/"
OFF = "/api/v1/users/me/tours-off/"


class ToursOffTests(APITestCase):
    def setUp(self):
        self.student = make_user("off.student@cit.edu", RoleName.STUDENT)

    def test_a_new_account_has_it_unset(self):
        self.assertFalse(self.student.tours_off)
        self.client.force_authenticate(self.student)
        self.assertIs(self.client.get(ME).json()["tours_off"], False)

    def test_sets_and_unsets_it(self):
        self.client.force_authenticate(self.student)
        response = self.client.put(OFF, {"off": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tours_off": True})
        self.student.refresh_from_db()
        self.assertTrue(self.student.tours_off)

        response = self.client.put(OFF, {"off": False}, format="json")
        self.assertEqual(response.json(), {"tours_off": False})
        self.student.refresh_from_db()
        self.assertFalse(self.student.tours_off)

    def test_unsetting_it_keeps_the_tours_seen(self):
        student = make_user("seen.student@cit.edu", RoleName.STUDENT, tours_seen=["discover"], tours_off=True)
        self.client.force_authenticate(student)
        self.client.put(OFF, {"off": False}, format="json")
        student.refresh_from_db()
        self.assertEqual(student.tours_seen, ["discover"])

    def test_anything_but_a_boolean_is_refused(self):
        self.client.force_authenticate(self.student)
        for body in ({"off": "true"}, {"off": "false"}, {"off": 1}, {"off": None}, {}):
            with self.subTest(body=body):
                response = self.client.put(OFF, body, format="json")
                self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertFalse(self.student.tours_off)

    def test_signed_out_is_refused(self):
        self.assertEqual(self.client.put(OFF, {"off": True}, format="json").status_code, 401)

    def test_only_tours_off_is_written(self):
        """A body naming other fields is ignored: the endpoint reads `off` alone."""
        self.client.force_authenticate(self.student)
        before = User.objects.filter(pk=self.student.pk).values().get()
        response = self.client.put(
            OFF,
            {"off": True, "first_name": "Changed", "is_staff": True, "tours_seen": ["discover"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        after = User.objects.filter(pk=self.student.pk).values().get()
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {"tours_off"})

    def test_sets_the_caller_only(self):
        other = make_user("other.off@cit.edu", RoleName.STUDENT)
        self.client.force_authenticate(self.student)
        self.client.put(OFF, {"off": True}, format="json")
        other.refresh_from_db()
        self.assertFalse(other.tours_off)

    def test_patch_cannot_write_it(self):
        self.client.force_authenticate(self.student)
        response = self.client.patch(ME, {"tours_off": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.tours_off)


class WhereItIsReadTests(APITestCase):
    def test_absent_from_the_administrators_list(self):
        admin = make_user("rdco.off@cit.edu", RoleName.RDCO)
        make_user("listed.off@cit.edu", RoleName.STUDENT, tours_off=True)
        self.client.force_authenticate(admin)
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertTrue(rows)
        self.assertTrue(all("tours_off" not in row for row in rows))

    def test_in_the_personal_data_export(self):
        student = make_user("export.off@cit.edu", RoleName.STUDENT, tours_off=True)
        self.client.force_authenticate(student)
        response = self.client.get("/api/v1/users/me/data/")
        self.assertEqual(response.status_code, 200)
        body = json.loads(b"".join(response) if response.streaming else response.content)
        self.assertIs(body["account"]["tours_off"], True)
