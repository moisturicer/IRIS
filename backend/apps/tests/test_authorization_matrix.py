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
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.services import _can_review, _can_submit_clearance

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


class OwnershipMatrixTests(APITestCase):
    """
    The ownership half of "role x action x ownership".

    Role alone is not the whole authorization question: `IsOwnerOrStaff` and the
    review gates turn on *which* record, not only *who* is asking. A suite that
    varied role and nothing else would have passed throughout the bug this
    ticket closes, because the bypass was invisible until you asked whether the
    right office was acting on the right record.
    """

    @classmethod
    def setUpTestData(cls):
        # Reference rows are seeded by migration; create() would collide.
        cls.record_type = RecordType.objects.first() or RecordType.objects.create(name="Thesis / Research")
        cls.owner     = make_user("owner@cit.edu", "Student")
        cls.stranger  = make_user("stranger@cit.edu", "Student")
        cls.adviser   = make_user("named-adviser@cit.edu", "Adviser")
        cls.other_adv = make_user("other-adviser@cit.edu", "Adviser")
        cls.rdco      = make_user("rdco-own@cit.edu", "RDCO")
        cls.itso      = make_user("itso-own@cit.edu", "ITSO")
        cls.ierc      = make_user("ierc-own@cit.edu", "IERC")

        cls.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=cls.record_type,
            added_by=cls.owner, pipeline_status="draft", adviser=cls.adviser,
        )
        RecordOwner.objects.create(record=cls.record, user=cls.owner, is_primary=True)

    # --- submit: owner vs non-owner, same role ----------------------------

    def test_a_student_cannot_submit_another_students_draft(self):
        url = reverse("record-submit", args=[self.record.pk])

        self.client.force_authenticate(self.stranger)
        self.assertEqual(
            self.client.post(url, {}, format="json").status_code, 403,
            "a non-owning Student must not submit someone else's draft",
        )

        self.client.force_authenticate(self.owner)
        self.assertNotEqual(
            self.client.post(url, {}, format="json").status_code, 403,
            "the owner must be able to submit their own draft",
        )

    # --- _can_review: the sequential gates --------------------------------

    def test_only_the_named_adviser_may_review_at_adviser_review(self):
        """
        The card's AC: "_can_review no longer short-circuits on a staff flag."
        Before, every office role was is_staff and so returned True here
        regardless of stage or assignment.
        """
        self.record.pipeline_status = "adviser_review"
        self.assertTrue(_can_review(self.adviser, self.record),
                        "the named adviser may review at adviser_review")
        self.assertFalse(_can_review(self.other_adv, self.record),
                         "an unrelated Adviser must not review someone else's record")
        for user, who in ((self.itso, "ITSO"), (self.ierc, "IERC"), (self.owner, "the owner")):
            self.assertFalse(_can_review(user, self.record),
                             f"{who} has no standing at the adviser gate")

    def test_rdco_reviews_only_at_its_own_stages(self):
        for stage in ("rdco_intake", "rdco_review"):
            self.record.pipeline_status = stage
            self.assertTrue(_can_review(self.rdco, self.record), f"RDCO at {stage}")
        self.record.pipeline_status = "parallel_review"
        self.assertFalse(_can_review(self.rdco, self.record),
                         "RDCO must not review at a clearance stage")

    # --- clearance: one office must not sign for another ------------------

    def test_an_office_cannot_record_another_offices_clearance(self):
        """
        The consequence the ticket did not name. `_can_submit_clearance` let any
        is_staff account act on *whichever* clearance was pending, so an ITSO
        officer could sign IERC's ethics clearance -- collapsing the office
        separation the whole workflow rests on.
        """
        self.record.pipeline_status = "itso_review"
        can_itso, office = _can_submit_clearance(self.itso, self.record)
        self.assertEqual(office, "itso", "ITSO's role maps to the itso office")

        can_ierc, _ = _can_submit_clearance(self.ierc, self.record)
        self.assertFalse(can_ierc,
                         "IERC must not record a clearance at the ITSO stage")

        can_owner, _ = _can_submit_clearance(self.owner, self.record)
        self.assertFalse(can_owner, "a Student holds no clearance office at all")
