"""
Workflow analytics (IR-626, ADR-043): served by `GET /api/v1/reviews/analytics/`.

**Every figure is computed from IR-144's workflow `AuditEvent`s**, replayed in
id order with the clock rule `docs/evaluation/AUDIT_EXPORT.md` writes down, so
anyone holding the audit export can reproduce it. `compute()` is the whole
arithmetic and touches no database; `workflow_analytics()` only fetches.

What the figures are not, and say so in the payload:

- **Time in stage is elapsed time**, from the party receiving the record to its
  assignment closing. It includes waits on the author (a revision request, a
  document request) and nights and weekends. It is not hands-on effort, which
  ADR-011 measures by its session protocol.
- **A turn whose start predates the log is unmeasured**, never zero: IR-144 has
  no backfill, so a close with no start is counted apart.
- **A cell with too few records shows no median.** See the two thresholds,
  which count distinct records; a record reopened under restart-all adds a
  second turn to the same cell.
- **Nothing is per reviewer.** No figure names or counts a person.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.records.models import Record
from core.enums import (
    ASSIGNABLE_PARTIES,
    OPEN_SEAT_STATES,
    AssignmentState,
    Party,
    ResubmissionRequestState,
)
from core.permissions import ROLE_RDCO, get_role_name, office_parties_of

from .deadlines import MANILA, is_overdue
from .models import RecordAssignment, ResubmissionRequest

#: Fewest distinct records a cell needs before it shows a median.
MIN_RECORDS_FOR_MEDIAN = 5
#: Fewest distinct records before it shows a 90th percentile: below ten, the
#: nearest-rank p90 is simply the slowest record.
MIN_RECORDS_FOR_P90 = 10
#: A record with no type, or one whose type was deleted.
UNSPECIFIED = "Unspecified"


@dataclass(frozen=True)
class Event:
    """One workflow `AuditEvent`, as the export carries it."""
    id: int
    event_type: str
    record: int
    created_at: datetime
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Turn:
    """One party's clock on one record: from receiving it to its close."""
    party: str
    record: int
    started_at: datetime | None
    ended_at: datetime
    how: str


@dataclass(frozen=True)
class OpenAssignment:
    """An active assignment now. `paused`: its clock waits on the owner (ADR-043 §4, §5)."""
    party: str
    due_at: datetime | None
    paused: bool
    open_seats: int


def turns(events):
    """Every closed turn in the log, in the order the clocks stopped."""
    return _replay(events)[0]


def _replay(events):
    """
    AUDIT_EXPORT.md's per-party clock, per record, in id order. Returns the
    closed turns, the `(record, party)` clocks still running, and every clock
    start as `(party, at)`.
    """
    started, done, entries = {}, [], []
    for event in sorted(events, key=lambda e: e.id):
        m, key = event.metadata, event.record
        if event.event_type == AuditEvent.SUBMITTED or (
            event.event_type == AuditEvent.ROUTED and m.get("opened")
        ):
            started[(key, m["to_party"])] = event.created_at
            entries.append((m["to_party"], event.created_at))
        elif event.event_type == AuditEvent.RESUBMITTED:
            # A revision does not stop the clock: only a party with none
            # running (a reopened office under restart_all) starts one.
            for party in m.get("rereview_parties", ()):
                if (key, party) not in started:
                    started[(key, party)] = event.created_at
                    entries.append((party, event.created_at))
        elif event.event_type == AuditEvent.ASSIGNMENT_CLOSED:
            party = m["party"]
            done.append(Turn(party, key, started.pop((key, party), None),
                             event.created_at, m["how"]))
    return done, started, entries


def _hours(delta):
    return round(delta.total_seconds() / 3600, 1)


def _p90(values):
    """Nearest rank: the smallest value at or above 90% of the sorted list."""
    return sorted(values)[math.ceil(0.9 * len(values)) - 1]


def _cell(party, record_type, cell_turns):
    hours = [(t.ended_at - t.started_at).total_seconds() / 3600 for t in cell_turns]
    records = len({t.record for t in cell_turns})
    too_few = [name for name, least in (("median", MIN_RECORDS_FOR_MEDIAN),
                                        ("p90", MIN_RECORDS_FOR_P90)) if records < least]
    return {
        "party": party,
        "record_type": record_type,
        "records": records,
        "turns": len(cell_turns),
        "median_hours": None if "median" in too_few else round(statistics.median(hours), 1),
        "p90_hours": None if "p90" in too_few else round(_p90(hours), 1),
        "too_few_for": too_few,
    }


def _time_in_stage(completed, record_types):
    by_party, by_type = defaultdict(list), defaultdict(list)
    for turn in completed:
        by_party[turn.party].append(turn)
        by_type[(turn.party, record_types.get(turn.record) or UNSPECIFIED)].append(turn)
    cells = [_cell(party, None, ts) for party, ts in sorted(by_party.items())]
    cells += [_cell(party, rtype, ts) for (party, rtype), ts
              in sorted(by_type.items())]
    return cells


def _manila_date(at):
    return at.astimezone(MANILA).date()


def _throughput(entries, closed, in_range):
    """Clock starts and closes per party per Manila week (Monday start)."""
    weeks = defaultdict(lambda: {"entered": 0, "left": 0})
    for party, at in entries:
        if in_range(at):
            weeks[(party, _week_start(at))]["entered"] += 1
    for turn in closed:
        if in_range(turn.ended_at):
            weeks[(turn.party, _week_start(turn.ended_at))]["left"] += 1
    return [{"party": party, "week_start": week.isoformat(), **counts}
            for (party, week), counts in sorted(weeks.items())]


def _week_start(at):
    day = _manila_date(at)
    return day - timedelta(days=day.weekday())


def _open_now(open_assignments, parties, now):
    """
    Active assignments per party now. Overdue is `deadline_payload`'s rule: a
    due date, a running clock, and past it. An undated assignment (opened
    before IR-619, or for a party with no Turnaround) is counted as undated,
    never as on time.
    """
    rows = {p: {"party": p, "open_count": 0, "unseated": 0, "open_seats": 0, "undated": 0,
                "paused": 0, "overdue": 0, "overdue_seats": 0} for p in parties}
    for a in open_assignments:
        row = rows.get(a.party)
        if row is None:
            continue
        overdue = is_overdue(a.due_at, paused=a.paused, now=now)
        row["open_count"] += 1
        row["unseated"] += a.open_seats == 0
        row["open_seats"] += a.open_seats
        row["undated"] += a.due_at is None
        row["paused"] += a.paused
        row["overdue"] += overdue
        row["overdue_seats"] += a.open_seats if overdue else 0
    return [rows[p] for p in sorted(rows)]


def compute(events, *, parties, record_types, now, open_assignments=(),
            date_from=None, date_to=None):
    """
    The whole analytics payload from an event log. No database.

    `date_from` and `date_to` are inclusive Manila dates. A turn is kept by
    when it ended, so one that began before the range still counts in full;
    throughput and revision cycles are kept by when their event happened.
    """
    parties = set(parties)

    def in_range(at):
        day = _manila_date(at)
        return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)

    closed, running, entries = _replay(events)
    closed = [t for t in closed if t.party in parties]
    entries = [(p, at) for p, at in entries if p in parties]
    in_window = [t for t in closed if in_range(t.ended_at)]
    completed = [t for t in in_window if t.how == AssignmentState.COMPLETED and t.started_at is not None]
    return {
        "open_now": _open_now(open_assignments, parties, now),
        "time_in_stage": _time_in_stage(completed, record_types),
        "unmeasured": _unmeasured(in_window, running, parties),
        "throughput": _throughput(entries, closed, in_range),
        **_revision_cycles(events, parties, in_range),
    }


def _revision_cycles(events, parties, in_range):
    """
    New Versions that answered a revision request, and the clearances each one
    preserved (ADR-003). An office sees the cycles it took part in: those that
    re-reviewed, reset or preserved it.
    """
    cycles = defaultdict(lambda: {"cycles": 0, "cycles_preserving": 0, "preserved_clearances": 0})
    by_office = defaultdict(int)
    for event in events:
        if not in_range(event.created_at):
            continue
        m = event.metadata
        if event.event_type == AuditEvent.RESUBMITTED:
            involved = (set(m.get("rereview_parties", ())) | set(m.get("reset_parties", ()))
                        | set(m.get("preserved_parties", ())))
            if involved & parties:
                row = cycles[m["policy"]]
                row["cycles"] += 1
                row["cycles_preserving"] += bool(set(m.get("preserved_parties", ())) & parties)
        elif event.event_type == AuditEvent.CLEARANCE_PRESERVED and m["party"] in parties:
            cycles[m["policy"]]["preserved_clearances"] += 1
            by_office[(m["party"], m["policy"])] += 1
    return {
        "revision_cycles": [{"policy": policy, **row} for policy, row in sorted(cycles.items())],
        "preserved_by_office": [
            {"party": party, "policy": policy, "preserved_clearances": n}
            for (party, policy), n in sorted(by_office.items())
        ],
    }


def _unmeasured(closed, running, parties):
    """What time in stage leaves out, per party, so its absence is visible."""
    rows = {p: {"party": p, "started_before_log": 0, "ended_not_completed": 0, "still_open": 0}
            for p in parties}
    for turn in closed:
        if turn.started_at is None:
            rows[turn.party]["started_before_log"] += 1
        elif turn.how != AssignmentState.COMPLETED:
            rows[turn.party]["ended_not_completed"] += 1
    for _record, party in running:
        if party in rows:
            rows[party]["still_open"] += 1
    return [rows[p] for p in sorted(rows)]


# --- fetching: the only part that touches the database -----------------------

#: The event types `compute()` reads. Everything else is left in the database.
READ_EVENT_TYPES = (
    AuditEvent.SUBMITTED, AuditEvent.ROUTED, AuditEvent.RESUBMITTED,
    AuditEvent.ASSIGNMENT_CLOSED, AuditEvent.CLEARANCE_PRESERVED,
)


class AnalyticsRefused(Exception):
    """The caller asked for an office that is not theirs."""


class AnalyticsError(Exception):
    """A filter that cannot be read."""


def parties_for(user):
    """
    Whose figures `user` may read: RDCO every assignable party (the Adviser
    stage included), any other office its own (ADR-043). Anyone else none.
    """
    if get_role_name(user) == ROLE_RDCO:
        return tuple(str(p) for p in ASSIGNABLE_PARTIES)
    return tuple(sorted(office_parties_of(user)))


def scoped_events(parties):
    """
    The workflow events that concern `parties`, and no others. This is where
    an office's scope is enforced: a row about only another office never
    leaves the database. A shared row (a new Version names every party it
    touched) does, and `compute()` reads only the scoped parties from it. A party appears as `to_party` (a start), `party` (a close or a
    preserved clearance), or in a new Version's party lists.
    """
    names = Q()
    for party in parties:
        names |= (Q(metadata__to_party=party) | Q(metadata__party=party)
                  | Q(metadata__rereview_parties__contains=[party])
                  | Q(metadata__reset_parties__contains=[party])
                  | Q(metadata__preserved_parties__contains=[party]))
    if not parties:
        return AuditEvent.objects.none()
    return AuditEvent.objects.filter(names, event_type__in=READ_EVENT_TYPES).order_by("id")


def scoped_open_assignments(parties):
    """Active assignments of `parties` now, each with its open-seat count."""
    open_revision = ResubmissionRequest.objects.filter(
        assignment=OuterRef("pk"), state=ResubmissionRequestState.OPEN)
    rows = (
        RecordAssignment.objects
        .filter(party__in=parties, state=AssignmentState.ACTIVE)
        .annotate(open_seats=Count("seats", filter=Q(seats__state__in=OPEN_SEAT_STATES)),
                  revision_open=Exists(open_revision))
        .values_list("party", "due_at", "document_pause_started_at", "revision_open", "open_seats")
    )
    return [OpenAssignment(party, due, paused=bool(pause) or revision, open_seats=seats)
            for party, due, pause, revision, seats in rows]


def _date(params, name):
    value = params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise AnalyticsError(f"`{name}` must be a date, YYYY-MM-DD.") from None


def workflow_analytics(user, params):
    """The payload for `user`, narrowed by `office`, `from` and `to`."""
    parties = parties_for(user)
    office = params.get("office")
    if office:
        if office not in {str(p) for p in ASSIGNABLE_PARTIES}:
            raise AnalyticsError(f"Unknown office `{office}`.")
        if office not in parties:
            raise AnalyticsRefused("You may read your own office's analytics only.")
        parties = (office,)
    date_from, date_to = _date(params, "from"), _date(params, "to")
    if date_from and date_to and date_from > date_to:
        raise AnalyticsError("`from` must not be after `to`.")

    # The whole history, not the range: a turn ending in range may have
    # started before it, and "still open" means open now, like `open_now`.
    rows = list(scoped_events(parties))
    events = [Event(r.pk, r.event_type, r.record_id, r.created_at, r.metadata) for r in rows]
    record_types = dict(
        Record.objects.with_deleted()
        .filter(pk__in={e.record for e in events})
        .values_list("pk", "record_type__name")
    )
    now = timezone.now()
    payload = compute(
        events, parties=parties, record_types=record_types, now=now,
        open_assignments=scoped_open_assignments(parties),
        date_from=date_from, date_to=date_to,
    )
    labels = dict(Party.choices)
    return {
        "parties": [{"party": p, "label": labels[p]} for p in parties],
        "data_since": min((e.created_at for e in events), default=None),
        "generated_at": now,
        "range": {"from": date_from, "to": date_to},
        "thresholds": {"median": MIN_RECORDS_FOR_MEDIAN, "p90": MIN_RECORDS_FOR_P90},
        **payload,
    }
