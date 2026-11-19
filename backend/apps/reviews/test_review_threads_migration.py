"""
IR-874's backfill, `reviews/0025`: existing review comments become general
threads with severity *Suggestion*, and nothing is rewritten (ADR-032 §7,
2026-11-04).

Mechanics follow `test_seat_backfill_migration.py`: rewind `reviews` to the
schema migration, write rows through the models as of it, migrate forward.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.records.models import RecordType
from apps.reviews.workflow_test_helpers import model_at_current_state, purge_records_at_current_state

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_BEFORE = [("reviews", "0024_review_threads")]
_AFTER = [("reviews", "0025_backfill_review_threads")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)


def _model(target, app, name):
    return MigrationExecutor(connection).loader.project_state(target).apps.get_model(app, name)


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(email=email, password="TestPass123!", role=role, is_verified=True)


def test_existing_comments_become_general_suggestion_threads_of_their_writer_s_party():
    _migrate(_BEFORE)
    try:
        owner = _user("ir874-owner@cit.edu", "Student")
        adviser = _user("ir874-adviser@cit.edu", "Adviser")
        itso = _user("ir874-itso@cit.edu", "ITSO")
        thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        record = model_at_current_state("records", "Record").objects.create(
            title="Backfilled", record_type_id=thesis.pk, added_by_id=owner.pk,
            pipeline_status="in_review", adviser_id=adviser.pk,
        )
        _model(_BEFORE, "records", "RecordOwner").objects.create(
            record_id=record.pk, user_id=owner.pk, is_primary=True,
        )
        Assignment = _model(_BEFORE, "reviews", "RecordAssignment")
        Seat = _model(_BEFORE, "reviews", "ReviewerSeat")
        for party, reviewer in (("adviser", adviser), ("itso", itso)):
            assignment = Assignment.objects.create(record_id=record.pk, party=party)
            Seat.objects.create(assignment_id=assignment.pk, reviewer_id=reviewer.pk, source="claimed",
                                assigned_at=timezone.now() - timedelta(days=1))

        Comment = _model(_BEFORE, "reviews", "ReviewComment")
        by_owner = Comment.objects.create(record_id=record.pk, author_id=owner.pk, body="Owner's.")
        by_adviser = Comment.objects.create(record_id=record.pk, author_id=adviser.pk, body="Adviser's.")
        by_itso = Comment.objects.create(record_id=record.pk, author_id=itso.pk, body="ITSO's.")
        reply = Comment.objects.create(
            record_id=record.pk, author_id=owner.pk, body="A reply.", reply_to_id=by_itso.pk,
        )
        orphan = Comment.objects.create(record_id=record.pk, author_id=None, body="Removed account.")
        before = {
            c.pk: (c.body, c.created_at, c.edited_at, c.version_id, c.reply_to_id)
            for c in Comment.objects.all()
        }

        _migrate(_AFTER)

        After = _model(_AFTER, "reviews", "ReviewComment")
        rows = {c.pk: c for c in After.objects.all()}
        assert {pk: (c.severity, c.party) for pk, c in rows.items()} == {
            by_owner.pk: ("suggestion", ""),
            by_adviser.pk: ("suggestion", "adviser"),
            by_itso.pk: ("suggestion", "itso"),
            reply.pk: (None, ""),
            orphan.pk: ("suggestion", ""),
        }
        # General, open, sent -- and nothing rewritten.
        assert all(c.anchor_version_id is None and c.state == "open" and not c.is_draft
                   for c in rows.values())
        assert {
            c.pk: (c.body, c.created_at, c.edited_at, c.version_id, c.reply_to_id)
            for c in rows.values()
        } == before
    finally:
        purge_records_at_current_state()
        call_command("migrate", verbosity=0)


_REPLIES_BEFORE = [("reviews", "0029_review_mentions")]
_REPLIES_AFTER = [("reviews", "0030_backfill_reply_parties")]


def test_existing_replies_keep_the_party_their_writer_held_when_they_wrote_them():
    """IR-1192's backfill, `reviews/0030`: only a reply's `party` is written."""
    _migrate(_REPLIES_BEFORE)
    try:
        owner = _user("ir1192-owner@iris.test", "Student")
        adviser = _user("ir1192-adviser@iris.test", "Adviser")
        itso = _user("ir1192-itso@iris.test", "ITSO")
        thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        record = model_at_current_state("records", "Record").objects.create(
            title="Replies backfilled", record_type_id=thesis.pk, added_by_id=owner.pk,
            pipeline_status="in_review", adviser_id=adviser.pk,
        )
        _model(_REPLIES_BEFORE, "records", "RecordOwner").objects.create(
            record_id=record.pk, user_id=owner.pk, is_primary=True,
        )
        Assignment = _model(_REPLIES_BEFORE, "reviews", "RecordAssignment")
        Seat = _model(_REPLIES_BEFORE, "reviews", "ReviewerSeat")
        for party, reviewer in (("adviser", adviser), ("itso", itso)):
            assignment = Assignment.objects.create(record_id=record.pk, party=party)
            Seat.objects.create(assignment_id=assignment.pk, reviewer_id=reviewer.pk, source="claimed",
                                assigned_at=timezone.now() - timedelta(days=1))

        Comment = _model(_REPLIES_BEFORE, "reviews", "ReviewComment")
        thread = Comment.objects.create(record_id=record.pk, author_id=itso.pk, body="ITSO's.",
                                        party="itso", severity="suggestion")
        by_owner = Comment.objects.create(record_id=record.pk, author_id=owner.pk, body="Owner's.",
                                          reply_to_id=thread.pk)
        by_adviser = Comment.objects.create(record_id=record.pk, author_id=adviser.pk, body="Adviser's.",
                                            reply_to_id=thread.pk)
        by_itso = Comment.objects.create(record_id=record.pk, author_id=itso.pk, body="ITSO's reply.",
                                         reply_to_id=thread.pk)
        orphan = Comment.objects.create(record_id=record.pk, author_id=None, body="Removed account.",
                                        reply_to_id=thread.pk)
        before = {
            c.pk: (c.body, c.created_at, c.edited_at, c.version_id, c.reply_to_id, c.severity)
            for c in Comment.objects.all()
        }

        _migrate(_REPLIES_AFTER)

        After = _model(_REPLIES_AFTER, "reviews", "ReviewComment")
        rows = {c.pk: c for c in After.objects.all()}
        assert {pk: c.party for pk, c in rows.items()} == {
            thread.pk: "itso",
            by_owner.pk: "",
            by_adviser.pk: "adviser",
            by_itso.pk: "itso",
            orphan.pk: "",
        }
        assert {
            c.pk: (c.body, c.created_at, c.edited_at, c.version_id, c.reply_to_id, c.severity)
            for c in rows.values()
        } == before
    finally:
        purge_records_at_current_state()
        call_command("migrate", verbosity=0)


_KIND_BEFORE = [("reviews", "0031_reviewcomment_kind")]
_KIND_AFTER = [("reviews", "0032_backfill_discussion")]


def test_comments_nobody_treated_as_a_review_item_become_discussion():
    """IR-1194's backfill, `reviews/0032`: only `kind`, and a discussion's severity, change."""
    _migrate(_KIND_BEFORE)
    try:
        owner = _user("ir1194-owner@iris.test", "Student")
        adviser = _user("ir1194-adviser@iris.test", "Adviser")
        thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        record = model_at_current_state("records", "Record").objects.create(
            title="Discussion backfilled", record_type_id=thesis.pk, added_by_id=owner.pk,
            pipeline_status="in_review", adviser_id=adviser.pk,
        )
        version = model_at_current_state("records", "RecordVersion").objects.create(
            record_id=record.pk, number=1, cause="submission", created_by_id=owner.pk,
        )
        Round = _model(_KIND_BEFORE, "reviews", "ReviewRound")
        round_ = Round.objects.create(record_id=record.pk, actor_id=adviser.pk, party="adviser",
                                      version_id=version.pk, verdict="comment_only")
        Comment = _model(_KIND_BEFORE, "reviews", "ReviewComment")

        def made(**fields):
            return Comment.objects.create(record_id=record.pk, body="A comment.", **fields)

        plain_owner = made(author_id=owner.pk, severity="suggestion")
        plain_reviewer = made(author_id=adviser.pk, party="adviser", severity="suggestion")
        reply = made(author_id=adviser.pk, party="adviser", reply_to_id=plain_owner.pk)
        anchored = made(author_id=owner.pk, anchor_version_id=version.pk, anchor_page=2,
                        anchor_quote="forty respondents")
        must_fix = made(author_id=adviser.pk, party="adviser", severity="must_fix")
        in_round = made(author_id=adviser.pk, party="adviser", severity="suggestion",
                        round_id=round_.pk)
        answered = made(author_id=adviser.pk, party="adviser", severity="suggestion",
                        answer="addressed", answer_note="Done.")
        acted_on = made(author_id=adviser.pk, party="adviser", severity="suggestion")
        _model(_KIND_BEFORE, "reviews", "ReviewThreadEvent").objects.create(
            thread_id=acted_on.pk, actor_id=owner.pk, kind="resolved")
        draft = made(author_id=adviser.pk, party="adviser", severity="suggestion", is_draft=True)
        thread_reply = made(author_id=owner.pk, reply_to_id=must_fix.pk)
        before = {c.pk: (c.body, c.created_at, c.author_id, c.party, c.reply_to_id)
                  for c in Comment.objects.all()}

        _migrate(_KIND_AFTER)

        rows = {c.pk: c for c in _model(_KIND_AFTER, "reviews", "ReviewComment").objects.all()}
        assert {pk: c.kind for pk, c in rows.items()} == {
            plain_owner.pk: "discussion", plain_reviewer.pk: "discussion", reply.pk: "discussion",
            anchored.pk: "thread", must_fix.pk: "thread", in_round.pk: "thread",
            answered.pk: "thread", acted_on.pk: "thread", draft.pk: "thread",
            thread_reply.pk: "thread",
        }
        assert (rows[plain_owner.pk].severity, rows[plain_reviewer.pk].severity) == (None, None)
        assert rows[must_fix.pk].severity == "must_fix"
        assert rows[in_round.pk].severity == "suggestion"
        assert {pk: (c.body, c.created_at, c.author_id, c.party, c.reply_to_id)
                for pk, c in rows.items()} == before
    finally:
        purge_records_at_current_state()
        call_command("migrate", verbosity=0)
