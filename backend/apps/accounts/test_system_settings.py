"""
IR-667: system settings are for administrators, and every change is audited.

`GET /settings/<key>/` was open to any signed-in user, and `PATCH` created
whatever key it was given and left no audit row. No screen calls either route.
The per-role refusals are also in the authorization matrix
(`apps/tests/access/table.py`).

**Seam: the API.**
"""

from rest_framework.test import APITestCase

from apps.accounts.models import Role, SystemSetting, User
from apps.audit.models import AuditEvent
from core.enums import RoleName


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


def _url(key):
    return f"/api/v1/settings/{key}/"


class SystemSettingTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.rdco = _user("settings-rdco@cit.edu", RoleName.RDCO)
        cls.student = _user("settings-student@cit.edu", RoleName.STUDENT)
        cls.itso = _user("settings-itso@cit.edu", RoleName.ITSO)
        cls.setting = SystemSetting.objects.create(key="announcement", value="old text")

    def test_only_rdco_can_read_a_setting(self):
        for user in (self.student, self.itso):
            with self.subTest(user=user.email):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(_url("announcement")).status_code, 403)

        self.client.force_authenticate(self.rdco)
        response = self.client.get(_url("announcement"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["value"], "old text")

    def test_an_anonymous_read_is_refused(self):
        self.assertEqual(self.client.get(_url("announcement")).status_code, 401)

    def test_a_refused_reader_cannot_tell_which_keys_exist(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(_url("no-such-key")).status_code, 403)

    def test_a_change_is_audited_with_its_old_and_new_value(self):
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(_url("announcement"), {"value": "new text"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.setting.refresh_from_db()
        self.assertEqual((self.setting.value, self.setting.updated_by), ("new text", self.rdco))
        event = AuditEvent.objects.get(event_type="SYSTEM_SETTING_CHANGED")
        self.assertEqual(event.user, self.rdco)
        self.assertEqual(
            event.metadata, {"key": "announcement", "old_value": "old text", "new_value": "new text"},
        )

    def test_writing_the_same_value_changes_nothing_and_audits_nothing(self):
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(_url("announcement"), {"value": "old text"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditEvent.objects.filter(event_type="SYSTEM_SETTING_CHANGED").exists())

    def test_a_patch_cannot_create_a_key(self):
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(_url("no-such-key"), {"value": "x"}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(SystemSetting.objects.filter(key="no-such-key").exists())
        self.assertFalse(AuditEvent.objects.filter(event_type="SYSTEM_SETTING_CHANGED").exists())

    def test_a_patch_without_a_value_is_refused(self):
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(_url("announcement"), {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "old text")

    def test_a_refused_writer_changes_nothing(self):
        self.client.force_authenticate(self.itso)

        response = self.client.patch(_url("announcement"), {"value": "new"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "old text")
