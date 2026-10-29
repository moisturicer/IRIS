"""
IR-626: workflow analytics, reproduced from fixture event logs.

Every expected figure below is worked by hand from the log it sits beside,
never recomputed the way `analytics` computes it.
"""
from datetime import date, datetime, timedelta, timezone as tz
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.records.models import Record, RecordType
from apps.reviews import analytics
from apps.reviews.analytics import Event
from apps.reviews.models import RecordAssignment, ReviewerSeat
from apps.tests.test_authorization_matrix import make_user

T0 = datetime(2026, 11, 2, 1, 0, tzinfo=tz.utc)  # Monday 09:00 Manila


class Log:
    """Builds an event log in id order, with times as hours after T0."""

    def __init__(self):
        self.events = []

    def add(self, event_type, record, hours, **metadata):
        self.events.append(Event(
            id=len(self.events) + 1, event_type=event_type, record=record,
            created_at=T0 + timedelta(hours=hours), metadata=metadata,
        ))
        return self

    def routed(self, record, hours, party, opened=True):
        return self.add(AuditEvent.ROUTED, record, hours, from_party="adviser",
                        to_party=party, opened=opened, nominee=None, group="g", hand_back=False)

    def closed(self, record, hours, party, how="completed"):
        return self.add(AuditEvent.ASSIGNMENT_CLOSED, record, hours, party=party,
                        assignment=record, how=how, decision=None, withdrawn_seats=[])


def compute(log, parties=("itso",), record_types=None, **kwargs):
    return analytics.compute(
        log.events, parties=parties, record_types=record_types or {},
        now=T0 + timedelta(days=30), **kwargs,
    )


def cell(result, party, record_type=None):
    return next(c for c in result["time_in_stage"]
                if c["party"] == party and c["record_type"] == record_type)


def test_time_in_stage_median_from_completed_turns():
    log = Log()
    for record, hours in enumerate((10, 20, 30, 40, 50), start=1):
        log.routed(record, 0, "itso").closed(record, hours, "itso")

    itso = cell(compute(log), "itso")

    assert itso["records"] == 5
    assert itso["turns"] == 5
    assert itso["median_hours"] == 30.0
    # Five records is enough for a median, not for a 90th percentile.
    assert itso["p90_hours"] is None
    assert itso["too_few_for"] == ["p90"]


def test_revisions_and_reassignment_do_not_restart_a_running_clock():
    # Record 1: ITSO routed at 0h, asks for a revision at 5h, the owner answers
    # at 50h, a coordinator reassigns the seat at 60h, ITSO closes at 70h.
    # Elapsed time in stage is the whole 70h: the author's wait is inside it.
    log = Log().routed(1, 0, "itso")
    log.add(AuditEvent.RESUBMISSION_REQUESTED, 1, 5, party="itso", request=1, reason="x", version=1)
    log.add(AuditEvent.DOCUMENT_REQUESTED, 1, 6, party="itso", request=2, items=[], message="m")
    log.add(AuditEvent.RESUBMITTED, 1, 50, version=2, policy="clearance_aware", requests=[1],
            rereview_parties=["itso"], reset_parties=["itso"], preserved_parties=[])
    log.add(AuditEvent.SEAT_REASSIGNED, 1, 60, party="itso", assignment=1, seat=9, reviewer=4,
            source="assigned", previous_seat=8, previous_reviewer=3)
    log.closed(1, 70, "itso")

    measured = analytics.turns(log.events)

    assert [(t.party, t.ended_at - t.started_at) for t in measured] == [("itso", timedelta(hours=70))]


def test_a_document_request_pause_moves_the_due_date_but_not_the_elapsed_time():
    # ITSO routed at 0h, asks for documents at 2h, the owner uploads at 50h
    # and the pause moves the due date (a system Extension); ITSO closes at
    # 60h. The pause is a deadline rule (ADR-043 §4), not a clock stop.
    log = Log().routed(1, 0, "itso")
    log.add(AuditEvent.DOCUMENT_REQUESTED, 1, 2, party="itso", request=1, items=[], message="m")
    log.add(AuditEvent.DOCUMENT_REQUEST_FULFILLED, 1, 50, party="itso", request=1, items=[])
    log.add(AuditEvent.ASSIGNMENT_EXTENDED, 1, 50, assignment=1, party="itso", extension=1,
            previous_due_at="x", due_at="y", reason="Document request pause: 2 working days.",
            system=True)
    log.closed(1, 60, "itso")

    assert [t.ended_at - t.started_at for t in analytics.turns(log.events)] == [timedelta(hours=60)]


def test_a_reopened_office_gets_a_second_clock_under_restart_all():
    # ITSO cleared at 10h; IERC asked; the new version at 40h reopens ITSO,
    # which closes again at 46h. Two ITSO turns: 10h and 6h.
    log = Log().routed(1, 0, "itso").routed(1, 0, "ierc").closed(1, 10, "itso")
    log.add(AuditEvent.RESUBMITTED, 1, 40, version=2, policy="restart_all", requests=[1],
            rereview_parties=["ierc", "itso"], reset_parties=["itso", "ierc"], preserved_parties=[])
    log.closed(1, 46, "itso").closed(1, 48, "ierc")

    itso = [t.ended_at - t.started_at for t in analytics.turns(log.events) if t.party == "itso"]

    assert itso == [timedelta(hours=10), timedelta(hours=6)]


def test_turns_with_no_start_or_that_were_ended_are_counted_apart_never_as_zero():
    log = Log()
    log.closed(1, 3, "itso")                                    # opened before IR-144's log
    log.routed(2, 0, "itso").closed(2, 4, "itso", how="withdrawn")
    log.routed(3, 0, "itso").closed(3, 5, "itso", how="closed_by_decision")
    log.routed(4, 0, "itso").closed(4, 8, "itso")
    log.routed(5, 0, "itso")                                    # still open

    result = compute(log)

    assert cell(result, "itso")["turns"] == 1
    assert result["unmeasured"] == [{
        "party": "itso", "started_before_log": 1, "ended_not_completed": 2, "still_open": 1,
    }]


def test_p90_is_nearest_rank_once_ten_records_exist_and_cells_split_by_record_type():
    log, types = Log(), {}
    for record in range(1, 11):          # 1h, 2h, ... 10h
        log.routed(record, 0, "itso").closed(record, record, "itso")
        types[record] = "Thesis / Research" if record <= 6 else "Proposal"

    result = compute(log, record_types=types)

    itso = cell(result, "itso")
    assert (itso["median_hours"], itso["p90_hours"], itso["too_few_for"]) == (5.5, 9.0, [])
    thesis = cell(result, "itso", "Thesis / Research")
    assert (thesis["records"], thesis["median_hours"], thesis["p90_hours"]) == (6, 3.5, None)
    proposal = cell(result, "itso", "Proposal")
    assert (proposal["records"], proposal["median_hours"], proposal["too_few_for"]) == (
        4, None, ["median", "p90"])


def test_only_the_scoped_parties_are_reported():
    log = Log()
    for record in range(1, 6):
        log.routed(record, 0, "itso").closed(record, 2, "itso")
        log.routed(record, 0, "ierc").closed(record, 3, "ierc")

    result = compute(log, parties=("ierc",))

    assert {c["party"] for c in result["time_in_stage"]} == {"ierc"}


def test_throughput_counts_entries_and_exits_per_manila_week():
    # T0 is Monday 2 Nov, 09:00 Manila. 160h later is Sunday 8 Nov 17:00 UTC,
    # already Monday 9 Nov 01:00 in Manila, so it falls in the second week.
    log = Log().routed(1, 0, "itso").routed(2, 10, "itso").closed(1, 160, "itso")
    log.add(AuditEvent.SUBMITTED, 3, 11, to_party="adviser", version=1)

    result = compute(log, parties=("adviser", "itso"))

    assert result["throughput"] == [
        {"party": "adviser", "week_start": "2026-11-02", "entered": 1, "left": 0},
        {"party": "itso", "week_start": "2026-11-02", "entered": 2, "left": 0},
        {"party": "itso", "week_start": "2026-11-09", "entered": 0, "left": 1},
    ]


def test_a_date_range_keeps_turns_by_when_they_ended_and_events_by_when_they_happened():
    # Record 1 enters in week one and leaves in week two; record 2 lives in
    # week one only. Asking for week two alone keeps record 1's whole turn,
    # including the time before the range began, and only week two's exit.
    log = Log().routed(1, 0, "itso").routed(2, 0, "itso").closed(2, 2, "itso")
    log.closed(1, 200, "itso")

    result = compute(log, date_from=date(2026, 11, 9), date_to=date(2026, 11, 15))

    assert cell(result, "itso")["turns"] == 1
    assert result["throughput"] == [
        {"party": "itso", "week_start": "2026-11-09", "entered": 0, "left": 1},
    ]


def revision_log():
    """
    Three new Versions. Record 1 (clearance-aware): IERC asked, ITSO's and
    KTTO's clearances survived. Record 2 (clearance-aware): ITSO asked, nothing
    else had cleared. Record 3 (restart-all): IERC asked, ITSO was reopened.
    """
    log = Log()

    def resubmitted(record, policy, rereview, reset, preserved):
        log.add(AuditEvent.RESUBMITTED, record, 20, version=2, policy=policy, requests=[record],
                rereview_parties=rereview, reset_parties=reset, preserved_parties=preserved)
        for party in preserved:
            log.add(AuditEvent.CLEARANCE_PRESERVED, record, 20, party=party, version=2, policy=policy)

    resubmitted(1, "clearance_aware", ["ierc"], ["ierc"], ["itso", "ktto"])
    resubmitted(2, "clearance_aware", ["itso"], ["itso"], [])
    resubmitted(3, "restart_all", ["ierc", "itso"], ["itso", "ierc"], [])
    return log


def test_rdco_sees_every_revision_cycle_and_every_preserved_clearance():
    result = compute(revision_log(), parties=("adviser", "itso", "ierc", "ktto", "rdco"))

    assert result["revision_cycles"] == [
        {"policy": "clearance_aware", "cycles": 2, "cycles_preserving": 1, "preserved_clearances": 2},
        {"policy": "restart_all", "cycles": 1, "cycles_preserving": 0, "preserved_clearances": 0},
    ]
    assert result["preserved_by_office"] == [
        {"party": "itso", "policy": "clearance_aware", "preserved_clearances": 1},
        {"party": "ktto", "policy": "clearance_aware", "preserved_clearances": 1},
    ]


def test_an_office_sees_only_the_cycles_its_own_office_took_part_in():
    itso = compute(revision_log(), parties=("itso",))
    ktto = compute(revision_log(), parties=("ktto",))

    assert itso["revision_cycles"] == [
        {"policy": "clearance_aware", "cycles": 2, "cycles_preserving": 1, "preserved_clearances": 1},
        {"policy": "restart_all", "cycles": 1, "cycles_preserving": 0, "preserved_clearances": 0},
    ]
    assert ktto["revision_cycles"] == [
        {"policy": "clearance_aware", "cycles": 1, "cycles_preserving": 1, "preserved_clearances": 1},
    ]
    assert ktto["preserved_by_office"] == [
        {"party": "ktto", "policy": "clearance_aware", "preserved_clearances": 1},
    ]


def test_open_and_overdue_now_from_the_open_assignments():
    # `now` is T0 + 30 days.
    late, later = T0 + timedelta(days=1), T0 + timedelta(days=40)
    open_now = [
        analytics.OpenAssignment("itso", due_at=None, paused=False, open_seats=0),   # pool, undated
        analytics.OpenAssignment("itso", due_at=late, paused=False, open_seats=2),   # overdue
        analytics.OpenAssignment("itso", due_at=late, paused=True, open_seats=1),    # waiting on owner
        analytics.OpenAssignment("itso", due_at=later, paused=False, open_seats=1),  # on time
        analytics.OpenAssignment("ierc", due_at=late, paused=False, open_seats=1),   # out of scope
    ]

    result = compute(Log(), parties=("itso", "ktto"), open_assignments=open_now)

    assert result["open_now"] == [
        {"party": "itso", "open_count": 4, "unseated": 1, "open_seats": 4, "undated": 1,
         "paused": 1, "overdue": 1, "overdue_seats": 2},
        {"party": "ktto", "open_count": 0, "unseated": 0, "open_seats": 0, "undated": 0,
         "paused": 0, "overdue": 0, "overdue_seats": 0},
    ]


# --- the endpoint: GET /api/v1/reviews/analytics/ ---------------------------


@pytest.mark.db_required
class AnalyticsEndpointTests(APITestCase):
    """The same arithmetic through the database, scoped to who is asking."""

    def setUp(self):
        self.itso = make_user("analytics-itso@cit.edu", "ITSO")
        self.rdco = make_user("analytics-rdco@cit.edu", "RDCO")
        owner = make_user("analytics-owner@cit.edu", "Student")
        self.thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.records = [
            Record.objects.create(title=f"Analytics {n}", record_type=self.thesis,
                                  added_by=owner, pipeline_status="in_review")
            for n in range(6)
        ]

    def event(self, event_type, record, hours, **metadata):
        # `created_at` is auto_now_add and the table is insert-only, so the
        # clock is set at insertion.
        with mock.patch("django.utils.timezone.now", return_value=T0 + timedelta(hours=hours)):
            AuditEvent.objects.create(event_type=event_type, record=record, metadata=metadata)

    def turn(self, record, party, start, end):
        self.event(AuditEvent.ROUTED, record, start, from_party="adviser", to_party=party,
                   opened=True, nominee=None, group="g", hand_back=False)
        self.event(AuditEvent.ASSIGNMENT_CLOSED, record, end, party=party, assignment=1,
                   how="completed", decision=None, withdrawn_seats=[])

    def get(self, user, **params):
        self.client.force_authenticate(user)
        return self.client.get(reverse("reviews-analytics"), params)

    def test_an_office_sees_its_own_figures_reproduced_from_the_log(self):
        for record, hours in zip(self.records, (10, 20, 30, 40, 50)):
            self.turn(record, "itso", 0, hours)
            self.turn(record, "ierc", 0, 1)
        overdue = RecordAssignment.objects.create(record=self.records[5], party="itso")
        # Opening samples the Turnaround; this one fell due yesterday.
        yesterday = datetime.now(tz.utc) - timedelta(days=1)
        RecordAssignment.objects.filter(pk=overdue.pk).update(due_at=yesterday, original_due_at=yesterday)
        ReviewerSeat.objects.create(assignment=overdue, reviewer=self.itso, source="claimed")

        response = self.get(self.itso)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["parties"], [{"party": "itso", "label": "ITSO"}])
        by_office = next(c for c in data["time_in_stage"] if c["record_type"] is None)
        self.assertEqual((by_office["party"], by_office["records"], by_office["median_hours"]),
                         ("itso", 5, 30.0))
        by_type = next(c for c in data["time_in_stage"] if c["record_type"] is not None)
        self.assertEqual(by_type["record_type"], "Thesis / Research")
        self.assertEqual(data["open_now"], [{
            "party": "itso", "open_count": 1, "unseated": 0, "open_seats": 1, "undated": 0,
            "paused": 0, "overdue": 1, "overdue_seats": 1,
        }])
        self.assertNotIn("ierc", str([c["party"] for key in ("time_in_stage", "throughput",
                                                               "open_now", "unmeasured")
                                      for c in data[key]]))
        self.assertEqual(data["data_since"], T0.isoformat().replace("+00:00", "Z"))

    def test_rdco_sees_every_party_and_may_narrow_to_one(self):
        self.turn(self.records[0], "ierc", 0, 3)
        self.turn(self.records[0], "itso", 0, 4)

        everyone = self.get(self.rdco).json()
        ierc = self.get(self.rdco, office="ierc").json()

        self.assertEqual([p["party"] for p in everyone["parties"]],
                         ["adviser", "itso", "ierc", "ktto", "rdco"])
        self.assertEqual({row["party"] for row in ierc["throughput"]}, {"ierc"})

    def test_scoping_removes_other_offices_before_events_are_loaded(self):
        self.turn(self.records[0], "itso", 0, 4)
        self.turn(self.records[1], "ierc", 0, 8)
        scoped = list(analytics.scoped_events(("itso",)))
        self.assertEqual(len(scoped), 2)
        self.assertTrue(all(
            (event.metadata.get("party") or event.metadata.get("to_party")) == "itso"
            for event in scoped
        ))
        RecordAssignment.objects.create(record=self.records[0], party="itso")
        RecordAssignment.objects.create(record=self.records[1], party="ierc")
        self.assertEqual(
            [assignment.party for assignment in analytics.scoped_open_assignments(("itso",))],
            ["itso"],
        )

    def test_an_office_may_not_ask_for_another_office(self):
        self.assertEqual(self.get(self.itso, office="ierc").status_code, 403)
        self.assertEqual(self.get(self.itso, office="itso").status_code, 200)

    def test_a_malformed_filter_is_refused(self):
        self.assertEqual(self.get(self.rdco, office="nobody").status_code, 400)
        self.assertEqual(self.get(self.rdco, **{"from": "29-10-2026"}).status_code, 400)
        self.assertEqual(self.get(self.rdco, **{"from": "2026-11-10", "to": "2026-11-01"}).status_code, 400)

    def test_nothing_in_the_payload_identifies_a_reviewer(self):
        self.turn(self.records[0], "itso", 0, 4)
        self.event(AuditEvent.SEAT_CLAIMED, self.records[0], 1, party="itso", assignment=1,
                   seat=1, reviewer=self.itso.pk, source="claimed")

        data = self.get(self.rdco).json()

        def keys(value):
            if isinstance(value, dict):
                for key, inner in value.items():
                    yield key
                    yield from keys(inner)
            elif isinstance(value, list):
                for inner in value:
                    yield from keys(inner)

        self.assertFalse({"reviewer", "user", "holder", "seat"} & set(keys(data)))

    def test_with_no_log_the_page_says_there_is_no_data_yet(self):
        data = self.get(self.rdco).json()

        self.assertIsNone(data["data_since"])
        self.assertEqual(data["time_in_stage"], [])
