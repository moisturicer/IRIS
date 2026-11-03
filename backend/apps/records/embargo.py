"""
A paper's embargo: its answer, and the acts that change it (ADR-052, IR-811,
IR-816, IR-812).

The only place that writes `Record`'s embargo stamps, so every write is audited
(decision 8). The state they add up to is `Record.embargo_state`, and what it
permits is `apps.ai.policy`'s to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from django.utils import timezone
from rest_framework import serializers

from apps.audit import workflow as audit
from core.enums import EmbargoState

from .models import Record

ANSWER_REQUIRED = "Say whether this paper is under embargo."
DATE_IN_THE_PAST = "The date to review this embargo cannot be in the past."
DRAFT_ANSWERS_INSTEAD = (
    "This paper hasn't been submitted, so its owners change their answer on the publish form."
)
NOTHING_TO_RELEASE = "This paper isn't under an embargo."
SENT_CANNOT_BE_RECALLED = "Text already sent to outside AI companies can't be recalled."

#: The states in which the check could already have let this paper's text out.
_AI_MAY_HAVE_IT = (EmbargoState.NONE, EmbargoState.RELEASED)


@dataclass(frozen=True)
class EmbargoAnswer:
    """What a person said. `until` is None for "no embargo"."""

    until: Optional[date]


class _AnswerSerializer(serializers.Serializer):
    embargoed = serializers.BooleanField()
    embargoed_until = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        until = attrs.get("embargoed_until")
        if not attrs["embargoed"]:
            if until is not None:
                raise serializers.ValidationError(
                    {"embargoed_until": "A paper with no embargo cannot have an embargo date."}
                )
        elif until is None:
            raise serializers.ValidationError(
                {"embargoed_until": "Choose the date to review this embargo."}
            )
        elif until < timezone.localdate():
            raise serializers.ValidationError({"embargoed_until": DATE_IN_THE_PAST})
        return attrs


class _UntilSerializer(serializers.Serializer):
    """Required and never null: no act after submission can blank the date."""

    embargoed_until = serializers.DateField()

    def validate_embargoed_until(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(DATE_IN_THE_PAST)
        return value


def answer_from(data: Any) -> Optional[EmbargoAnswer]:
    """
    The answer in a request, or None when it carries no answer at all.

    **The toggle's absence is checked first, by hand.** DRF reads a boolean
    missing from form data as False, so without this a form post that never
    gave the toggle would record "no embargo" that nobody said, and send the
    paper to a vendor.

    Raises DRF's `ValidationError` for an answer that is malformed or incomplete.
    """
    if "embargoed" not in data:
        if "embargoed_until" in data:
            raise serializers.ValidationError({"embargoed": ANSWER_REQUIRED})
        return None
    serializer = _AnswerSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return EmbargoAnswer(until=serializer.validated_data.get("embargoed_until"))


def until_from(data: Any) -> date:
    """The date in a request to set or extend. Raises DRF's `ValidationError`."""
    serializer = _UntilSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["embargoed_until"]


def _store(record: Record, until: Optional[date], *, actor) -> None:
    record.embargoed_until = until
    record.embargo_answered_at = timezone.now()
    record.embargo_answered_by = actor
    record.embargo_released_at = None
    record.embargo_released_by = None
    record.save(update_fields=[
        "embargoed_until", "embargo_answered_at", "embargo_answered_by",
        "embargo_released_at", "embargo_released_by", "updated_at",
    ])


def record_answer(record: Record, answer: EmbargoAnswer, *, actor) -> None:
    """
    Store `answer` with who gave it and when, replacing any answer before it.

    For a person, only ever on a draft: before submission the answer is the owners'
    to change freely (§5). After it, changing an embargo is a separate act (IR-812),
    because this would let an owner end one with no release (§6). The test-data
    commands also call this on a paper past draft, and only one with no answer yet.
    """
    _store(record, answer.until, actor=actor)
    audit.embargo_answered(record, actor, until=answer.until)


def set_embargo(record: Record, until: date, *, actor) -> dict:
    """
    Put a submitted paper under an embargo, or move an active one's date (§5).

    Allowed on a released paper too: that's a new embargo, not an undone release,
    and only the Adviser or RDCO can release it again (amended 2026-11-02). The
    date may move earlier, because a date ends nothing (§9).

    Returns the response body, which says so when the check could already have
    let text out. A later refusal stops further sending, and only that.
    """
    previous_state, previous_until = record.embargo_state, record.embargoed_until
    _store(record, until, actor=actor)
    if previous_state == EmbargoState.ACTIVE:
        audit.embargo_extended(record, actor, until=until, previous_until=previous_until)
    else:
        audit.embargo_set(record, actor, until=until, previous_state=previous_state)

    payload = state_payload(record)
    if previous_state in _AI_MAY_HAVE_IT:
        payload["notice"] = SENT_CANNOT_BE_RECALLED
    return payload


def release_embargo(record: Record, *, actor) -> dict:
    """
    End an active embargo and send the paper on (§6, §10).

    The date stays, as what the embargo held until. A refused paper is never tried
    again by anything else, so the release is what queues it, and the check still
    decides: an IP mark or missing consent keeps holding it back (§13).
    """
    from apps.ai.tasks import send_to_ai_on_commit

    record.embargo_released_at = timezone.now()
    record.embargo_released_by = actor
    record.save(update_fields=["embargo_released_at", "embargo_released_by", "updated_at"])
    audit.embargo_released(record, actor, until=record.embargoed_until)
    send_to_ai_on_commit(record.pk)
    return state_payload(record)


def state_payload(record: Record) -> dict:
    """`{state, until}`: where the embargo stands, as the API says it."""
    until = record.embargoed_until
    return {"state": record.embargo_state.value, "until": until.isoformat() if until else None}
