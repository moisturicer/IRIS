"""
Record versions: the one writer, and the questions everything else asks
(ADR-032 §5, as amended 2026-10-08; IR-416).

**One function writes every version.** `write_version()` is called by the
legacy `POST /records/<id>/submit/` and `routing.enter_at_adviser()` (v1,
`submission`) and by the legacy `resubmit_record()` (the next version,
`revision`). IR-273's resubmission calls it too. Nothing else creates a
`RecordVersion`, so the numbering has one author.

**The manuscript lock lives here too.** Once a record is submitted, its
manuscript changes only through a new version, so `may_replace_manuscript()`
allows a replacement only while the owner is preparing one: a `draft`, or a
legacy `declined` until IR-274. IR-273 adds `awaiting_resubmission`. Staff
are not exempt.
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction

from core.enums import PipelineStatus, VersionCause

from .models import Record, RecordVersion

#: The statuses in which a record's manuscript may be replaced (module note).
MANUSCRIPT_REPLACEABLE_STATUSES = frozenset({
    PipelineStatus.DRAFT,
    PipelineStatus.DECLINED,
})


def may_replace_manuscript(record) -> bool:
    """May `record`'s manuscript be replaced right now? (module note)"""
    return record.pipeline_status in MANUSCRIPT_REPLACEABLE_STATUSES


def latest_version(record) -> Optional[RecordVersion]:
    """The record's newest version, or None before it is first submitted."""
    return record.versions.order_by("-number").first()


def versions_payload(record) -> list[dict]:
    """
    The record's versions, oldest first, as the record detail and tracker
    payloads carry them. Callers send it only to a viewer who may read the
    review (`may_read_review`, IR-479), because earlier versions are review
    material (ADR-032 §5 Amendment).
    """
    rows = list(record.versions.select_related("created_by").order_by("number"))
    return [
        {
            "number": v.number,
            "cause": v.cause,
            "cause_label": v.get_cause_display(),
            "created_at": v.created_at.isoformat(),
            "created_by_name": v.created_by.get_full_name() if v.created_by else None,
            "manuscript_url": (
                f"/api/v1/records/{record.pk}/versions/{v.number}/manuscript/"
                if v.manuscript else None
            ),
        }
        for v in rows
    ]


@transaction.atomic
def write_version(record, actor, cause: VersionCause) -> RecordVersion:
    """
    Write `record`'s next version, naming its manuscript as it stands now.

    The record's row is locked first, so two writers cannot both take the
    same number; `(record, number)` is unique as well, so a race that got past
    the lock would fail rather than write a duplicate. `actor` may be None
    where nobody is recorded.
    """
    # Only the record row (see `routing._locked`).
    Record.objects.select_for_update(of=("self",)).get(pk=record.pk)
    previous = (
        RecordVersion.objects.filter(record=record)
        .order_by("-number").values_list("number", flat=True).first()
    )
    created_by = actor if getattr(actor, "is_authenticated", False) else None
    return RecordVersion.objects.create(
        record=record,
        number=(previous or 0) + 1,
        cause=cause,
        manuscript=record.abstract_file.name or None,
        created_by=created_by,
    )
