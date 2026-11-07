"""
The System Admin role (ADR-051 decisions 1 to 6, amended 2026-11-03, IR-781).

The System Admin runs IRIS itself and holds no workflow access. It alone reads
the Audit Log and system settings, and it alone gives office roles and the
coordinator flag. RDCO gives Student and Adviser and keeps the rest of account
administration, but acts on no System Admin account. Nobody is given the role
through the API: it is given in Django's admin site.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role, RoleRequest, SystemSetting, User
from apps.accounts.test_password_policy import registration
from apps.records.models import Record, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName
from core.permissions import REVIEWER_ROLES, STAFF_ROLES, office_parties_of


def make(email, role_name=None, **extra):
    role = Role.objects.get(name=role_name) if role_name else None
    return User.objects.create_user(
        email=email, password="Kalamansi-Tide-42", first_name="Test", last_name="User",
        role=role, is_verified=True, **extra,
    )


class SystemAdminBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sysadmin = make("sa-admin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.other_sysadmin = make("sa-admin2@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.rdco = make("sa-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make("sa-itso@cit.edu", RoleName.ITSO)
        cls.student = make("sa-student@cit.edu", RoleName.STUDENT)
        cls.adviser = make("sa-adviser@cit.edu", RoleName.ADVISER)
        cls.superuser = make("sa-super@cit.edu", is_staff=True, is_superuser=True)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def give(self, actor, target, role_name):
        return self.as_(actor).patch(
            reverse("user-change-role", args=[target.pk]), {"role_name": role_name}, format="json",
        )

    def role_of(self, user):
        user.refresh_from_db()
        return user.role.name if user.role else None


class TheRoleTests(SystemAdminBase):
    def test_a_migration_adds_it(self):
        self.assertTrue(Role.objects.filter(name="System Admin").exists())

    def test_it_carries_no_workflow_access(self):
        self.assertNotIn(RoleName.SYSTEM_ADMIN, STAFF_ROLES)
        self.assertNotIn(RoleName.SYSTEM_ADMIN, REVIEWER_ROLES)
        self.assertEqual(office_parties_of(self.sysadmin), frozenset())

    def test_it_sees_the_public_catalogue_only(self):
        kind = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        published = Record.objects.create(
            title="Published", record_type=kind, pipeline_status=PipelineStatus.PUBLISHED,
        )
        in_review = Record.objects.create(
            title="In review", record_type=kind, pipeline_status=PipelineStatus.IN_REVIEW,
        )

        visible = set(Record.objects.visible_to(self.sysadmin).values_list("pk", flat=True))

        self.assertIn(published.pk, visible)
        self.assertNotIn(in_review.pk, visible)


class AuditLogAndSettingsTests(SystemAdminBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.setting = SystemSetting.objects.create(key="announcement", value="old text")

    def test_only_the_system_admin_reads_the_audit_log_and_its_export(self):
        for name in ("audit-list", "audit-export", "audit-event-types"):
            with self.subTest(route=name):
                self.assertEqual(self.as_(self.sysadmin).get(reverse(name)).status_code, status.HTTP_200_OK)
                for user in (self.rdco, self.superuser, self.itso, self.student):
                    self.assertEqual(
                        self.as_(user).get(reverse(name)).status_code, status.HTTP_403_FORBIDDEN,
                        user.email,
                    )

    def test_only_the_system_admin_reads_and_changes_a_setting(self):
        url = reverse("system-setting", args=["announcement"])

        self.assertEqual(self.as_(self.rdco).get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.as_(self.rdco).patch(url, {"value": "new"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.as_(self.superuser).get(url).status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(self.as_(self.sysadmin).get(url).status_code, status.HTTP_200_OK)
        response = self.as_(self.sysadmin).patch(url, {"value": "new"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "new")


class WhoGivesWhichRoleTests(SystemAdminBase):
    def test_the_system_admin_gives_office_roles(self):
        for role_name in (RoleName.KTTO, RoleName.ITSO, RoleName.IERC, RoleName.RDCO):
            with self.subTest(role=role_name):
                target = make(f"sa-new-{role_name.lower()}@cit.edu", RoleName.STUDENT)

                response = self.give(self.sysadmin, target, role_name)

                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(self.role_of(target), role_name)

    def test_rdco_gives_student_or_adviser_to_someone_outside_the_offices(self):
        response = self.give(self.rdco, self.student, RoleName.ADVISER)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.role_of(self.student), RoleName.ADVISER)

    def test_rdco_cannot_give_an_office_role(self):
        for role_name in (RoleName.KTTO, RoleName.ITSO, RoleName.IERC, RoleName.RDCO):
            with self.subTest(role=role_name):
                response = self.give(self.rdco, self.student, role_name)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.role_of(self.student), RoleName.STUDENT)

    def test_rdco_cannot_change_an_office_account(self):
        response = self.give(self.rdco, self.itso, RoleName.STUDENT)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.role_of(self.itso), RoleName.ITSO)

    def test_nobody_gives_the_system_admin_role_through_the_api(self):
        for actor in (self.sysadmin, self.rdco, self.superuser):
            with self.subTest(actor=actor.email):
                response = self.give(actor, self.student, RoleName.SYSTEM_ADMIN)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.role_of(self.student), RoleName.STUDENT)

    def test_nobody_changes_a_system_admin_s_role_through_the_api(self):
        for actor in (self.sysadmin, self.rdco):
            for target in (self.sysadmin, self.other_sysadmin):
                with self.subTest(actor=actor.email, target=target.email):
                    response = self.give(actor, target, RoleName.STUDENT)

                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                    self.assertEqual(self.role_of(target), RoleName.SYSTEM_ADMIN)

    def test_only_the_system_admin_grants_the_coordinator_flag(self):
        url = reverse("user-coordinator", args=[self.itso.pk])

        refused = self.as_(self.rdco).patch(url, {"is_office_coordinator": True}, format="json")
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

        granted = self.as_(self.sysadmin).patch(url, {"is_office_coordinator": True}, format="json")
        self.assertEqual(granted.status_code, status.HTTP_200_OK, granted.data)
        self.itso.refresh_from_db()
        self.assertTrue(self.itso.is_office_coordinator)

    def test_both_see_the_users_list(self):
        for user in (self.rdco, self.sysadmin):
            with self.subTest(user=user.email):
                self.assertEqual(self.as_(user).get(reverse("user-list")).status_code, status.HTTP_200_OK)


class RdcoLeavesSystemAdminAccountsAloneTests(SystemAdminBase):
    def test_it_cannot_lock_or_unlock_one(self):
        lock = self.as_(self.rdco).patch(
            reverse("user-lock", args=[self.sysadmin.pk]), {"is_locked": True}, format="json",
        )
        self.assertEqual(lock.status_code, status.HTTP_403_FORBIDDEN)
        self.sysadmin.refresh_from_db()
        self.assertFalse(self.sysadmin.is_locked)

        User.objects.filter(pk=self.sysadmin.pk).update(is_locked=True)
        unlock = self.as_(self.rdco).post(reverse("user-unlock", args=[self.sysadmin.pk]))
        self.assertEqual(unlock.status_code, status.HTTP_403_FORBIDDEN)
        self.sysadmin.refresh_from_db()
        self.assertTrue(self.sysadmin.is_locked)

    def test_it_cannot_revoke_one_s_session(self):
        token = RefreshToken.for_user(self.sysadmin)

        response = self.as_(self.rdco).delete(reverse("user-session-revoke", args=[token["jti"]]))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_cannot_edit_one(self):
        response = self.as_(self.rdco).patch(
            reverse("user-detail", args=[self.sysadmin.pk]), {"first_name": "Renamed"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.sysadmin.refresh_from_db()
        self.assertEqual(self.sysadmin.first_name, "Test")

    def test_it_cannot_approve_a_role_request_that_would_change_one(self):
        request = RoleRequest.objects.create(
            user=self.sysadmin, requested_role=Role.objects.get(name=RoleName.STUDENT),
        )

        response = self.as_(self.rdco).patch(
            reverse("role-request-detail", args=[request.pk]), {"action": "approve"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(self.role_of(self.sysadmin), RoleName.SYSTEM_ADMIN)

    def test_it_cannot_give_an_office_role_by_approving_a_request(self):
        request = RoleRequest.objects.create(
            user=self.student, requested_role=Role.objects.get(name=RoleName.KTTO),
        )

        response = self.as_(self.rdco).patch(
            reverse("role-request-detail", args=[request.pk]), {"action": "approve"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(self.role_of(self.student), RoleName.STUDENT)

    def test_it_still_approves_a_student_or_adviser_request(self):
        request = RoleRequest.objects.create(
            user=make("sa-newcomer@cit.edu"), requested_role=Role.objects.get(name=RoleName.ADVISER),
        )

        response = self.as_(self.rdco).patch(
            reverse("role-request-detail", args=[request.pk]), {"action": "approve"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.APPROVED)

    def test_it_still_sees_one_in_the_users_list(self):
        response = self.as_(self.rdco).get(reverse("user-list"), {"page_size": 100})
        rows = response.data["results"] if isinstance(response.data, dict) else response.data

        self.assertIn(self.sysadmin.pk, {row["id"] for row in rows})

    def test_it_still_locks_and_revokes_anyone_else(self):
        lock = self.as_(self.rdco).patch(
            reverse("user-lock", args=[self.student.pk]), {"is_locked": True}, format="json",
        )
        self.assertEqual(lock.status_code, status.HTTP_200_OK)

        token = RefreshToken.for_user(self.adviser)
        revoke = self.as_(self.rdco).delete(reverse("user-session-revoke", args=[token["jti"]]))
        self.assertEqual(revoke.status_code, status.HTTP_200_OK)


class RegistrationRoleTests(APITestCase):
    def test_only_student_or_adviser_can_be_asked_for(self):
        for role_name in (RoleName.SYSTEM_ADMIN, RoleName.RDCO, RoleName.KTTO, RoleName.ITSO, RoleName.IERC):
            with self.subTest(role=role_name):
                response = self.client.post(
                    reverse("auth-register"),
                    registration("Kalamansi-Tide-42", email=f"reg-{role_name.lower().replace(' ', '-')}@cit.edu",
                                 role_name=role_name),
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("role_name", response.data)

    def test_student_passes_the_role_check(self):
        response = self.client.post(
            reverse("auth-register"),
            registration("Kalamansi-Tide-42", email="reg-student@cit.edu", role_name=RoleName.STUDENT),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("role_name", response.data)
        self.assertIn("course_id", response.data)
