"""
Tests for apps.records.

No pytest is configured for this repo (backend/requirements/development.txt
says so explicitly) -- these use Django's own django.test.TestCase /
rest_framework.test.APITestCase, which need no extra setup. Run with:

    docker compose exec -T backend python manage.py test apps.records
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.reviews.models import RecordClearance
from .models import DeleteRequest, Record, RecordOwner, RecordType


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
        # Consent is sent here so these tests keep testing what they were
        # written for -- ownership (IR-226). Submitting now also requires DPA
        # consent, and without it every case below would fail on the consent
        # gate before the permission check it exists to exercise ever ran.
        # Changed deliberately, not to make a red test green: the assertions
        # are untouched, and consent has its own suite in
        # `DpaConsentAtSubmitTests` below.
        return self.client.post(
            reverse("record-submit", args=[self.record.id]),
            {"dpa_accepted": True},
            format="json",
        )

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
        """
        404, not 403, since IR-153.

        The refusal this test exists to prove is unchanged -- a non-owner still
        cannot move someone else's draft into the pipeline, which is what the
        pipeline_status assertion below pins down. What changed is *which*
        refusal: `RecordViewSet.get_queryset()` now filters by
        `Record.objects.visible_to(user)`, so a draft this user cannot see is
        already absent from the queryset by the time `get_object()` looks, and
        DRF raises 404 before `IsOwnerOrStaff` ever runs.

        The 403 asserted here previously was the weaker answer: it confirmed
        that a record with this id exists and is someone's draft. Deliberately
        updated rather than worked around -- a non-owner acting on a record they
        *can* see (a published one) still gets 403 from `IsOwnerOrStaff`, so
        both codes remain reachable and mean different things.
        """
        self.client.force_authenticate(self.other)
        response = self._submit()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
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


class MineEndpointTests(APITestCase):
    """
    GET /records/mine/ is RecordViewSet.mine() -- MyRecordsViewSet also exists
    in this file with serializer_class = RecordDetailSerializer, but is never
    registered in urls.py, so it serves nothing. mine() hardcoded
    RecordListSerializer directly, which has no `clearances` field. Found
    while building My Workspace: the frontend read record.clearances
    everywhere and always got undefined, because the real endpoint was never
    returning it -- MyRecordsViewSet's richer serializer was a red herring
    that looked live but wasn't reachable.
    """

    def setUp(self):
        self.thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("mine_owner@cit.edu", "Student")
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=self.thesis,
            added_by=self.owner, pipeline_status="parallel_review",
            requested_ierc=True,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        RecordClearance.objects.create(record=self.record, office="ierc", status="pending")

    def test_mine_includes_clearances(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("record-mine"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        mine = next(r for r in response.data if r["id"] == self.record.id)
        self.assertIn("clearances", mine, "My Workspace needs this to show office status")
        self.assertEqual(mine["clearances"][0]["office"], "ierc")
        self.assertEqual(mine["clearances"][0]["status"], "pending")


class DeadPermissionKwargSweepTests(APITestCase):
    """
    A systematic sweep for the bug found on submit/tags: a @action's
    permission_classes kwarg is dead code whenever the ViewSet's
    get_permissions() is a full override that never falls back to
    super().get_permissions() (which is what actually consults the kwarg).

    Dead does not always mean vulnerable -- DownloadRequestViewSet's catch-all
    happens to return the same [IsAuthenticated, IsStaff] the kwargs declare,
    and ReviewViewSet ends its override with super(), so both are fine. The
    ones below are the cases where the fallback is *weaker* than what the
    action declared, so the declared restriction silently did nothing.
    """

    def setUp(self):
        self.thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.student = make_user("sweep_student@cit.edu", "Student")
        self.rdco = make_user("sweep_rdco@cit.edu", "RDCO")

        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=self.thesis,
            added_by=self.student, pipeline_status="published",
        )
        RecordOwner.objects.create(record=self.record, user=self.student, is_primary=True)
        self.delete_request = DeleteRequest.objects.create(
            record=self.record, requested_by=self.student,
            status="pending", previous_pipeline_status="published",
        )

    def test_student_cannot_bulk_import_records(self):
        """
        import_excel declares IsStaff and creates records straight in
        'published', bypassing the review pipeline entirely -- exactly what a
        non-staff user must not be able to reach.
        """
        self.client.force_authenticate(self.student)
        response = self.client.post(reverse("record-import-excel"), {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_student_cannot_download_import_template(self):
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("record-download-template"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_approve_a_delete_request(self):
        """The destructive one: approve() soft-deletes the record."""
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("delete-request-approve", args=[self.delete_request.id])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.record.refresh_from_db()
        self.assertFalse(self.record.is_deleted, "record must survive an unauthorised approve")

    def test_student_cannot_decline_a_delete_request(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("delete-request-decline", args=[self.delete_request.id])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_rdco_can_still_approve_a_delete_request(self):
        """The fix must not lock out the role that is supposed to do this."""
        self.client.force_authenticate(self.rdco)
        response = self.client.post(
            reverse("delete-request-approve", args=[self.delete_request.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertTrue(self.record.is_deleted)


class RecordVisibilityTests(APITestCase):
    """
    IR-153: `RecordViewSet.get_queryset()` filtered only on `list`, so every
    other action ran against the unfiltered manager. `GET /records/<id>/`
    therefore returned any record to any authenticated account -- including
    unpublished drafts, their abstracts and their review history.

    The fix is one predicate, `Record.objects.visible_to(user)`, applied on
    every action. These tests pin down who it lets through and -- just as
    importantly -- that a refusal is indistinguishable from a record that does
    not exist, so the API never confirms someone else's draft is there.
    """

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner    = make_user("vis-owner@cit.edu", "Student")
        self.stranger = make_user("vis-stranger@cit.edu", "Student")
        self.adviser  = make_user("vis-adviser@cit.edu", "Adviser")
        self.rdco     = make_user("vis-rdco@cit.edu", "RDCO")

        self.draft = Record.objects.create(
            title="Unpublished Draft", abstract="B" * 40,
            record_type=self.record_type, added_by=self.owner,
            pipeline_status="draft", adviser=self.adviser,
        )
        RecordOwner.objects.create(record=self.draft, user=self.owner, is_primary=True)

        self.published = Record.objects.create(
            title="Published Work", abstract="C" * 40,
            record_type=self.record_type, added_by=self.owner,
            pipeline_status="published",
        )
        RecordOwner.objects.create(record=self.published, user=self.owner, is_primary=True)

    def _get(self, record):
        return self.client.get(reverse("record-detail", args=[record.id]))

    def test_owner_can_retrieve_own_draft(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self._get(self.draft).status_code, status.HTTP_200_OK)

    def test_stranger_cannot_retrieve_someone_elses_draft(self):
        """The actual vulnerability: this returned 200 with the full record."""
        self.client.force_authenticate(self.stranger)
        self.assertEqual(
            self._get(self.draft).status_code,
            status.HTTP_404_NOT_FOUND,
            "an unrelated authenticated user could read someone else's unpublished draft",
        )

    def test_refusal_is_indistinguishable_from_a_missing_record(self):
        """
        A 403 would confirm the record exists. The response for "not yours" and
        the response for "no such record" must not differ.
        """
        self.client.force_authenticate(self.stranger)
        refused = self._get(self.draft)
        missing = self.client.get(reverse("record-detail", args=[self.draft.id + 10_000]))
        self.assertEqual(refused.status_code, missing.status_code)
        self.assertEqual(refused.data, missing.data)

    def test_assigned_adviser_can_retrieve_the_draft(self):
        """
        The adviser is not in STAFF_ROLES, but `adviser_review` is the first
        gate in the Proposal pipeline -- excluding them would break the
        workflow this system exists to run.
        """
        self.client.force_authenticate(self.adviser)
        self.assertEqual(self._get(self.draft).status_code, status.HTTP_200_OK)

    def test_unassigned_adviser_cannot_retrieve_the_draft(self):
        """Holding the Adviser role is not the same as being *this* record's adviser."""
        other_adviser = make_user("vis-adviser2@cit.edu", "Adviser")
        self.client.force_authenticate(other_adviser)
        self.assertEqual(self._get(self.draft).status_code, status.HTTP_404_NOT_FOUND)

    def test_office_staff_can_retrieve_any_draft(self):
        """RDCO performs intake review; it cannot review what it cannot open."""
        self.client.force_authenticate(self.rdco)
        self.assertEqual(self._get(self.draft).status_code, status.HTTP_200_OK)

    def test_anyone_authenticated_can_retrieve_a_published_record(self):
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self._get(self.published).status_code, status.HTTP_200_OK)

    def test_anonymous_cannot_retrieve(self):
        response = self._get(self.published)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_list_still_excludes_drafts_for_the_owner(self):
        """
        Regression guard on Discover. `visible_to` is wider than the public
        catalogue, so applying it to `list` without narrowing would surface a
        user's own drafts in the browse surface. Own drafts belong to
        /records/mine/, not to Discover.
        """
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("record-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = {row["id"] for row in response.data["results"]}
        self.assertIn(self.published.id, returned)
        self.assertNotIn(
            self.draft.id, returned,
            "a draft leaked into the public browse list",
        )

    def test_list_still_excludes_drafts_for_staff(self):
        """Staff see everything through `visible_to`; Discover is still a catalogue."""
        self.client.force_authenticate(self.rdco)
        response = self.client.get(reverse("record-list"))
        returned = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.draft.id, returned)


class DpaConsentAtSubmitTests(APITestCase):
    """
    DPA consent is recorded per disclosure, at submission (IR-226, FR-M6-02).

    The wizard has shown a consent gate at step 3 since IR-88, but it lived
    entirely in the browser: `submit()` neither checked nor stored anything, so
    a direct API call bypassed it and left no trace either way. The only
    persisted consent in the system was `User.consent_given` -- one boolean, set
    once, at signup. "This person ticked a box months ago" is not evidence that
    *this disclosure* was submitted under the terms.

    What these tests pin down is that the refusal happens **before** the
    transition. A record that reaches a review queue with no consent behind it
    is worse than one that was never submitted, because the workflow has
    already started acting on it.
    """

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("dpa-owner@cit.edu", "Student")
        self.record = Record.objects.create(
            title="C" * 10, abstract="D" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status="draft",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        self.url = reverse("record-submit", args=[self.record.id])
        self.client.force_authenticate(self.owner)

    def _post(self, payload=None):
        return self.client.post(self.url, payload or {}, format="json")

    def test_submitting_without_consent_is_refused(self):
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("10173", str(response.data))

    def test_a_refused_submit_leaves_the_record_in_draft(self):
        """The assertion that matters more than the status code.

        If the consent check ran after `lifecycle.apply`, this endpoint would
        return 400 while the record sat in `rdco_intake` -- refused, and in a
        review queue anyway.
        """
        self._post()
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, "draft")
        self.assertIsNone(self.record.dpa_accepted_at)
        self.assertIsNone(self.record.dpa_accepted_by)

    def test_explicitly_declining_consent_is_refused(self):
        """`false` must be refused, not merely absent-vs-present.

        A check that only tested for the key's presence would accept
        `{"dpa_accepted": false}` -- an explicit refusal recorded as consent.
        """
        response = self._post({"dpa_accepted": False})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, "draft")

    def test_consent_is_stamped_with_who_and_when(self):
        response = self._post({"dpa_accepted": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, "rdco_intake")
        self.assertIsNotNone(self.record.dpa_accepted_at)
        self.assertEqual(self.record.dpa_accepted_by, self.owner)
        self.assertTrue(self.record.dpa_accepted)

    def test_dpa_accepted_is_derived_not_stored(self):
        """The property must follow the timestamp, having no state of its own."""
        self.assertFalse(self.record.dpa_accepted)
        self.record.dpa_accepted_at = timezone.now()
        self.assertTrue(self.record.dpa_accepted)

    def test_resubmission_preserves_the_original_consent(self):
        """Consent is given once per disclosure and survives revision.

        Re-stamping on resubmission would quietly replace "when the owner
        accepted the terms" with "when they last fixed a typo", which is the
        one thing this timestamp exists to answer.
        """
        from apps.reviews.services import resubmit_record

        original = timezone.now() - timedelta(days=3)
        Record.objects.filter(pk=self.record.pk).update(
            pipeline_status="declined",
            dpa_accepted_at=original,
            dpa_accepted_by=self.owner,
        )
        self.record.refresh_from_db()

        resubmit_record(self.record, self.owner)

        self.record.refresh_from_db()
        self.assertEqual(self.record.dpa_accepted_at, original)
        self.assertEqual(self.record.dpa_accepted_by, self.owner)
        self.assertNotEqual(
            self.record.pipeline_status, "declined",
            "the resubmission itself should still have moved the record",
        )

    def test_consent_fields_are_not_writable_through_the_record_serializer(self):
        """Consent the subject can set on themselves is not evidence.

        `RecordWriteSerializer.fields` is an explicit allowlist, so this holds
        today by construction -- which is exactly why it needs a test. Nothing
        else would stop someone adding these two names to that list.
        """
        from .serializers import RecordWriteSerializer

        writable = set(RecordWriteSerializer().fields)
        self.assertNotIn("dpa_accepted_at", writable)
        self.assertNotIn("dpa_accepted_by", writable)
        self.assertNotIn("dpa_accepted", writable)

    def test_patching_consent_directly_does_not_stamp_it(self):
        """The allowlist above, exercised over HTTP rather than by inspection."""
        self.client.patch(
            reverse("record-detail", args=[self.record.id]),
            {"dpa_accepted_at": timezone.now().isoformat()},
            format="json",
        )
        self.record.refresh_from_db()
        self.assertIsNone(
            self.record.dpa_accepted_at,
            "PATCH must not be able to stamp consent -- only submit() may",
        )

    def test_detail_serializer_exposes_consent_read_only(self):
        Record.objects.filter(pk=self.record.pk).update(
            dpa_accepted_at=timezone.now(), dpa_accepted_by=self.owner
        )
        response = self.client.get(reverse("record-detail", args=[self.record.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["dpa_accepted"])
        self.assertIsNotNone(response.data["dpa_accepted_at"])
