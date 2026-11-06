"""Marking the papers already loaded on a development database (IR-815, IR-882).

ADR-052 decision 16, as amended: the proxy papers are released once. The gate is what these
read, because that is what the marking is for.
"""

from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.ai.policy.records import decision_for_record
from core.enums import EmbargoState, PipelineStatus

from .management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from .models import Record, RecordType


def mark(**options):
    out = StringIO()
    call_command("mark_corpus_cleared", stdout=out, **options)
    return out.getvalue()


class _Papers(TestCase):
    def setUp(self):
        self.loader = User.objects.create_user(email=DEFAULT_OWNER_EMAIL, password="x")
        self.someone_else = User.objects.create_user(email="someone@cit.edu", password="x")

    def paper(self, title="Proxy paper", owner=None, **fields):
        fields.setdefault("pipeline_status", PipelineStatus.PUBLISHED)
        return Record.objects.create(
            title=title,
            added_by=owner or self.loader,
            record_type=RecordType.objects.first(),
            **fields,
        )


@override_settings(DEBUG=True)
class MarkCorpusClearedTests(_Papers):
    def test_a_loaded_paper_may_reach_the_ai_afterwards(self):
        record = self.paper()
        self.assertFalse(decision_for_record(record).allowed)

        mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.RELEASED)
        self.assertTrue(decision_for_record(record).allowed)

    def test_the_loader_account_released_it_and_consented(self):
        record = self.paper()

        mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_released_by, self.loader)
        self.assertEqual(record.dpa_accepted_by, self.loader)

    def test_another_owners_paper_stays_embargoed(self):
        record = self.paper(owner=self.someone_else)

        mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
        self.assertIsNone(record.dpa_accepted_at)

    def test_the_owner_can_be_named(self):
        record = self.paper(owner=self.someone_else)

        mark(owner_email="someone@cit.edu")

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.RELEASED)

    def test_a_date_someone_set_is_never_overridden(self):
        set_at = timezone.now()
        record = self.paper(embargo_date_set_at=set_at, embargoed_until=date(2099, 1, 1))

        mark()

        record.refresh_from_db()
        self.assertEqual(record.embargoed_until, date(2099, 1, 1))
        self.assertEqual(record.embargo_date_set_at, set_at)
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)

    def test_consent_someone_already_gave_keeps_their_name(self):
        given_at = timezone.now()
        record = self.paper(dpa_accepted_at=given_at, dpa_accepted_by=self.someone_else)

        mark()

        record.refresh_from_db()
        self.assertEqual(record.dpa_accepted_by, self.someone_else)
        self.assertEqual(record.dpa_accepted_at, given_at)

    def test_a_paper_declared_institutional_stays_embargoed_and_is_named(self):
        record = self.paper(title="A real CIT-U thesis", origin=Record.Origin.INSTITUTIONAL)

        report = mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
        self.assertIn("A real CIT-U thesis", report)

    def test_an_ip_marked_paper_is_released_and_still_refused(self):
        record = self.paper(is_ip=True)

        mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.RELEASED)
        self.assertFalse(decision_for_record(record).allowed)

    def test_a_second_run_changes_nothing(self):
        record = self.paper()
        mark()
        record.refresh_from_db()
        first_release = record.embargo_released_at

        report = mark()

        record.refresh_from_db()
        self.assertEqual(record.embargo_released_at, first_release)
        self.assertIn("Marked 0 paper(s)", report)

    def test_dry_run_writes_nothing_and_says_what_it_would_do(self):
        record = self.paper()

        report = mark(dry_run=True)

        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
        self.assertIsNone(record.dpa_accepted_at)
        self.assertIn("Would mark 1 paper(s)", report)

    def test_a_draft_is_left_alone(self):
        """`--owner-email` can name anyone, and a draft hasn't been submitted."""
        draft = self.paper(pipeline_status=PipelineStatus.DRAFT)

        mark()

        draft.refresh_from_db()
        self.assertEqual(draft.embargo_state, EmbargoState.ACTIVE)
        self.assertIsNone(draft.dpa_accepted_at)

    def test_it_sends_nothing_to_anyone(self):
        self.paper()

        with patch("apps.ai.tasks.index_record.delay") as index, \
                patch("apps.ai.tasks.embed_record.delay") as embed, \
                patch("apps.ai.tasks.embed_chunk_set.delay") as embed_chunks, \
                patch("apps.ai.overview.service._enqueue_overview") as overview:
            with self.captureOnCommitCallbacks(execute=True):
                mark()

        index.assert_not_called()
        embed.assert_not_called()
        embed_chunks.assert_not_called()
        overview.assert_not_called()

    def test_the_report_names_the_next_step(self):
        self.paper()

        self.assertIn("backfill_embeddings --dry-run", mark())

    def test_finding_nothing_says_whose_papers_are_waiting(self):
        """The default owner is a guess at how a corpus was loaded."""
        self.paper(owner=self.someone_else)
        self.paper(title="Another", owner=self.someone_else)

        report = mark()

        self.assertIn("someone@cit.edu (2)", report)

    def test_an_owner_who_does_not_exist_is_an_error_that_says_who_does(self):
        self.paper()

        with self.assertRaises(CommandError) as caught:
            mark(owner_email="nobody@cit.edu")

        self.assertIn("nobody@cit.edu", str(caught.exception))
        self.assertIn(f"{DEFAULT_OWNER_EMAIL} (1)", str(caught.exception))


class MarkCorpusClearedGuardTests(_Papers):
    def test_it_refuses_with_debug_off(self):
        # No `override_settings(DEBUG=False)`: the test runner already forces it.
        record = self.paper()

        with self.assertRaises(CommandError) as caught:
            mark()

        self.assertIn("DEBUG", str(caught.exception))
        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)

    def test_there_is_no_way_past_the_refusal(self):
        with self.assertRaises(TypeError):
            mark(force=True)
