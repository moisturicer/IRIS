"""The recovery mail worker (ADR-045 §6).

`deliver_recovery_intent` takes one intent through two steps, each safe to
run twice or concurrently:

1. **Issue.** Under the intent's row lock: give up if it has expired or a
   newer request for the same recipient superseded it; look the address up
   (exact match, more than one fails closed); lock the account and check it is
   eligible *now*; revoke the account's older links of this purpose and issue
   one token, bound to this intent one-to-one. The raw token is kept only
   encrypted, until the mail is sent.
2. **Send.** Re-check the token is still usable, take a lease so a concurrent
   worker skips the intent, and send outside any transaction -- an SMTP
   conversation must never hold a row lock. Then record the outcome:
   sent, a transient failure scheduled for retry at 30, 120 and 300 seconds
   with the same token, or a permanent failure.

`dispatch_recovery_intents` is the periodic safety net: it re-enqueues every
intent that is due and unleased (so a lost broker message or a crashed
on-commit hook costs one interval, not the email), expires stale pending
intents and purges terminal records after the retention period.

Nothing here logs an address, a token, a link or an SMTP exception's text.
"""

import logging
import smtplib
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from apps.accounts.models import (
    RecoveryAttempt, RecoveryBucket, RecoveryGeneration, RecoveryIntent, RecoveryPurpose, RecoveryToken, User,
)
from apps.audit.models import AuditEvent

from . import audit, clock, crypto, service
from .service import is_eligible, usable

logger = logging.getLogger(__name__)

Status = RecoveryIntent.Status

#: How long a sending worker holds an intent. Longer than any SMTP timeout,
#: so a worker that dies mid-send is retried by the dispatcher afterwards.
LEASE = timedelta(seconds=120)

TOKEN_LIFETIMES = {
    RecoveryPurpose.PASSWORD_RESET: lambda: settings.RECOVERY_RESET_TTL_SECONDS,
    RecoveryPurpose.EMAIL_VERIFICATION: lambda: settings.RECOVERY_VERIFICATION_TTL_SECONDS,
}


class PermanentFailure(Exception):
    """The server refused this message for good; retrying would not help."""


def _finish(intent, status, at):
    intent.status = status
    intent.finished_at = at
    intent.lease_until = None
    intent.address_encrypted = ""
    intent.payload_encrypted = ""
    intent.save()


def deliver_recovery_intent(intent_id) -> None:
    identity = RecoveryIntent.objects.filter(pk=intent_id).values("recipient", "purpose").first()
    if identity is None:
        return
    with transaction.atomic():
        # Admission takes generation before intent as well. Holding it until
        # issuance commits prevents a delayed worker overtaking a new request.
        if identity["recipient"]:
            RecoveryGeneration.objects.select_for_update().filter(**identity).first()
        intent = RecoveryIntent.objects.select_for_update().filter(pk=intent_id).first()
        if intent is None or intent.status in RecoveryIntent.TERMINAL:
            return
        at = clock.now()
        if intent.status == Status.PENDING:
            _issue(intent, at)
            if intent.status != Status.ISSUED:
                return
        at = clock.now()
        if intent.next_attempt_at > at or (intent.lease_until and intent.lease_until > at):
            return
        if intent.attempts >= settings.RECOVERY_MAIL_MAX_ATTEMPTS:
            _finish(intent, Status.FAILED, at)
            audit.record(AuditEvent.RECOVERY_EMAIL_FAILED, purpose=intent.purpose, outcome="failed",
                         reason="attempts_exhausted", correlation_id=intent.correlation_id,
                         attempt=intent.attempts)
            logger.error("recovery mail for intent %s exhausted its attempts", intent_id)
            return
        if not _sendable(intent, at):
            _finish(intent, Status.WITHDRAWN, at)
            return
        message = _compose(intent)
        intent.attempts += 1
        intent.lease_until = at + LEASE
        intent.save(update_fields=["attempts", "lease_until"])
        attempt = intent.attempts

    try:
        _send(message)
    except PermanentFailure:
        _record_failure(intent_id, attempt, permanent=True)
    except Exception as exc:  # noqa: BLE001 -- network, timeout, 4xx: all transient
        logger.warning("recovery mail attempt %s for intent %s failed (%s)",
                       attempt, intent_id, type(exc).__name__)
        _record_failure(intent_id, attempt, permanent=False)
    else:
        _record_sent(intent_id, attempt)


def _issue(intent, at) -> None:
    """Step 1. Leaves the intent ISSUED, or in a terminal state."""
    if at >= intent.expires_at:
        _finish(intent, Status.EXPIRED, at)
        return
    current = (RecoveryGeneration.objects.filter(recipient=intent.recipient, purpose=intent.purpose)
               .values_list("current", flat=True).first())
    if current != intent.generation:
        _finish(intent, Status.SUPERSEDED, at)
        return

    address = crypto.decrypt(intent.address_encrypted)
    matches = list(User.objects.filter(email=address).values_list("pk", flat=True)[:2])
    user = User.objects.select_for_update().get(pk=matches[0]) if len(matches) == 1 else None
    at = clock.now()
    if at >= intent.expires_at:
        _finish(intent, Status.EXPIRED, intent.expires_at)
        return
    if user is None or user.email != address or not is_eligible(user) or not _purpose_applies(user, intent.purpose):
        audit.record(AuditEvent.RECOVERY_SUPPRESSED, purpose=intent.purpose, outcome="suppressed",
                     reason="not_eligible", correlation_id=intent.correlation_id)
        _finish(intent, Status.INELIGIBLE, at)
        return

    RecoveryToken.objects.select_for_update().filter(
        user=user, purpose=intent.purpose, consumed_at__isnull=True, revoked_at__isnull=True,
    ).update(revoked_at=at)
    raw = crypto.new_token()
    RecoveryToken.objects.create(
        digest=crypto.digest(raw), user=user, purpose=intent.purpose, email=user.email,
        credential_version=user.credential_version, issued_at=at,
        expires_at=at + timedelta(seconds=TOKEN_LIFETIMES[intent.purpose]()), intent=intent,
    )
    intent.user = user
    intent.status = Status.ISSUED
    intent.address_encrypted = ""
    intent.payload_encrypted = crypto.encrypt(raw)
    intent.next_attempt_at = at
    intent.save()


def _purpose_applies(user, purpose) -> bool:
    """A verified account is sent no verification email (ADR-045 §1)."""
    return not (purpose == RecoveryPurpose.EMAIL_VERIFICATION and user.is_verified)


def _sendable(intent, at) -> bool:
    if intent.purpose == RecoveryPurpose.PASSWORD_CHANGED:
        return at < intent.expires_at and intent.user is not None and bool(intent.user.email)
    token = RecoveryToken.objects.filter(intent=intent).select_related("user").first()
    return token is not None and usable(token, token.user, intent.purpose, at) \
        and _purpose_applies(token.user, intent.purpose)


def _compose(intent) -> EmailMessage:
    help_line = "If you need help, contact RDCO or your department administrator."
    if intent.purpose == RecoveryPurpose.PASSWORD_CHANGED:
        return EmailMessage(
            subject="Your IRIS password was changed",
            body=(
                "The password for your IRIS account was just changed, and every "
                "device signed in to it was signed out.\n\n"
                "If you made this change, you do not need to do anything.\n\n"
                f"If you did not, request a new password at {settings.FRONTEND_URL}/password/forgot "
                f"and tell RDCO or your department administrator.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[intent.user.email],
        )
    token = RecoveryToken.objects.get(intent=intent)
    raw = crypto.decrypt(intent.payload_encrypted)
    expires = token.expires_at.astimezone(dt_timezone.utc)
    return EmailMessage(
        subject="Reset your IRIS password",
        body=(
            "Someone asked to reset the password for your IRIS account.\n\n"
            "To choose a new password, open this link:\n\n"
            f"{settings.FRONTEND_URL}/password/reset#token={raw}\n\n"
            f"The link works once and expires at {expires.isoformat()} UTC.\n\n"
            "If you did not request this, ignore this email. Your password has not changed.\n\n"
            f"{help_line}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[token.email],
    )


def _send(message) -> None:
    try:
        message.send(fail_silently=False)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise PermanentFailure() from exc
    except smtplib.SMTPResponseException as exc:
        if 500 <= exc.smtp_code < 600:
            raise PermanentFailure() from exc
        raise


def _record_sent(intent_id, attempt) -> None:
    at = clock.now()
    with transaction.atomic():
        intent = RecoveryIntent.objects.select_for_update().get(pk=intent_id)
        if intent.status != Status.ISSUED or intent.attempts != attempt:
            return
        _finish(intent, Status.SENT, at)
        audit.record(AuditEvent.RECOVERY_EMAIL_SENT, purpose=intent.purpose, outcome="sent",
                     correlation_id=intent.correlation_id, attempt=attempt)


def _record_failure(intent_id, attempt, *, permanent) -> None:
    at = clock.now()
    with transaction.atomic():
        intent = RecoveryIntent.objects.select_for_update().get(pk=intent_id)
        if intent.status != Status.ISSUED or intent.attempts != attempt:
            return
        if not permanent and attempt < settings.RECOVERY_MAIL_MAX_ATTEMPTS:
            delay = settings.RECOVERY_MAIL_RETRY_DELAYS[attempt - 1]
            intent.next_attempt_at = at + timedelta(seconds=delay)
            intent.lease_until = None
            intent.save(update_fields=["next_attempt_at", "lease_until"])
            transaction.on_commit(lambda: service.enqueue(intent_id, countdown=delay))
            return
        reason = "rejected" if permanent else "attempts_exhausted"
        _finish(intent, Status.FAILED, at)
        audit.record(AuditEvent.RECOVERY_EMAIL_FAILED, purpose=intent.purpose, outcome="failed",
                     reason=reason, correlation_id=intent.correlation_id, attempt=attempt)
    # The internal alert ADR-045 §6 asks for: aggregate-safe, no payload.
    logger.error("recovery mail for intent %s failed for good (%s)", intent_id, reason)


def dispatch_recovery_intents() -> int:
    """Re-enqueue what is due, expire what is stale, purge what is old.
    Returns how many intents it enqueued."""
    at = clock.now()
    for intent_id in RecoveryIntent.objects.filter(
        status=Status.PENDING, expires_at__lte=at,
    ).values_list("pk", flat=True):
        with transaction.atomic():
            intent = RecoveryIntent.objects.select_for_update().get(pk=intent_id)
            if intent.status == Status.PENDING:
                _finish(intent, Status.EXPIRED, intent.expires_at)

    due = list(
        RecoveryIntent.objects.filter(status__in=(Status.PENDING, Status.ISSUED), next_attempt_at__lte=at)
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=at))
        .order_by("next_attempt_at").values_list("pk", flat=True)[:500]
    )
    for intent_id in due:
        service.enqueue(intent_id)

    retention = at - timedelta(days=settings.RECOVERY_RECORD_RETENTION_DAYS)
    RecoveryToken.objects.filter(expires_at__lt=retention).delete()
    RecoveryIntent.objects.filter(status__in=RecoveryIntent.TERMINAL, finished_at__lt=retention).delete()
    RecoveryAttempt.objects.filter(at__lt=at - timedelta(days=1)).delete()
    _purge_idle_keys()
    return len(due)


def _purge_idle_keys() -> None:
    """Delete counters and generations nothing refers to any more (§6).

    Rows a request holds locked are skipped and left for the next run, and
    the emptiness check is repeated under the lock, so a purge never removes
    a counter a request is in the middle of using.
    """
    with transaction.atomic():
        idle = list(
            RecoveryBucket.objects.filter(attempts__isnull=True)
            .select_for_update(skip_locked=True, of=("self",)).values_list("key", flat=True)
        )
        RecoveryBucket.objects.filter(key__in=idle, attempts__isnull=True).delete()
    with transaction.atomic():
        unused = ~Exists(RecoveryIntent.objects.filter(
            recipient=OuterRef("recipient"), purpose=OuterRef("purpose"),
        ))
        idle = list(
            RecoveryGeneration.objects.filter(unused)
            .select_for_update(skip_locked=True).values_list("pk", flat=True)
        )
        RecoveryGeneration.objects.filter(unused, pk__in=idle).delete()
