"""
Answering the data notice (ADR-054 decisions 1-4, 17; IR-789).

The one place a person's answer is written, and the one place the sign-in
block is decided. Everything else -- registration, the answer endpoint, the
authentication class -- calls in here, so there is one rule.

**The rule.** A signed-in person has *answered* when `answered_notice_version`
equals the number of the current notice (the highest). Anything else -- never
answered, or answered an older version -- is *answer required*, and the server
then refuses every request except the few in `ALLOWED_WHILE_UNANSWERED`. It is
enforced in `IdleAwareJWTAuthentication`, not in a view or a permission class,
so a new endpoint is covered the day it exists, for office staff and the System
Admin as much as for a student.

**Last answer stands (decision 4).** Nothing here ever clears or downgrades a
stored answer. Publishing a new notice (IR-790) only changes which number is
current; a person who never signs in again keeps what they last said.

**Versions.** An answer names the version the person was shown. If a newer one
was published meanwhile, `answer_notice` refuses with `StaleNotice`, which
carries the current notice so the person can read it before answering.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event

from .models import DataNotice, NoticeAnswer, User

#: The code the server answers every blocked request with. A client keys off
#: it, never off the message.
ACCEPTANCE_REQUIRED_CODE = "notice_acceptance_required"
STALE_NOTICE_CODE = "notice_stale"

#: URL names reachable while the current notice is unanswered: read the notice,
#: answer it, sign out -- and request account deletion, which ADR-054 decision 3
#: keeps open and which joins this set when its route exists (ADR-051). Keep
#: this to *names*, never prefixes: a new route is blocked until someone
#: decides it belongs here.
ALLOWED_WHILE_UNANSWERED = frozenset({
    "notice-current",
    "notice-answer",
    "auth-logout",
})


class NoticeAcceptanceRequired(PermissionDenied):
    """403 with ``code: notice_acceptance_required``: answer the notice first."""

    default_code = ACCEPTANCE_REQUIRED_CODE

    def __init__(self, current_version: int | None):
        super().__init__("Read and answer the current data notice to continue.", ACCEPTANCE_REQUIRED_CODE)
        # DRF's own error details would turn every value into a string, the
        # version number included. A client reads `code` and the version.
        self.detail = {
            "detail": "Read and answer the current data notice to continue.",
            "code": ACCEPTANCE_REQUIRED_CODE,
            "notice_version": current_version,
        }


class StaleNotice(APIException):
    """409 with ``code: notice_stale``, carrying the notice that is now current."""

    status_code = status.HTTP_409_CONFLICT
    default_code = STALE_NOTICE_CODE

    def __init__(self, notice: DataNotice):
        super().__init__("A newer data notice was published. Read it before answering.", STALE_NOTICE_CODE)
        # Raw, not DRF's stringified error details: the notice must arrive as
        # the same typed payload `GET /auth/notice/` serves.
        self.detail = {
            "detail": "A newer data notice was published. Read it before answering.",
            "code": STALE_NOTICE_CODE,
            "notice": notice_payload(notice),
        }


def current_notice_number() -> int | None:
    """The current notice's number, in one cheap indexed query."""
    return DataNotice.objects.order_by("-number").values_list("number", flat=True).first()


def requires_answer(user: User) -> bool:
    """Must `user` answer before using IRIS?

    True when no notice has been answered, or the answered one is older than
    the current. A notice-less database (migration 0019 not run) blocks nobody:
    there is nothing to answer.
    """
    current = current_notice_number()
    if current is None:
        return False
    answered = user.answered_notice_version
    return answered is None or answered < current


def notice_payload(notice: DataNotice) -> dict:
    return {
        "version": notice.number,
        "title": notice.title,
        "subtitle": notice.subtitle,
        "sections": notice.sections,
        "published_at": notice.published_at,
    }


def answer_payload(user: User) -> dict | None:
    """The person's last answer as the API shows it, or None if unanswered."""
    if user.answered_notice_version is None:
        return None
    return {
        "version": user.answered_notice_version,
        "ai_consent": user.ai_consent,
        "answered_at": user.notice_answered_at,
    }


def require_current(notice_version: int) -> DataNotice:
    """The current notice, if `notice_version` is it; else `StaleNotice`.

    A version *newer* than any published is as wrong as an older one -- the
    client named something the server never showed -- and is refused the same
    way, with the real current notice.
    """
    current = DataNotice.current()
    if current is None:
        raise APIException("No data notice has been published.")
    if notice_version != current.number:
        raise StaleNotice(current)
    return current


@transaction.atomic
def answer_notice(user: User, *, notice_version: int, ai_consent: bool) -> NoticeAnswer:
    """Record `user`'s answer to the notice they were shown.

    Raises `StaleNotice` when `notice_version` is not the current notice.
    Saying No to AI is a complete, normal answer: the account is unaffected
    (decision 6). The data-privacy agreement is implied by answering at all --
    the endpoint and registration both require it to be True before calling.

    Writes the append-only history row, mirrors it onto the user, and audits
    the act, all in one transaction.
    """
    # Locked so two answers racing (two tabs) cannot interleave their mirror
    # writes and leave the user row disagreeing with the latest history row.
    locked = User.objects.select_for_update().get(pk=user.pk)
    notice = require_current(notice_version)
    now = timezone.now()
    answer = NoticeAnswer.objects.create(
        user=locked, notice=notice, agreed_dpa=True, ai_consent=bool(ai_consent), answered_at=now,
    )
    previous = locked.answered_notice_version
    previous_ai = locked.ai_consent
    locked.answered_notice_version = notice.number
    locked.ai_consent = bool(ai_consent)
    locked.notice_answered_at = now
    locked.consent_given = True
    locked.save(update_fields=[
        "answered_notice_version", "ai_consent", "notice_answered_at", "consent_given",
    ])
    # Keep the caller's in-memory user in step (request.user is a separate object).
    user.answered_notice_version = locked.answered_notice_version
    user.ai_consent = locked.ai_consent
    user.notice_answered_at = locked.notice_answered_at
    user.consent_given = True
    create_audit_event(
        AuditEvent.NOTICE_ANSWERED, locked,
        metadata={
            "notice_version": notice.number,
            "ai_consent": bool(ai_consent),
            "previous_notice_version": previous,
            "previous_ai_consent": previous_ai,
        },
    )
    return answer
