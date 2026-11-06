"""
Finish review: a Seat holder sends their draft threads with a summary and a
verdict (ADR-032 §7, 2026-11-04 amendment; IR-874).

`POST /records/<id>/finish-review/`
`{"verdict": str, "summary": str, "to"?: [...], "suggested_offices"?: [...], "token"?: str}`

**It grants no new authority.** Every verdict but *Comment only* is taken by
the service that owns it, with the summary as that act's reason or comment,
and that service's own checks and refusals stand:

| verdict | service |
|---|---|
| `request_revision` | `revisions.request_revision` |
| `send_to_rdco` | `routing.accept_and_route` (`to`, `suggested_offices`) |
| `cleared`, `finding` | `office_review.record_office_review` |
| `accept`, `publish`, `keep_unlisted`, `reject` | `decisions.decide` (`token`) |

**Comment only** is a recorded review round with no outcome: it writes a
`ReviewRound` and no `Review`, changes no Clearance and leaves the Seat open.

**In one transaction**, after the record lock: the caller's drafts are sent,
the verdict is taken, and a `ReviewRound` records the round, naming the
`Review` the verdict wrote. A refused verdict sends nothing. Before
anything is written, it refuses -- who before what:

- a caller with no open Seat here (403; 404 to one who may not read the review);
- a record not in review, an unknown verdict, an unopened Seat (400);
- *Comment only* with neither a summary nor a draft (400);
- an approval -- *Accept & send to RDCO*, *Clear*, *Accept* -- that would send
  one of the caller's own *Must fix* drafts: it would be refused by that very
  thread as soon as it was sent (400).

**One notification per finished review.** A verdict's service tells whom it
always tells, and its notice now counts the comments sent with it ("The
review came with 3 comments."); the threads add no notice of their own.
*Comment only* tells the owners and the other open Seat holders, once. So
does an office reviewer's Clear or finding that does not complete the
office, which no notice announced before: it says only that comments were
sent, never the verdict (`notify_office_completed`).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit import workflow as audit
from apps.records.versions import latest_version
from core.enums import OPEN_SEAT_STATES, ReviewVerdict, SeatState, ThreadSeverity
from core.permissions import may_read_review

from . import decisions, office_review, revisions, routing, seats
from .models import ReviewComment, ReviewerSeat, ReviewRound

#: Verdicts that approve, so a *Must fix* sent with one would refuse it.
APPROVALS = (ReviewVerdict.SEND_TO_RDCO, ReviewVerdict.CLEARED, ReviewVerdict.ACCEPT)

#: The Decision outcomes, by their `decisions` names.
DECISION_VERDICTS = {
    ReviewVerdict.ACCEPT: decisions.ACCEPT,
    ReviewVerdict.PUBLISH: decisions.PUBLISH,
    ReviewVerdict.KEEP_UNLISTED: decisions.KEEP_UNLISTED,
    ReviewVerdict.REJECT: decisions.REJECT,
}


class FinishNotFound(Exception):
    """404: the caller may not read this record's review."""


class FinishRefused(Exception):
    """403: the caller holds no open Seat here."""


class FinishError(Exception):
    """400: understood, but not possible as asked."""


def _take_verdict(record, actor, verdict, summary, *, to, suggested_offices, token, threads):
    """
    Take `verdict` through the service that owns it, and return the `Review` it
    wrote. Routing and office review return no Review, so theirs is the one
    this act wrote under the record lock: newer than any row that was there.
    """
    from .models import Review

    before = Review.objects.filter(record=record).order_by("-pk").values_list("pk", flat=True).first() or 0
    if verdict == ReviewVerdict.REQUEST_REVISION:
        return revisions.request_revision(record, actor, reason=summary, threads=threads).review, True
    if verdict in DECISION_VERDICTS:
        return decisions.decide(
            record, actor, outcome=DECISION_VERDICTS[verdict], comment=summary, token=token,
            thread_count=threads,
        ), True
    if verdict == ReviewVerdict.SEND_TO_RDCO:
        routing.accept_and_route(
            record, actor, to=to, reason=summary, suggested_offices=suggested_offices,
            threads=threads,
        )
        announced = True
    else:
        _, announced = office_review.record_office_review(
            record, actor, outcome=verdict, comment=summary, threads=threads,
        )
    review = Review.objects.filter(record=record, reviewed_by=actor, pk__gt=before).order_by("-pk").first()
    return review, announced


@transaction.atomic
def finish_review(record, actor, *, verdict, summary="", to=None, suggested_offices=None,
                  token=None) -> ReviewRound:
    """Finish the caller's review of `record` (module note). Returns the round."""
    record = routing._locked(record)
    if not may_read_review(actor, record):
        raise FinishNotFound
    seat = revisions._open_seat(record, actor)
    if seat is None:
        raise FinishRefused("Only a reviewer holding this record's review may finish a review.")
    if not routing.is_in_review(record):
        raise FinishError("This record is not in review.")
    if not isinstance(verdict, str) or verdict not in ReviewVerdict.values:
        raise FinishError("Choose how to finish your review.")
    if seat.state == SeatState.ASSIGNED:
        raise FinishError("Open the review first.")
    summary = summary.strip() if isinstance(summary, str) else ""

    drafts = list(
        ReviewComment.objects.select_for_update()
        .filter(record=record, author=actor, is_draft=True, reply_to__isnull=True)
        .order_by("created_at", "pk")
    )
    if verdict == ReviewVerdict.COMMENT_ONLY and not summary and not drafts:
        raise FinishError("Write a summary or a comment first.")
    must_fix = sum(1 for d in drafts if d.severity == ThreadSeverity.MUST_FIX)
    if verdict in APPROVALS and must_fix:
        raise FinishError(
            "You can't approve while sending a Must fix comment. Change it to Suggestion, "
            "or request a revision."
        )

    party = str(seat.assignment.party)
    version = latest_version(record)
    now = timezone.now()
    # Sent before the verdict, so a Decision closes them with the rest. A sent
    # draft is dated when it was sent: that is when anyone else first read it.
    ReviewComment.objects.filter(pk__in=[d.pk for d in drafts]).update(is_draft=False, created_at=now)

    review, announced = None, False
    if verdict != ReviewVerdict.COMMENT_ONLY:
        review, announced = _take_verdict(
            record, actor, verdict, summary,
            to=to, suggested_offices=suggested_offices, token=token, threads=len(drafts),
        )
    round_ = ReviewRound.objects.create(
        record=record, actor=actor, party=party, version=version,
        verdict=verdict, summary=summary, review=review,
    )
    ReviewComment.objects.filter(pk__in=[d.pk for d in drafts]).update(round=round_)
    audit.review_finished(round_, actor, threads=[d.pk for d in drafts], must_fix=must_fix)

    if verdict == ReviewVerdict.COMMENT_ONLY:
        _notify_unannounced(record, actor, round_, len(drafts), comment_only=True)
    elif not announced and drafts:
        # An office reviewer's verdict that completed nothing announces nothing,
        # so the comments it sent are told on their own.
        _notify_unannounced(record, actor, round_, len(drafts), comment_only=False)
    return round_


def _notify_unannounced(record, actor, round_, threads, *, comment_only):
    from apps.notifications.services import notify_review_finished

    others = list({
        s.reviewer for s in ReviewerSeat.objects.filter(
            assignment__record=record, state__in=OPEN_SEAT_STATES, reviewer__isnull=False,
        ).exclude(reviewer=actor).select_related("reviewer")
    })
    label = seats._label(round_.party)
    transaction.on_commit(lambda: notify_review_finished(
        record, actor=actor, party_label=label,
        version=round_.version.number if round_.version_id else None,
        threads=threads, reviewers=others, comment_only=comment_only,
    ))


def round_payload(round_) -> dict:
    """One finished review, as the tracker's timeline shows it. Review content."""
    return {
        "id": round_.pk,
        "party": round_.party,
        "label": seats._label(round_.party),
        "actor_name": (round_.actor.get_full_name() or round_.actor.email) if round_.actor else None,
        "version": round_.version.number if round_.version_id else None,
        "verdict": round_.verdict,
        "summary": round_.summary,
        "review": round_.review_id,
        "threads": round_.threads.count(),
        "created_at": round_.created_at.isoformat(),
    }


def rounds_payload(record) -> list[dict]:
    return [
        round_payload(r) for r in ReviewRound.objects.filter(record=record)
        .select_related("actor", "version").order_by("created_at", "pk")
    ]
