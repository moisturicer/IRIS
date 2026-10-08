"""
My Reviews: a reviewer's own seats, plus their office's pool (ADR-032 §9 and its
2026-10-08 Amendment, IR-268). Served by `GET /api/v1/reviews/mine/`.

**Current work and history are sourced differently.**

- **To review** and **In review** are current work, and split by model. A
  record on the new model (`in_review`) comes from seats and pools. Every other
  record comes from the old pipeline's own per-role queue, unchanged until
  IR-260, which puts its pending work in To review. The shadow pools cannot
  stand in for that queue: IERC is active at `itso_review` before it may act,
  a `declined` record keeps its requester active, and RDCO's intake work sits
  under `intake`.
- **Done** is history, and is never split by model or `pipeline_status` -- a
  new-model record that gets published is no longer `in_review`. It is the
  union of (1) every `done` seat, and (2) every `Review` with no seat behind it
  that My Reviews already shows: no `done` seat of its author on its
  assignment, and no open one on a record whose current work comes from seats.
  (2) is the old pipeline's history from before IR-415, which the seat backfill
  did not seat. Its second clause keeps a revision request out of Done while
  its author's seat is still open, so one piece of work is never both current
  and history.

**A Done row's outcome is the reviewer's own verdict `Review`**, derived
(`ReviewOutcome`) and never stored. The outcome filter runs in the database,
on annotations that `_outcome()` reads back, so a page of a filter is a page.

**The query count is flat in the number of rows.** Everything a row needs is
read in a fixed number of queries per page, never per row.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Exists, F, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.documents.models import DocumentRequest
from apps.records.models import Record, RecordOwner
from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    ClearanceStatus,
    DocumentRequestState,
    MyReviewsTab,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    ReviewDecision,
    ReviewOutcome,
    ReviewStage,
    RoleName,
    SeatSource,
    SeatState,
)
from core.permissions import (
    get_role_name,
    is_office_coordinator,
    is_office_member,
    office_parties_of,
)

from .models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    ReviewerSeat,
    RoutingEvent,
)

PAGE_SIZE = 50

#: The specialist offices: their `approved` is a clearance, not an acceptance.
SPECIALIST_STAGES = (ReviewStage.ITSO, ReviewStage.IERC, ReviewStage.KTTO)

#: Row kinds. A pool row is an office's assignment nobody is seated on; a
#: legacy row is the old pipeline's queue; a review row is a Done decision with
#: no seat behind it.
SEAT, POOL, LEGACY, REVIEW = "seat", "pool", "legacy", "review"

#: Done's two sources, in the order a tie on time breaks (descending).
_RANK = {SEAT: 1, REVIEW: 0}

#: The old pipeline's queue, per role: the statuses each role acts at today.
#: Moved here from the retired `/reviews/pending/`, unchanged (ADR-032 §9
#: Amendment: old-pipeline records stay exactly where they are until IR-260).
_LEGACY_STATUSES = {
    RoleName.ADVISER: (PipelineStatus.ADVISER_REVIEW,),
    RoleName.RDCO: (PipelineStatus.RDCO_INTAKE, PipelineStatus.RDCO_REVIEW),
    RoleName.ITSO: (PipelineStatus.ITSO_REVIEW,),
    RoleName.IERC: (PipelineStatus.PARALLEL_REVIEW,),
    RoleName.KTTO: (PipelineStatus.ITSO_REVIEW, PipelineStatus.PARALLEL_REVIEW),
}

#: The party a role reviews as, for a legacy row.
_PARTY_OF_ROLE = {
    RoleName.ADVISER: Party.ADVISER,
    RoleName.RDCO: Party.RDCO,
    RoleName.ITSO: Party.ITSO,
    RoleName.IERC: Party.IERC,
    RoleName.KTTO: Party.KTTO,
}

#: The party whose routing event explains a legacy row's stage.
_ROUTED_PARTY_AT = {
    PipelineStatus.RDCO_INTAKE: Party.INTAKE,
}

#: The stages a party's Reviews are recorded at. RDCO staffed intake.
_STAGES_OF_PARTY = {
    Party.RDCO: (ReviewStage.RDCO, ReviewStage.RDCO_INTAKE),
}


class MyReviewsRefused(Exception):
    """The caller may not see this view of My Reviews. A 403."""


class MyReviewsError(Exception):
    """A request My Reviews cannot answer as asked. A 400."""


# --- the request ----------------------------------------------------------------------

@dataclass(frozen=True)
class _Scope:
    """Whose work a request lists: the caller's own, or one office's (§9)."""

    user: object
    office: str | None

    @property
    def pool_parties(self) -> frozenset:
        return frozenset({self.office}) if self.office else office_parties_of(self.user)

    def seats(self):
        if self.office:
            return ReviewerSeat.objects.filter(assignment__party=self.office)
        return ReviewerSeat.objects.filter(reviewer=self.user)

    def reviews(self):
        if self.office:
            stages = _STAGES_OF_PARTY.get(Party(self.office), (self.office,))
            return Review.objects.filter(stage__in=stages)
        return Review.objects.filter(reviewed_by=self.user)


def _scope(user, office) -> _Scope:
    """
    The view a request asks for. `office` is a coordinator's own office only:
    anyone else asking for one is refused, whatever office they name.
    """
    if not office:
        return _Scope(user, None)
    if not is_office_coordinator(user, office):
        raise MyReviewsRefused("Only a coordinator of that office may list its reviews.")
    return _Scope(user, str(office))


def _tab(raw) -> MyReviewsTab:
    if not raw:
        return MyReviewsTab.TO_REVIEW
    try:
        return MyReviewsTab(raw)
    except ValueError:
        raise MyReviewsError(f"Unknown tab {raw!r}.")


def _outcome_filter(raw):
    if not raw:
        return None
    try:
        return ReviewOutcome(raw)
    except ValueError:
        raise MyReviewsError(f"Unknown outcome {raw!r}.")


# --- the sources ----------------------------------------------------------------------

def _visible(user):
    return Record.objects.visible_to(user)


def _current_seats(scope, state):
    """Seats in `state` on new-model records, whose current work seats describe."""
    return scope.seats().filter(
        state=state,
        assignment__state=AssignmentState.ACTIVE,
        assignment__record__pipeline_status=PipelineStatus.IN_REVIEW,
        assignment__record__in=_visible(scope.user),
    )


def _pool(scope):
    """Active office assignments on new-model records that nobody is seated on."""
    live = ReviewerSeat.objects.filter(assignment=OuterRef("pk")).exclude(state=SeatState.WITHDRAWN)
    return RecordAssignment.objects.filter(
        party__in=scope.pool_parties,
        state=AssignmentState.ACTIVE,
        record__pipeline_status=PipelineStatus.IN_REVIEW,
        record__in=_visible(scope.user),
    ).exclude(Exists(live))


def _legacy_role(scope):
    """Whose old-pipeline queue the request reads: the caller's role."""
    return get_role_name(scope.user)


def _legacy(scope):
    """The old pipeline's queue for the caller's role, as `/reviews/pending/` served it."""
    role = _legacy_role(scope)
    statuses = _LEGACY_STATUSES.get(role)
    if not statuses:
        return Record.objects.none()
    records = Record.objects.filter(pipeline_status__in=statuses)
    if role == RoleName.ADVISER:
        records = records.filter(adviser=scope.user)
    office = _PARTY_OF_ROLE[role]
    if str(office) in (str(s) for s in SPECIALIST_STAGES):
        pending = RecordClearance.objects.filter(office=str(office), status=ClearanceStatus.PENDING)
        records = records.filter(pk__in=pending.values("record_id"))
    return records


def _verdict(seat_assignment, seat_reviewer):
    """The seat holder's latest Review on the seat's assignment: their verdict."""
    return Review.objects.filter(
        assignment=OuterRef(seat_assignment), reviewed_by=OuterRef(seat_reviewer),
    ).order_by("-created_at", "-pk")


def _latest_approval(record_ref):
    return Review.objects.filter(
        record=OuterRef(record_ref), status=ReviewDecision.APPROVED,
    ).order_by("-created_at", "-pk").values("pk")[:1]


def _done_seats(scope):
    verdict = _verdict("assignment_id", "reviewer_id")
    return scope.seats().filter(
        state=SeatState.DONE, assignment__record__in=_visible(scope.user),
    ).annotate(
        when=Coalesce("done_at", "assigned_at"),
        v_id=Subquery(verdict.values("pk")[:1]),
        v_status=Subquery(verdict.values("status")[:1]),
        v_stage=Subquery(verdict.values("stage")[:1]),
        record_status=F("assignment__record__pipeline_status"),
        latest_approval=Subquery(_latest_approval("assignment__record_id")),
    )


def _seatless_reviews(scope):
    """
    Done's second source: Reviews with no seat behind them that My Reviews
    already shows. See the module note for why each clause is there.
    """
    shown = ReviewerSeat.objects.filter(
        assignment=OuterRef("assignment"), reviewer=OuterRef("reviewed_by"),
    ).filter(
        Q(state=SeatState.DONE)
        | Q(state__in=OPEN_SEAT_STATES, assignment__record__pipeline_status=PipelineStatus.IN_REVIEW)
    )
    return scope.reviews().filter(record__in=_visible(scope.user)).exclude(Exists(shown)).annotate(
        when=F("created_at"),
        v_id=F("pk"),
        v_status=F("status"),
        v_stage=F("stage"),
        record_status=F("record__pipeline_status"),
        latest_approval=Subquery(_latest_approval("record_id")),
    )


# --- outcomes -------------------------------------------------------------------------

def _published_q():
    return Q(record_status=PipelineStatus.PUBLISHED, latest_approval=F("v_id"))


def _outcome_q(outcome) -> Q:
    """The database form of `_outcome()`: one must agree with the other."""
    approved = Q(v_status=ReviewDecision.APPROVED)
    specialist = Q(v_stage__in=SPECIALIST_STAGES)
    return {
        ReviewOutcome.CLEARED: approved & specialist,
        ReviewOutcome.FINDING: Q(v_status=ReviewDecision.NEGATIVE_FINDING),
        ReviewOutcome.REJECTED: Q(v_status=ReviewDecision.REJECTED),
        ReviewOutcome.REVISION_REQUESTED: Q(v_status=ReviewDecision.DECLINED),
        ReviewOutcome.PUBLISHED: approved & ~specialist & _published_q(),
        ReviewOutcome.ACCEPTED: approved & ~specialist & ~_published_q(),
    }[outcome]


def _outcome(item) -> ReviewOutcome | None:
    """A Done row's outcome, from the annotations `_outcome_q` filters on."""
    status = item.v_status
    if status is None:
        return None
    if status == ReviewDecision.NEGATIVE_FINDING:
        return ReviewOutcome.FINDING
    if status == ReviewDecision.REJECTED:
        return ReviewOutcome.REJECTED
    if status == ReviewDecision.DECLINED:
        return ReviewOutcome.REVISION_REQUESTED
    if status != ReviewDecision.APPROVED:
        return None
    if item.v_stage in SPECIALIST_STAGES:
        return ReviewOutcome.CLEARED
    if item.record_status == PipelineStatus.PUBLISHED and item.latest_approval == item.v_id:
        return ReviewOutcome.PUBLISHED
    return ReviewOutcome.ACCEPTED


# --- paging Done ----------------------------------------------------------------------

def _encode(when: datetime, kind: str, pk: int) -> str:
    raw = f"{when.isoformat()}|{_RANK[kind]}|{pk}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor):
    """`(when, rank, pk)` from a cursor, or a 400."""
    if not cursor:
        return None
    try:
        when, rank, pk = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        parsed = parse_datetime(when)
        if parsed is None:
            raise ValueError
        return parsed, int(rank), int(pk)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise MyReviewsError("That page link is no longer valid.")


def _after(queryset, kind, cursor):
    """
    The rows that come after `cursor` in Done's order: newest first, ties
    broken by source then id, so the two sources interleave as one list.
    """
    if cursor is None:
        return queryset
    when, rank, pk = cursor
    mine = _RANK[kind]
    if mine < rank:
        return queryset.filter(when__lte=when)
    if mine > rank:
        return queryset.filter(when__lt=when)
    return queryset.filter(Q(when__lt=when) | Q(when=when, pk__lt=pk))


# --- rows -----------------------------------------------------------------------------

def _name(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.email


def _since(when):
    now = timezone.now()
    return {"waiting_since": when.isoformat(), "waiting_days": max((now - when).days, 0)}


def _row(*, kind, pk, record, party, party_label, **fields) -> dict:
    row = {
        "key": f"{kind}:{pk}",
        "kind": kind,
        "record": record.pk,
        "title": record.title,
        "record_type_name": record.record_type.name if record.record_type_id else None,
        "party": str(party),
        "party_label": party_label,
        "stage_label": None,
        "seat": None,
        "assignment": None,
        "holder": None,
        "holder_name": None,
        "is_mine": False,
        "routed_by": None,
        "routed_reason": "",
        "submitted_by": None,
        "waiting_since": None,
        "waiting_days": None,
        "waiting_on": None,
        "outcome": None,
        "outcome_label": None,
        "decided_at": None,
        "can_claim": False,
        "can_assign": False,
    }
    row.update(fields)
    return row


def _row_party(stage) -> Party:
    """A Review's stage as a My Reviews party: intake was staffed by RDCO."""
    if stage in (ReviewStage.RDCO_INTAKE, ReviewStage.INTAKE):
        return Party.RDCO
    return Party(stage)


def _seat_row(seat, scope, *, since=None, **fields):
    assignment = seat.assignment
    reviewer = seat.reviewer
    return _row(
        kind=SEAT, pk=seat.pk, record=assignment.record,
        party=assignment.party, party_label=str(Party(assignment.party).label),
        seat=seat.pk, assignment=assignment.pk,
        holder=seat.reviewer_id, holder_name=_name(reviewer),
        is_mine=seat.reviewer_id == scope.user.pk,
        **(_since(since) if since else {}),
        **fields,
    )


def _current_rows(scope, tab) -> list[dict]:
    """To review or In review: seats, then (To review only) the pool and the old queue."""
    user = scope.user
    rows = []
    state = SeatState.ASSIGNED if tab == MyReviewsTab.TO_REVIEW else SeatState.IN_REVIEW
    seats = _current_seats(scope, state).select_related(
        "assignment__record__record_type", "reviewer",
    )
    for seat in seats:
        since = seat.assigned_at if state == SeatState.ASSIGNED else (seat.opened_at or seat.assigned_at)
        rows.append(_seat_row(seat, scope, since=since, entry=seat.source == SeatSource.ENTRY))

    if tab == MyReviewsTab.TO_REVIEW:
        for assignment in _pool(scope).select_related("record__record_type"):
            party = assignment.party
            rows.append(_row(
                kind=POOL, pk=assignment.pk, record=assignment.record,
                party=party, party_label=str(Party(party).label),
                assignment=assignment.pk,
                can_claim=is_office_member(user, party),
                can_assign=is_office_coordinator(user, party),
                **_since(assignment.opened_at),
            ))
        role = _legacy_role(scope)
        legacy = _legacy(scope).select_related("record_type").annotate(
            last_review=Max("reviews__created_at"),
        )
        for record in legacy:
            party = _PARTY_OF_ROLE[role]
            rows.append(_row(
                kind=LEGACY, pk=record.pk, record=record,
                party=party, party_label=str(Party(party).label),
                stage_label=record.get_pipeline_status_display(),
                routing_party=_ROUTED_PARTY_AT.get(record.pipeline_status, party),
                **_since(record.last_review or record.created_at),
            ))

    _add_context(rows)
    rows.sort(key=lambda r: r["waiting_since"])
    return rows


def _add_context(rows):
    """Who routed each row and why, who submitted it, and what it waits on."""
    if not rows:
        return
    record_ids = {r["record"] for r in rows}

    latest = {}
    events = (
        RoutingEvent.objects.filter(record_id__in=record_ids)
        .select_related("actor").order_by("record_id", "to_party", "-created_at", "-pk")
    )
    for event in events:
        latest.setdefault((event.record_id, str(event.to_party)), event)

    owners = {}
    for owner in (
        RecordOwner.objects.filter(record_id__in=record_ids)
        .select_related("user").order_by("record_id", "-is_primary", "pk")
    ):
        owners.setdefault(owner.record_id, owner.user)

    author = set(
        ResubmissionRequest.objects.filter(
            record_id__in=record_ids, state=ResubmissionRequestState.OPEN,
        ).values_list("record_id", flat=True)
    )
    document = set(
        DocumentRequest.objects.filter(
            record_id__in=record_ids, state=DocumentRequestState.OPEN,
        ).values_list("record_id", flat=True)
    )

    for row in rows:
        party = str(row.pop("routing_party", None) or row["party"])
        event = latest.get((row["record"], party))
        submitted = row.pop("entry", False) or (
            row["party"] == Party.ADVISER and (event is None or event.from_party is None)
        )
        if submitted:
            row["submitted_by"] = _name(owners.get(row["record"]))
        elif event is not None:
            row["routed_by"] = _name(event.actor) if event.actor_id else None
            row["routed_reason"] = event.reason
        if row["record"] in author:
            row["waiting_on"] = "author"
        elif row["record"] in document:
            row["waiting_on"] = "document"


def _done_rows(scope, outcome, cursor) -> tuple[list[dict], str | None]:
    seats = _done_seats(scope)
    reviews = _seatless_reviews(scope)
    if outcome is not None:
        seats = seats.filter(_outcome_q(outcome))
        reviews = reviews.filter(_outcome_q(outcome))
    seats = _after(seats, SEAT, cursor).select_related(
        "assignment__record__record_type", "reviewer",
    ).order_by("-when", "-pk")[: PAGE_SIZE + 1]
    reviews = _after(reviews, REVIEW, cursor).select_related(
        "record__record_type", "reviewed_by",
    ).order_by("-when", "-pk")[: PAGE_SIZE + 1]

    merged = sorted(
        [(s.when, _RANK[SEAT], s.pk, SEAT, s) for s in seats]
        + [(r.when, _RANK[REVIEW], r.pk, REVIEW, r) for r in reviews],
        key=lambda t: (t[0], t[1], t[2]),
        reverse=True,
    )
    page, more = merged[:PAGE_SIZE], len(merged) > PAGE_SIZE

    rows = []
    for when, _rank, _pk, kind, item in page:
        verdict = _outcome(item)
        decided = {
            "outcome": verdict.value if verdict else None,
            "outcome_label": str(verdict.label) if verdict else "Completed by your office",
            "decided_at": when.isoformat(),
        }
        if kind == SEAT:
            rows.append(_seat_row(item, scope, **decided))
        else:
            rows.append(_row(
                kind=REVIEW, pk=item.pk, record=item.record,
                party=_row_party(item.stage), party_label=str(ReviewStage(item.stage).label),
                        holder=item.reviewed_by_id, holder_name=_name(item.reviewed_by),
                is_mine=item.reviewed_by_id == scope.user.pk,
                **decided,
            ))
    next_cursor = None
    if more:
        when, _rank, pk, kind, _item = page[-1]
        next_cursor = _encode(when, kind, pk)
    return rows, next_cursor


# --- the endpoint's one call ----------------------------------------------------------

def _counts(scope) -> dict:
    """Every tab's size in this view. `office` narrows them; `outcome` never does."""
    return {
        MyReviewsTab.TO_REVIEW.value: (
            _current_seats(scope, SeatState.ASSIGNED).count()
            + _pool(scope).count()
            + _legacy(scope).count()
        ),
        MyReviewsTab.IN_REVIEW.value: _current_seats(scope, SeatState.IN_REVIEW).count(),
        MyReviewsTab.DONE.value: _done_seats(scope).count() + _seatless_reviews(scope).count(),
    }


def my_reviews(user, *, tab=None, outcome=None, office=None, cursor=None) -> dict:
    """
    One tab of `user`'s My Reviews: `{rows, counts, next}`. `next` is the Done
    page after this one, or None. Raises `MyReviewsRefused` (403) for an
    office view the caller may not see and `MyReviewsError` (400) for a
    parameter it cannot read.
    """
    scope = _scope(user, office)
    tab = _tab(tab)
    outcome = _outcome_filter(outcome)
    next_cursor = None
    if tab == MyReviewsTab.DONE:
        rows, next_cursor = _done_rows(scope, outcome, _decode(cursor))
    else:
        rows = _current_rows(scope, tab)
    return {"rows": rows, "counts": _counts(scope), "next": next_cursor}
