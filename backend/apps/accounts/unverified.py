"""
Unverified registrations (ADR-051 decisions 22 to 26, IR-705).

An account whose registrant has not verified their email. It expires
``UNVERIFIED_REGISTRATION_DAYS`` after registering, and registering again on its
address replaces it, unless something links to it. Both remove the row outright,
with its role request, links and notice answers, because the account never
signed in. Neither is Account deletion, and the period is not a Retention
period. Audit rows stay: `AuditEvent.user` has no database constraint.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event

from .models import User

logger = logging.getLogger(__name__)

ALREADY_REGISTERED = "This email address is already registered."


def _dependents():
    """A subquery per way something else can depend on an account (IR-705,
    decided 2026-11-11): co-owning a Record, advising one, or a reviewer seat,
    review or upload review in any state. Wider than Account deletion's
    blockers on purpose: removing this row is permanent, and none of these
    should exist for an account that never signed in."""
    from apps.documents.models import UploadReview
    from apps.records.models import Record, RecordOwner
    from apps.reviews.models import Review, ReviewerSeat

    return (
        RecordOwner.objects.filter(user=OuterRef("pk")),
        Record.objects.filter(adviser=OuterRef("pk")),
        ReviewerSeat.objects.filter(reviewer=OuterRef("pk")),
        Review.objects.filter(reviewed_by=OuterRef("pk")),
        UploadReview.objects.filter(reviewed_by=OuterRef("pk")),
    )


def unverified_accounts():
    """Accounts still waiting on their registrant's email."""
    return User.objects.filter(is_verified=False, deleted_at__isnull=True)


def _with_dependents(queryset):
    """``queryset`` annotated with each dependent, and the condition "any of them"."""
    linked = Q()
    for index, dependent in enumerate(_dependents()):
        queryset = queryset.annotate(**{f"_dependent{index}": Exists(dependent)})
        linked |= Q(**{f"_dependent{index}": True})
    return queryset, linked


def replaceable(queryset):
    """The unverified registrations in ``queryset`` that nothing links to."""
    queryset, linked = _with_dependents(queryset & unverified_accounts())
    return queryset.exclude(linked)


def _on(email: str):
    return User.objects.filter(email__iexact=email)


def address_is_free(email: str) -> bool:
    """True when nobody holds ``email`` in any letter case, or only replaceable
    registrations do."""
    taken = _on(email)
    return not taken.exclude(pk__in=replaceable(taken).values("pk")).exists()


def lock_address(email: str) -> None:
    """Hold registration on ``email``, whatever its letter case, until the
    transaction ends. Two registrations of ``Ana@`` and ``ana@`` at once would
    otherwise lock different rows and send-limit buckets, and both save."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 705))", [email.lower()])


def replaceable_for(email: str):
    """The unverified registrations on ``email``, in any letter case, that
    registering again replaces, locked. Call inside a transaction."""
    return list(replaceable(_on(email)).select_for_update())


def replace(users) -> None:
    """Remove ``users`` because their address is registering again (decision 25),
    each with an audit event naming only the earlier account."""
    for user in users:
        create_audit_event(AuditEvent.REGISTRATION_REPLACED, user)
        user.delete()


def expire_unverified_registrations(now=None) -> dict:
    """Remove every unverified registration older than the setting (decision 24).

    One registered exactly ``UNVERIFIED_REGISTRATION_DAYS`` ago has expired.
    One something links to is skipped and logged by id. A run writes one audit
    event with the counts and nothing that names a person.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.UNVERIFIED_REGISTRATION_DAYS)
    with transaction.atomic():
        due, linked = _with_dependents(unverified_accounts().filter(date_joined__lte=cutoff))
        skipped = list(due.filter(linked).values_list("pk", flat=True))
        for pk in skipped:
            logger.warning("unverified registration %s not expired: something links to it", pk)
        expired = 0
        for user in due.exclude(linked).select_for_update():
            user.delete()
            expired += 1
        counts = {"expired": expired, "skipped": len(skipped)}
        create_audit_event(AuditEvent.UNVERIFIED_REGISTRATIONS_EXPIRED, None, metadata=counts)
    return counts
