"""
IR-415's seat backfill, `reviews/0010`, over assignments that predate seats.

ADR-032 §13: one seat per existing active assignment -- `record.adviser` for
an Adviser assignment, the most recent reviewer of that party where one
exists -- and every other assignment left seatless, which is the office's
pool. Nothing is guessed, and nothing that is not active gets a seat.

Mechanics follow `test_shadow_backfill_migration.py`: rewind `reviews` only
and write rows through the current models, which is safe because `0010`
changes no schema. Rows are written directly so no dual-write can produce
the seats under test.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordType
from apps.reviews.models import RecordAssignment, RecordClearance, Review, ReviewerSeat

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_BEFORE = [("reviews", "0009_reviewer_seat")]
_AFTER = [("reviews", "0010_backfill_reviewer_seats")]

T0 = timezone.now() - timedelta(days=10)


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", role=role, is_verified=True
    )


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)


def _seats(assignment):
    return {
        (s.reviewer_id, s.state, s.source, s.opened_at)
        for s in ReviewerSeat.objects.filter(assignment=assignment)
    }


def test_the_backfill_seats_each_active_assignment_it_can_map_and_no_other():
    _migrate(_BEFORE)
    try:
        owner = _user("ir415-owner@cit.edu", "Student")
        adviser = _user("ir415-adviser@cit.edu", "Adviser")
        itso_old = _user("ir415-itso-old@cit.edu", "ITSO")
        itso_new = _user("ir415-itso-new@cit.edu", "ITSO")
        ierc = _user("ir415-ierc@cit.edu", "IERC")
        rdco = _user("ir415-rdco@cit.edu", "RDCO")
        # get_or_create: a flushing TransactionTestCase earlier in the run
        # removes the rows records/0002 seeds.
        thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        proposal = RecordType.objects.get_or_create(name="Proposal")[0]

        def record(title, status, record_type=thesis, **extra):
            return Record.objects.create(
                title=title, record_type=record_type, added_by=owner,
                pipeline_status=status, **extra,
            )

        def review(record_, stage, by, minutes, decision="approved"):
            r = Review.objects.create(record=record_, reviewed_by=by, stage=stage, status=decision)
            at = T0 + timedelta(minutes=minutes)
            Review.objects.filter(pk=r.pk).update(created_at=at)
            return at

        # An Adviser who has not reviewed yet: an `assigned` entry seat.
        unread = record("unread", "adviser_review", proposal, adviser=adviser)
        unread_a = RecordAssignment.objects.create(record=unread, party="adviser")

        # An Adviser who asked for changes: still holds it, `in_review`.
        declined = record("declined", "declined", proposal, adviser=adviser)
        declined_at = review(declined, "adviser", adviser, 1, decision="declined")
        declined_a = RecordAssignment.objects.create(record=declined, party="adviser")

        # An Adviser assignment on a record that names no Adviser: unmappable.
        orphan = record("orphan", "adviser_review", proposal)
        orphan_a = RecordAssignment.objects.create(record=orphan, party="adviser")

        # ITSO reviewed twice; the most recent reviewer is seated. Their
        # clearance signature is the latest act, so it wins over the reviews.
        reread = record("reread", "parallel_review", requested_itso=True, requested_ierc=True)
        review(reread, "itso", itso_old, 2, decision="declined")
        review(reread, "itso", itso_new, 3)
        clearance = RecordClearance.objects.create(
            record=reread, office="itso", status="pending", reviewed_by=itso_new,
        )
        signed_at = T0 + timedelta(minutes=4)
        RecordClearance.objects.filter(pk=clearance.pk).update(updated_at=signed_at)
        itso_a = RecordAssignment.objects.create(record=reread, party="itso")
        # IERC has not looked at it: the pool.
        ierc_a = RecordAssignment.objects.create(record=reread, party="ierc")

        # RDCO final review by someone who already reviewed it.
        final = record("final", "rdco_review")
        final_at = review(final, "rdco", rdco, 5)
        rdco_a = RecordAssignment.objects.create(record=final, party="rdco")

        # Intake is retired: never seated, even with an intake review on record.
        intake = record("intake", "rdco_intake")
        review(intake, "rdco_intake", rdco, 6)
        intake_a = RecordAssignment.objects.create(record=intake, party="intake")

        # A finished turn is history: no seat.
        done = record("done", "published")
        review(done, "ierc", ierc, 7)
        done_a = RecordAssignment.objects.create(
            record=done, party="ierc", state="completed", closed_at=T0,
        )

        _migrate(_AFTER)

        assert _seats(unread_a) == {(adviser.pk, "assigned", "entry", None)}
        assert _seats(declined_a) == {(adviser.pk, "in_review", "entry", declined_at)}
        assert _seats(orphan_a) == set()
        assert _seats(itso_a) == {(itso_new.pk, "in_review", "claimed", signed_at)}
        assert _seats(ierc_a) == set()
        assert _seats(rdco_a) == {(rdco.pk, "in_review", "claimed", final_at)}
        assert _seats(intake_a) == set()
        assert _seats(done_a) == set()

        # Re-running finds every mappable assignment already seated.
        _migrate(_BEFORE)
        _migrate(_AFTER)
        assert ReviewerSeat.objects.filter(assignment=unread_a).count() == 1
    finally:
        call_command("migrate", verbosity=0)
