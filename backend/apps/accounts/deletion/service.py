"""
Account deletion: request, cancel, reject and confirm (ADR-051 §8-§12, IR-785).

Every act runs in one transaction with the request row locked, so two System
Admins acting at once can't both decide it; the loser gets `Refused` with 409.
Confirmation erases the person's details and private data and keeps the row
(see `registry`), because deleting a `User` would cascade into ownership and
review history.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from core.enums import PipelineStatus, RequestStatus, SessionEndReason
from core.utils import send_email_async

from ..models import AccountDeletionRequest, User
from . import registry
from .blockers import blockers_for

FORMER_FIRST_NAME = "Former"
FORMER_LAST_NAME = "user"


class Refused(Exception):
    """An act the request's current state doesn't allow."""

    def __init__(self, detail: str, *, status: int = 409, blockers=None):
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.blockers = blockers or []


def former_email(user_id: int) -> str:
    """A unique address that can't receive mail, freeing the real one (ADR-051 §12)."""
    return f"deleted-{user_id}@deleted.invalid"


def is_deleted(user) -> bool:
    return getattr(user, "deleted_at", None) is not None


# --- the person -------------------------------------------------------------

@transaction.atomic
def request_deletion(user) -> AccountDeletionRequest:
    User.objects.select_for_update().get(pk=user.pk)
    if AccountDeletionRequest.objects.filter(user=user, status=RequestStatus.PENDING).exists():
        raise Refused("You already have a pending deletion request.")
    made = AccountDeletionRequest.objects.create(user=user)
    create_audit_event(AuditEvent.ACCOUNT_DELETION_REQUESTED, user, metadata={"request": made.pk})
    return made


@transaction.atomic
def cancel_deletion(user) -> AccountDeletionRequest:
    pending = (
        AccountDeletionRequest.objects.select_for_update()
        .filter(user=user, status=RequestStatus.PENDING).first()
    )
    if pending is None:
        raise Refused("You have no pending deletion request.")
    pending.status = RequestStatus.CANCELLED
    pending.decided_at = timezone.now()
    pending.save(update_fields=["status", "decided_at"])
    create_audit_event(AuditEvent.ACCOUNT_DELETION_CANCELLED, user, metadata={"request": pending.pk})
    return pending


# --- the System Admin -------------------------------------------------------

def _lock_pending(request_id: int, actor) -> AccountDeletionRequest:
    found = (
        AccountDeletionRequest.objects.select_for_update()
        .select_related("user").filter(pk=request_id).first()
    )
    if found is None:
        raise Refused("Not found.", status=404)
    if found.user_id == actor.pk:
        raise Refused("Nobody decides their own deletion request.", status=403)
    if found.status != RequestStatus.PENDING:
        raise Refused("This request was already decided or cancelled. Reload to see where it stands.")
    return found


@transaction.atomic
def reject_deletion(request_id: int, actor, reason: str) -> AccountDeletionRequest:
    reason = (reason or "").strip()
    if not reason:
        raise Refused("A reason is required to reject a deletion request.", status=400)
    found = _lock_pending(request_id, actor)
    found.status = RequestStatus.DECLINED
    found.decided_by = actor
    found.decided_at = timezone.now()
    found.reason = reason
    found.save(update_fields=["status", "decided_by", "decided_at", "reason"])
    create_audit_event(
        AuditEvent.ACCOUNT_DELETION_REJECTED, actor,
        metadata={"request": found.pk, "target_user": found.user.email},
    )
    person = found.user
    transaction.on_commit(lambda: _tell_rejected(person, actor, reason))
    return found


@transaction.atomic
def confirm_deletion(request_id: int, actor) -> AccountDeletionRequest:
    found = _lock_pending(request_id, actor)
    person = User.objects.select_for_update().get(pk=found.user_id)
    blockers = blockers_for(person)
    if blockers:
        raise Refused(
            "Someone is still waiting on this person. RDCO, a coordinator or the person must clear it first.",
            blockers=blockers,
        )

    # Read before erasing: the outcome email goes to the address they had.
    address, first_name = person.email, person.first_name
    create_audit_event(
        AuditEvent.ACCOUNT_DELETION_CONFIRMED, actor,
        metadata={"request": found.pk, "target_user": address},
    )
    _settle_papers(person)
    _delete_private_rows(person)
    _erase_person(person)

    found.status = RequestStatus.APPROVED
    found.decided_by = actor
    found.decided_at = timezone.now()
    found.save(update_fields=["status", "decided_by", "decided_at"])
    transaction.on_commit(lambda: _email(
        address, "[IRIS] Your account has been deleted",
        f"Hello {first_name},\n\nYour IRIS account has been deleted, as you asked. "
        "You can no longer sign in, and your personal details have been removed. "
        "Names on published papers stay, and the audit log keeps its records.\n\n"
        "-- The IRIS Team",
    ))
    return found


# --- what confirmation does -------------------------------------------------

def _settle_papers(person) -> None:
    """Delete sole-owner drafts, pass on the Contact person, keep a published paper's Adviser name."""
    from apps.records.models import Record, RecordOwner
    from apps.records.services import soft_delete_record

    for ownership in (
        RecordOwner.objects.filter(user=person, record__is_deleted=False)
        .select_related("record").order_by("record_id")
    ):
        record = ownership.record
        others = RecordOwner.objects.filter(record=record).exclude(user=person).order_by("pk")
        if not others.exists():
            if record.pipeline_status == PipelineStatus.DRAFT:
                soft_delete_record(record, deleted_by=person)
            continue
        if ownership.is_primary:
            # ADR-051 decision 28: the longest-standing remaining owner takes over.
            successor = others.select_related("user").first()
            ownership.is_primary = False
            ownership.save(update_fields=["is_primary"])
            successor.is_primary = True
            successor.save(update_fields=["is_primary"])
            transaction.on_commit(lambda r=record, u=successor.user: _tell_new_contact(r, u))

    for record in Record.objects.filter(adviser=person, pipeline_status=PipelineStatus.PUBLISHED):
        record.adviser_name = person.get_full_name() or ""
        record.adviser = None
        record.save(update_fields=["adviser_name", "adviser", "updated_at"])


def _delete_private_rows(person) -> None:
    for model, field_name in registry.user_relations():
        rule = registry.RELATIONS[registry.label(model, field_name)]
        if rule.action == registry.DELETE:
            model._base_manager.filter(**{field_name: person}, **rule.where).delete()


def _erase_person(person) -> None:
    from ..sessions import end_all_sessions

    end_all_sessions(person, SessionEndReason.DELETED)
    person.email = former_email(person.pk)
    person.first_name = FORMER_FIRST_NAME
    person.middle_initial = ""
    person.last_name = FORMER_LAST_NAME
    person.role = None
    person.is_office_coordinator = False
    person.is_active = False
    person.is_staff = False
    person.is_superuser = False
    person.is_verified = False
    person.set_unusable_password()
    person.credential_version += 1
    person.deleted_at = timezone.now()
    person.save(update_fields=[
        "email", "first_name", "middle_initial", "last_name", "role", "is_office_coordinator",
        "is_active", "is_staff", "is_superuser", "is_verified", "password",
        "credential_version", "deleted_at",
    ])


# --- notices (after commit; a failed notice never undoes the act) -----------

def _email(address: str, subject: str, message: str) -> None:
    send_email_async(subject=subject, message=message, recipient_list=[address])


def _tell_rejected(person, actor, reason: str) -> None:
    from apps.notifications.services import notify_account_deletion_rejected

    notify_account_deletion_rejected(person, actor, reason)
    _email(
        person.email, "[IRIS] Your account deletion request was not accepted",
        f"Hello {person.first_name},\n\nA System Admin did not accept your request to delete "
        f"your IRIS account. Their reason:\n\n{reason}\n\n"
        f"Your account stays as it is. You can ask again from Settings at {settings.FRONTEND_URL}.\n\n"
        "-- The IRIS Team",
    )


def _tell_new_contact(record, user) -> None:
    from apps.notifications.services import notify_contact_person_took_over

    notify_contact_person_took_over(record, user)
