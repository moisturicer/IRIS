"""Recovery audit events (ADR-045 §8).

Written directly rather than through `create_audit_event`, which swallows its
own failure: a completion and its audit row must commit or roll back together.
The metadata is an allowlist -- purpose, correlation id, coarse outcome and
reason, attempt number -- and nothing here accepts an address, a token or a
password, so none can reach the log by accident.
"""

from apps.audit.models import AuditEvent


def record(event_type, *, purpose, outcome, correlation_id=None, reason="", attempt=None, user=None):
    metadata = {"purpose": purpose, "outcome": outcome}
    if correlation_id is not None:
        metadata["correlation_id"] = str(correlation_id)
    if reason:
        metadata["reason"] = reason
    if attempt is not None:
        metadata["attempt"] = attempt
    AuditEvent.objects.create(event_type=event_type, user=user, metadata=metadata)
