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
