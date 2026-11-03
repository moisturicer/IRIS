"""
KTTO's release of an IP-marked paper (ADR-052 decisions 11 to 13, IR-813).

The only place that writes `Record.ip_released_*`, so every release is audited.
The mark itself stays: the paper is still IP, and only what the disclosure check
lets out changes. Whether anything is sent is still `apps.ai.policy`'s to decide,
so an embargo or missing consent keeps holding the paper back (§13).
"""

from __future__ import annotations

from django.utils import timezone

from apps.audit import workflow as audit
from core.enums import PipelineStatus

from .models import Record

NOTHING_TO_RELEASE = "This paper isn't marked as intellectual property."
ALREADY_RELEASED = "KTTO has already released this paper's IP mark."
DRAFT_HAS_NOTHING_TO_RELEASE = "This paper hasn't been submitted, so its IP mark can't be released yet."
MARK_CANNOT_BE_CLEARED = (
    "An IP mark can't be removed. KTTO releases a marked paper for the AI instead."
)


def why_not_releasable(record: Record) -> str | None:
    """Why `record` has no mark to release, or None when it has one."""
    if record.pipeline_status == PipelineStatus.DRAFT:
        return DRAFT_HAS_NOTHING_TO_RELEASE
    if not record.is_ip:
        return NOTHING_TO_RELEASE
    if record.ip_released:
        return ALREADY_RELEASED
    return None


def release_ip(record: Record, *, actor) -> dict:
    """
    Release `record`'s IP mark for the AI, and send the paper on (§11, §10).

    A refused paper is never tried again by anything else, so the release is
    what queues it, as an embargo's release does.
    """
    from apps.ai.tasks import send_to_ai_on_commit

    record.ip_released_at = timezone.now()
    record.ip_released_by = actor
    record.save(update_fields=["ip_released_at", "ip_released_by", "updated_at"])
    audit.ip_released(record, actor)
    send_to_ai_on_commit(record.pk)
    return state_payload(record)


def state_payload(record: Record) -> dict:
    """`{marked, released}`: where the IP mark stands, as the API says it."""
    return {"marked": record.is_ip, "released": record.ip_released}
