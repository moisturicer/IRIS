"""
Supplementary attachments: who files one, and who may remove it (IR-474, IR-476).

ADR-032 §10, as amended 2026-10-06, grants `attach_file`: an office files a
supplementary file **of its own** on a record it takes part in, and may remove
one. Taking part is an active assignment the user can staff
(`tracker.requestable_parties`), the same test that offers the action in Paper
View.

A file belongs to an office, not a person (§10's IR-476 amendment, the same
"party, not person" rule as a document request). So the removal rule is: the
file's party is one the user can staff, **and** the user's office is taking part
right now. An owner is not an office and removes nothing here; a file with no
party is left to the superuser in Django admin (`admin.py`).

One rule, asked in two places that must agree: `RecordFileDeleteView`, and the
per-file `can_remove` the record payloads carry so the screen offers Remove
only where the server will allow it.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.enums import Party

logger = logging.getLogger(__name__)


def filing_party(record, user) -> Optional[str]:
    """
    The office `user` files as on `record`, or None when they take no part.

    RDCO staffs both `intake` and `rdco`, and always files as `rdco`, so no row
    carries the `intake` value IR-260 would have to migrate. Every other office
    staffs exactly one party.
    """
    from apps.reviews.tracker import requestable_parties

    parties = requestable_parties(record, user)
    if not parties:
        return None
    if str(Party.INTAKE) in parties:
        return str(Party.RDCO)
    return parties[0]


def removable_parties(record, user) -> frozenset:
    """
    The parties whose files `user` may remove on `record`.

    Empty unless the user's office holds an active assignment on the record;
    otherwise every party they can staff. Compute it once per record and test
    each file with `may_remove`.
    """
    from apps.reviews.tracker import requestable_parties, staffable_parties

    if not requestable_parties(record, user):
        return frozenset()
    # RDCO staffs `rdco` too, so it may remove its own files at intake.
    return staffable_parties(record, user)


def may_remove(record_file, user, *, removable: Optional[frozenset] = None) -> bool:
    """`user` may remove `record_file`. Pass `removable` to reuse one record's set."""
    if record_file.party is None:
        return False
    if removable is None:
        removable = removable_parties(record_file.record, user)
    return record_file.party in removable


def delete_record_file(record_file) -> None:
    """
    Delete the row, then the stored file. Every removal path calls this: the
    API (`RecordFileDeleteView`) and the escape hatch (`admin.py`).

    The row goes first, so a failed delete never leaves a row whose file is
    gone. A stored file that then fails to delete is an orphan on disk, which
    nothing serves -- the lesser failure.
    """
    record_file.delete()
    if not record_file.file:
        return
    try:
        record_file.file.delete(save=False)
    except Exception:
        logger.exception("RecordFile removed but its stored file was not: %s", record_file.file.name)
