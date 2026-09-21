"""
IR-265: intake and the specialist offices can no longer end a Record.

ADR-021's authority rule is "a specialist's negative finding informs the
decision; it is not the decision". On the current pipeline that means:

- **Intake** (RDCO at `rdco_intake`) may accept or request revision, never reject.
- **ITSO, IERC and KTTO** may clear or request revision, never reject.
- **Reject stays** with RDCO at final review and with the assigned Adviser on a
  Proposal -- the two parties ADR-021 gives the decision to.

**Why this module stands alone.** IR-260 retires `test_workflow_characterisation.py`
and the matrix built on it. The rule pinned here survives the cutover, so it must
not be deleted with them. Nothing here imports from those suites.

**Seam: the reviews API.** A refusal is asserted in three halves -- the request
fails, the Record did not move, and nothing was written (no `Review` row, no
clearance change). A refusal that still wrote the office's clearance as
`rejected` would pass a status-only assertion.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordClearance, Review
from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    RoleName,
)

REVIEW_SUBMIT = "/api/v1/reviews/submit/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class RejectAuthorityTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("reject-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = _user("reject-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = _user("reject-rdco@cit.edu", RoleName.RDCO)
        cls.offices = {
            Office.ITSO: _user("reject-itso@cit.edu", RoleName.ITSO),
            Office.IERC: _user("reject-ierc@cit.edu", RoleName.IERC),
            Office.KTTO: _user("reject-ktto@cit.edu", RoleName.KTTO),
        }

    # --- setup ---------------------------------------------------------------

    def make_record(self, type_name, pipeline_status, **extra):
        record = Record.objects.create(
            title=f"Reject authority {type_name}",
            abstract="A" * 40,
            record_type=RecordType.objects.get(name=type_name),
            added_by=self.owner,
            pipeline_status=pipeline_status,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def record_with_pending_clearances(self, type_name, **requested):
        """
        Reached through intake approval, which is what creates the clearance
        rows. A record parked at a clearance stage with hand-made rows would be a
        state the workflow never produces.
        """
        record = self.make_record(
            type_name, PipelineStatus.RDCO_INTAKE, **requested
        )
        response = self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        record.refresh_from_db()
        return record

    # --- drivers and observations --------------------------------------------

    def review(self, record, actor, decision, comment="Reason given."):
        self.client.force_authenticate(actor)
        return self.client.post(
            REVIEW_SUBMIT,
            {"record_id": record.pk, "status": decision, "comment": comment},
            format="json",
        )

    def status_of(self, record):
        record.refresh_from_db()
        return record.pipeline_status

    def clearance_rows(self, record):
        return set(
            RecordClearance.objects.filter(record=record).values_list(
                "office", "status", "reviewed_by_id", "comment"
            )
        )

    def assert_refused_without_effect(self, record, actor, from_status):
        reviews_before = Review.objects.filter(record=record).count()
        clearances_before = self.clearance_rows(record)

        response = self.review(record, actor, ReviewDecision.REJECTED)

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST, response.data
        )
        self.assertTrue(str(response.data.get("detail", "")).strip())
        self.assertEqual(self.status_of(record), from_status)
        self.assertEqual(
            Review.objects.filter(record=record).count(),
            reviews_before,
            "a refused rejection still wrote a Review row",
        )
        self.assertEqual(
            self.clearance_rows(record),
            clearances_before,
            "a refused rejection still changed a clearance",
        )

    # --- refused ---------------------------------------------------------------

    def test_intake_cannot_reject(self):
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT):
            with self.subTest(record_type=type_name):
                record = self.make_record(
                    type_name, PipelineStatus.RDCO_INTAKE,
                    requested_ierc=True, requested_ktto=True,
                )
                self.assert_refused_without_effect(
                    record, self.rdco, PipelineStatus.RDCO_INTAKE
                )
                self.assertFalse(
                    RecordClearance.objects.filter(record=record).exists(),
                    "a refused intake rejection still opened the clearance phase",
                )

    def test_an_office_cannot_reject_its_pending_clearance(self):
        cases = (
            (RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW, Office.ITSO),
            (RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW, Office.KTTO),
            (RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW, Office.IERC),
            (RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW, Office.KTTO),
        )
        for type_name, stage, office in cases:
            with self.subTest(stage=stage, office=office):
                # Rule change, IR-266: ITSO is requested only where the case parks
                # at `itso_review`. A Thesis requesting ITSO now enters it too,
                # so requesting it for the parallel-stage cases would park them
                # at the wrong stage.
                record = self.record_with_pending_clearances(
                    type_name,
                    requested_itso=stage == PipelineStatus.ITSO_REVIEW,
                    requested_ierc=True, requested_ktto=True,
                )
                self.assertEqual(record.pipeline_status, stage)
                self.assertEqual(
                    RecordClearance.objects.get(record=record, office=office).status,
                    ClearanceStatus.PENDING,
                )

                self.assert_refused_without_effect(record, self.offices[office], stage)

    # --- still allowed where ADR-021 keeps it ----------------------------------

    def test_rdco_can_reject_at_final_review(self):
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT):
            with self.subTest(record_type=type_name):
                record = self.make_record(type_name, PipelineStatus.RDCO_REVIEW)

                response = self.review(record, self.rdco, ReviewDecision.REJECTED)

                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED, response.data
                )
                self.assertEqual(self.status_of(record), PipelineStatus.REJECTED)

    def test_the_assigned_adviser_can_reject_a_proposal(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )

        response = self.review(record, self.adviser, ReviewDecision.REJECTED)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.REJECTED)

    def test_an_adviser_not_assigned_to_the_proposal_cannot_reject_it(self):
        """The decision belongs to the *assigned* Adviser, not the Adviser role."""
        other_adviser = _user("reject-other-adviser@cit.edu", RoleName.ADVISER)
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )

        self.assert_refused_without_effect(
            record, other_adviser, PipelineStatus.ADVISER_REVIEW
        )

    # --- what intake and the offices keep ---------------------------------------

    def test_intake_can_still_accept_or_request_revision(self):
        for decision, expected in (
            (ReviewDecision.APPROVED, PipelineStatus.RDCO_REVIEW),
            (ReviewDecision.DECLINED, PipelineStatus.DECLINED),
        ):
            with self.subTest(decision=decision):
                record = self.make_record(
                    RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE
                )

                response = self.review(record, self.rdco, decision)

                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED, response.data
                )
                self.assertEqual(self.status_of(record), expected)

    def test_an_office_can_still_clear_or_request_revision(self):
        for decision, expected_clearance in (
            (ReviewDecision.APPROVED, ClearanceStatus.CLEARED),
            (ReviewDecision.DECLINED, ClearanceStatus.DECLINED),
        ):
            with self.subTest(decision=decision):
                record = self.record_with_pending_clearances(
                    RecordTypeName.THESIS_RESEARCH,
                    requested_ierc=True, requested_ktto=True,
                )

                response = self.review(record, self.offices[Office.IERC], decision)

                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED, response.data
                )
                self.assertEqual(
                    RecordClearance.objects.get(record=record, office=Office.IERC).status,
                    expected_clearance,
                )
