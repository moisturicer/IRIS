"""May this PDF leave campus to be read? (IR-850, ADR-056 §5)

The disclosure gate decides, read fresh: when a read is queued, and again inside
the admitted attempt just before sending. Local Extractors are never gated.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from apps.ai.admission.errors import AdmissionDenied

#: Why a read was not sent. Public, like every admission reason code.
DISCLOSURE_REFUSED = "disclosure_refused"

_subject: ContextVar[Optional[int]] = ContextVar("extraction_subject", default=None)


class NotDisclosed(AdmissionDenied):
    """Nothing was sent: the gate refuses the Record, or none was named."""

    def __init__(self) -> None:
        super().__init__(DISCLOSURE_REFUSED)


def leaves_campus(extractor) -> bool:
    """An Extractor that does not say reads as leaving: the gate fails closed."""
    return bool(getattr(extractor, "leaves_campus", True))


def permits(record) -> bool:
    from apps.ai.policy import decision_for_record

    return decision_for_record(record).allowed


def awaits_disclosure(record) -> bool:
    """The current Extractor leaves campus and the gate refuses ``record``."""
    from .selection import current_extractor

    return leaves_campus(current_extractor()) and not permits(record)


@contextmanager
def reading(record_id: int) -> Iterator[None]:
    """Name the Record whose PDF the extraction inside sends."""
    token = _subject.set(record_id)
    try:
        yield
    finally:
        _subject.reset(token)


def require_disclosure() -> None:
    """Raise `NotDisclosed` unless the named Record may leave now, read fresh."""
    from apps.records.models import Record

    record_id = _subject.get()
    record = None if record_id is None else (
        Record.objects.filter(pk=record_id, is_deleted=False).first()
    )
    if record is None or not permits(record):
        raise NotDisclosed()
