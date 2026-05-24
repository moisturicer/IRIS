"""
Audit service — thin wrapper around AuditEvent.objects.create().

Always import AuditEvent *inside* functions to avoid circular imports
when this module is loaded early in the Django startup cycle.

Design rule: create_audit_event() must NEVER raise.  Audit failures
must not break the main request/response path.
"""


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
        One of AuditEvent.LOGIN | LOGOUT | ACCESS | UPLOAD | DOWNLOAD |
        DELETE | RENAME (see AuditEvent.EVENT_TYPE_CHOICES).
    user       : accounts.User or None
        The acting user.  Passing None is allowed (anonymous access).
    record     : records.Record or None
        The record this event relates to, if any.
    metadata   : dict or None
        Arbitrary extra data stored in the JSONB column
        (e.g. {"filename": "report.pdf", "slot": "Patent Draft"}).
    """
    try:
        from .models import AuditEvent  # local import to break circular deps
        AuditEvent.objects.create(
            event_type=event_type,
            user=user,
            record=record,
            metadata=metadata or {},
        )
    except Exception:
        # Audit must never crash the caller.
        pass
