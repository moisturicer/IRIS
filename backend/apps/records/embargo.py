"""
A paper's embargo: the acts that change it (ADR-052, IR-811, IR-812, IR-882).

Every paper starts embargoed (`Record.is_embargoed` defaults true, ADR-052's
IR-879 amendment), so there is no answer to give: only the Adviser or RDCO set a
date or release it. The only place that writes `Record`'s embargo stamps, so
every write is audited (decision 8). The state they add up to is
`Record.embargo_state`, and what it permits is `apps.ai.policy`'s to decide.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.audit import workflow as audit
from core.enums import EmbargoState

from .models import Record

DATE_IN_THE_PAST = "The date to review this embargo cannot be in the past."
NOT_SUBMITTED = "This paper hasn't been submitted, so its embargo can't change yet."
NOTHING_TO_RELEASE = "This paper isn't under an embargo."
SENT_CANNOT_BE_RECALLED = "Text already sent to outside AI companies can't be recalled."


class _UntilSerializer(serializers.Serializer):
    """Required and never null: setting a date never blanks one."""

    embargoed_until = serializers.DateField()

    def validate_embargoed_until(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(DATE_IN_THE_PAST)
        return value


def until_from(data: Any) -> date:
    """The date in a request to set or extend. Raises DRF's `ValidationError`."""
    serializer = _UntilSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["embargoed_until"]


def set_embargo(record: Record, until: date, *, actor) -> dict:
    """
    Give an embargo a review date, move it, or embargo a released paper again (§5).

    The Adviser or RDCO only, as amended for IR-882. A released paper held again
    is a new embargo, not an undone release, and only the Adviser or RDCO can
    release it again (amended 2026-11-02). The date may move earlier, because a
    date ends nothing (§9).

    Returns the response body, which says so when the check could already have
    let text out. A later refusal stops further sending, and only that.
    """
    previous_state, previous_until = record.embargo_state, record.embargoed_until
    record.is_embargoed = True
    record.embargoed_until = until
    record.embargo_date_set_at = timezone.now()
    record.embargo_date_set_by = actor
    record.embargo_released_at = None
    record.embargo_released_by = None
    record.save(update_fields=[
        "is_embargoed", "embargoed_until", "embargo_date_set_at", "embargo_date_set_by",
        "embargo_released_at", "embargo_released_by", "updated_at",
    ])
    if previous_state == EmbargoState.ACTIVE and previous_until is not None:
        audit.embargo_extended(record, actor, until=until, previous_until=previous_until)
    else:
        audit.embargo_set(record, actor, until=until, previous_state=previous_state)

    payload = state_payload(record)
    if previous_state == EmbargoState.RELEASED:
        payload["notice"] = SENT_CANNOT_BE_RECALLED
    return payload


def mark_released(record: Record, *, actor) -> None:
    """
    Release `record`'s embargo and audit it, queuing nothing.

    `release_embargo` is the act a person takes. This is its write alone, for the
    test-data commands (decision 16, as amended), which queue the paper's reading
    themselves once consent is in place too. The date stays, as what the embargo
    held until.
    """
    record.is_embargoed = False
    record.embargo_released_at = timezone.now()
    record.embargo_released_by = actor
    record.save(update_fields=[
        "is_embargoed", "embargo_released_at", "embargo_released_by", "updated_at",
    ])
    audit.embargo_released(record, actor, until=record.embargoed_until)


def release_embargo(record: Record, *, actor) -> dict:
    """
    End an active embargo and send the paper on (§6, §10).

    A refused paper is never tried again by anything else, so the release is what
    queues it, and the check still decides: an IP mark or missing consent keeps
    holding it back (§13).
    """
    from apps.ai.tasks import send_to_ai_on_commit

    mark_released(record, actor=actor)
    send_to_ai_on_commit(record.pk)
    return state_payload(record)


def state_payload(record: Record) -> dict:
    """`{state, until}`: where the embargo stands, as the API says it."""
    until = record.embargoed_until
    return {"state": record.embargo_state.value, "until": until.isoformat() if until else None}
