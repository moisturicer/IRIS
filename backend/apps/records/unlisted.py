"""
RDCO publishes an Unlisted paper later (ADR-047 §10, IR-878).

**Unlisted** is `completed`: a Thesis/Research or Project RDCO accepted and kept
out of Discover, for example ahead of a patent filing. Its review is over. Any
RDCO member may later publish it, with an optional note, once its embargo is
released (ADR-052 decision 14 as amended): a person ends an embargo on purpose,
so publishing never releases one itself.

**What the act writes, in one transaction:** an `UnlistedPublication` row
(who, when, the note), the status `published`, and one `PUBLISHED` audit
event. It writes no `Review` and no `DECISION_RECORDED`: the paper's final
Decision stays its *keep unlisted*, which the history keeps reading as such
because of that row. No Version, Clearance or review reopens.

*Who may ask* is `IsRDCO`, checked by the endpoint before the paper is looked
up; the endpoint also takes the per-record lock, so an embargo set at the same
moment lands before or after, never alongside. The owners and the Adviser are
told after commit.
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction
from rest_framework import serializers

from apps.audit import workflow as audit
from core.enums import EmbargoState, PipelineStatus

from .lifecycle import type_name_of
from .models import Record, UnlistedPublication

#: The note is read in a notification and an email, so it is bounded.
MAX_NOTE_LENGTH = 1000

NOT_UNLISTED = "Only an Unlisted paper can be published this way."
NOTE_TOO_LONG = f"Keep the note to {MAX_NOTE_LENGTH} characters."
NOTE_NOT_TEXT = "Write the note as text."


def was_published_from_unlisted(record: Record) -> bool:
    """
    Did RDCO publish `record` from Unlisted after its Decision? Then that
    Decision was a *keep unlisted*, whatever the status says now.
    """
    return UnlistedPublication.objects.filter(record=record).exists()


def is_unlisted(record: Record) -> bool:
    """A Thesis/Research or Project RDCO kept unlisted. A Proposal never is."""
    from apps.reviews.routing import ROUTABLE_TYPES

    return (
        record.pipeline_status == PipelineStatus.COMPLETED
        and type_name_of(record) in ROUTABLE_TYPES
    )


def blocked_reason(record: Record) -> Optional[str]:
    """Why an Unlisted paper can't be published yet, naming its embargo, or None."""
    from apps.reviews.decisions import embargo_refusal

    if record.embargo_state != EmbargoState.RELEASED:
        return embargo_refusal(record)
    return None


def offer_payload(record: Record, user) -> Optional[dict]:
    """
    `publish_unlisted` on Record detail: present when the act is offered, with
    the reason it is held back, if any. A rendering hint; the act re-checks it.
    """
    from .rdco_acts import is_rdco

    if not (is_rdco(user) and is_unlisted(record)):
        return None
    return {"blocked": blocked_reason(record)}


def publish_unlisted(record: Record, note, *, actor) -> dict:
    """
    Publish `record`, an Unlisted paper, as RDCO. Raises a `ValidationError`
    (a 400) naming what stands in the way, writing nothing.
    """
    from apps.notifications.services import notify_published_later

    if not is_unlisted(record):
        raise serializers.ValidationError({"detail": NOT_UNLISTED})
    refused = blocked_reason(record)
    if refused:
        raise serializers.ValidationError({"detail": refused})
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise serializers.ValidationError({"note": NOTE_NOT_TEXT})
    note = note.strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise serializers.ValidationError({"note": NOTE_TOO_LONG})

    publication = UnlistedPublication.objects.create(record=record, published_by=actor, note=note)
    record.pipeline_status = PipelineStatus.PUBLISHED
    record.save(update_fields=["pipeline_status", "updated_at"])
    audit.published_from_unlisted(record, actor)
    transaction.on_commit(lambda: notify_published_later(record, published_by=actor, note=note))
    return {
        "id": record.pk,
        "pipeline_status": record.pipeline_status,
        "published_at": publication.published_at.isoformat(),
    }
