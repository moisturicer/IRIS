"""
Audit service — thin wrapper around AuditEvent.objects.create().

Always import AuditEvent *inside* functions to avoid circular imports
when this module is loaded early in the Django startup cycle.

Design rule: create_audit_event() must NEVER raise.  Audit failures
must not break the main request/response path.

**Each insert runs in its own savepoint (IR-144).** The workflow services
call this inside their own `transaction.atomic()`. On PostgreSQL a failed
INSERT aborts the whole transaction, so swallowing the exception alone is not
enough: every later statement of the act -- and its commit -- would fail. The
savepoint rolls back the audit row only, and the act carries on. A failure is
logged at ERROR with the event type and Record id, because an evaluation event
that silently goes missing cannot be reconstructed afterwards.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def create_audit_event(
    event_type: str,
    user,
    record=None,
    metadata: dict | None = None,
) -> None:
    """
    Persist one AuditEvent row.

    Parameters
    ----------
    event_type : str
        One of the AuditEvent constants (see AuditEvent.EVENT_TYPE_CHOICES).
        The workflow types are written through `apps.audit.workflow`, which
        fixes their metadata keys.
    user       : accounts.User or None
        The acting user.  Passing None is allowed (anonymous access, or an
        act IRIS took itself, such as the hand-back to RDCO).
    record     : records.Record or None
        The record this event relates to, if any.
    metadata   : dict or None
        Arbitrary extra data stored in the JSONB column
        (e.g. {"filename": "report.pdf", "slot": "Patent Draft"}).
    """
    try:
        from .models import AuditEvent  # local import to break circular deps

        with transaction.atomic():
            AuditEvent.objects.create(
                event_type=event_type,
                user=user,
                record=record,
                metadata=metadata or {},
            )
    except Exception:
        # Audit must never crash the caller.
        logger.exception(
            "audit event %s for record %s was not written",
            event_type, getattr(record, "pk", None),
        )
