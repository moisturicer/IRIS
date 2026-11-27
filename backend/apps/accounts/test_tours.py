"""The student guided tours an account has seen (IR-1342).

`POST /users/me/tours/<key>/` is the one write: a known key, for the signed-in
account, touching `tours_seen` alone (AC 8). `tours_seen` is read on the
person's own `/users/me/` and in their data export (AC 9), never on the
administrators' list. The frontend's copy of the keys is checked here so the
two cannot drift.
"""
import importlib
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.accounts.tests import make_user
from apps.accounts.tours import TOUR_KEYS
from core.enums import RoleName

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_KEYS = REPO_ROOT / "frontend" / "src" / "features" / "onboarding" / "tourKeys.json"

ME = "/api/v1/users/me/"


def tour_url(key):
    return f"/api/v1/users/me/tours/{key}/"


def test_the_frontend_reads_the_same_keys():
    assert json.loads(FRONTEND_KEYS.read_text(encoding="utf-8")) == list(TOUR_KEYS)


class MarkSeenTests(APITestCase):
    def setUp(self):
        self.student = make_user("new.student@cit.edu", RoleName.STUDENT)

    def test_a_new_account_has_seen_no_tour(self):
        self.assertEqual(self.student.tours_seen, [])
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(ME).json()["tours_seen"], [])

    def test_marks_a_known_key(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(tour_url("discover"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tours_seen": ["discover"]})
        self.student.refresh_from_db()
        self.assertEqual(self.student.tours_seen, ["discover"])

    def test_marking_again_changes_nothing(self):
        self.client.force_authenticate(self.student)
        self.client.post(tour_url("discover"))
        self.client.post(tour_url("publish"))
        response = self.client.post(tour_url("discover"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tours_seen": ["discover", "publish"]})

    def test_an_unknown_key_is_refused(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(tour_url("review"))
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.tours_seen, [])

    def test_signed_out_is_refused(self):
        self.assertEqual(self.client.post(tour_url("discover")).status_code, 401)

    def test_only_tours_seen_is_written(self):
        """A body naming other fields is ignored: the endpoint takes none."""
        self.client.force_authenticate(self.student)
        before = User.objects.filter(pk=self.student.pk).values().get()
        response = self.client.post(
            tour_url("library"),
            {"first_name": "Changed", "is_staff": True, "role": None, "tours_seen": ["x"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        after = User.objects.filter(pk=self.student.pk).values().get()
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {"tours_seen"})
        self.assertEqual(after["tours_seen"], ["library"])

    def test_marks_the_caller_only(self):
        other = make_user("other.student@cit.edu", RoleName.STUDENT)
        self.client.force_authenticate(self.student)
        self.client.post(tour_url("ask"))
        other.refresh_from_db()
        self.assertEqual(other.tours_seen, [])

    def test_patch_cannot_write_it(self):
        self.client.force_authenticate(self.student)
        response = self.client.patch(ME, {"tours_seen": list(TOUR_KEYS)}, format="json")
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.tours_seen, [])


class WhereItIsReadTests(APITestCase):
    def test_absent_from_the_administrators_list(self):
        admin = make_user("rdco@cit.edu", RoleName.RDCO)
        make_user("listed.student@cit.edu", RoleName.STUDENT, tours_seen=["discover"])
        self.client.force_authenticate(admin)
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertTrue(rows)
        self.assertTrue(all("tours_seen" not in row for row in rows))

    def test_in_the_personal_data_export(self):
        student = make_user("export.student@cit.edu", RoleName.STUDENT, tours_seen=["discover", "ask"])
        self.client.force_authenticate(student)
        response = self.client.get("/api/v1/users/me/data/")
        self.assertEqual(response.status_code, 200)
        body = json.loads(b"".join(response) if response.streaming else response.content)
        self.assertEqual(body["account"]["tours_seen"], ["discover", "ask"])


_BEFORE = [("accounts", "0024_session_remembered")]
_AFTER = [("accounts", "0025_tours_seen")]


@pytest.mark.db_required
@pytest.mark.django_db(transaction=True)
def test_the_migration_marks_existing_accounts_only():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_BEFORE).apps
    executor.migrate(_BEFORE)
    try:
        OldUser = old_apps.get_model("accounts", "User")
        existing = OldUser.objects.create(email="before@cit.edu", password="!")

        executor = MigrationExecutor(connection)
        executor.migrate(_AFTER)
        NewUser = executor.loader.project_state(_AFTER).apps.get_model("accounts", "User")

        # The keys as they were when 0025 ran, not today's `TOUR_KEYS`.
        frozen = importlib.import_module("apps.accounts.migrations.0025_tours_seen").KEYS_AT_THIS_MIGRATION
        assert NewUser.objects.get(pk=existing.pk).tours_seen == frozen
        after = NewUser.objects.create(email="after@cit.edu", password="!")
        assert NewUser.objects.get(pk=after.pk).tours_seen == []
    finally:
        call_command("migrate", verbosity=0)
