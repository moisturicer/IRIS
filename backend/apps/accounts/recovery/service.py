"""Admitting recovery requests and consuming recovery links (ADR-045 §1-§6).

The request path never looks the address up. It counts, decides from the
counters alone, and writes a `RecoveryIntent`; whether an account exists is
the worker's question (`delivery`). That is what makes the response, its
timing and its side effects the same for every address.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.credentials import set_password_and_invalidate
from apps.accounts.models import (
    RecoveryGeneration, RecoveryIntent, RecoveryPurpose, RecoveryToken, User,
)
from apps.audit.models import AuditEvent

from . import audit, clock, crypto, limits

logger = logging.getLogger(__name__)

MAX_PASSWORD_LENGTH = 128


class InvalidLink(Exception):
    """Any token that cannot be used, for whatever reason. One answer for all."""


class PasswordRejected(Exception):
    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


def is_eligible(user) -> bool:
    """ADR-045 §1: restrictions first. An axes lockout is not a restriction."""
    return user.is_active and not user.is_locked and user.has_usable_password()


def admit_request(purpose: str, address: str) -> None:
    """Admit a request for ``purpose`` mail to ``address``, or suppress it.

    Either way the caller answers the same 202. Admission bumps the
    recipient's generation, supersedes its older pending intents and writes a
    new one, enqueued only once all of that has committed.
    """
    at = clock.now()
    recipient = crypto.identifier("recipient", address)
    with transaction.atomic():
        if limits.admit(f"rcpt:{recipient}", limits.recipient_windows(), at) is not None:
            audit.record(AuditEvent.RECOVERY_SUPPRESSED, purpose=purpose,
                         outcome="suppressed", reason="recipient_limit")
            return

        generation = None
        while generation is None:
            # The dispatcher may purge an unused row between insert and lock.
            RecoveryGeneration.objects.bulk_create(
                [RecoveryGeneration(recipient=recipient, purpose=purpose)], ignore_conflicts=True
            )
            generation = (RecoveryGeneration.objects.select_for_update()
                          .filter(recipient=recipient, purpose=purpose).first())
        generation.current += 1
        generation.save(update_fields=["current"])

        RecoveryIntent.objects.filter(
            recipient=recipient, purpose=purpose, status=RecoveryIntent.Status.PENDING,
        ).update(status=RecoveryIntent.Status.SUPERSEDED, finished_at=at,
                 address_encrypted="", payload_encrypted="")

        intent = RecoveryIntent.objects.create(
            purpose=purpose, recipient=recipient, generation=generation.current,
            address_encrypted=crypto.encrypt(address),
            created_at=at, next_attempt_at=at,
            expires_at=at + timedelta(seconds=settings.RECOVERY_INTENT_TTL_SECONDS),
        )
        audit.record(AuditEvent.RECOVERY_REQUESTED, purpose=purpose, outcome="admitted",
                     correlation_id=intent.correlation_id)
        transaction.on_commit(lambda: enqueue(intent.pk))


def enqueue(intent_id, countdown=None) -> None:
    """Hand an intent to a worker. A broker failure is not the request's
    problem: the intent is committed, and the dispatcher will find it."""
    from .tasks import deliver_recovery_intent_task

    try:
        deliver_recovery_intent_task.apply_async(args=[str(intent_id)], countdown=countdown)
    except Exception:  # noqa: BLE001 -- any broker failure; the dispatcher recovers
        logger.warning("recovery intent %s was not enqueued; the dispatcher will pick it up", intent_id)


def usable(token, user, purpose, at) -> bool:
    """Whether ``token`` may still be consumed, judged against ``user`` as
    they are now, not as they were when the email went out."""
    return (
        token.purpose == purpose
        and token.consumed_at is None
        and token.revoked_at is None
        and at < token.expires_at
        and token.email == user.email
        and token.credential_version == user.credential_version
        and is_eligible(user)
    )


def password_errors(user, new_password: str, confirm_password: str) -> dict:
    """ADR-045 §4, in the API's own envelope. Empty when the password is good."""
    errors = {}
    if len(new_password) > MAX_PASSWORD_LENGTH:
        errors["new_password"] = [f"Ensure this field has no more than {MAX_PASSWORD_LENGTH} characters."]
    elif user.check_password(new_password):
        errors["new_password"] = ["Choose a different password."]
    else:
        try:
            validate_password(new_password, user)
        except DjangoValidationError as exc:
            errors["new_password"] = list(exc.messages)
    if new_password != confirm_password:
        errors["confirm_password"] = ["Passwords do not match."]
    return errors


def confirm_reset(raw_token: str, new_password: str, confirm_password: str) -> None:
    """Consume a reset link and set the password, or raise.

    Raises `InvalidLink` before any password check, so a bad link says nothing
    about the password, and `PasswordRejected` -- leaving the link usable --
    when only the password is wrong. A rejection's audit row commits; only a
    completion changes anything else.
    """
    outcome = _consume_reset(raw_token, new_password, confirm_password)
    if outcome is InvalidLink:
        raise InvalidLink()
    if outcome:
        raise PasswordRejected(outcome)


def _consume_reset(raw_token, new_password, confirm_password):
    purpose = RecoveryPurpose.PASSWORD_RESET
    with transaction.atomic():
        user = token = None
        if crypto.TOKEN_PATTERN.fullmatch(raw_token):
            token_digest = crypto.digest(raw_token)
            user_id = (RecoveryToken.objects.filter(digest=token_digest)
                       .values_list("user_id", flat=True).first())
            if user_id is not None:
                # User before token: the order every recovery write takes.
                user = User.objects.select_for_update().filter(pk=user_id).first()
                token = RecoveryToken.objects.select_for_update().filter(digest=token_digest).first()
        at = clock.now()
        if user is None or token is None or not usable(token, user, purpose, at):
            audit.record(AuditEvent.RECOVERY_TOKEN_REJECTED, purpose=purpose,
                         outcome="rejected", reason="invalid_link")
            return InvalidLink

        errors = password_errors(user, new_password, confirm_password)
        if errors:
            return errors

        token.consumed_at = at
        token.save(update_fields=["consumed_at"])
        set_password_and_invalidate(user, new_password, at)
        correlation_id = token.intent.correlation_id if token.intent_id else None
        audit.record(AuditEvent.PASSWORD_RESET_COMPLETED, purpose=purpose, outcome="completed",
                     correlation_id=correlation_id, user=user)
        user_id = user.pk
        transaction.on_commit(lambda: notify_password_changed(user_id))
    return None


def notify_password_changed(user_id) -> None:
    """The non-secret notice after a reset (§6). Created after the reset has
    committed: failing to write or send it can never undo the password."""
    at = clock.now()
    try:
        with transaction.atomic():
            intent = RecoveryIntent.objects.create(
                purpose=RecoveryPurpose.PASSWORD_CHANGED, user_id=user_id,
                status=RecoveryIntent.Status.ISSUED, created_at=at, next_attempt_at=at,
                expires_at=at + timedelta(seconds=settings.RECOVERY_INTENT_TTL_SECONDS),
            )
            transaction.on_commit(lambda: enqueue(intent.pk))
    except Exception:  # noqa: BLE001 -- the reset has committed; the notice is best effort
        logger.exception("password-changed notice for user %s was not recorded", user_id)
