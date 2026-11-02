"""
A paper's embargo answer (ADR-052, IR-811, IR-816).

The only place that writes `Record`'s embargo stamps. The state they add up to
is `Record.embargo_state`, and what it permits is `apps.ai.policy`'s to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from django.utils import timezone
from rest_framework import serializers

from .models import Record

ANSWER_REQUIRED = "Say whether this paper is under embargo."


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
            raise serializers.ValidationError(
                {"embargoed_until": "The date to review this embargo cannot be in the past."}
            )
        return attrs


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


def record_answer(record: Record, answer: EmbargoAnswer, *, actor) -> None:
    """
    Store `answer` with who gave it and when, replacing any answer before it.

    Only ever on a draft: before submission the answer is the owners' to change
    freely (§5). After it, changing an embargo is a separate act (IR-812), because
    this would let an owner end one with no release (§6).
    """
    record.embargoed_until = answer.until
    record.embargo_answered_at = timezone.now()
    record.embargo_answered_by = actor
    record.embargo_released_at = None
    record.embargo_released_by = None
    record.save(update_fields=[
        "embargoed_until", "embargo_answered_at", "embargo_answered_by",
        "embargo_released_at", "embargo_released_by", "updated_at",
    ])


def state_payload(record: Record) -> dict:
    """`{state, until}`: where the embargo stands, as the API says it."""
    until = record.embargoed_until
    return {"state": record.embargo_state.value, "until": until.isoformat() if until else None}
