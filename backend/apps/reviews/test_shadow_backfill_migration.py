"""
IR-257's backfill, `reviews/0008`, applied over Records that predate it.

Every Record written before IR-257 has no shadow rows: nothing wrote them. The
backfill gives each one the rows §6 of `docs/workflow_routing_architecture.md`
maps its status and clearances to, once. What it must not do is **invent
history**: the old model never recorded who sent a record where, so no
`RoutingEvent` is written, and an assignment is dated from a real `Review` or
`RecordClearance` timestamp or not at all.

Mechanics follow `test_workflow_tables_migration.py`: rewind `reviews` only,
and write the rows through the current models, which is safe here because
`0008` changes no schema. Rows are written directly rather than through the
workflow, precisely so that no dual-write can produce the rows under test.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordType
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    RoutingEvent,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_BEFORE = [("reviews", "0007_reviewer_directed_routing_tables")]
_AFTER = [("reviews", "0008_backfill_shadow_assignments")]
_MARKER = "backfilled from review history (IR-257)"

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


def _rows(record):
    """{party: (state, opened_at, closed_at, closed_by_id)} for one record."""
    return {
        a.party: (a.state, a.opened_at, a.closed_at, a.closed_by_id)
        for a in RecordAssignment.objects.filter(record=record)
    }


def _active(record):
    return {
        party for party, (state, *_rest) in _rows(record).items() if state == "active"
    }


def _completed(record):
    return {
        party for party, (state, *_rest) in _rows(record).items() if state == "completed"
    }


class _World:
    """One Record per §6 row, built as the old code would have left it."""

    def __init__(self):
        self.owner = _user("ir257-owner@cit.edu", "Student")
        self.adviser = _user("ir257-adviser@cit.edu", "Adviser")
        self.rdco = _user("ir257-rdco@cit.edu", "RDCO")
        self.office = {o: _user(f"ir257-{o}@cit.edu", o.upper()) for o in ("itso", "ierc", "ktto")}
        # get_or_create: a flushing TransactionTestCase earlier in the run
        # removes the rows records/0002 seeds.
        self.types = {
            name: RecordType.objects.get_or_create(name=name)[0]
            for name in ("Proposal", "Thesis / Research", "Project")
        }
        self.minute = 0

    def record(self, title, status, type_name="Project", **extra):
        return Record.objects.create(
            title=title, record_type=self.types[type_name], added_by=self.owner,
            pipeline_status=status, **extra,
        )

    def review(self, record, stage, decision, by=None, comment=""):
        """A Review at a strictly later, known time, so dating can be asserted."""
        self.minute += 1
        by = by or (self.office.get(stage) or (self.adviser if stage == "adviser" else self.rdco))
        review = Review.objects.create(
            record=record, reviewed_by=by, stage=stage, status=decision, comment=comment,
        )
        at = T0 + timedelta(minutes=self.minute)
        Review.objects.filter(pk=review.pk).update(created_at=at)
        review.created_at = at
        return review

    def clearance(self, record, office, status):
        return RecordClearance.objects.create(record=record, office=office, status=status)


def test_the_backfill_writes_the_section6_rows_and_invents_no_routing():
    _migrate(_BEFORE)
    try:
        w = _World()

        draft = w.record("draft", "draft")
        adviser = w.record("adviser", "adviser_review", "Proposal", adviser=w.adviser)
        intake = w.record("intake", "rdco_intake", "Thesis / Research")

        itso = w.record("itso", "itso_review", requested_itso=True, requested_ktto=True)
        w.review(itso, "rdco_intake", "approved")
        w.review(itso, "ktto", "approved")
        itso_pending = w.clearance(itso, "itso", "pending")
        w.clearance(itso, "ktto", "cleared")

        parallel = w.record("parallel", "parallel_review", requested_itso=True,
                            requested_ierc=True, requested_ktto=True)
        w.review(parallel, "rdco_intake", "approved")
        w.review(parallel, "itso", "approved")
        w.clearance(parallel, "itso", "cleared")
        w.clearance(parallel, "ierc", "pending")
        w.clearance(parallel, "ktto", "pending")

        final = w.record("final", "rdco_review", requested_ierc=True)
        w.review(final, "rdco_intake", "approved")
        w.review(final, "ierc", "approved")
        w.clearance(final, "ierc", "cleared")

        by_office = w.record("declined by IERC", "declined", requested_itso=True,
                             requested_ierc=True, requested_ktto=True)
        w.review(by_office, "rdco_intake", "approved")
        w.review(by_office, "itso", "approved")
        ierc_decline = w.review(by_office, "ierc", "declined", comment="Consent form")
        w.clearance(by_office, "itso", "cleared")
        w.clearance(by_office, "ierc", "declined")
        w.clearance(by_office, "ktto", "pending")

        at_intake = w.record("declined at intake", "declined", "Thesis / Research")
        intake_decline = w.review(at_intake, "rdco_intake", "declined")

        published = w.record("published", "published", requested_ktto=True)
        first_intake = w.review(published, "rdco_intake", "declined")
        w.review(published, "rdco_intake", "approved")
        w.review(published, "ktto", "approved")
        last = w.review(published, "rdco", "approved")

        # Already dual-written: the backfill leaves it exactly as it is.
        live = w.record("live", "rdco_intake", "Thesis / Research")
        existing = RecordAssignment.objects.create(record=live, party="intake")

        _migrate(_AFTER)

        assert _rows(draft) == {}
        assert _active(adviser) == {"adviser"}
        assert _active(intake) == {"intake"}

        assert (_active(itso), _completed(itso)) == ({"itso"}, {"intake", "ktto"})
        assert _rows(itso)["itso"][1] == itso_pending.created_at
        assert (_active(parallel), _completed(parallel)) == ({"ierc", "ktto"}, {"intake", "itso"})
        assert (_active(final), _completed(final)) == ({"rdco"}, {"intake", "ierc"})

        assert (_active(by_office), _completed(by_office)) == ({"ierc", "ktto"}, {"intake", "itso"})
        request = ResubmissionRequest.objects.get(record=by_office)
        assert (request.party, request.state, request.review_id) == ("ierc", "open", ierc_decline.pk)
        assert request.assignment.party == "ierc" and request.assignment.state == "active"
        assert request.reason == "Consent form"
        assert request.created_at == ierc_decline.created_at

        # A decline at intake is Intake's request, and Intake was never passed.
        assert (_active(at_intake), _completed(at_intake)) == ({"intake"}, set())
        assert ResubmissionRequest.objects.get(record=at_intake).review_id == intake_decline.pk

        # Terminal: one completed row per distinct stage, dated from its reviews.
        assert _active(published) == set()
        assert _completed(published) == {"intake", "ktto", "rdco"}
        _state, opened, closed, closed_by = _rows(published)["intake"]
        assert opened == first_intake.created_at
        assert closed < last.created_at
        assert _rows(published)["rdco"][2:] == (last.created_at, w.rdco.pk)

        assert list(RecordAssignment.objects.filter(record=live)) == [existing]
        assert RecordAssignment.objects.filter(record=live).get().reason == ""

        # Historical routing is not invented; every backfilled row says what it is.
        assert RoutingEvent.objects.count() == 0
        assert set(
            RecordAssignment.objects.exclude(record=live).values_list("reason", flat=True)
        ) == {_MARKER}
        assert ResubmissionRequest.objects.count() == 2

        # Reverse removes what the backfill wrote, and only that.
        _migrate(_BEFORE)
        assert list(RecordAssignment.objects.all()) == [existing]
        assert ResubmissionRequest.objects.count() == 0
    finally:
        call_command("migrate", verbosity=0)


def test_a_declined_record_with_no_decline_on_record_stops_the_backfill():
    """§7.1's rule for the contract migration, applied here too: never guess."""
    _migrate(_BEFORE)
    try:
        w = _World()
        orphan = w.record("declined, no review", "declined")

        with pytest.raises(Exception, match=str(orphan.pk)):
            _migrate(_AFTER)
        assert RecordAssignment.objects.count() == 0
    finally:
        Record.objects.filter(pipeline_status="declined", reviews__isnull=True).delete()
        call_command("migrate", verbosity=0)
