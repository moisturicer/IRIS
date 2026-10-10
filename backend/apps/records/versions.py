"""
Record versions: the one writer, and the questions everything else asks
(ADR-032 §5, as amended 2026-10-08; IR-416).

**One function writes every version.** `write_version()` is called by
`routing.enter_at_adviser()` (v1, `submission`) and by IR-273's new version
(the next version, `revision`). Nothing else creates a `RecordVersion`, so the
numbering has one author.

**The manuscript lock lives here too.** Once a record is submitted, its
manuscript changes only through a new version, so `may_replace_manuscript()`
allows a replacement only while the owner is preparing one: a `draft`, or a
record in review with a revision request open (`awaiting_resubmission`,
IR-273). Staff are not exempt, and in
that last case only an owner may: the revision is theirs to make.

**Which manuscript a reader is shown** (IR-273, settled in IR-416). Between
the owner's upload and their new version, the stored manuscript is a file no
reviewer was ever handed. `served_manuscript()` gives everyone but an owner
the latest version's file meanwhile; an owner reads their own upload, and
`manuscript_unsubmitted()` says so. The upload is not extracted until its
version is submitted (`manuscript_awaits_submission()`), so the chunks Ask
IRIS answers from are always the submitted manuscript's. If the last request is withdrawn first,
`restore_submitted_manuscript()` puts the latest version's file back, so an
upload no version can carry is never left as the record's manuscript.
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction

from core.enums import PipelineStatus, VersionCause
from core.permissions import is_record_owner

from .models import Record, RecordVersion

#: The statuses in which a record's manuscript may be replaced (module note).
MANUSCRIPT_REPLACEABLE_STATUSES = frozenset({PipelineStatus.DRAFT})


def _awaiting_resubmission(record) -> bool:
    """On the new model with a revision request open (ADR-032 §5)."""
    from apps.reviews.revisions import open_requests

    return (
        record.pipeline_status == PipelineStatus.IN_REVIEW
        and open_requests(record).exists()
    )


def may_replace_manuscript(record, user=None) -> bool:
    """May `user` replace `record`'s manuscript right now? (module note)"""
    if record.pipeline_status in MANUSCRIPT_REPLACEABLE_STATUSES:
        return True
    return _awaiting_resubmission(record) and is_record_owner(user, record)


def stored_manuscript_unsubmitted(record) -> bool:
    """
    Does the record store a manuscript other than its latest version's -- an
    owner's upload for a version not yet submitted? (module note)
    """
    latest = latest_version(record)
    return latest is not None and (latest.manuscript.name or None) != (record.abstract_file.name or None)


def manuscript_awaits_submission(record) -> bool:
    """
    Is the stored manuscript an owner's revision on the new model, waiting
    for its version? Then it is not extracted yet (IR-273): the chunks Ask
    IRIS answers from stay the submitted manuscript's, the same file every
    reviewer is served, until `submit_new_version` sends the new one.
    """
    return record.pipeline_status == PipelineStatus.IN_REVIEW and stored_manuscript_unsubmitted(record)


def manuscript_unsubmitted(record, user) -> bool:
    """
    Is the stored manuscript one `user`, an owner, uploaded for a version
    they have not submitted yet? False for anyone else: they never read it.
    """
    return (
        bool(record.abstract_file) and stored_manuscript_unsubmitted(record)
        and is_record_owner(user, record)
    )


def served_manuscript(record, user):
    """
    The manuscript file `user` reads as the record's current one (module
    note): the stored file for an owner, and for everyone else the latest
    version's while the stored one is still unsubmitted. Falsy when there is
    no manuscript.
    """
    if stored_manuscript_unsubmitted(record) and not is_record_owner(user, record):
        return latest_version(record).manuscript
    return record.abstract_file


def restore_submitted_manuscript(record) -> bool:
    """
    Put the latest version's manuscript back as the record's own, when the
    owner's upload was never submitted. The last revision request was
    withdrawn, so no version can carry it any more, and the lock that let it
    in has closed again (IR-273). The upload's file stays in storage, as every
    manuscript file does. Nothing is re-extracted: the upload never was
    (`manuscript_awaits_submission`), so the chunks are still this file's.
    Returns whether anything changed.
    """
    if not stored_manuscript_unsubmitted(record):
        return False
    record.abstract_file = latest_version(record).manuscript.name or None
    record.save(update_fields=["abstract_file", "updated_at"])
    return True


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
