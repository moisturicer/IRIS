"""
The coordinator console (IR-623): `GET /api/v1/reviews/office/`.

One office's open work as its coordinator sees it -- every unfinished seat
and every unclaimed pool assignment, with its due date -- and each member's
load. It adds no decision right: the acts on it are IR-415's seat endpoints
and IR-619's extension, each refused on its own.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, ReviewerSeat
from core.enums import (
    AssignmentState,
    Party,
    PipelineStatus,
    RecordTypeName,
    RoleName,
    SeatSource,
    SeatState,
)

from .workflow_test_helpers import make_user

URL = reverse("reviews-office")
MANILA = ZoneInfo("Asia/Manila")


class OfficeConsoleTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("console-owner@cit.edu", RoleName.STUDENT)
        cls.maria = make_user("console-maria@cit.edu", RoleName.ITSO)
        cls.maria.first_name, cls.maria.last_name = "Maria", "Reyes"
        cls.maria.save(update_fields=["first_name", "last_name"])
        cls.juan = make_user("console-juan@cit.edu", RoleName.ITSO)
        cls.juan.first_name, cls.juan.last_name = "Juan", "Santos"
        cls.juan.save(update_fields=["first_name", "last_name"])
        cls.coordinator = make_user("console-coord@cit.edu", RoleName.ITSO)
        cls.coordinator.first_name, cls.coordinator.last_name = "Cora", "Dinator"
        cls.coordinator.is_office_coordinator = True
        cls.coordinator.save(update_fields=["first_name", "last_name", "is_office_coordinator"])
        cls.ierc_coordinator = make_user("console-ierc-coord@cit.edu", RoleName.IERC)
        cls.ierc_coordinator.is_office_coordinator = True
        cls.ierc_coordinator.save(update_fields=["is_office_coordinator"])
        cls.rdco = make_user("console-rdco@cit.edu", RoleName.RDCO)

    def record(self, title, pipeline_status=PipelineStatus.IN_REVIEW):
        record = Record.objects.create(
            title=title, abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            added_by=self.owner, pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def assignment(self, record, party=Party.ITSO, *, due_in_days=None):
        assignment = RecordAssignment.objects.create(record=record, party=party)
        if due_in_days is not None:
            due = timezone.now() + timedelta(days=due_in_days)
            RecordAssignment.objects.filter(pk=assignment.pk).update(due_at=due, original_due_at=due)
            assignment.refresh_from_db()
        return assignment

    def seat(self, assignment, reviewer, state=SeatState.ASSIGNED):
        return ReviewerSeat.objects.create(
            assignment=assignment, reviewer=reviewer, state=state, source=SeatSource.CLAIMED,
        )

    def get(self, user, **params):
        self.client.force_authenticate(user)
        return self.client.get(URL, params)

    # -- what it lists ---------------------------------------------------------

    def test_lists_open_seats_and_unclaimed_pool_with_due_dates(self):
        overdue = self.assignment(self.record("Overdue thesis"), due_in_days=-2)
        seat = self.seat(overdue, self.maria, SeatState.IN_REVIEW)
        pool = self.assignment(self.record("Unclaimed thesis"), due_in_days=3)

        response = self.get(self.coordinator, office="itso")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["office"], response.data["office_label"]), ("itso", "ITSO"))
        rows = response.data["rows"]
        self.assertEqual(
            [(r["kind"], r["title"], r["seat"], r["assignment"], r["reviewer_name"], r["is_overdue"])
             for r in rows],
            [
                ("seat", "Overdue thesis", seat.pk, overdue.pk, "Maria Reyes", True),
                ("pool", "Unclaimed thesis", None, pool.pk, None, False),
            ],
        )
        self.assertEqual(rows[0]["seat_state"], SeatState.IN_REVIEW)
        self.assertEqual(rows[0]["opened_at"], overdue.opened_at.isoformat())
        self.assertIsNotNone(rows[1]["due_at"])
        # The coordinator may extend a running clock: IR-619's own predicate.
        self.assertTrue(rows[0]["can_extend"])

    def test_orders_overdue_first_then_soonest_due_then_undated(self):
        later = self.assignment(self.record("Due later"), due_in_days=9)
        undated = self.assignment(self.record("No turnaround"))
        sooner = self.assignment(self.record("Due sooner"), due_in_days=1)
        late = self.assignment(self.record("Late"), due_in_days=-1)

        rows = self.get(self.coordinator, office="itso").data["rows"]

        self.assertEqual([r["assignment"] for r in rows], [late.pk, sooner.pk, later.pk, undated.pk])

    def test_leaves_out_finished_withdrawn_closed_other_office_and_not_in_review(self):
        done = self.assignment(self.record("Finished"))
        self.seat(done, self.maria, SeatState.DONE)
        withdrawn = self.assignment(self.record("Withdrawn then claimed"))
        self.seat(withdrawn, self.juan, SeatState.WITHDRAWN)
        kept = self.seat(withdrawn, self.maria)
        closed = self.assignment(self.record("Closed"))
        RecordAssignment.objects.filter(pk=closed.pk).update(state=AssignmentState.COMPLETED)
        self.assignment(self.record("At IERC"), Party.IERC)
        self.assignment(self.record("A draft", PipelineStatus.DRAFT))

        rows = self.get(self.coordinator, office="itso").data["rows"]

        self.assertEqual([(r["kind"], r["seat"]) for r in rows], [("seat", kept.pk)])

    def test_load_counts_each_members_open_and_overdue_seats(self):
        self.seat(self.assignment(self.record("A"), due_in_days=-1), self.maria)
        self.seat(self.assignment(self.record("B"), due_in_days=4), self.maria, SeatState.IN_REVIEW)
        self.seat(self.assignment(self.record("C")), self.maria, SeatState.DONE)

        load = self.get(self.coordinator, office="itso").data["load"]

        self.assertEqual(
            [(m["name"], m["open_count"], m["overdue"]) for m in load],
            # Every member, idle ones too, so the coordinator sees who is free.
            [("Cora Dinator", 0, 0), ("Maria Reyes", 2, 1), ("Juan Santos", 0, 0)],
        )

    def test_without_an_office_it_answers_for_the_office_the_caller_coordinates(self):
        self.assignment(self.record("Unclaimed"))

        response = self.get(self.coordinator)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["office"], "itso")

    def test_query_count_does_not_grow_with_rows(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.get(self.coordinator, office="itso").status_code, 200)
            return len(ctx.captured_queries)

        self.seat(self.assignment(self.record("One"), due_in_days=2), self.maria)
        self.assignment(self.record("Two"), due_in_days=2)
        baseline = count()
        for n in range(4):
            self.seat(self.assignment(self.record(f"More {n}"), due_in_days=2), self.juan)
            self.assignment(self.record(f"Pool {n}"), due_in_days=2)
        self.assertEqual(count(), baseline)

    # -- who may read it -------------------------------------------------------

    def test_only_a_coordinator_of_that_office_may_read_it(self):
        self.assignment(self.record("Unclaimed"))
        for user, office in (
            (self.maria, "itso"),             # a member, not a coordinator
            (self.ierc_coordinator, "itso"),  # another office's coordinator
            (self.rdco, "itso"),
            (self.maria, None),
            (self.owner, None),
        ):
            with self.subTest(user=user.email, office=office):
                response = self.get(user, **({"office": office} if office else {}))
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    # -- the acts it offers land on the Review timeline -------------------------

    def test_reassignment_and_extension_reach_the_tracker_with_their_reasons(self):
        record = self.record("Reassigned thesis")
        assignment = self.assignment(record, due_in_days=2)
        seat = self.seat(assignment, self.maria, SeatState.IN_REVIEW)
        self.client.force_authenticate(self.coordinator)
        moved = self.client.post(
            reverse("seat-reassign", args=[seat.pk]),
            {"reviewer": self.juan.pk, "reason": "Maria is on leave."}, format="json",
        )
        self.assertEqual(moved.status_code, status.HTTP_201_CREATED, moved.data)
        new_due = datetime.combine(
            assignment.due_at.astimezone(MANILA).date() + timedelta(days=3), time(23, 59), tzinfo=MANILA,
        )
        extended = self.client.post(
            reverse("assignment-extend", args=[assignment.pk]),
            {"due_at": new_due.isoformat(), "reason": "Committee meets Friday."}, format="json",
        )
        self.assertEqual(extended.status_code, status.HTTP_200_OK, extended.data)

        tracker = self.client.get(f"/api/v1/records/{record.pk}/tracker/").data

        [reassigned] = tracker["reassignments"]
        self.assertEqual(
            {k: reassigned[k] for k in ("party", "label", "from_name", "to_name", "by_name", "reason")},
            {"party": "itso", "label": "ITSO", "from_name": "Maria Reyes", "to_name": "Juan Santos",
             "by_name": "Cora Dinator", "reason": "Maria is on leave."},
        )
        self.assertIsNotNone(reassigned["at"])
        [history] = [h for h in tracker["assignment_deadline_history"] if h["assignment"] == assignment.pk]
        self.assertEqual(history["label"], "ITSO")
        [extension] = history["extensions"]
        self.assertEqual(
            (extension["reason"], extension["actor_name"]), ("Committee meets Friday.", "Cora Dinator"),
        )

    def test_who_reassigned_and_why_are_review_content(self):
        record = self.record("Reassigned thesis")
        seat = self.seat(self.assignment(record), self.maria)
        self.client.force_authenticate(self.coordinator)
        self.client.post(
            reverse("seat-reassign", args=[seat.pk]),
            {"reviewer": self.juan.pk, "reason": "Maria is on leave."}, format="json",
        )

        # RDCO reads the record but holds no part in its review (IR-479).
        self.client.force_authenticate(self.rdco)
        [reassigned] = self.client.get(f"/api/v1/records/{record.pk}/tracker/").data["reassignments"]

        self.assertEqual(
            {k: reassigned[k] for k in ("party", "from_name", "to_name", "by_name", "reason")},
            {"party": "itso", "from_name": None, "to_name": None, "by_name": None, "reason": None},
        )

    def test_anonymous_is_refused(self):
        self.assertIn(
            self.client.get(URL).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
