"""
Tests for the transition table itself (IR-136, ADR-002 as amended 2026-09-09).

**Scope split, on purpose.** `apps/reviews/test_workflow_characterisation.py`
(IR-197) already asserts what the workflow *does*, end to end through HTTP, and
it passes unchanged against this refactor — that is the evidence for "the
existing transitions behave identically". Duplicating it here would add runtime
and no information.

What this file covers instead is the table's own structure and the guarantees
the ADR amendment makes about it: that the two structures agree with each other,
that the sequential/parallel split is declared once and derived everywhere, that
`apply()` refuses an undeclared edge, and that the settings override — the
ADR-005 configuration seam — actually takes effect. Those are properties of the
table, invisible to a behavioural test, and each one is something a later change
could silently break while every workflow test stayed green.
"""

from django.test import SimpleTestCase, TestCase, override_settings

from apps.records import lifecycle
from apps.records.lifecycle import (
    STAGES,
    TRANSITIONS,
    Edge,
    Stage,
    StageKind,
    WorkflowEvent,
)
from core.enums import Office, PipelineStatus, ReviewStage
from core.exceptions import InvalidPipelineTransition


class TableStructureTests(SimpleTestCase):
    """Pure: the table's internal consistency, no database."""

    def test_every_edge_declares_exactly_one_destination(self):
        """
        `Edge.__post_init__` enforces this, so the table cannot be constructed
        wrongly — this proves the guard is real rather than assumed.
        """
        for key, edge in TRANSITIONS.items():
            with self.subTest(edge=key):
                self.assertNotEqual(
                    bool(edge.to), bool(edge.resolver),
                    "an edge must have a literal destination or a resolver, never both",
                )

        with self.assertRaises(ValueError):
            Edge(decision="approved", to=PipelineStatus.PUBLISHED, resolver="after_clearance")
        with self.assertRaises(ValueError):
            Edge(decision="approved")

    def test_every_named_resolver_exists(self):
        """
        A typo in a resolver name would otherwise surface only when a user hit
        that exact transition in production.
        """
        for key, edge in TRANSITIONS.items():
            if edge.resolver:
                with self.subTest(edge=key):
                    self.assertIn(edge.resolver, lifecycle._RESOLVERS)

    def test_every_review_edge_starts_at_a_declared_stage(self):
        """
        A **review** edge out of a status with no `STAGES` entry would have no
        kind, so `apply()` could not tell a sequential gate from a parallel
        group, and nothing would say what `Review.stage` should hold.

        Only review events are covered, and that narrowing is the point. Stage 2
        added record-lifecycle edges — submit, complete, request-delete, soft
        delete, restore — that start at `draft`, `approved`, `pending_delete`
        and the published statuses. **Nothing is reviewed at any of those**, so
        they are correctly absent from `STAGES`.

        This test previously exempted only `RESUBMIT` and asserted the rule
        against every other edge. Stage 2 made it fail thirteen times, and the
        test was wrong rather than the table: it had generalised from a table
        that happened to contain only review edges. Corrected deliberately, with
        the review/lifecycle split now named once in `lifecycle.REVIEW_EVENTS`
        rather than re-listed here.
        """
        for (from_status, event) in TRANSITIONS:
            if event not in lifecycle.REVIEW_EVENTS:
                continue
            with self.subTest(status=from_status, event=event):
                self.assertIn(from_status, STAGES)

    def test_lifecycle_edges_do_not_require_a_stage(self):
        """
        The other half, asserted rather than left implicit: the record-lifecycle
        events genuinely do start outside `STAGES`, so the narrowing above is
        describing the table as it is and not quietly excusing a gap.
        """
        lifecycle_origins = {
            from_status
            for (from_status, event) in TRANSITIONS
            if event not in lifecycle.REVIEW_EVENTS
        }
        self.assertTrue(
            lifecycle_origins - set(STAGES),
            "no lifecycle edge starts outside STAGES -- if that is now true, the "
            "narrowing in the test above is no longer earning its keep",
        )

    def test_sequential_stages_declare_what_a_review_records_as(self):
        for status, stage in STAGES.items():
            if stage.kind is StageKind.SEQUENTIAL:
                with self.subTest(status=status):
                    self.assertIsNotNone(
                        stage.records_as,
                        "a sequential gate must say which ReviewStage it records at",
                    )
                    self.assertEqual(stage.offices, ())

    def test_parallel_stages_declare_a_non_empty_office_group(self):
        """
        A parallel stage with no offices would auto-clear on entry — the exact
        situation `enter_clearance_stage` skips rather than creates.
        """
        for status, stage in STAGES.items():
            if stage.kind is StageKind.PARALLEL:
                with self.subTest(status=status):
                    self.assertTrue(stage.offices)
                    self.assertIsNone(
                        stage.records_as,
                        "a parallel stage takes its ReviewStage from the acting office",
                    )

    def test_all_three_routes_are_reachable_as_data(self):
        """
        ADR-002's acceptance criterion, read off the table rather than from
        prose: every gate on each of the three documented routes is declared,
        and each has an approve edge.
        """
        routes = {
            "Proposal": [PipelineStatus.ADVISER_REVIEW],
            "Thesis/Research": [
                PipelineStatus.RDCO_INTAKE,
                PipelineStatus.PARALLEL_REVIEW,
                PipelineStatus.RDCO_REVIEW,
            ],
            "Project": [
                PipelineStatus.RDCO_INTAKE,
                PipelineStatus.ITSO_REVIEW,
                PipelineStatus.PARALLEL_REVIEW,
                PipelineStatus.RDCO_REVIEW,
            ],
        }
        for route, stages in routes.items():
            for status in stages:
                with self.subTest(route=route, stage=status):
                    self.assertIn(status, STAGES)
                    self.assertIsNotNone(
                        lifecycle.edge_for(status, WorkflowEvent.APPROVE)
                    )

    def test_every_gate_can_be_declined_and_rejected(self):
        """
        The decline/reject pair is ADR-003's foundation: a decline invites a
        resubmission, a rejection is terminal. A gate offering only one of them
        would silently remove that choice from a reviewer.
        """
        for status in STAGES:
            for event in (WorkflowEvent.DECLINE, WorkflowEvent.REJECT):
                with self.subTest(status=status, event=event):
                    self.assertIsNotNone(lifecycle.edge_for(status, event))


class DerivedVocabularyTests(SimpleTestCase):
    """The sequential/parallel split is declared once and read everywhere."""

    def test_clearance_offices_are_derived_from_the_stage_groups(self):
        """
        This replaced a set literal inside `resubmit_record` — the one ADR-003's
        contribution turned on. Deriving it means an office added to a group
        cannot leave a stale copy behind.
        """
        self.assertEqual(
            lifecycle.clearance_offices(),
            frozenset({Office.ITSO, Office.IERC, Office.KTTO}),
        )

    def test_is_clearance_stage_agrees_with_the_declared_kind(self):
        for status, stage in STAGES.items():
            with self.subTest(status=status):
                self.assertEqual(
                    lifecycle.is_clearance_stage(status),
                    stage.kind is StageKind.PARALLEL,
                )

    def test_a_terminal_status_is_not_a_clearance_stage(self):
        for status in (
            PipelineStatus.DRAFT,
            PipelineStatus.PUBLISHED,
            PipelineStatus.DECLINED,
            PipelineStatus.REJECTED,
        ):
            with self.subTest(status=status):
                self.assertFalse(lifecycle.is_clearance_stage(status))

    def test_review_stage_resolves_the_union_both_ways(self):
        """
        `Review.stage` holds a gate at a sequential stage and an **office** at a
        parallel one. One field, two sources — ADR-002 amendment, point 5.
        """
        self.assertEqual(
            lifecycle.review_stage_for(PipelineStatus.RDCO_INTAKE),
            ReviewStage.RDCO_INTAKE,
        )
        self.assertEqual(
            lifecycle.review_stage_for(PipelineStatus.PARALLEL_REVIEW, office=Office.KTTO),
            Office.KTTO,
        )
        self.assertIsNone(lifecycle.review_stage_for(PipelineStatus.PUBLISHED))


class ConfigurationSeamTests(SimpleTestCase):
    """
    `settings.WORKFLOW_TABLE` is what makes ADR-005's "configuration within the
    instance" true without a `tenant_id` or a migration, and how ADR-004's
    `RESTART_ALL` evaluation instance will differ from production. If the
    override silently did nothing, both claims would be false and nothing else
    would notice.
    """

    def test_without_the_setting_the_defaults_are_used(self):
        stages, transitions = lifecycle.load_table()
        self.assertIs(stages, STAGES)
        self.assertIs(transitions, TRANSITIONS)

    @override_settings(
        WORKFLOW_TABLE={
            "STAGES": {
                PipelineStatus.RDCO_INTAKE: Stage(
                    kind=StageKind.PARALLEL, offices=(Office.KTTO,)
                )
            }
        }
    )
    def test_an_overridden_stage_changes_what_the_table_reports(self):
        """A tenant reshaping a stage must actually reshape behaviour."""
        self.assertTrue(lifecycle.is_clearance_stage(PipelineStatus.RDCO_INTAKE))
        self.assertEqual(lifecycle.clearance_offices(), frozenset({Office.KTTO}))

    @override_settings(WORKFLOW_TABLE={"TRANSITIONS": {}})
    def test_an_overridden_edge_set_is_honoured(self):
        self.assertIsNone(
            lifecycle.edge_for(PipelineStatus.RDCO_INTAKE, WorkflowEvent.APPROVE)
        )


class ApplyRefusalTests(TestCase):
    """`apply()` refuses what the table does not declare."""

    def test_an_undeclared_transition_raises(self):
        from apps.records.models import Record, RecordType

        record_type = RecordType.objects.first()
        self.assertIsNotNone(record_type, "no seeded RecordType -- migrations incomplete")
        record = Record.objects.create(
            title="Undeclared Transition", abstract="Z" * 40,
            record_type=record_type, pipeline_status=PipelineStatus.PUBLISHED,
        )
        with self.assertRaises(InvalidPipelineTransition):
            lifecycle.apply(record, WorkflowEvent.APPROVE)

        record.refresh_from_db()
        self.assertEqual(
            record.pipeline_status, PipelineStatus.PUBLISHED,
            "a refused transition must not move the record",
        )

    def test_the_refusal_names_the_status_and_the_event(self):
        """A reviewer reading the error should not have to guess which edge was missing."""
        from apps.records.models import Record, RecordType

        record = Record.objects.create(
            title="Refusal Message", abstract="Z" * 40,
            record_type=RecordType.objects.first(),
            pipeline_status=PipelineStatus.DRAFT,
        )
        with self.assertRaises(InvalidPipelineTransition) as caught:
            lifecycle.apply(record, WorkflowEvent.APPROVE)
        message = str(caught.exception)
        self.assertIn(PipelineStatus.DRAFT, message)
        self.assertIn(WorkflowEvent.APPROVE.value, message)
