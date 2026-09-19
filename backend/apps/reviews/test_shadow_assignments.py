"""
Shadow assignments, routing events and resubmission requests (IR-257).

IR-256 added the reviewer-directed routing tables beside the pipeline. This
ticket dual-writes them: every transition that moves a Record also writes who
holds it, where it was routed and what revision is outstanding. The pipeline
stays authoritative -- nothing reads these rows yet -- so the only thing to
prove is that the shadow is **accurate**, and accurate means one thing:
after every transition, the Record's active assignments equal the §6 mapping
of `docs/workflow_routing_architecture.md` for its status and clearances.

**The IR-140 matrix is the oracle.** Rather than restate a second set of
routes, `ShadowOracle` wraps the three HTTP drivers every matrix and
characterisation case uses (`submit_record`, `review`, `resubmit`) and checks
the shadow after each one: a transition that succeeded must leave the §6
mapping, one that was refused must leave every shadow row exactly as it was.
The whole matrix is then re-run with the oracle mixed in, under both
resubmission arms, so every cell and every stateful walk the matrix already
drives is checked -- including the ones added after this file.

**`section6_active` is written out from the document, never imported.** The
production code has its own reading of §6; importing it here would test the
mapping against itself and pass for any mapping, including a wrong one. The
named cases below pin a handful of transitions with literal party sets as well,
so the two readings are not the only witnesses to each other.

**Seam: HTTP** (IR-255's confirmed test seam), except where a failure has to be
forced from inside the transaction -- the one thing the API cannot reach.
"""

from unittest import mock

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.records.lifecycle import ResubmissionPolicy
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    RoutingEvent,
)
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ResubmissionRequestState,
    ReviewDecision,
)

# Modules, not names, for the reason `test_workflow_matrix.py` gives: a
# `*Tests` class bound as a module-level name is collected here too.
from . import test_workflow_characterisation as characterisation
from . import test_workflow_matrix as matrix
from .test_workflow_characterisation import WorkflowCharacterisationBase


# ---------------------------------------------------------------------------
# §6, restated from the document
# ---------------------------------------------------------------------------

#: `Review.stage` -> party (§6's preamble). `rdco_intake` is a stored stage, and
#: `intake` is the party it names.
_STAGE_TO_PARTY = {
    "adviser": "adviser",
    "rdco_intake": "intake",
    "rdco": "rdco",
    "itso": "itso",
    "ierc": "ierc",
    "ktto": "ktto",
}


def _offices_with(record, clearance_status) -> set:
    return set(
        RecordClearance.objects.filter(record=record, status=clearance_status)
        .values_list("office", flat=True)
    )


def declining_party(record):
    """The party of the last decline `Review`, which is who asked for changes."""
    stage = (
        Review.objects.filter(record=record, status=ReviewDecision.DECLINED)
        .order_by("-created_at", "-pk")
        .values_list("stage", flat=True)
        .first()
    )
    return _STAGE_TO_PARTY.get(stage)


def section6_active(record) -> set:
    """The "Active assignments" column of §6, for the record as it is now."""
    record.refresh_from_db()
    s = record.pipeline_status
    if s == PipelineStatus.ADVISER_REVIEW:
        return {"adviser"}
    if s == PipelineStatus.RDCO_INTAKE:
        return {"intake"}
    if s in (PipelineStatus.ITSO_REVIEW, PipelineStatus.PARALLEL_REVIEW):
        return _offices_with(record, ClearanceStatus.PENDING)
    if s == PipelineStatus.RDCO_REVIEW:
        return {"rdco"}
    if s == PipelineStatus.DECLINED:
        return {declining_party(record)} | _offices_with(record, ClearanceStatus.PENDING)
    # draft, and every terminal status: nobody holds it.
    return set()


def active_parties(record) -> set:
    return set(
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .values_list("party", flat=True)
    )


def shadow_rows() -> tuple:
    """Every shadow row, every column. A refused transition must not move any."""
    return (
        list(RecordAssignment.objects.order_by("pk").values_list()),
        list(RoutingEvent.objects.order_by("pk").values_list()),
        list(ResubmissionRequest.objects.order_by("pk").values_list()),
    )


class ShadowOracle:
    """
    Wraps the HTTP drivers so every transition a suite drives is checked.

    Not a `TestCase`; mixed in ahead of one. Only responses the drivers return
    are checked, so a suite that posts to an endpoint directly is unaffected
    -- which is also why this cannot silently turn a matrix case red for a
    reason that has nothing to do with the shadow.
    """

    def _checked(self, record, send):
        before = shadow_rows()
        response = send()
        if status.is_success(response.status_code):
            self.assert_shadow_matches_section6(record)
        else:
            self.assertEqual(
                shadow_rows(), before,
                f"a refused transition ({response.status_code}) wrote shadow rows",
            )
        return response

    def assert_shadow_matches_section6(self, record):
        expected = section6_active(record)
        self.assertEqual(
            active_parties(record), expected,
            f"active assignments at {record.pipeline_status!r} do not match §6",
        )
        open_requests = list(
            ResubmissionRequest.objects.filter(
                record=record, state=ResubmissionRequestState.OPEN
            ).values_list("party", flat=True)
        )
        if record.pipeline_status == PipelineStatus.DECLINED:
            self.assertEqual(open_requests, [declining_party(record)])
        else:
            self.assertEqual(open_requests, [])

    def submit_record(self, record, as_user=None):
        return self._checked(
            record, lambda: super(ShadowOracle, self).submit_record(record, as_user)
        )

    def review(self, record, as_user, decision, comment=""):
        return self._checked(
            record,
            lambda: super(ShadowOracle, self).review(record, as_user, decision, comment),
        )

    def resubmit(self, record, as_user=None):
        return self._checked(
            record, lambda: super(ShadowOracle, self).resubmit(record, as_user)
        )


# ---------------------------------------------------------------------------
# The matrix, re-run with the oracle, under both arms
# ---------------------------------------------------------------------------

class ClearanceAwareShadowMatrixTests(
    ShadowOracle, matrix.WorkflowMatrixMixin, WorkflowCharacterisationBase
):
    """Every IR-140 cell and walk, shadow checked, production arm."""

    policy = ResubmissionPolicy.CLEARANCE_AWARE


@override_settings(WORKFLOW_TABLE=matrix.RESTART_ALL)
class RestartAllShadowMatrixTests(
    ShadowOracle, matrix.WorkflowMatrixMixin, WorkflowCharacterisationBase
):
    """The same, under ADR-004's comparison arm."""

    policy = ResubmissionPolicy.RESTART_ALL


class ClearanceRoutingShadowTests(ShadowOracle, characterisation.ClearanceRoutingTests):
    """IR-197's clearance routing, for the requested-office variants."""


class ResubmissionShadowTests(
    ShadowOracle, characterisation.ClearanceAwareResubmissionTests
):
    """IR-197's resubmission cases, including the sequential restart."""


class RouteWalkthroughShadowTests(
    ShadowOracle, characterisation.ProposalRouteEndToEndTests
):
    """Draft to terminal, for each record type."""


# ---------------------------------------------------------------------------
# Named cases, with literal expectations
# ---------------------------------------------------------------------------

class ShadowRowsTests(WorkflowCharacterisationBase):
    """What each acceptance criterion says, stated once per criterion."""

    def submitted(self, type_name, **extra):
        record = self.make_record(type_name, **extra)
        response = self.submit_record(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return record

    def test_submitting_a_proposal_routes_it_from_the_owner_to_the_adviser(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)

        events = list(RoutingEvent.objects.filter(record=record))
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0].from_party, "the submitter, not a party, sent it")
        self.assertEqual(events[0].to_party, Party.ADVISER)
        self.assertEqual(events[0].actor_id, self.owner.pk)

        assignment = RecordAssignment.objects.get(record=record)
        self.assertEqual(assignment.party, Party.ADVISER)
        self.assertEqual(assignment.state, AssignmentState.ACTIVE)
        self.assertIsNone(assignment.opened_by_id, "opened by submission")

    def test_submitting_a_thesis_or_project_routes_it_to_intake(self):
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT):
            with self.subTest(type_name=type_name):
                record = self.submitted(type_name)
                self.assertEqual(
                    list(RoutingEvent.objects.filter(record=record)
                         .values_list("from_party", "to_party")),
                    [(None, Party.INTAKE)],
                )
                self.assertEqual(active_parties(record), {Party.INTAKE})

    def test_intake_routing_onward_is_one_decision_to_several_parties(self):
        record = self.submitted(
            RecordTypeName.PROJECT, requested_itso=True, requested_ktto=True
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)

        onward = list(RoutingEvent.objects.filter(record=record, from_party=Party.INTAKE))
        self.assertEqual({e.to_party for e in onward}, {Party.ITSO, Party.KTTO})
        self.assertEqual(len({e.group_id for e in onward}), 1)
        self.assertEqual(active_parties(record), {Party.ITSO, Party.KTTO})
        intake = RecordAssignment.objects.get(record=record, party=Party.INTAKE)
        self.assertEqual(intake.state, AssignmentState.COMPLETED)
        self.assertEqual(intake.closed_by_id, self.rdco.pk)

    def test_the_hand_back_to_rdco_is_not_a_route(self):
        """
        ADR-021 §10: when the last office finishes, IRIS opens RDCO's
        assignment. That is a hand-back, not a party's routing decision, so it
        writes no `RoutingEvent` and has no `opened_by`. Intake's decision is
        the only route here, to both offices at once: intake creates every
        requested office's clearance row, so IERC is pending -- and held --
        from the start (§6).
        """
        record = self.submitted(
            RecordTypeName.PROJECT, requested_itso=True, requested_ierc=True
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.itso, ReviewDecision.APPROVED)
        self.review(record, self.ierc, ReviewDecision.APPROVED)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
        self.assertEqual(
            list(RoutingEvent.objects.filter(record=record)
                 .order_by("created_at", "to_party")
                 .values_list("from_party", "to_party")),
            [(None, Party.INTAKE), (Party.INTAKE, Party.IERC), (Party.INTAKE, Party.ITSO)],
        )
        rdco = RecordAssignment.objects.get(record=record, party=Party.RDCO)
        self.assertIsNone(rdco.opened_by_id, "opened by IRIS, not a person")
        ierc = RecordAssignment.objects.get(record=record, party=Party.IERC)
        self.assertEqual(ierc.opened_by_id, self.rdco.pk, "routed by Intake's decision")

    def test_resubmitting_routes_nothing(self):
        """ADR-021 §11: resubmission resolves requests; it is not a new route."""
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.rdco, ReviewDecision.DECLINED)
        self.add_upload_after_decline(record)
        routed_before = RoutingEvent.objects.filter(record=record).count()

        self.resubmit(record)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)
        self.assertEqual(active_parties(record), {Party.INTAKE})
        self.assertEqual(
            RoutingEvent.objects.filter(record=record).count(), routed_before
        )

    def test_a_decline_at_intake_is_attributed_to_intake(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.review(record, self.rdco, ReviewDecision.DECLINED, comment="Missing abstract")

        decline = Review.objects.get(record=record, status=ReviewDecision.DECLINED)
        request = ResubmissionRequest.objects.get(record=record)
        self.assertEqual(request.state, ResubmissionRequestState.OPEN)
        self.assertEqual(request.party, Party.INTAKE)
        self.assertEqual(request.review_id, decline.pk)
        self.assertEqual(request.requested_by_id, self.rdco.pk)
        self.assertEqual(request.reason, "Missing abstract")
        self.assertEqual(request.assignment.party, Party.INTAKE)
        self.assertEqual(request.assignment.state, AssignmentState.ACTIVE)

    def test_an_office_decline_opens_one_request_for_that_office_only(self):
        record = self.submitted(
            RecordTypeName.PROJECT, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.review(record, self.ierc, ReviewDecision.DECLINED)

        self.assertEqual(
            list(ResubmissionRequest.objects.filter(record=record)
                 .values_list("party", "state")),
            [(Party.IERC, ResubmissionRequestState.OPEN)],
        )
        self.assertEqual(active_parties(record), {Party.IERC})
        ktto = RecordAssignment.objects.get(record=record, party=Party.KTTO)
        self.assertEqual(ktto.state, AssignmentState.COMPLETED)

    def test_resubmitting_resolves_the_request_and_keeps_it(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.review(record, self.rdco, ReviewDecision.DECLINED)
        self.add_upload_after_decline(record)

        response = self.resubmit(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request = ResubmissionRequest.objects.get(record=record)
        self.assertEqual(request.state, ResubmissionRequestState.RESUBMITTED)
        self.assertEqual(request.resolved_by_id, self.owner.pk)
        self.assertIsNotNone(request.resolved_at)

    def test_every_review_written_now_names_its_assignment(self):
        record = self.submitted(RecordTypeName.PROJECT, requested_ktto=True)
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.review(record, self.rdco, ReviewDecision.APPROVED)

        for review in Review.objects.filter(record=record):
            with self.subTest(stage=review.stage):
                self.assertIsNotNone(review.assignment_id)
                self.assertEqual(
                    review.assignment.party, _STAGE_TO_PARTY[review.stage]
                )
        self.assertEqual(active_parties(record), set())

    def test_a_refused_transition_writes_no_shadow_rows(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        before = shadow_rows()

        refused = self.review(record, self.rdco, ReviewDecision.REJECTED)

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(shadow_rows(), before)

    def test_a_transition_that_fails_midway_writes_nothing_at_all(self):
        """
        The shadow rows, the Review and the status move share one transaction.

        Forced from inside, after the assignments have been written: the
        routing events are the last thing a transition writes, so failing there
        proves the rows before it roll back with the pipeline move -- and the
        `Review` the service wrote before calling the table does too.
        """
        record = self.submitted(RecordTypeName.PROJECT, requested_ktto=True)
        before = shadow_rows()
        reviews_before = Review.objects.count()

        with mock.patch(
            "apps.reviews.shadow.RoutingEvent.objects.bulk_create",
            side_effect=RuntimeError("forced"),
        ):
            with self.assertRaises(RuntimeError):
                self.review(record, self.rdco, ReviewDecision.APPROVED)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)
        self.assertEqual(shadow_rows(), before)
        self.assertEqual(Review.objects.count(), reviews_before)
        self.assertFalse(RecordClearance.objects.filter(record=record).exists())

    def test_deleting_an_in_flight_record_withdraws_its_assignment(self):
        """`WITHDRAWN` is a close the party did not finish (AssignmentState)."""
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.client.force_authenticate(self.owner)

        response = self.client.delete(reverse("record-detail", args=[record.pk]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        intake = RecordAssignment.objects.get(record=record, party=Party.INTAKE)
        self.assertEqual(intake.state, AssignmentState.WITHDRAWN)
        self.assertEqual(intake.closed_by_id, self.owner.pk)
