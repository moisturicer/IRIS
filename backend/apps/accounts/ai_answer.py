"""
Changing one's AI answer after giving it (ADR-054 decisions 11-13, IR-791).

A person's answer is asked at sign-up and after every new notice (`notice.py`),
and **Settings can change it at any time** -- waiting for a new notice could mean
waiting indefinitely, and a person must be able to withdraw. This module is that
act, for the signed-in person's own answer only; there is no way to name another
account.

**Yes to No reaches forward only (decision 12).** The person's answer changes, so
papers they create from now on carry a No. Every paper that already carries a Yes
keeps it, and what was already processed stays and stays in use. Nothing here
touches a paper.

**No to Yes asks which papers (decision 13), and assumes neither.** `papers` is
required for that one change:

* ``from_now`` -- only papers created from now on. Papers already holding a No
  keep it.
* ``all`` -- also the papers the person is **Contact person** of that hold a No.
  Their stored answer becomes Yes and each is sent on through
  `apps.ai.tasks.send_to_ai_on_commit`, which runs the disclosure gate, so the
  embargo and the IP mark still apply. Text sent to a vendor can't be recalled;
  that is why the choice is the person's and is never made for them.

A paper holding Yes or no answer at all is left alone either way, and a
co-owner's papers (where the person is not the Contact person) are never reached:
the Contact person's answer carries the paper (decision 9).

The same two choices apply wherever the answer changes to Yes, the notice
pop-up included, so `AnswerNoticeView` calls `require_papers_choice` and
`include_papers` too.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event

from .models import DataNotice, NoticeAnswer, User
from .notice import NoticeAcceptanceRequired, answer_payload

SCOPE_ALL = "all"
SCOPE_FROM_NOW = "from_now"
SCOPES = (SCOPE_ALL, SCOPE_FROM_NOW)

PAPERS_CHOICE_REQUIRED_CODE = "papers_choice_required"


class PapersChoiceRequired(APIException):
    """400 with ``code: papers_choice_required``: a No becoming a Yes must say which papers."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = PAPERS_CHOICE_REQUIRED_CODE

    def __init__(self):
        message = (
            "Choose which papers the Yes covers: `papers` is `all` (every paper you are "
            "Contact person of that holds a No) or `from_now` (only papers from now on)."
        )
        super().__init__(message, PAPERS_CHOICE_REQUIRED_CODE)
        # Raw, not DRF's stringified error details, so a client reads `code`.
        self.detail = {"detail": message, "code": PAPERS_CHOICE_REQUIRED_CODE, "papers": list(SCOPES)}


def becomes_yes(previous: bool | None, new: bool) -> bool:
    """Is this a No turning into a Yes -- the one change that asks about papers?

    A first answer (``previous`` None) is not: nobody can have a paper holding a
    No before they have answered once, and a paper with no answer stored is
    outside this choice by decision 13 ("hold a No").
    """
    return previous is False and new is True


def require_papers_choice(previous: bool | None, new: bool, papers: str | None) -> None:
    """Refuse a No-to-Yes change that doesn't say which papers, before anything is written."""
    if becomes_yes(previous, new) and papers not in SCOPES:
        raise PapersChoiceRequired()


def include_papers(user: User, *, papers: str | None) -> list[int]:
    """Switch the papers `user` is Contact person of that hold a No to Yes, if asked.

    Returns the ids switched (empty unless ``papers == "all"``). Each is sent on
    after commit through the same call the embargo release uses, so the gate
    decides every one. Runs in the caller's transaction.
    """
    if papers != SCOPE_ALL:
        return []
    from apps.ai.tasks import send_to_ai_on_commit
    from apps.records.models import Record

    ids = list(
        Record.objects.select_for_update(of=("self",))
        .filter(owners__user=user, owners__is_primary=True, ai_consent=False)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if ids:
        Record.objects.filter(pk__in=ids).update(ai_consent=True)
    for record_id in ids:
        send_to_ai_on_commit(record_id)
    return ids


def _audit(user: User, *, previous: bool | None, new: bool, papers: str | None, ids: list[int]) -> None:
    create_audit_event(
        AuditEvent.AI_ANSWER_CHANGED, user,
        metadata={
            "previous_ai_consent": previous,
            "ai_consent": new,
            # None when the change asked no question (anything but No to Yes).
            "papers": papers if becomes_yes(previous, new) else None,
            "papers_updated": len(ids),
            "paper_ids": ids,
        },
    )


def audit_sweep(user: User, *, previous: bool | None, new: bool, papers: str | None, ids: list[int]) -> None:
    """Audit a papers sweep made while answering a notice (the answer itself is
    already audited as `NOTICE_ANSWERED`), so what a Yes reached is on record."""
    if papers == SCOPE_ALL:
        _audit(user, previous=previous, new=new, papers=papers, ids=ids)


@transaction.atomic
def change_ai_answer(user: User, *, ai_consent: bool, papers: str | None = None) -> dict:
    """Change `user`'s own AI answer; return what the API reports.

    Refuses with `NoticeAcceptanceRequired` if they haven't answered the current
    notice (the authentication class already blocks that; this keeps the rule
    when called from elsewhere), and with `PapersChoiceRequired` for a No-to-Yes
    change that doesn't say which papers. Saying the same thing again changes and
    audits nothing.

    Appends the history row for the notice they last answered (`NoticeAnswer` is
    append-only and expects exactly this: "Settings can change the answer"),
    mirrors it onto the user, applies the papers choice and audits the act, all in
    one transaction.
    """
    # Locked so two changes racing (two tabs) cannot leave the mirror and the
    # newest history row disagreeing, and so a paper sweep sees one answer.
    locked = User.objects.select_for_update().get(pk=user.pk)
    notice = DataNotice.current()
    if notice is None or locked.answered_notice_version != notice.number:
        raise NoticeAcceptanceRequired(notice.number if notice else None)

    new = bool(ai_consent)
    previous = locked.ai_consent
    if previous is new:
        return {"answer": answer_payload(locked), "changed": False, "papers_updated": 0}
    require_papers_choice(previous, new, papers)

    now = timezone.now()
    NoticeAnswer.objects.create(user=locked, notice=notice, agreed_dpa=True, ai_consent=new, answered_at=now)
    locked.ai_consent = new
    locked.notice_answered_at = now
    locked.save(update_fields=["ai_consent", "notice_answered_at"])
    # Keep the caller's in-memory user in step (request.user is a separate object).
    user.ai_consent = new
    user.notice_answered_at = now

    ids = include_papers(locked, papers=papers if becomes_yes(previous, new) else None)
    _audit(locked, previous=previous, new=new, papers=papers, ids=ids)
    return {"answer": answer_payload(locked), "changed": True, "papers_updated": len(ids)}
