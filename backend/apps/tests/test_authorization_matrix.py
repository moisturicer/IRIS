"""
The authorization matrix: role x action x ownership (IR-165).

This suite is the deliverable, not the fix. The defect it pins down is easy to
reintroduce -- `is_django_staff()` returned True for `is_staff`, and migration
`accounts/0005` set `is_staff = True` on every office role, so every
`is_django_staff(user) or <role check>` short-circuited to True for RDCO, KTTO,
ITSO and IERC. `ADMIN_ROLES` constrained nobody. Anyone who seeds a user with
`is_staff=True` brings the whole class of bug back, and only a test that asserts
*refusal* will notice.

Two rules this suite follows deliberately:

1.  **Every negative case asserts 403, not "not 200".** A 404 or a 500 is not a
    refusal; it is a different bug wearing a refusal's clothes.
2.  **Positive cases assert `!= 403`, not `== 200`.** Whether a permitted role
    then gets 200, 404 or 400 depends on fixtures and payloads that have nothing
    to do with authorization. Asserting 200 would couple this suite to every
    serializer in the project and make it fail for reasons it does not test.

Run:
    docker compose exec -T backend python manage.py test apps.tests.test_authorization_matrix
"""
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User

# Every application role. The matrix is only honest if it enumerates all of
# them -- a suite that tests "RDCO can, Student cannot" and stops would have
# passed throughout the entire is_staff bypass.
ALL_ROLES = ["Student", "Adviser", "RDCO", "KTTO", "ITSO", "IERC"]


def make_user(email, role_name=None, **extra):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    extra.setdefault("is_verified", True)
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, **extra,
    )


class AuthorizationMatrixTests(APITestCase):
    """
    For each protected endpoint: exactly the named roles may reach it, and every
    other role is refused with 403.
    """

    @classmethod
    def setUpTestData(cls):
        cls.users = {name: make_user(f"{name.lower()}@cit.edu", name) for name in ALL_ROLES}
        # A Django superuser with NO application role. IR-165 reserves
        # `is_superuser` for the Django admin site, so it must NOT confer API
        # authorization -- this account is the one that proves the bypass is gone.
        cls.root = make_user("root@cit.edu", None, is_staff=True, is_superuser=True)

    # --- the assertion the whole suite is built on -------------------------

    def assert_only(self, allowed, method, url, data=None):
        """
        `allowed` roles reach the view; every other role gets 403; the
        role-less superuser gets 403 too.
        """
        allowed = set(allowed)
        for name in ALL_ROLES:
            self.client.force_authenticate(self.users[name])
            resp = getattr(self.client, method)(url, data or {}, format="json")
            if name in allowed:
                self.assertNotEqual(
                    resp.status_code, 403,
                    f"{name} should reach {method.upper()} {url}, got 403",
                )
            else:
                self.assertEqual(
                    resp.status_code, 403,
                    f"{name} must be REFUSED {method.upper()} {url}, got {resp.status_code}",
                )

        self.client.force_authenticate(self.root)
        resp = getattr(self.client, method)(url, data or {}, format="json")
        self.assertEqual(
            resp.status_code, 403,
            "a role-less superuser must not pass an application role check "
            f"({method.upper()} {url} returned {resp.status_code}) -- "
            "is_superuser is for the Django admin site, not the API",
        )
        self.client.force_authenticate(None)

    # --- audit ------------------------------------------------------------

    def test_audit_log_is_rdco_only(self):
        """
        The headline case. `docs/ui-ux/02-information-architecture.md` §5 says
        audit is RDCO-only and notes the frontend constant is already correct
        while the backend is not; SRS FR-M6-06 says the log is read-only to all
        roles except system administrators. The view used DRF's `IsAdminUser`,
        which reads `is_staff` -- so all four offices could read it.
        """
        self.assert_only(["RDCO"], "get", reverse("audit-list"))

    # --- account administration -------------------------------------------

    def test_role_requests_are_rdco_only(self):
        self.assert_only(["RDCO"], "get", reverse("role-request-list"))

    def test_user_list_is_rdco_only(self):
        """
        `ADMIN_ROLES` was {KTTO, RDCO}. The 2026-09-06 role-screen review
        narrowed account administration to RDCO: KTTO is a technology-transfer
        office and has no reason to manage user accounts.
        """
        self.assert_only(["RDCO"], "get", reverse("user-list"))

    def test_change_user_role_is_rdco_only(self):
        target = make_user("target@cit.edu", "Student")
        self.assert_only(
            ["RDCO"], "post",
            reverse("user-change-role", args=[target.pk]),
            {"role": "Adviser"},
        )

    # --- request queues ---------------------------------------------------

    def test_delete_request_approval_is_rdco_only(self):
        self.assert_only(["RDCO"], "post", reverse("delete-request-approve", args=[1]))

    def test_download_request_approval_is_rdco_only(self):
        self.assert_only(["RDCO"], "post", reverse("download-request-approve", args=[1]))

    # --- authoring --------------------------------------------------------

    def test_record_creation_is_student_and_adviser_only(self):
        """
        SRS Use Cases M2-2.1 (Create IP Disclosure Draft) and M2-2.2 (Submit
        Record for Review) both name the actor "Record Owner (Student or
        Adviser)". The clearing offices must not author records they may later
        clear, and RDCO performs both intake and final review -- so RDCO
        submitting would mean reviewing its own record at two of three gates.

        `RecordViewSet` had no role gate on creation at all.
        """
        self.assert_only(
            ["Student", "Adviser"], "post",
            reverse("record-list"),
            {"title": "A disclosure", "abstract": "x"},
        )

    # --- a role check that is already correct, pinned so it stays that way --

    def test_opportunity_posting_matches_its_declared_roles(self):
        """
        `OPPORTUNITY_POSTER_ROLES = {RDCO, KTTO, Adviser}` is the one role set in
        `core/permissions.py` that carries a written rationale for its
        membership. Pinned here so the is_staff removal does not widen or narrow
        it by accident.
        """
        self.assert_only(
            ["RDCO", "KTTO", "Adviser"], "post",
            reverse("opportunity-list"),
            {"title": "A call", "kind": "conference"},
        )
