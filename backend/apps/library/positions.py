"""
A reader's place in a paper, apart from the HTTP layer (IR-573, ADR-044
§Amendment 2026-11-16, resume).

Three rules live here so the views stay thin:

* what the client sent is a well-formed place (`clean`);
* a place is stored and given back only for the Manuscript identity the reader
  is served now (`save`, `current`), so a replaced file never inherits another
  file's place, and only the `MAX_READING_POSITIONS` most recently read are kept;
* once no one is served a file's bytes, every place on it is deleted
  (`forget_replaced`, which `signals.py` runs when a Record or Version is saved).
"""

import math
import uuid

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.records.versions import latest_version, served_manuscript_identity

from .models import MAX_READING_POSITIONS, ReadingPosition

#: No Manuscript has more pages than this; it keeps a page inside the column's range.
MAX_PAGE = 100_000


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def clean(data) -> dict:
    """`{manuscript_revision, page, fraction}` from a PUT body, or a 400. A refused write stores nothing."""
    data = data if isinstance(data, dict) else {}
    errors = {}

    revision = data.get("manuscript_revision")
    try:
        revision = uuid.UUID(revision) if isinstance(revision, str) else None
    except ValueError:
        revision = None
    if revision is None:
        errors["manuscript_revision"] = ["Send the Manuscript revision the paper was opened at."]

    page = data.get("page")
    if not _is_int(page) or not 1 <= page <= MAX_PAGE:
        errors["page"] = ["Say which page the reader is on, counting from 1."]

    fraction = data.get("fraction")
    if not (_is_int(fraction) or isinstance(fraction, float)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        errors["fraction"] = ["Say how far down the page the reader is, from 0 to 1."]

    if errors:
        raise ValidationError(errors)
    return {"manuscript_revision": revision, "page": page, "fraction": float(fraction)}


def current(user, record) -> ReadingPosition | None:
    """
    The reader's place in `record`, while the bytes it was read on are still the
    ones they are served. A place on other bytes is deleted rather than given
    back: the file it was read on is gone for this reader, by a path the
    receiver did not see (a maintenance command's `.update()`).
    """
    row = ReadingPosition.objects.filter(owner=user, record=record).first()
    if row is None:
        return None
    revision, sha256 = served_manuscript_identity(record, user)
    if (row.manuscript_revision, row.manuscript_sha256) != (revision, sha256):
        row.delete()
        return None
    return row


def save(user, record, identity, *, page, fraction) -> None:
    """
    Move the reader's one place in `record` on the bytes `identity` names -- the
    `(revision, sha256)` the caller checked they are served -- and keep only
    their most recently read.
    """
    revision, sha256 = identity
    with transaction.atomic():
        ReadingPosition.objects.update_or_create(
            owner=user, record=record,
            defaults={"manuscript_revision": revision, "manuscript_sha256": sha256, "page": page, "fraction": fraction},
        )
        stale = (
            ReadingPosition.objects.filter(owner=user)
            .order_by("-updated_at", "-pk")
            .values_list("pk", flat=True)[MAX_READING_POSITIONS:]
        )
        ReadingPosition.objects.filter(pk__in=list(stale)).delete()


def forget_replaced(record) -> None:
    """
    Delete every place in `record` on bytes no one is served any more. Two
    identities are still served: the Record's own file (its owners read their
    unsubmitted upload) and its latest Version's (everyone else reads that).
    """
    version = latest_version(record)
    served = {record.manuscript_revision, version.manuscript_revision if version else None} - {None}
    ReadingPosition.objects.filter(record_id=record.pk).exclude(manuscript_revision__in=served).delete()
