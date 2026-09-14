"""
The pre-IR-136 workflow characterisation baseline (IR-197).

**Read this before changing anything in here.**

IR-136 rewrites the workflow into a declarative transition table (ADR-002, amended
2026-09-09). Its acceptance criterion is "the existing eleven transitions behave
identically to today", and this suite is the only thing that can make that claim
checkable. It was written *before* IR-136 started, deliberately, and its value comes
entirely from being left alone through it.

**So: if a test here fails during IR-136, that is the signal, not an inconvenience.**
Either behaviour changed — decide deliberately whether that was intended and say so
in the PR — or the test was coupled to an implementation detail and should never
have been written this way. Do not "update the expectation" to make a refactor green.
That is the one move this suite exists to prevent.

**This suite records what the workflow DOES, not what it should do.** Some of what is
pinned below is not behaviour anyone would design on purpose — the Excel importer
jumping straight to `published` is the clearest example. It is characterised because
IR-136 has to preserve it while making it a declared, auditable edge; whether it stays
*permitted* is a separate decision (see ADR-002's amendment). Where a test looks like
it is endorsing something odd, the docstring says so.

**Seam: HTTP only.** Every assertion goes through the API with `APITestCase`. Nothing
here imports from `apps.reviews.services` or touches a service function directly, even
though that would be faster and more precise, because IR-136 restructures exactly those
internals. A suite coupled to `approve_record`'s signature would need rewriting mid-
refactor, which destroys its worth as evidence. The one seam also reaches the seven
`records/views.py` transitions that a service-level suite cannot see at all — and those
include the unguarded ones.

Existing coverage this deliberately does not duplicate: `apps/reviews/tests.py` already
characterises ADR-018's conditional office routing at the service seam, and
`test_clearance_payload.py` covers the serialized payload shape. This suite is about the
*transitions*.

Scope note: `CLEARANCE_AWARE` resubmission only. The `RESTART_ALL` comparison belongs to
IR-140's remaining half, which is properly blocked on IR-137 (ADR-004).
"""

import importlib.util
from datetime import timedelta
from unittest import skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import RecordUpload, UploadSlot
from apps.records.models import DeleteRequest, Record, RecordOwner, RecordType
from apps.reviews.models import RecordClearance, Review
from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    RequestStatus,
    ReviewDecision,
    ReviewStage,
    RoleName,
)

PYEXCEL_AVAILABLE = importlib.util.find_spec("pyexcel") is not None

#: `parse_excel_import` swallows a missing pyexcel and returns an error list rather
#: than raising, so without this guard the import test would fail with "created no
#: record" and send the reader hunting for a workflow bug that isn't there.
#: `pyexcel-xls`/`pyexcel-xlsx` are in requirements/base.txt, so CI has them.
NEEDS_PYEXCEL = "requires pyexcel (requirements/base.txt); present in CI"

SUBMIT_REVIEW = "/api/v1/reviews/submit/"
RESUBMIT = "/api/v1/reviews/resubmit/"


def make_user(email, role_name):
    """
    Reference rows are seeded by migration with explicit primary keys, which leaves
    the Postgres sequence at 1 -- `Role.objects.create()` raises duplicate-key
    (IR-126). get_or_create reuses the seeded row.
    """
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class WorkflowCharacterisationBase(APITestCase):
    """Actors and record factories shared by every case below."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("char-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("char-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = make_user("char-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make_user("char-itso@cit.edu", RoleName.ITSO)
        cls.ierc = make_user("char-ierc@cit.edu", RoleName.IERC)
        cls.ktto = make_user("char-ktto@cit.edu", RoleName.KTTO)

    def record_type(self, name):
        rt = RecordType.objects.filter(name=name).first()
        self.assertIsNotNone(rt, f"RecordType {name!r} is not seeded -- migrations incomplete")
        return rt

    def make_record(self, type_name, pipeline_status=PipelineStatus.DRAFT, **extra):
        record = Record.objects.create(
            title=f"Characterisation {type_name}",
            abstract="A" * 40,
            record_type=self.record_type(type_name),
            added_by=self.owner,
            pipeline_status=pipeline_status,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    # --- drivers, all through HTTP -------------------------------------

    def submit_record(self, record, as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        # DPA consent is a precondition on submitting (IR-226), not a workflow
        # edge. This suite characterises routing, so it supplies consent and
        # goes on asserting about destinations; the consent gate itself is
        # covered in `apps.records.tests.DpaConsentAtSubmitTests`.
        return self.client.post(
            reverse("record-submit", args=[record.pk]),
            {"dpa_accepted": True},
            format="json",
        )

    def review(self, record, as_user, decision, comment=""):
        self.client.force_authenticate(as_user)
        return self.client.post(
            SUBMIT_REVIEW,
            {"record_id": record.pk, "status": decision, "comment": comment},
            format="json",
        )

    def resubmit(self, record, as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        return self.client.post(RESUBMIT, {"record_id": record.pk}, format="json")

    def status_of(self, record):
        record.refresh_from_db()
        return record.pipeline_status

    def clearances(self, record):
        """{office: status} -- the shape most assertions below care about."""
        return dict(
            RecordClearance.objects.filter(record=record).values_list("office", "status")
        )

    def add_upload_after_decline(self, record):
        """
        `resubmit_record` refuses unless a document was uploaded after the decline.
        Backdating is not an option -- the check compares against the decline's
        timestamp -- so this creates a genuinely later upload.
        """
        slot = UploadSlot.objects.create(
            name=f"Manuscript {record.pk}", record_type=record.record_type
        )
        upload = RecordUpload.objects.create(
            record=record, slot=slot,
            file=SimpleUploadedFile(f"revised-{record.pk}.pdf", b"%PDF-1.4 revised"),
            uploaded_by=self.owner,
        )
        RecordUpload.objects.filter(pk=upload.pk).update(
            created_at=timezone.now() + timedelta(seconds=5)
        )
        return upload


class SubmissionRoutingTests(WorkflowCharacterisationBase):
    """
    `POST /records/<id>/submit/` -- the type-differentiated entry point.

    This is the transition the thesis calls "type-differentiated routing", and it is
    currently a two-branch `if` in `records/views.py`.
    """

    def test_each_record_type_enters_its_own_first_stage(self):
        cases = [
            (RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW),
            (RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE),
            (RecordTypeName.PROJECT, PipelineStatus.RDCO_INTAKE),
        ]
        for type_name, expected in cases:
            with self.subTest(record_type=type_name):
                extra = {"adviser": self.adviser} if type_name == RecordTypeName.PROPOSAL else {}
                record = self.make_record(type_name, **extra)
                response = self.submit_record(record)
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(self.status_of(record), expected)

    def test_a_proposal_without_an_adviser_cannot_be_submitted(self):
        """Nobody could review it -- the Proposal route's only reviewer is the adviser."""
        record = self.make_record(RecordTypeName.PROPOSAL)
        response = self.submit_record(record)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.status_of(record), PipelineStatus.DRAFT)


class SequentialReviewTests(WorkflowCharacterisationBase):
    """
    `POST /reviews/submit/` at the sequential gates: adviser_review, rdco_intake,
    rdco_review. One endpoint, dispatching on the record's current stage.
    """

    def test_adviser_approval_moves_a_proposal_to_approved_not_published(self):
        """
        Proposals terminate at `approved` -- visible as ongoing research. Only the
        Thesis/Research and Project routes reach `published`.
        """
        record = self.make_record(
            RecordTypeName.PROPOSAL,
            pipeline_status=PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )
        response = self.review(record, self.adviser, ReviewDecision.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.APPROVED)

        review = Review.objects.get(record=record)
        self.assertEqual(review.stage, ReviewStage.ADVISER)
        self.assertEqual(review.status, ReviewDecision.APPROVED)

    def test_rdco_approval_at_final_review_publishes(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.RDCO_REVIEW
        )
        response = self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.PUBLISHED)
        self.assertEqual(Review.objects.get(record=record).stage, ReviewStage.RDCO)

    def test_a_decline_is_recoverable_and_a_rejection_is_terminal(self):
        """
        The distinction ADR-003 rests on: `declined` invites a resubmission,
        `rejected` does not. Both are pinned in one test so the pair cannot drift
        apart unnoticed.
        """
        cases = [
            (ReviewDecision.DECLINED, PipelineStatus.DECLINED),
            (ReviewDecision.REJECTED, PipelineStatus.REJECTED),
        ]
        for decision, expected in cases:
            with self.subTest(decision=decision):
                record = self.make_record(
                    RecordTypeName.THESIS_RESEARCH,
                    pipeline_status=PipelineStatus.RDCO_INTAKE,
                )
                response = self.review(record, self.rdco, decision, comment="Needs work.")
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(self.status_of(record), expected)

                review = Review.objects.get(record=record)
                self.assertEqual(review.stage, ReviewStage.RDCO_INTAKE)
                self.assertEqual(review.status, decision)

    def test_rejection_is_characterised_at_all_three_sequential_gates(self):
        """
        `reject_record` had no test calling it anywhere before IR-197. Walked at
        every sequential stage because the terminal path is the one nobody exercises
        by hand.
        """
        cases = [
            (RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW, self.adviser, ReviewStage.ADVISER),
            (RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE, self.rdco, ReviewStage.RDCO_INTAKE),
            (RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_REVIEW, self.rdco, ReviewStage.RDCO),
        ]
        for type_name, stage, actor, expected_stage in cases:
            with self.subTest(stage=stage):
                extra = {"adviser": self.adviser} if type_name == RecordTypeName.PROPOSAL else {}
                record = self.make_record(type_name, pipeline_status=stage, **extra)
                response = self.review(record, actor, ReviewDecision.REJECTED)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(self.status_of(record), PipelineStatus.REJECTED)
                self.assertEqual(Review.objects.get(record=record).stage, expected_stage)


class ClearanceRoutingTests(WorkflowCharacterisationBase):
    """
    RDCO intake approval creates the clearance set (ADR-018 -- conditional on what
    the submitter requested), and the office reviews that follow.
    """

    def test_intake_approval_creates_clearances_only_for_requested_offices(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        response = self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(
            self.clearances(record),
            {Office.IERC: ClearanceStatus.PENDING, Office.KTTO: ClearanceStatus.PENDING},
        )

    def test_a_record_requesting_no_offices_skips_the_clearance_stage(self):
        """A clearance stage with no office attached would just auto-clear (ADR-018)."""
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.RDCO_INTAKE
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
        self.assertEqual(self.clearances(record), {})

    def test_itso_is_structurally_project_only(self):
        """A Thesis/Research record requesting ITSO does not get an ITSO clearance."""
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_itso=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertNotIn(Office.ITSO, self.clearances(record))
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

    def test_a_project_requesting_itso_enters_the_itso_stage_first(self):
        record = self.make_record(
            RecordTypeName.PROJECT,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)

    def test_itso_clearing_opens_the_parallel_stage_and_creates_ierc(self):
        """IERC's row is created when ITSO clears, and only because it was requested."""
        record = self.make_record(
            RecordTypeName.PROJECT,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        response = self.review(record, self.itso, ReviewDecision.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(self.clearances(record)[Office.ITSO], ClearanceStatus.CLEARED)
        self.assertIn(Office.IERC, self.clearances(record))

    def test_the_clearance_review_is_recorded_against_the_acting_office(self):
        """
        `Review.stage` holds an *office* for a clearance review, resolved from the
        reviewer's role. This is the union that IR-136's `apply()` has to keep
        populating two different ways (ADR-002 amendment, point 5).
        """
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)

        clearance_review = Review.objects.get(record=record, stage=ReviewStage.KTTO)
        self.assertEqual(clearance_review.status, ReviewDecision.APPROVED)
        self.assertEqual(self.clearances(record)[Office.KTTO], ClearanceStatus.CLEARED)

    def test_one_office_clearing_leaves_the_others_pending(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)

        self.assertEqual(
            self.clearances(record),
            {Office.IERC: ClearanceStatus.PENDING, Office.KTTO: ClearanceStatus.CLEARED},
        )
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

    def test_the_last_office_clearing_advances_to_final_review(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.review(record, self.ierc, ReviewDecision.APPROVED)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)

    def test_an_office_decline_pauses_the_pipeline(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise the IP claim.")

        self.assertEqual(self.status_of(record), PipelineStatus.DECLINED)
        self.assertEqual(self.clearances(record)[Office.KTTO], ClearanceStatus.DECLINED)


class ClearanceAwareResubmissionTests(WorkflowCharacterisationBase):
    """
    **ADR-003's primary research contribution, characterised.**

    On resubmission the declining office's clearance resets and every other office's
    completed work is preserved. Today that turns on a set-membership test inside
    `resubmit_record`; IR-136 moves the decision into the transition table. These
    tests must survive that move untouched -- they assert the outcome, never the
    mechanism.
    """

    def _record_at_parallel_review(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        return record

    def test_resubmission_after_an_office_decline_preserves_the_other_office(self):
        """The contribution itself. If one test in this file matters, it is this one."""
        record = self._record_at_parallel_review()
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)

        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(
            self.clearances(record),
            {
                Office.IERC: ClearanceStatus.CLEARED,   # preserved
                Office.KTTO: ClearanceStatus.PENDING,   # reset
            },
        )
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

    def test_resubmission_after_a_sequential_decline_clears_every_clearance(self):
        """
        The other half of the rule: a decline at a sequential gate is a full restart,
        so no clearance survives and the record re-enters its route from the top.
        """
        record = self._record_at_parallel_review()
        self.review(record, self.ierc, ReviewDecision.APPROVED)

        # Force the record back to a sequential gate and decline there.
        Record.objects.filter(pk=record.pk).update(
            pipeline_status=PipelineStatus.RDCO_REVIEW
        )
        self.review(record, self.rdco, ReviewDecision.DECLINED, comment="Start again.")
        self.add_upload_after_decline(record)

        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(self.clearances(record), {})
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)

    def test_resubmission_requires_a_document_uploaded_after_the_decline(self):
        """Resubmitting is not a way to skip doing the revision."""
        record = self._record_at_parallel_review()
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")

        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.status_of(record), PipelineStatus.DECLINED)

    def test_only_a_declined_record_can_be_resubmitted(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.RDCO_INTAKE
        )
        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)

    def test_resubmission_records_its_own_history(self):
        """
        IR-139 added `resubmission_count` / `last_resubmitted_at` because `preserved`
        is defined against the resubmission timestamp, not the decline's. Pinned here
        so IR-136 cannot drop the bookkeeping while preserving the status move.
        """
        record = self._record_at_parallel_review()
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)
        self.resubmit(record)

        record.refresh_from_db()
        self.assertEqual(record.resubmission_count, 1)
        self.assertIsNotNone(record.last_resubmitted_at)


class RecordsAppTransitionTests(WorkflowCharacterisationBase):
    """
    The transitions that live outside `reviews/services.py` -- the seven IR-136 has to
    pull into the table. A service-seam suite cannot reach any of these.
    """

    def test_a_created_record_starts_as_a_draft(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse("record-list"),
            {
                "title": "A Newly Created Record",
                "abstract": "B" * 40,
                "record_type": self.record_type(RecordTypeName.THESIS_RESEARCH).pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            Record.objects.get(pk=response.data["id"]).pipeline_status,
            PipelineStatus.DRAFT,
        )

    def test_rdco_can_complete_an_approved_proposal(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL,
            pipeline_status=PipelineStatus.APPROVED,
            adviser=self.adviser,
        )
        self.client.force_authenticate(self.rdco)
        response = self.client.post(reverse("record-complete", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.COMPLETED)

    def test_completion_is_refused_off_the_proposal_route(self):
        cases = [
            ("wrong status", RecordTypeName.PROPOSAL, PipelineStatus.PUBLISHED),
            ("wrong type", RecordTypeName.THESIS_RESEARCH, PipelineStatus.APPROVED),
        ]
        for label, type_name, pipeline_status in cases:
            with self.subTest(case=label):
                record = self.make_record(type_name, pipeline_status=pipeline_status)
                self.client.force_authenticate(self.rdco)
                response = self.client.post(reverse("record-complete", args=[record.pk]))
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(self.status_of(record), pipeline_status)

    def test_deleting_a_draft_soft_deletes_it_immediately(self):
        """
        `soft_delete_record` writes **two** things -- `is_deleted` and a move to
        `pending_delete`. Both are asserted because IR-136 pulls the status write
        into the table while the flag stays where it is, so a refactor could easily
        preserve one and drop the other.
        """
        record = self.make_record(RecordTypeName.THESIS_RESEARCH)
        self.client.force_authenticate(self.owner)
        response = self.client.delete(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        record.refresh_from_db()
        self.assertTrue(record.is_deleted)
        self.assertEqual(record.pipeline_status, PipelineStatus.PENDING_DELETE)
        self.assertFalse(DeleteRequest.objects.filter(record=record).exists())

    def test_deleting_a_published_record_raises_a_delete_request(self):
        """Removal from the public catalogue is reviewed, not immediate."""
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.PUBLISHED
        )
        self.client.force_authenticate(self.owner)
        self.client.delete(reverse("record-detail", args=[record.pk]))

        self.assertEqual(self.status_of(record), PipelineStatus.PENDING_DELETE)
        request = DeleteRequest.objects.get(record=record)
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.previous_pipeline_status, PipelineStatus.PUBLISHED)

    def test_declining_a_delete_request_restores_the_previous_status(self):
        """A refused deletion must leave no trace on the record."""
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.PUBLISHED
        )
        self.client.force_authenticate(self.owner)
        self.client.delete(reverse("record-detail", args=[record.pk]))
        request = DeleteRequest.objects.get(record=record)

        self.client.force_authenticate(self.rdco)
        response = self.client.post(reverse("delete-request-decline", args=[request.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(self.status_of(record), PipelineStatus.PUBLISHED)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.DECLINED)

    def test_approving_a_delete_request_soft_deletes_the_record(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.PUBLISHED
        )
        self.client.force_authenticate(self.owner)
        self.client.delete(reverse("record-detail", args=[record.pk]))
        request = DeleteRequest.objects.get(record=record)

        self.client.force_authenticate(self.rdco)
        response = self.client.post(reverse("delete-request-approve", args=[request.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        record.refresh_from_db()
        self.assertTrue(record.is_deleted)


class LegacyImportTests(WorkflowCharacterisationBase):
    """
    The Excel importer, which creates records **straight at `published`**, bypassing
    the review pipeline entirely.

    Characterised, emphatically not endorsed. ADR-002 calls this "the Excel bypass"
    and says IR-136 turns it into "a declared, auditable edge" -- declared and
    visible, not removed. This test exists so that conversion is provably
    behaviour-preserving; whether the bypass stays *permitted* is a separate decision
    the ADR-002 amendment deliberately leaves open.
    """

    @staticmethod
    def _workbook_bytes(rows):
        import io

        import openpyxl

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["Title", "Abstract", "Record Type"])
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    @skipUnless(PYEXCEL_AVAILABLE, NEEDS_PYEXCEL)
    def test_imported_records_land_published_without_any_review(self):
        payload = self._workbook_bytes(
            [["An Imported Legacy Record", "C" * 40, RecordTypeName.PROJECT]]
        )
        self.client.force_authenticate(self.rdco)
        response = self.client.post(
            reverse("record-import-excel"),
            {"file": SimpleUploadedFile(
                "legacy.xlsx", payload,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        imported = Record.objects.filter(title="An Imported Legacy Record").first()
        self.assertIsNotNone(imported, "the importer created no record")
        self.assertEqual(
            imported.pipeline_status, PipelineStatus.PUBLISHED,
            "the legacy import no longer jumps straight to published -- if that was "
            "intended, say so in the PR; it is a behaviour change, not a refactor",
        )
        self.assertFalse(
            Review.objects.filter(record=imported).exists(),
            "an imported record acquired a Review row -- it bypasses review by design",
        )


class ProposalRouteEndToEndTests(WorkflowCharacterisationBase):
    """One walk of each route, so a break anywhere in the chain surfaces as a chain break."""

    def test_a_proposal_walks_draft_to_completed(self):
        record = self.make_record(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.assertEqual(self.status_of(record), PipelineStatus.DRAFT)

        self.submit_record(record)
        self.assertEqual(self.status_of(record), PipelineStatus.ADVISER_REVIEW)

        self.review(record, self.adviser, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.APPROVED)

        self.client.force_authenticate(self.rdco)
        self.client.post(reverse("record-complete", args=[record.pk]))
        self.assertEqual(self.status_of(record), PipelineStatus.COMPLETED)

    def test_a_thesis_walks_draft_to_published(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.submit_record(record)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)

        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)

        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PUBLISHED)

    def test_a_project_walks_draft_to_published_through_itso(self):
        """The longest route, and the only one with a sequential office gate."""
        record = self.make_record(
            RecordTypeName.PROJECT,
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        self.submit_record(record)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)

        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)

        self.review(record, self.itso, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)

        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PUBLISHED)
