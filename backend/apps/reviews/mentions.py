"""
@mentions in the review discussion (ADR-032 §7 Conveniences; IR-877 build
notes 3 and 4).

**Who may be mentioned.** Only someone `may_read_review` admits for the
record, and an active account. Anyone else refuses the whole comment, with
the same words whether or not that person exists, so a mention never grants
access and nobody is told (`people`).

**Picked beside the text.** A comment carries the people it mentions as a
list of account ids beside its body; nothing is parsed out of the body. An
edit that sends the list replaces it, and one that leaves it out keeps it.

**Told once per comment.** A removed name is kept inactive, never deleted,
so a name added back finds itself already told (`ReviewMention`). A comment
that posts at once tells its new names when the request commits
(`tell_now`). A draft tells nobody until *Finish review* sends it; then each
person gets one notice counting the drafts that mention them, after their
access is checked again (`tell_finished`). Nobody is told about their own
comment.
"""

from __future__ import annotations

from collections import Counter

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.enums import AssignmentState, Party
from core.permissions import may_read_review

from .models import RecordAssignment, ReviewerSeat, ReviewMention

#: More names than any comment needs, few enough that one comment is never a broadcast.
MAX_MENTIONS = 20

REFUSED = "You can only mention people who take part in this review."


class MentionError(ValueError):
    """400: the mentions are not a list of people who may read this review."""


TOO_MANY = f"A comment mentions at most {MAX_MENTIONS} people."


def _ids(value) -> list[int]:
    if not isinstance(value, list):
        raise MentionError("Mentions are a list of people.")
    if len(value) > MAX_MENTIONS * 10:  # bounds the work before duplicates are dropped
        raise MentionError(TOO_MANY)
    ids = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise MentionError("Mentions are a list of people.")
        if item not in ids:
            ids.append(item)
    if len(ids) > MAX_MENTIONS:
        raise MentionError(TOO_MANY)
    return ids


def people(record, value, comment=None) -> list:
    """
    The accounts `value` names, or `MentionError`. Each name new to `comment`
    must be an active account `may_read_review` admits. A name the comment
    already mentions is kept unchecked, so someone who has since lost access
    never stops its author editing it; they are not told again either way.
    """
    ids = _ids(value)
    kept = set(comment.mentions.filter(active=True).values_list("user_id", flat=True)) if comment else set()
    found = {u.pk: u for u in get_user_model().objects.filter(pk__in=ids)}
    for i in ids:
        if i in kept:
            continue
        if i not in found or not found[i].is_active or not may_read_review(found[i], record):
            raise MentionError(REFUSED)
    return [found[i] for i in ids]


def replace(comment, users) -> None:
    """Make `users` the comment's mentions; a dropped name stays, inactive."""
    wanted = {u.pk for u in users}
    rows = {m.user_id: m for m in ReviewMention.objects.select_for_update().filter(comment=comment)}
    for user in users:
        row = rows.get(user.pk)
        if row is None:
            ReviewMention.objects.create(comment=comment, user=user)
        elif not row.active:
            row.active = True
            row.save(update_fields=["active"])
    ReviewMention.objects.filter(comment=comment, active=True).exclude(user_id__in=wanted).update(active=False)


def _untold(comments, actor):
    return (
        ReviewMention.objects.select_for_update(of=("self",))
        .filter(comment__in=comments, active=True, notified_at__isnull=True)
        .exclude(user=actor)
        .select_related("user")
    )


def _send(record, actor, rows, version) -> None:
    """Queue one notice per person in `rows`, counting their comments, and mark
    them told. `notified_at` is when the notice was queued: like every review
    notice it is sent once the request commits, and a send that fails is
    logged, not retried, so the person is never told twice."""
    from apps.notifications.services import notify_mentioned

    ReviewMention.objects.filter(pk__in=[m.pk for m in rows]).update(notified_at=timezone.now())
    for user, count in Counter(m.user for m in rows).items():
        transaction.on_commit(lambda user=user, count=count: notify_mentioned(
            record, actor=actor, recipient=user, comments=count, version=version,
        ))


def tell_now(comment, actor) -> None:
    """A comment that posted or changed in the open tells the names new to it."""
    if comment.is_draft:
        return
    _send(comment.record, actor, list(_untold([comment], actor)),
          comment.version.number if comment.version_id else None)


def tell_finished(record, actor, drafts, version) -> None:
    """*Finish review* sent `drafts`: one notice per person they mention."""
    rows = [m for m in _untold(drafts, actor) if m.user.is_active and may_read_review(m.user, record)]
    _send(record, actor, rows, version.number if version else None)


def payload(comment) -> list[dict]:
    """The comment's current mentions, as `{id, name}`, in the order they were added."""
    return [
        {"id": m.user_id, "name": m.user.get_full_name()}
        for m in sorted(comment.mentions.all(), key=lambda m: m.pk) if m.active
    ]


def candidates(record) -> list:
    """Everyone who may be mentioned on `record`, by name: its owners, anyone who
    ever held a seat, and the members of each party holding it now."""
    from apps.reviews.tracker import ROLE_TO_PARTIES

    users = get_user_model().objects.filter(is_active=True)
    seen = {o.user for o in record.owners.select_related("user")}
    seen |= {s.reviewer for s in ReviewerSeat.objects.filter(
        assignment__record=record, reviewer__isnull=False).select_related("reviewer")}
    parties = set(RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
                  .values_list("party", flat=True))
    if str(Party.ADVISER) in parties and record.adviser_id:
        seen.add(record.adviser)
    roles = [role for role, held in ROLE_TO_PARTIES.items()
             if any(str(p) in parties for p in held if p != Party.ADVISER)]
    seen |= set(users.filter(role__name__in=roles))
    admitted = [u for u in seen if u.is_active and may_read_review(u, record)]
    return sorted(admitted, key=lambda u: (u.get_full_name().lower(), u.pk))
