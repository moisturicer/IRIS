"""
Tests for the record-level transition table (IR-136, ADR-002 as amended
2026-09-09; rewritten for IR-274).

**What the table is now.** IR-274 deleted the fixed review pipeline: the
`STAGES` registry, every review edge and the resolvers that routed a record
between stages. Review is assignments, seats and Decisions, tested at the HTTP
seam in `apps/reviews/` (`test_routing`, `test_office_review`,
`test_decisions`, `test_revisions`, `test_new_version`). What remains here is
the record-owned edges -- requesting deletion, soft deletion, restoring -- the
ADR-005 configuration seam that can override them, ADR-004's resubmission
policy, and the deciding parties the tracker reads.

These are properties of the table, invisible to a behavioural test, and each
one is something a later change could silently break while every workflow test
stayed green.
"""

from django.test import SimpleTestCase, TestCase, override_settings

from apps.records import lifecycle
from apps.records.lifecycle import TRANSITIONS, Edge, WorkflowEvent
from core.enums import (
    DELETE_REVIEW_STATUSES,
    Party,
    PipelineStatus,
    RecordTypeName,
)
from core.exceptions import InvalidPipelineTransition


class TableStructureTests(SimpleTestCase):
    """Pure: the table's internal consistency, no database."""

    def test_every_edge_declares_exactly_one_destination(self):
        """
        `Edge.__post_init__` enforces this, so the table cannot be constructed
        wrongly -- this proves the guard is real rather than assumed.
        """
        for key, edge in TRANSITIONS.items():
            with self.subTest(edge=key):
                self.assertNotEqual(bool(edge.to), bool(edge.resolver))

        with self.assertRaises(ValueError):
            Edge(to=PipelineStatus.PUBLISHED, resolver="restore_previous")
        with self.assertRaises(ValueError):
            Edge()

    def test_every_named_resolver_exists(self):
        """A typo in a resolver name would otherwise surface only in production."""
        for key, edge in TRANSITIONS.items():
            if edge.resolver:
                with self.subTest(edge=key):
                    self.assertIn(edge.resolver, lifecycle._RESOLVERS)

    def test_only_the_record_owned_events_remain(self):
        """
        IR-274: nothing in the table reviews a record. A review edge coming
        back would be a second, fixed routing model beside the assignments.
        """
        self.assertEqual(
            {event for _status, event in TRANSITIONS},
            {WorkflowEvent.REQUEST_DELETE, WorkflowEvent.SOFT_DELETE, WorkflowEvent.RESTORE},
        )

    def test_deletion_needs_review_exactly_for_accepted_work(self):
        requestable = {s for s, e in TRANSITIONS if e is WorkflowEvent.REQUEST_DELETE}
        self.assertEqual(requestable, set(DELETE_REVIEW_STATUSES))
        for status in requestable:
            self.assertEqual(
                TRANSITIONS[(status, WorkflowEvent.REQUEST_DELETE)].to,
                PipelineStatus.PENDING_DELETE,
            )

    def test_soft_delete_is_legal_from_every_status(self):
        for status in PipelineStatus.values:
            with self.subTest(status=status):
                self.assertEqual(
                    lifecycle.edge_for(status, WorkflowEvent.SOFT_DELETE).to,
                    PipelineStatus.PENDING_DELETE,
                )

    def test_only_a_record_held_for_deletion_can_be_restored(self):
        restorable = {s for s, e in TRANSITIONS if e is WorkflowEvent.RESTORE}
        self.assertEqual(restorable, {PipelineStatus.PENDING_DELETE})


class _Type:
    def __init__(self, name):
        self.name = name


class _Record:
    def __init__(self, type_name):
        self.record_type = _Type(type_name) if type_name else None


class DecidingPartiesTests(SimpleTestCase):
    """Who may decide each record type -- what the tracker's *final review* reads."""

    def test_a_proposal_and_every_other_type(self):
        self.assertEqual(
            lifecycle.deciding_parties_for(_Record(RecordTypeName.PROPOSAL)),
            {Party.ADVISER, Party.RDCO},
        )
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT, None):
            with self.subTest(type_name=type_name):
                self.assertEqual(
                    lifecycle.deciding_parties_for(_Record(type_name)), {Party.RDCO},
                )

    def test_the_retired_intake_decides_nothing(self):
        for parties in (*lifecycle.DECIDING_PARTIES.values(), lifecycle.DEFAULT_DECIDING_PARTIES):
            self.assertNotIn(Party.INTAKE, parties)


class ConfigurationSeamTests(SimpleTestCase):
    """
    `settings.WORKFLOW_TABLE` is what makes ADR-005's "configuration within the
    instance" true without a `tenant_id` or a migration. If the override
    silently did nothing, that claim would be false and nothing else would
    notice.
    """

    @override_settings(WORKFLOW_TABLE={})
    def test_without_the_setting_the_defaults_are_used(self):
        self.assertIs(lifecycle.load_table(), TRANSITIONS)

    @override_settings(WORKFLOW_TABLE={"TRANSITIONS": {}})
    def test_an_overridden_edge_set_is_honoured(self):
        self.assertIsNone(
            lifecycle.edge_for(PipelineStatus.PUBLISHED, WorkflowEvent.REQUEST_DELETE)
        )


class ApplyRefusalTests(TestCase):
    """`apply()` refuses what the table does not declare."""

    def _record(self, status):
        from apps.records.models import Record, RecordType

        record_type = RecordType.objects.first()
        self.assertIsNotNone(record_type, "no seeded RecordType -- migrations incomplete")
        return Record.objects.create(
            title="Undeclared Transition", abstract="Z" * 40,
            record_type=record_type, pipeline_status=status,
        )

    def test_an_undeclared_transition_raises_and_moves_nothing(self):
        record = self._record(PipelineStatus.DRAFT)
        with self.assertRaises(InvalidPipelineTransition):
            lifecycle.apply(record, WorkflowEvent.REQUEST_DELETE)

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)

    def test_the_refusal_names_the_status_and_the_event(self):
        """A reader of the error should not have to guess which edge was missing."""
        record = self._record(PipelineStatus.IN_REVIEW)
        with self.assertRaises(InvalidPipelineTransition) as caught:
            lifecycle.apply(record, WorkflowEvent.RESTORE)
        message = str(caught.exception)
        self.assertIn(PipelineStatus.IN_REVIEW, message)
        self.assertIn(WorkflowEvent.RESTORE.value, message)


class ResubmissionPolicyTests(SimpleTestCase):
    """
    The policy as *table configuration* (IR-137, ADR-004).

    What the two policies do to a record is asserted end to end in
    `apps/reviews/test_new_version.py`. What is checked here is the
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
        self.assertIs(lifecycle.load_table(), TRANSITIONS)


class PolicyIsRecordedTests(SimpleTestCase):
    """
    The `apps.*` logger must actually emit INFO (IR-137, ADR-004).

    ADR-004 requires that the arm a run used be recoverable afterwards, and this
    branch records it with `logger.info` in `new_version`. That line is only
    a record if something is listening: before this ticket there was no `LOGGING`
    setting at all, the root logger sat at WARNING with no handlers, and the line
    was composed and dropped.

    Deliberately asserts on the *configuration* rather than capturing a log.
    `assertLogs` attaches its own handler and lowers the level itself, so a test
    written that way passes whether or not the deployed settings would emit
    anything — it would not have caught the bug it exists to prevent.
    """

    def test_app_logs_are_enabled_at_info(self):
        import logging

        self.assertTrue(
            logging.getLogger("apps.reviews.new_version").isEnabledFor(logging.INFO),
            "apps.* logging is not enabled at INFO, so the line naming which "
            "resubmission policy ran is discarded and the evaluation arm cannot "
            "be recovered from a run",
        )


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
        # Applies it to the new model's resubmission (IR-273), and logs which
        # arm ran. Serializes no policy: only which offices a version keeps,
        # as `offices_preserved` already does.
        "apps/reviews/new_version.py",
        "config/settings/base.py",  # loads it from the environment
    }

    #: Both spellings of the policy, plus the table it lives in.
    #:
    #: Underscores are stripped from the haystack before matching, so one needle
    #: catches `resubmission_policy` *and* `ResubmissionPolicy` — the earlier
    #: version lowercased only, which missed the class entirely: a serializer
    #: could import the enum and expose `ChoiceField(choices=...)` under any
    #: field name and the guard would have passed it.
    #:
    #: `WORKFLOW_TABLE` is here because reading the policy is not the only way to
    #: reach it — an endpoint writing the table wholesale would set the policy
    #: without ever naming it.
    NEEDLES = ("resubmissionpolicy", "workflowtable")

    def test_only_the_permitted_modules_mention_the_policy(self):
        from pathlib import Path

        backend = Path(lifecycle.__file__).resolve().parent.parent.parent
        offenders = sorted(
            path.relative_to(backend).as_posix()
            for path in backend.rglob("*.py")
            if not path.name.startswith("test_")
            and "tests" not in path.parts
            and ".venv" not in path.parts
            and "migrations" not in path.parts
            and any(
                needle in path.read_text(encoding="utf-8").lower().replace("_", "")
                for needle in self.NEEDLES
            )
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
