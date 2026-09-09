"""
The two experimental arms of ADR-004, asserted against each other (IR-137).

**Why this file exists at all.** ADR-003's contribution is clearance-aware
resubmission; ADR-004 says that counting preserved clearances cannot produce a
negative result, so the claim is only testable against IRIS running the *other*
policy. These tests are the evidence that the other policy exists and differs in
exactly one way.

**Why it is separate from `test_workflow_characterisation.py`.** That suite is
IR-197's pre-IR-136 behavioural baseline and its scope note reserves
`RESTART_ALL` for this ticket. It is evidence precisely because it did not
change across the refactor, so it is not edited here — this file imports its
base class and adds cases beside it.

The drivers are HTTP, for the same reason the characterisation suite gives: a
test coupled to `resubmit_record`'s signature stops being evidence the moment
the signature moves.
"""

from django.test import override_settings

from apps.records import lifecycle
from apps.reviews import clearance_state
from apps.reviews.models import RecordClearance
from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
)

from .test_workflow_characterisation import WorkflowCharacterisationBase

#: The evaluation instance's setting, as ADR-004 describes it: one key in the
#: same `WORKFLOW_TABLE` override that reshapes stages and edges.
RESTART_ALL = {"RESUBMISSION_POLICY": lifecycle.ResubmissionPolicy.RESTART_ALL}


class ResubmissionPolicyBase(WorkflowCharacterisationBase):
    """Record factories for the one sequence both arms are measured on."""

    def _thesis_at_parallel_review(self):
        """IERC + KTTO clear concurrently; no ITSO stage exists for this type."""
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True,
            requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        return record

    def _project_at_itso_review(self):
        """A Project requesting all three: its route starts at `itso_review`."""
        record = self.make_record(
            RecordTypeName.PROJECT,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_itso=True,
            requested_ierc=True,
            requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        return record

    def _one_office_declines_after_a_peer_cleared(self, record):
        """The sequence the experiment measures: IERC clears, KTTO declines."""
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)


class ClearanceAwareArmTests(ResubmissionPolicyBase):
    """The production default. Unchanged behaviour, restated as the control arm."""

    def test_the_peer_office_keeps_its_status_reviewer_and_timestamp(self):
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)
        before = RecordClearance.objects.get(record=record, office=Office.IERC)
        reviewed_by, updated_at = before.reviewed_by_id, before.updated_at

        self.resubmit(record)

        after = RecordClearance.objects.get(record=record, office=Office.IERC)
        self.assertEqual(after.status, ClearanceStatus.CLEARED)
        self.assertEqual(
            (after.reviewed_by_id, after.updated_at),
            (reviewed_by, updated_at),
            "a preserved clearance must be untouched, not merely still cleared -- "
            "a rewritten timestamp would make `is_preserved` report it as fresh",
        )

    def test_only_the_declining_office_resets(self):
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        self.resubmit(record)

        self.assertEqual(
            self.clearances(record),
            {Office.IERC: ClearanceStatus.CLEARED, Office.KTTO: ClearanceStatus.PENDING},
        )


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class RestartAllArmTests(ResubmissionPolicyBase):
    """The comparison arm. Same sequence, every clearance reset."""

    def test_every_office_resets_to_pending(self):
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        self.resubmit(record)

        self.assertEqual(
            self.clearances(record),
            {Office.IERC: ClearanceStatus.PENDING, Office.KTTO: ClearanceStatus.PENDING},
            "restart-all resets the peer that had already cleared -- that repeated "
            "review is the cost the experiment measures",
        )

    def test_the_clearance_rows_are_reset_rather_than_deleted(self):
        """
        ADR-004 says *reset to pending*, not delete.

        Deleting would drop which offices this record engages, and the office set
        is ADR-018 data on the record rather than a function of its type. The
        record would then re-enter its clearance phase with a different set of
        offices than it left with, and the two arms would differ in more than the
        policy.
        """
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        self.resubmit(record)

        self.assertEqual(
            set(
                RecordClearance.objects.filter(record=record).values_list(
                    "office", flat=True
                )
            ),
            {Office.IERC, Office.KTTO},
        )

    def test_a_reset_row_stops_reporting_the_moment_it_cleared(self):
        """
        `.update()` bypasses `auto_now`, so `updated_at` has to be set by hand.

        Without that, a row reset to `pending` still carries the timestamp of the
        clearance it just lost, and `clearance_payload` publishes it as the
        office's decision time. Under this arm that is every row rather than one,
        so the stale timestamps would be a visible difference between the two
        arms that is not the policy — in an experiment measuring time-on-task.
        """
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)
        cleared_at = RecordClearance.objects.get(
            record=record, office=Office.IERC
        ).updated_at

        self.resubmit(record)

        after = RecordClearance.objects.get(record=record, office=Office.IERC)
        self.assertEqual(after.status, ClearanceStatus.PENDING)
        self.assertGreater(
            after.updated_at,
            cleared_at,
            "a row reset to pending still claims the time it was cleared",
        )

    def test_the_reviewer_and_comment_are_cleared_on_every_row(self):
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        self.resubmit(record)

        for clearance in RecordClearance.objects.filter(record=record):
            with self.subTest(office=clearance.office):
                self.assertIsNone(clearance.reviewed_by_id)
                self.assertEqual(clearance.comment, "")

    def test_the_record_re_enters_at_the_stage_its_offices_clear_at(self):
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        self.resubmit(record)

        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

    def test_a_project_restarts_at_the_first_clearance_stage_not_the_declining_one(self):
        """
        The difference restart-all actually makes to routing.

        ITSO cleared, then KTTO declined at `parallel_review`. Clearance-aware
        would route back to `parallel_review` and leave ITSO alone; restart-all
        sends the record back to `itso_review`, because ITSO must review again
        too. Landing at `parallel_review` here would leave a pending ITSO
        clearance at a stage that cannot clear it.
        """
        record = self._project_at_itso_review()
        self.review(record, self.itso, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)

        self.resubmit(record)

        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)
        self.assertEqual(
            RecordClearance.objects.filter(
                record=record, status=ClearanceStatus.PENDING
            ).count(),
            3,
        )

    def test_the_resubmission_names_the_arm_that_ran(self):
        """
        ADR-004: the arm must be recoverable from a run afterwards.

        That the `apps.*` logger is actually enabled to emit this is a separate
        assertion, in `test_lifecycle.py` — `assertLogs` here would pass even
        with logging switched off, so it proves the line's *content*, not that
        anyone would ever see it.
        """
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)

        with self.assertLogs("apps.reviews.services", level="INFO") as captured:
            self.resubmit(record)

        self.assertTrue(
            any(
                lifecycle.ResubmissionPolicy.RESTART_ALL.value in line
                for line in captured.output
            ),
            f"no log line named the active arm: {captured.output}",
        )

    def test_nothing_is_preserved_so_the_frontend_needs_no_policy_branch(self):
        """
        The payload shape is identical under both policies (IR-139, IR-141).

        `offices_preserved` is empty because a pending clearance is never
        preserved -- not because the serializer knows which policy is active. It
        does not, and `PreservationNotice` renders off an empty array rather than
        off a flag.
        """
        record = self._thesis_at_parallel_review()
        self._one_office_declines_after_a_peer_cleared(record)
        self.resubmit(record)
        record.refresh_from_db()

        payload = clearance_state.resubmission_payload(
            record,
            clearances=RecordClearance.objects.filter(record=record),
            latest_decline_stage=Office.KTTO,
        )

        self.assertEqual(payload["offices_preserved"], [])
        self.assertEqual(payload["declining_office"], Office.KTTO)


class SwitchIsOnTheClearanceBranchTests(ResubmissionPolicyBase):
    """
    The acceptance criterion that is easiest to get wrong and hardest to see.

    A decline at a *sequential* gate is a different case, not a different policy:
    it already restarts the whole route. If the policy switch had been put on
    that branch instead, the two arms would differ in how non-clearance declines
    behave as well, and the comparison would measure two changes at once.
    """

    def _thesis_declined_by_rdco_at_intake(self):
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True,
            requested_ktto=True,
        )
        self.review(record, self.rdco, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)
        return record

    def test_a_sequential_decline_behaves_identically_under_both_policies(self):
        under_default = self._thesis_declined_by_rdco_at_intake()
        self.resubmit(under_default)
        default_status = self.status_of(under_default)
        default_clearances = self.clearances(under_default)

        with override_settings(WORKFLOW_TABLE=RESTART_ALL):
            under_restart_all = self._thesis_declined_by_rdco_at_intake()
            self.resubmit(under_restart_all)
            restart_status = self.status_of(under_restart_all)
            restart_clearances = self.clearances(under_restart_all)

        self.assertEqual(default_status, restart_status)
        self.assertEqual(default_clearances, restart_clearances)
        self.assertEqual(
            default_status,
            PipelineStatus.RDCO_INTAKE,
            "a non-clearance decline restarts the route regardless of policy",
        )
