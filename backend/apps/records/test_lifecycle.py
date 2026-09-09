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


class ResubmissionPolicyTests(SimpleTestCase):
    """
    The policy as *table configuration* (IR-137, ADR-004).

    What the two policies do to a record is asserted end to end in
    `apps/reviews/test_resubmission_policy.py`. What is checked here is the
    setting itself: that production defaults to the contribution, that an
    instance can override it, and that a mistyped value fails loudly. The last
    one matters more than it looks — a silent fallback to the default would run
    the evaluation instance on the production arm and contaminate every
    measurement taken from it, with nothing in the output to show for it.
    """

    @override_settings(WORKFLOW_TABLE={})
    def test_the_production_default_is_clearance_aware(self):
        """
        Pinned to an empty table rather than read from live settings.

        Reading the real setting would make this test assert what *this* deploy
        happens to be configured as — so it would fail on the evaluation
        instance ADR-004 requires, which is a correct configuration, not a bug.
        What the acceptance criterion actually claims is that the code defaults
        to the contribution when nothing selects an arm.
        """
        self.assertIs(
            lifecycle.resubmission_policy(),
            lifecycle.ResubmissionPolicy.CLEARANCE_AWARE,
        )

    @override_settings(WORKFLOW_TABLE={"RESUBMISSION_POLICY": "RESTART_ALL"})
    def test_the_specs_own_upper_case_spelling_is_accepted(self):
        """
        ADR-004 and IR-137 both write `RESTART_ALL`.

        An operator copying the value out of the document it is specified in is
        the likeliest way this gets typed, so rejecting that spelling would fail
        precisely the person who read the documentation.
        """
        self.assertIs(
            lifecycle.resubmission_policy(), lifecycle.ResubmissionPolicy.RESTART_ALL
        )

    @override_settings(WORKFLOW_TABLE={"RESUBMISSION_POLICY": "restart-all"})
    def test_the_refusal_names_the_values_that_would_have_worked(self):
        """An operator who mistypes it should not have to read the source."""
        with self.assertRaises(ValueError) as caught:
            lifecycle.resubmission_policy()
        message = str(caught.exception)
        self.assertIn("restart-all", message)
        self.assertIn(lifecycle.ResubmissionPolicy.CLEARANCE_AWARE.value, message)
        self.assertIn(lifecycle.ResubmissionPolicy.RESTART_ALL.value, message)

    @override_settings(
        WORKFLOW_TABLE={"RESUBMISSION_POLICY": lifecycle.ResubmissionPolicy.RESTART_ALL}
    )
    def test_an_instance_can_select_the_comparison_arm(self):
        self.assertIs(
            lifecycle.resubmission_policy(), lifecycle.ResubmissionPolicy.RESTART_ALL
        )

    @override_settings(WORKFLOW_TABLE={"RESUBMISSION_POLICY": "restart_all"})
    def test_the_setting_may_be_written_as_its_plain_string_value(self):
        """Configuration arrives from the environment as a string, never as an enum."""
        self.assertIs(
            lifecycle.resubmission_policy(), lifecycle.ResubmissionPolicy.RESTART_ALL
        )

    @override_settings(WORKFLOW_TABLE={"RESUBMISSION_POLICY": "restart-all"})
    def test_an_unrecognised_policy_refuses_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            lifecycle.resubmission_policy()

    @override_settings(
        WORKFLOW_TABLE={"RESUBMISSION_POLICY": lifecycle.ResubmissionPolicy.RESTART_ALL}
    )
    def test_overriding_the_policy_leaves_the_rest_of_the_table_alone(self):
        """`WORKFLOW_TABLE` carries independent keys; one must not shadow another."""
        stages, transitions = lifecycle.load_table()
        self.assertIs(stages, STAGES)
        self.assertIs(transitions, TRANSITIONS)


class PolicyIsNotReachableThroughTheApiTests(SimpleTestCase):
    """
    ADR-004's hard operational rule, enforced rather than trusted.

    "A policy flag that resets clearances could corrupt live customer workflows
    if enabled on the production instance" — so it is deployment configuration,
    not an in-app setting. The risk is not that someone adds a policy endpoint
    on purpose; it is that the name gets added to a serializer's `fields` during
    some unrelated change and nobody notices it is now writable.
    """

    #: The only modules allowed to name the policy at all.
    #:
    #: An allowlist rather than a list of API filenames to search. Naming the
    #: surfaces (`serializers.py`, `views.py`, ...) only catches a field added
    #: to a file someone happened to name conventionally — it is blind to
    #: `config/urls.py`, a `serializers/` package, `api.py`, `viewsets.py`, or
    #: anything under `core/`. Inverting it means a new mention anywhere in the
    #: backend fails until a person decides it belongs.
    PERMITTED = {
        "apps/records/lifecycle.py",  # defines it
        "apps/records/apps.py",  # validates it at startup
        "apps/reviews/services.py",  # reads it to log which arm ran
        "config/settings/base.py",  # loads it from the environment
    }

    def test_only_the_permitted_modules_mention_the_policy(self):
        from pathlib import Path

        backend = Path(lifecycle.__file__).resolve().parent.parent.parent
        offenders = sorted(
            path.relative_to(backend).as_posix()
            for path in backend.rglob("*.py")
            if "test" not in path.name
            and ".venv" not in path.parts
            and "migrations" not in path.parts
            and "resubmission_policy" in path.read_text(encoding="utf-8").lower()
            and path.relative_to(backend).as_posix() not in self.PERMITTED
        )
        self.assertEqual(
            offenders,
            [],
            "the resubmission policy is named in a module that is not permitted "
            "to know about it. It is deployment configuration (ADR-004 Security "
            "Impact), never a field, an endpoint or a serialized value -- if this "
            "mention is legitimate, add it to PERMITTED deliberately",
        )
