"""
Every declared review edge, walked twice -- once per resubmission policy (IR-140).

**What this adds that the two suites beside it do not.**

`test_workflow_characterisation.py` (IR-197) pins today's behaviour under the
production default and is deliberately frozen; its own scope note reserves
`RESTART_ALL` for this ticket. `test_resubmission_policy.py` (IR-137) proves the
comparison arm exists and differs in exactly one way, on one sequence. Neither
walks the whole transition space, and neither runs the *whole* suite under both
arms -- which is IR-140's acceptance criterion and the reason this file exists.

**The parametrisation.** `WorkflowMatrixMixin` holds every assertion and is not
itself a `TestCase`, so it is never collected on its own. Two concrete classes
mix it into the characterisation base -- one per arm -- and the arm is named in
the class name, so a failure says which policy it failed under before anyone
reads the traceback. **Exactly one test method's expectations depend on
`self.policy`** -- `test_resubmission_after_a_clearance_decline`, the central
assertion. One other method reads the policy, `test_the_configured_arm_is_actually_active`,
and it asserts only *which arm is running*, never an outcome. Keeping that count
at one is how "nothing else may differ between the two arms" stays structural
rather than a claim in prose: every other assertion in this file is written once
and must hold identically under both policies, so an arm that diverged anywhere
else would fail rather than be quietly accommodated.

**Expected destinations are written out, never read back from the table.**
`MATRIX` states where each cell lands. Deriving those from
`lifecycle.TRANSITIONS` would be a test of the table against itself: it would
pass for any table, including a wrong one. The table *is* read to enumerate
stages and their office groups -- `test_the_matrix_covers_every_declared_review_edge`
fails the build when an edge is added and left uncovered, and the parallel-stage
cases iterate `Stage.offices` rather than naming ITSO/IERC/KTTO. That is the
honest form of the ticket's "a fourth office needs no new test code": the suite
notices the office and exercises it, while what the office should *do* stays a
statement a person made.

**On "every type x stage x event".** The matrix walks each record type through
the stages its own route actually contains. Parking a Proposal at `rdco_intake`
to fill a cartesian grid would assert against a state the workflow never
produces, and a green test on an unreachable state is worse than no test --
it reads as coverage. One cell is off-route deliberately: `adviser_review` for a
non-Proposal, because `_resolve_after_adviser_review` has a live type-dependent
branch there that no route reaches.

**Seam: HTTP**, for IR-197's reason -- a test coupled to `approve_record`'s
signature stops being evidence the moment the signature moves.
"""

from dataclasses import dataclass

from django.test import override_settings
from rest_framework import status

from apps.records import lifecycle
from apps.records.lifecycle import ResubmissionPolicy, WorkflowEvent
from apps.records.models import Record
from apps.reviews.models import RecordClearance, Review
from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    ReviewStage,
    RoleName,
)

# Imported as a *module*, not as names. `pytest.ini` collects `*Tests`, and a
# `TestCase` bound as a module-level name in this file would be collected here
# as well as in its own module -- re-running all thirty-one of IR-197's cases
# under the default policy, silently, for no benefit. Qualifying them keeps each
# case running exactly where it is defined, and the subclasses below are then
# the only copies that run under the comparison arm.
from . import test_workflow_characterisation as characterisation
from .test_workflow_characterisation import WorkflowCharacterisationBase, make_user

#: The evaluation instance's setting, as ADR-004 describes it. Spelled out here
#: rather than imported from `test_resubmission_policy.py`: that file is IR-137's
#: evidence, and this suite should not break if it is reorganised.
RESTART_ALL = {"RESUBMISSION_POLICY": ResubmissionPolicy.RESTART_ALL}


@dataclass(frozen=True)
class Cell:
    """
    One (record type, stage, event) of the matrix and what it must produce.

    `actor` names an attribute on the test case rather than holding a user,
    because the users are built in `setUpTestData` and this table is built at
    import time. `expect_review_stage` is asserted alongside the pipeline move
    because a transition that lands the record correctly while writing the wrong
    audit row is a regression this suite has to catch -- IR-136 writes both.
    """

    record_type: str
    stage: str
    event: WorkflowEvent
    actor: str
    expect_status: str
    expect_review_stage: str
    note: str = ""

    @property
    def id(self) -> str:
        return f"{self.record_type}/{self.stage}/{self.event.value}/by-{self.actor}"


#: Cells whose destination is a literal edge or a type-dependent resolver, so the
#: outcome is a function of the cell alone. Parallel *approvals* are absent on
#: purpose: where they land depends on which peers have already cleared, so they
#: are stateful and get named tests below rather than a row that would need a
#: fourth key to say what else had happened by then.
MATRIX: tuple[Cell, ...] = (
    # --- Proposal: the adviser gate is its whole review route ---------------
    Cell(RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW,
         WorkflowEvent.APPROVE, "adviser",
         PipelineStatus.APPROVED, ReviewStage.ADVISER,
         "Proposals stop at `approved`, visible as ongoing research"),
    Cell(RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW,
         WorkflowEvent.DECLINE, "adviser",
         PipelineStatus.DECLINED, ReviewStage.ADVISER),
    Cell(RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW,
         WorkflowEvent.REJECT, "adviser",
         PipelineStatus.REJECTED, ReviewStage.ADVISER),

    # The off-route cell, included deliberately: `_resolve_after_adviser_review`
    # branches on record type and no route reaches this side of the branch.
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.ADVISER_REVIEW,
         WorkflowEvent.APPROVE, "adviser",
         PipelineStatus.PUBLISHED, ReviewStage.ADVISER,
         "the non-Proposal side of the adviser resolver"),

    # --- RDCO intake: shared by both non-Proposal routes --------------------
    # Approval here is ADR-018 conditional routing. A record requesting no
    # office is the canonical cell -- it skips the clearance phase rather than
    # entering one that would auto-clear. The requested-office variants are
    # IR-197's `ClearanceRoutingTests`, re-run under both arms at the bottom.
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.APPROVE, "rdco",
         PipelineStatus.RDCO_REVIEW, ReviewStage.RDCO_INTAKE,
         "no office requested, so the clearance phase is skipped"),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.DECLINE, "rdco",
         PipelineStatus.DECLINED, ReviewStage.RDCO_INTAKE),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.REJECT, "rdco",
         PipelineStatus.REJECTED, ReviewStage.RDCO_INTAKE),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.APPROVE, "rdco",
         PipelineStatus.RDCO_REVIEW, ReviewStage.RDCO_INTAKE),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.DECLINE, "rdco",
         PipelineStatus.DECLINED, ReviewStage.RDCO_INTAKE),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_INTAKE,
         WorkflowEvent.REJECT, "rdco",
         PipelineStatus.REJECTED, ReviewStage.RDCO_INTAKE),

    # --- RDCO final review --------------------------------------------------
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.APPROVE, "rdco",
         PipelineStatus.PUBLISHED, ReviewStage.RDCO),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.DECLINE, "rdco",
         PipelineStatus.DECLINED, ReviewStage.RDCO),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.REJECT, "rdco",
         PipelineStatus.REJECTED, ReviewStage.RDCO),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.APPROVE, "rdco",
         PipelineStatus.PUBLISHED, ReviewStage.RDCO),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.DECLINE, "rdco",
         PipelineStatus.DECLINED, ReviewStage.RDCO),
    Cell(RecordTypeName.PROJECT, PipelineStatus.RDCO_REVIEW,
         WorkflowEvent.REJECT, "rdco",
         PipelineStatus.REJECTED, ReviewStage.RDCO),

    # --- Clearance stages: decline and reject are literal edges -------------
    # A `Review` at a parallel stage records the acting *office*, not a gate
    # name -- `Review.stage` is a union (ADR-002 amendment, point 5).
    Cell(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW,
         WorkflowEvent.DECLINE, "itso",
         PipelineStatus.DECLINED, Office.ITSO),
    Cell(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW,
         WorkflowEvent.REJECT, "itso",
         PipelineStatus.REJECTED, Office.ITSO),
    Cell(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW,
         WorkflowEvent.DECLINE, "ktto",
         PipelineStatus.DECLINED, Office.KTTO,
         "KTTO starts in parallel with ITSO, so it acts at this stage too"),
    Cell(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW,
         WorkflowEvent.REJECT, "ktto",
         PipelineStatus.REJECTED, Office.KTTO),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW,
         WorkflowEvent.DECLINE, "ierc",
         PipelineStatus.DECLINED, Office.IERC),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW,
         WorkflowEvent.REJECT, "ierc",
         PipelineStatus.REJECTED, Office.IERC),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW,
         WorkflowEvent.DECLINE, "ktto",
         PipelineStatus.DECLINED, Office.KTTO),
    Cell(RecordTypeName.THESIS_RESEARCH, PipelineStatus.PARALLEL_REVIEW,
         WorkflowEvent.REJECT, "ktto",
         PipelineStatus.REJECTED, Office.KTTO),
)

#: The decision string each event carries over the wire.
EVENT_DECISION = {
    WorkflowEvent.APPROVE: ReviewDecision.APPROVED,
    WorkflowEvent.DECLINE: ReviewDecision.DECLINED,
    WorkflowEvent.REJECT: ReviewDecision.REJECTED,
}

def stateful_approval_cells(stages) -> set:
    """
    Parallel approvals, which `MATRIX` cannot express.

    Where a clearance approval lands depends on which peers have already
    cleared, so these are driven from the table by
    `test_every_office_the_table_declares_can_clear_its_own_stage` rather than
    stated as a row, and the completeness check counts them as covered.

    Takes `stages` rather than reading `lifecycle.STAGES` directly: the
    completeness check reads the *active* table through `load_table()`, and an
    instance overriding `STAGES` would otherwise have this set describe CIT-U's
    table while the other side of the comparison described the instance's --
    which would report a gap that is not there, or hide one that is.
    """
    return {
        (status, WorkflowEvent.APPROVE, office)
        for status, stage in stages.items()
        if stage.is_parallel
        for office in stage.offices
    }

def non_gate_statuses(stages) -> tuple:
    """
    Statuses where nothing is reviewed -- every status the table does not
    declare as a gate.

    Derived, so a status promoted into `STAGES` leaves this set on its own
    rather than being counted as both. Takes `stages` for the same reason
    `stateful_approval_cells` does: as a module constant it read
    `lifecycle.STAGES` once at import, which is the CIT-U default and not
    necessarily the table an overriding instance is running.
    """
    return tuple(s for s in PipelineStatus.values if s not in stages)


class WorkflowMatrixMixin:
    """
    Every assertion in this file. Mixed into a `TestCase` by the two arms below.

    Not a `TestCase` itself, deliberately: as a base class its tests would run a
    third time under whichever policy happened to be configured, and that run
    would be indistinguishable in the output from the arm it duplicated.
    """

    #: Set by each concrete class; `test_the_configured_arm_is_actually_active`
    #: is what stops this from being decoration.
    policy: ResubmissionPolicy = ResubmissionPolicy.CLEARANCE_AWARE

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # A second adviser, for the case that the *assigned* adviser is the only
        # one who may act -- `_can_review` tests `record.adviser_id`, not the role.
        cls.other_adviser = make_user("matrix-other-adviser@cit.edu", RoleName.ADVISER)

    # --- helpers ---------------------------------------------------------

    def actor_for(self, name):
        """
        The fixture user a `Cell.actor` or an `Office` value names.

        **This is where the "a fourth office needs no new test code" claim runs
        out, and it is recorded rather than left to be discovered.** It resolves
        by attribute name, which works for offices only because every `Office`
        value happens to equal a fixture attribute on the base class -- `itso`,
        `ierc`, `ktto`. A fourth office added to `STAGES` would be *enumerated*
        by the table-driven cases and by the completeness check, and would then
        fail here with `AttributeError` until someone adds the matching user. A
        loud failure naming the missing fixture is the intended behaviour; a
        silent skip would let the office look covered when it is not.
        """
        actor = getattr(self, name, None)
        if actor is None:
            raise AttributeError(
                f"no fixture user named {name!r} on this test case. An office or "
                f"actor named in the table needs a matching user in "
                f"`setUpTestData` before it can be exercised."
            )
        return actor

    def record_at(self, type_name, stage, **extra):
        """
        A record of `type_name` parked at `stage`.

        Sequential gates are set directly, as IR-197 does. A parallel stage is
        reached through its real route -- intake approval is what creates the
        clearance rows, and a record sitting at `itso_review` with no rows is a
        state the workflow cannot produce, so building one would test fiction.
        """
        if stage == PipelineStatus.ITSO_REVIEW:
            record = self.make_record(
                type_name, pipeline_status=PipelineStatus.RDCO_INTAKE,
                requested_itso=True, requested_ierc=True, requested_ktto=True,
                **extra,
            )
            self.review(record, self.rdco, ReviewDecision.APPROVED)
            record.refresh_from_db()
            self.assertEqual(record.pipeline_status, PipelineStatus.ITSO_REVIEW)
            return record

        if stage == PipelineStatus.PARALLEL_REVIEW:
            record = self.make_record(
                type_name, pipeline_status=PipelineStatus.RDCO_INTAKE,
                requested_ierc=True, requested_ktto=True, **extra,
            )
            self.review(record, self.rdco, ReviewDecision.APPROVED)
            record.refresh_from_db()
            self.assertEqual(record.pipeline_status, PipelineStatus.PARALLEL_REVIEW)
            return record

        if stage == PipelineStatus.ADVISER_REVIEW:
            extra.setdefault("adviser", self.adviser)

        return self.make_record(type_name, pipeline_status=stage, **extra)

    def latest_review(self, record):
        return Review.objects.filter(record=record).order_by("-created_at").first()

    def clearance_of(self, record, office):
        return RecordClearance.objects.get(record=record, office=office)

    def walk_intake(self, type_name, **requested):
        """Submit and clear intake, returning the record wherever that lands."""
        record = self.make_record(
            type_name, pipeline_status=PipelineStatus.RDCO_INTAKE, **requested
        )
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        record.refresh_from_db()
        return record

    # --- the arm is real --------------------------------------------------

    def test_the_configured_arm_is_actually_active(self):
        """
        Without this, the comparison arm can pass by being the control arm.

        `override_settings` on the class is the only thing selecting the policy.
        If it stopped applying -- renamed setting, a decorator dropped in a
        merge, a base class reordered -- every test below would still pass, both
        classes would run `CLEARANCE_AWARE`, and the suite would report that the
        two arms agree everywhere. That is the one failure this file cannot be
        allowed to have, so the arm is asserted before anything is measured.
        """
        self.assertIs(lifecycle.resubmission_policy(), self.policy)

    # --- the matrix -------------------------------------------------------

    def test_every_matrix_cell_lands_where_it_should(self):
        """
        The type x stage x event grid, one `subTest` per cell.

        Asserts three things, not one: where the record went, what the `Review`
        row recorded, and -- via `Review.stage` -- which party it was attributed
        to. IR-136 writes the status and the audit row from different places, so
        a cell that moves the record correctly while mis-attributing the review
        is exactly the regression a status-only assertion would wave through.
        """
        for cell in MATRIX:
            with self.subTest(cell=cell.id, note=cell.note):
                record = self.record_at(cell.record_type, cell.stage)
                actor = self.actor_for(cell.actor)

                response = self.review(
                    record, actor, EVENT_DECISION[cell.event], comment=cell.note
                )

                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED, response.data
                )
                self.assertEqual(self.status_of(record), cell.expect_status)

                review = self.latest_review(record)
                self.assertIsNotNone(review, "the transition wrote no Review row")
                self.assertEqual(review.stage, cell.expect_review_stage)
                self.assertEqual(review.status, EVENT_DECISION[cell.event])
                self.assertEqual(review.reviewed_by_id, actor.pk)

    def test_the_matrix_covers_every_declared_review_edge(self):
        """
        Coverage as a checked fact rather than a claim in a docstring.

        The acceptance criterion is "every type x stage x event is covered", and
        the only honest way to assert that is against the table's own edge set.
        Add a stage, or an event at an existing stage, and this fails until a
        cell exists for it.

        **Why the parallel stages are counted per office rather than per edge.**
        An earlier version of this check compared `(stage, event)` pairs alone,
        and a deliberate mutation exposed it: deleting the ITSO decline cell left
        it green, because KTTO's cell at the same stage carries the same pair.
        A clearance stage has one edge but several parties who may take it, and
        it is the *party* that varies -- so at a parallel stage the unit of
        coverage is `(stage, event, office)`. That is also what makes the
        ticket's "a fourth office needs no new test code" bite in the direction
        that matters: an office added to a group fails this test until it is
        exercised, rather than being silently absent from a green suite.
        """
        stages, transitions = lifecycle.load_table()

        declared = set()
        for (from_status, event) in transitions:
            if event not in lifecycle.REVIEW_EVENTS:
                continue
            stage = stages.get(from_status)
            if stage is not None and stage.is_parallel:
                declared |= {(from_status, event, office) for office in stage.offices}
            else:
                declared.add((from_status, event, None))

        covered = set()
        for cell in MATRIX:
            stage = stages.get(cell.stage)
            if stage is not None and stage.is_parallel:
                # At a parallel stage the actor's role *is* the office, and
                # `expect_review_stage` is that office -- asserted per cell in
                # `test_every_matrix_cell_lands_where_it_should`.
                covered.add((cell.stage, cell.event, cell.expect_review_stage))
            else:
                covered.add((cell.stage, cell.event, None))

        covered |= stateful_approval_cells(stages)

        self.assertEqual(
            declared - covered,
            set(),
            "declared review edges with no case in this suite",
        )
        self.assertEqual(
            covered - declared,
            set(),
            "cases asserting on edges the table does not declare",
        )

    def test_every_record_type_is_exercised(self):
        """The other axis of the grid: no type may be missing from the matrix."""
        self.assertEqual(
            {cell.record_type for cell in MATRIX},
            {
                RecordTypeName.PROPOSAL,
                RecordTypeName.THESIS_RESEARCH,
                RecordTypeName.PROJECT,
            },
        )

    # --- parallel clearance: partial, full, out of order -------------------

    def test_one_office_clearing_leaves_the_record_where_it_is(self):
        """Partial completion. The stage holds until every office has answered."""
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED)

        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(
            self.clearances(record),
            {Office.IERC: ClearanceStatus.CLEARED, Office.KTTO: ClearanceStatus.PENDING},
        )

    def test_the_last_office_clearing_advances_to_final_review(self):
        """Full completion, in the order the offices happen to be listed."""
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.APPROVED)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
        self.assertEqual(
            set(self.clearances(record).values()), {ClearanceStatus.CLEARED}
        )

    def test_the_offices_may_clear_in_either_order(self):
        """
        Out-of-order completion. Same two offices, both sequences, same end state.

        A parallel stage that only worked when its offices answered in the order
        the table lists them would not be parallel, and the difference would be
        invisible in any test that always drives them the same way round.
        """
        for order in ((self.ierc, self.ktto), (self.ktto, self.ierc)):
            with self.subTest(order=[u.email for u in order]):
                record = self.walk_intake(
                    RecordTypeName.THESIS_RESEARCH,
                    requested_ierc=True,
                    requested_ktto=True,
                )
                for officer in order:
                    self.review(record, officer, ReviewDecision.APPROVED)

                self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
                self.assertEqual(
                    self.clearances(record),
                    {
                        Office.IERC: ClearanceStatus.CLEARED,
                        Office.KTTO: ClearanceStatus.CLEARED,
                    },
                )

    def test_ktto_may_clear_before_itso_at_the_itso_stage(self):
        """
        The out-of-order case that is easy to get wrong, because it crosses stages.

        KTTO's group membership spans `itso_review` and `parallel_review`. Clearing
        it first must not advance the record past ITSO, and must not strand it
        either: ITSO clearing afterwards still opens the parallel stage.
        """
        record = self.record_at(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW)

        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.assertEqual(
            self.status_of(record),
            PipelineStatus.ITSO_REVIEW,
            "KTTO clearing first must not carry the record past ITSO",
        )

        self.review(record, self.itso, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(
            self.clearances(record),
            {
                Office.ITSO: ClearanceStatus.CLEARED,
                Office.KTTO: ClearanceStatus.CLEARED,
                Office.IERC: ClearanceStatus.PENDING,
            },
        )

    def test_every_office_the_table_declares_can_clear_its_own_stage(self):
        """
        Driven off `STAGES`, so a fourth office is exercised without new code.

        This is the one place the ticket's SaaS criterion can be honoured
        literally: which offices exist is the table's to say, and the assertion
        -- that an office can clear at a stage its group contains -- holds for
        any office the table adds. Its limit is recorded on `actor_for`.

        **The destination is asserted here too, not only the clearance row.**
        These cells are what the completeness check credits for the parallel
        `APPROVE` edges, and an earlier version asserted only that the office's
        row went to `cleared` -- which would have held even if the record had
        jumped to `published`, leaving the edge counted as covered while nothing
        checked where it led. The rule asserted is the one `after_clearance`
        implements: a record advances to `rdco_review` exactly when no clearance
        is left pending, and otherwise stays where the route puts it. Stated as
        a consequence of the *observed* pending set rather than as a literal,
        because which offices remain differs per stage -- the fixed
        stage-by-stage destinations are pinned separately, and literally, by
        `test_ktto_may_clear_before_itso_at_the_itso_stage` and the two
        completion tests above.
        """
        stages, _ = lifecycle.load_table()
        for stage, declared in stages.items():
            if not declared.is_parallel:
                continue
            for office in declared.offices:
                with self.subTest(stage=stage, office=office):
                    record = self.record_at(
                        RecordTypeName.PROJECT
                        if stage == PipelineStatus.ITSO_REVIEW
                        else RecordTypeName.THESIS_RESEARCH,
                        stage,
                    )
                    officer = self.actor_for(office)

                    response = self.review(record, officer, ReviewDecision.APPROVED)

                    self.assertEqual(
                        response.status_code, status.HTTP_201_CREATED, response.data
                    )
                    self.assertEqual(
                        self.clearance_of(record, office).status,
                        ClearanceStatus.CLEARED,
                    )
                    self.assertEqual(self.latest_review(record).stage, office)

                    still_pending = set(
                        RecordClearance.objects.filter(
                            record=record, status=ClearanceStatus.PENDING
                        ).values_list("office", flat=True)
                    )
                    landed = self.status_of(record)
                    if still_pending:
                        self.assertIn(
                            landed,
                            set(stages),
                            f"cleared with {sorted(still_pending)} still pending, "
                            f"but the record left the clearance phase for {landed!r}",
                        )
                        self.assertTrue(
                            still_pending & set(stages[landed].offices),
                            f"record moved to {landed!r}, whose offices "
                            f"{stages[landed].offices} cannot clear the pending "
                            f"{sorted(still_pending)}",
                        )
                    else:
                        self.assertEqual(landed, PipelineStatus.RDCO_REVIEW)

    def test_a_clearance_is_recorded_against_its_own_office_only(self):
        """One office acting must not move another office's row."""
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED, comment="Ethics fine.")

        ktto_row = self.clearance_of(record, Office.KTTO)
        self.assertEqual(ktto_row.status, ClearanceStatus.PENDING)
        self.assertIsNone(ktto_row.reviewed_by_id)
        self.assertEqual(ktto_row.comment, "")

    # --- invalid transitions ---------------------------------------------

    def test_no_role_can_review_at_a_status_that_is_not_a_gate(self):
        """
        Refused, not silently ignored -- the distinction the criterion is about.

        A no-op answering 200 and leaving the record alone would satisfy a
        status-only assertion, so all three halves are checked: the call fails
        with 400, the record did not move, *and* no `Review` row was written.
        Driven over every non-gate status the enum has, so a new terminal state
        is covered the day it is added.

        **What this does and does not prove -- read before strengthening it.**
        Every actor is tried, so the claim is that *nobody* can drive one of
        these, which is the behaviour the acceptance criterion is about. It is
        deliberately not a claim about *which layer* refuses: at this seam a view
        guard always runs first (`_can_review` in `reviews/services.py`, the
        status precondition in `records/views.py::complete`), and it raises the
        same `InvalidPipelineTransition` the table would, so both arrive as an
        identical 400. The table's refusal is therefore **not independently
        observable through the API** -- it is defence in depth behind the view
        guards, and it is asserted in isolation by
        `apps/records/test_lifecycle.py::ApplyRefusalTests`, at the seam where it
        is actually reachable. Saying that plainly here is the point: an earlier
        version of this docstring claimed the table was being exercised, which
        would have been evidence for something this test cannot see.

        **Two layers refuse, and the expected code says which.** The owner is a
        Student and `ReviewViewSet` is gated by `IsReviewer`, so their request is
        refused by the permission class with **403** and never reaches the
        workflow -- a stronger refusal than the reviewing roles get, not a weaker
        one. Every reviewing role is admitted to the endpoint and refused with
        **400** by `_can_review`. Asserting the exact code per role rather than
        "any 4xx" is deliberate: it pins which layer is doing the work, so a
        change that moved the owner's refusal from the permission class into the
        service -- widening who can reach the workflow -- would fail here instead
        of passing as just another refusal.
        """
        actors = ("rdco", "adviser", "itso", "ierc", "ktto", "owner")
        stages, _ = lifecycle.load_table()
        for from_status in non_gate_statuses(stages):
            for event in (WorkflowEvent.APPROVE, WorkflowEvent.DECLINE, WorkflowEvent.REJECT):
                for actor in actors:
                    with self.subTest(
                        from_status=from_status, event=event.value, actor=actor
                    ):
                        record = self.make_record(
                            RecordTypeName.THESIS_RESEARCH,
                            pipeline_status=from_status,
                            adviser=self.adviser,
                        )
                        response = self.review(
                            record, self.actor_for(actor), EVENT_DECISION[event]
                        )

                        expected = (
                            status.HTTP_403_FORBIDDEN
                            if actor == "owner"
                            else status.HTTP_400_BAD_REQUEST
                        )
                        self.assertEqual(
                            response.status_code,
                            expected,
                            f"{actor} drove {event.value} at {from_status}: "
                            f"{response.data}",
                        )
                        self.assertEqual(self.status_of(record), from_status)
                        self.assertFalse(
                            Review.objects.filter(record=record).exists(),
                            "a refused transition still wrote a Review row",
                        )

    def test_the_refusal_says_what_was_wrong(self):
        """
        A 400 with an empty body is a refusal nobody can act on.

        `InvalidPipelineTransition`'s message is what the reviewer UI shows, so
        it is part of the contract rather than a debugging aid.
        """
        record = self.make_record(
            RecordTypeName.THESIS_RESEARCH, pipeline_status=PipelineStatus.PUBLISHED
        )
        response = self.review(record, self.rdco, ReviewDecision.APPROVED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(str(response.data.get("detail", "")).strip())

    def test_a_rejection_is_terminal_under_every_route(self):
        """
        Nothing continues out of `rejected` -- that is the whole difference from
        `declined`, and ADR-003's contribution is defined against it.
        """
        for type_name in (
            RecordTypeName.PROPOSAL,
            RecordTypeName.THESIS_RESEARCH,
            RecordTypeName.PROJECT,
        ):
            with self.subTest(record_type=type_name):
                record = self.make_record(
                    type_name, pipeline_status=PipelineStatus.REJECTED
                )
                self.assertEqual(
                    self.resubmit(record).status_code, status.HTTP_400_BAD_REQUEST
                )
                self.assertEqual(
                    self.review(record, self.rdco, ReviewDecision.APPROVED).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(self.status_of(record), PipelineStatus.REJECTED)

    def test_resubmission_is_refused_from_every_status_but_declined(self):
        for from_status in PipelineStatus.values:
            if from_status == PipelineStatus.DECLINED:
                continue
            with self.subTest(from_status=from_status):
                record = self.make_record(
                    RecordTypeName.THESIS_RESEARCH, pipeline_status=from_status
                )
                response = self.resubmit(record)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(self.status_of(record), from_status)

    # --- a reviewer cannot act at a stage they do not own ------------------

    def test_an_office_cannot_clear_at_a_stage_its_group_excludes(self):
        """
        IERC has a pending row while the record sits at `itso_review` -- intake
        creates every requested office's row at once -- so the row alone is not
        standing. IERC's gate is `parallel_review`, and acting early must fail.

        This is the office separation the thesis contribution rests on: if any
        office with a pending row could answer at any clearance stage, "parallel
        multi-office clearance" would be one queue with three names.
        """
        record = self.record_at(RecordTypeName.PROJECT, PipelineStatus.ITSO_REVIEW)
        self.assertEqual(
            self.clearance_of(record, Office.IERC).status, ClearanceStatus.PENDING
        )

        response = self.review(record, self.ierc, ReviewDecision.APPROVED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(
            self.clearance_of(record, Office.IERC).status, ClearanceStatus.PENDING
        )
        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)

    def test_an_office_cannot_act_at_a_sequential_gate(self):
        """
        The IR-165 regression, pinned at the HTTP seam.

        `accounts/0005` sets `is_staff=True` on every office role, so a Django
        staff bypass here meant ITSO, IERC and KTTO could approve or reject at
        the adviser and RDCO gates their office has no standing at.
        """
        for gate, type_name in (
            (PipelineStatus.RDCO_INTAKE, RecordTypeName.THESIS_RESEARCH),
            (PipelineStatus.RDCO_REVIEW, RecordTypeName.THESIS_RESEARCH),
            (PipelineStatus.ADVISER_REVIEW, RecordTypeName.PROPOSAL),
        ):
            for office in (self.itso, self.ierc, self.ktto):
                with self.subTest(gate=gate, officer=office.email):
                    record = self.record_at(type_name, gate)
                    response = self.review(record, office, ReviewDecision.APPROVED)

                    self.assertEqual(
                        response.status_code,
                        status.HTTP_400_BAD_REQUEST,
                        f"{office.email} acted at {gate}: {response.data}",
                    )
                    self.assertEqual(self.status_of(record), gate)

    def test_only_the_assigned_adviser_may_review_a_proposal(self):
        """
        `_can_review` tests `record.adviser_id`, not the Adviser role -- a
        per-record condition, which is why the transition table cannot express
        it and authorization stays outside the table (ADR-002's module note).
        """
        record = self.make_record(
            RecordTypeName.PROPOSAL,
            pipeline_status=PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )
        response = self.review(record, self.other_adviser, ReviewDecision.APPROVED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.ADVISER_REVIEW)

    def test_an_adviser_cannot_act_at_an_rdco_gate(self):
        for gate in (PipelineStatus.RDCO_INTAKE, PipelineStatus.RDCO_REVIEW):
            with self.subTest(gate=gate):
                record = self.make_record(
                    RecordTypeName.THESIS_RESEARCH, pipeline_status=gate
                )
                response = self.review(record, self.adviser, ReviewDecision.APPROVED)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(self.status_of(record), gate)

    # --- the two arms -----------------------------------------------------

    def test_resubmission_after_a_clearance_decline(self):
        """
        **The central assertion, and the only test here that knows which arm it
        is running under.**

        One office clears, a peer declines, the owner revises and resubmits.
        Under `CLEARANCE_AWARE` the cleared office keeps its status, its reviewer
        and its timestamp -- untouched, not merely still cleared, because a
        rewritten timestamp would make `clearance_state` publish preserved work
        as fresh. Under `RESTART_ALL` every office is pending again, and that
        repeated review is the cost the experiment measures.

        The expectation is a lookup rather than an `if`, so both arms are stated
        side by side and neither can be edited without the other being read.
        """
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED, comment="Ethics fine.")
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)

        before = self.clearance_of(record, Office.IERC)
        was = (before.status, before.reviewed_by_id, before.updated_at)

        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        expected = {
            ResubmissionPolicy.CLEARANCE_AWARE: {
                Office.IERC: ClearanceStatus.CLEARED,
                Office.KTTO: ClearanceStatus.PENDING,
            },
            ResubmissionPolicy.RESTART_ALL: {
                Office.IERC: ClearanceStatus.PENDING,
                Office.KTTO: ClearanceStatus.PENDING,
            },
        }[self.policy]
        self.assertEqual(self.clearances(record), expected)

        after = self.clearance_of(record, Office.IERC)
        now = (after.status, after.reviewed_by_id, after.updated_at)
        if self.policy is ResubmissionPolicy.CLEARANCE_AWARE:
            self.assertEqual(
                now,
                was,
                "the peer's clearance must be untouched -- status, reviewer and "
                "timestamp -- not merely still cleared",
            )
        else:
            self.assertIsNone(after.reviewed_by_id)
            self.assertEqual(after.comment, "")
            self.assertGreater(
                after.updated_at,
                was[2],
                "a row reset to pending still claims the moment it cleared",
            )

        # Both arms re-enter the clearance phase, and both re-enter it with the
        # office set the record left with. Asserted here rather than in a
        # separate test because "where it lands" is the other half of what the
        # policy decides, and splitting them would let one arm change alone.
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(
            set(self.clearances(record)),
            {Office.IERC, Office.KTTO},
            "resetting must not change which offices the record engages",
        )

    def test_a_full_route_is_identical_under_both_arms(self):
        """
        The negative half of "nothing else may differ".

        A route walked without a decline never resubmits, so the policy has
        nothing to act on and every observable must match the other arm exactly.
        The expected values are literals rather than a comparison against a run
        under the other policy: a test that diffs two live runs passes when both
        are wrong in the same way, which is precisely the failure that would
        invalidate the comparison the thesis rests on.
        """
        record = self.walk_intake(
            RecordTypeName.PROJECT,
            requested_itso=True,
            requested_ierc=True,
            requested_ktto=True,
        )
        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)

        self.review(record, self.itso, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)

        self.review(record, self.ktto, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)

        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.assertEqual(self.status_of(record), PipelineStatus.PUBLISHED)

        self.assertEqual(
            self.clearances(record),
            {
                Office.ITSO: ClearanceStatus.CLEARED,
                Office.IERC: ClearanceStatus.CLEARED,
                Office.KTTO: ClearanceStatus.CLEARED,
            },
        )
        self.assertEqual(
            list(
                Review.objects.filter(record=record)
                .order_by("created_at")
                .values_list("stage", flat=True)
            ),
            [
                ReviewStage.RDCO_INTAKE,
                Office.ITSO,
                Office.IERC,
                Office.KTTO,
                ReviewStage.RDCO,
            ],
        )

    def test_a_sequential_decline_restarts_the_route_under_both_arms(self):
        """
        The switch sits on the clearance branch only (IR-137).

        If it had been put on the sequential branch as well, the two arms would
        differ in how ordinary declines behave and the comparison would measure
        two changes at once. Stated as literals here for the same reason as
        above -- this must hold in both arms, not merely agree between them.
        """
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED)

        Record.objects.filter(pk=record.pk).update(
            pipeline_status=PipelineStatus.RDCO_REVIEW
        )
        self.review(record, self.rdco, ReviewDecision.DECLINED, comment="Start again.")
        self.add_upload_after_decline(record)

        self.assertEqual(self.resubmit(record).status_code, status.HTTP_200_OK)
        self.assertEqual(self.clearances(record), {})
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)

    def test_resubmission_bookkeeping_is_the_same_in_both_arms(self):
        """
        IR-139's counters are not policy-dependent, and must not become so:
        `preserved` is defined against `last_resubmitted_at`, so an arm that
        recorded it differently would move the definition of the thing being
        compared.
        """
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)
        self.resubmit(record)

        record.refresh_from_db()
        self.assertEqual(record.resubmission_count, 1)
        self.assertIsNotNone(record.last_resubmitted_at)

    def test_the_declining_office_is_pending_again_in_both_arms(self):
        """
        The half of the outcome the two arms agree on.

        Whatever happens to the peers, the office that asked for a revision must
        be waiting to see it. An arm that left the declining office `declined`
        would strand the record at a stage that cannot clear.
        """
        record = self.walk_intake(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)

        self.resubmit(record)

        self.assertEqual(
            self.clearance_of(record, Office.KTTO).status, ClearanceStatus.PENDING
        )


class ClearanceAwareMatrixTests(WorkflowMatrixMixin, WorkflowCharacterisationBase):
    """The production default (ADR-003). The control arm."""

    policy = ResubmissionPolicy.CLEARANCE_AWARE


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class RestartAllMatrixTests(WorkflowMatrixMixin, WorkflowCharacterisationBase):
    """The evaluation instance's arm (ADR-004). Same assertions, one differs."""

    policy = ResubmissionPolicy.RESTART_ALL


# ---------------------------------------------------------------------------
# IR-197's characterisation suite, re-executed under the comparison arm.
#
# This is the acceptance criterion "the full suite passes under CLEARANCE_AWARE
# **and** RESTART_ALL", and subclassing is how it is met without editing a file
# whose value comes entirely from being left alone. Every class below is a bare
# subclass -- the cases run unmodified against the other policy.
#
# `ClearanceAwareResubmissionTests` is the one exception, and the exception is
# the finding: exactly one of IR-197's thirty cases is policy-dependent, and it
# is the one that carries ADR-003's contribution. Its override states the
# `RESTART_ALL` expectation rather than relaxing the assertion, which is what
# the ticket asks for -- "if a test only passes under one policy, that is a
# finding about the implementation, not a test to relax". Here it is neither: it
# is the intended difference, named in one place.
# ---------------------------------------------------------------------------


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class SubmissionRoutingUnderRestartAllTests(characterisation.SubmissionRoutingTests):
    """Type-differentiated entry does not depend on the resubmission policy."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class SequentialReviewUnderRestartAllTests(characterisation.SequentialReviewTests):
    """The sequential gates do not depend on the resubmission policy."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class ClearanceRoutingUnderRestartAllTests(characterisation.ClearanceRoutingTests):
    """ADR-018 conditional routing does not depend on the resubmission policy."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class RecordsAppTransitionsUnderRestartAllTests(characterisation.RecordsAppTransitionTests):
    """The record-owned edges do not depend on the resubmission policy."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class LegacyImportUnderRestartAllTests(characterisation.LegacyImportTests):
    """The Excel bypass does not depend on the resubmission policy."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class RouteWalkthroughsUnderRestartAllTests(characterisation.ProposalRouteEndToEndTests):
    """All three routes, walked end to end under the comparison arm."""


@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class ResubmissionUnderRestartAllTests(characterisation.ClearanceAwareResubmissionTests):
    """
    IR-197's resubmission cases under the comparison arm.

    Four of the five run unchanged. The fifth is overridden below because it is
    the contribution itself, and the two arms are *supposed* to disagree there.
    """

    def test_resubmission_after_an_office_decline_preserves_the_other_office(self):
        """
        The one case that differs, restated for this arm.

        IR-197 asserts the peer's clearance survives. Under `RESTART_ALL` it does
        not -- every office is pending and the record re-enters the phase with
        the same office set it left. The method keeps its original name so the
        pairing is visible in the output: the same case, both arms, adjacent in
        an alphabetical test list.
        """
        record = self._record_at_parallel_review()
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.add_upload_after_decline(record)

        response = self.resubmit(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(
            self.clearances(record),
            {
                Office.IERC: ClearanceStatus.PENDING,  # reset, not preserved
                Office.KTTO: ClearanceStatus.PENDING,
            },
        )
        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
