"""Ingestion: the lifecycle, the idempotency key, and the job that carries
both (IR-115 G).

``lifecycle`` and ``keys`` are pure — no Django, no I/O — for the same
reason ``apps.ai.chunking`` is: the rules worth being sure about should be
testable with a table and an assertion. ``jobs`` is the thin Django layer
that claims a key and moves a row through the table.
"""

from .keys import ingestion_job_key
from .lifecycle import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    IngestionState,
    assert_transition,
    is_allowed_transition,
    staleness_after,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "IllegalTransition",
    "IngestionState",
    "assert_transition",
    "is_allowed_transition",
    "staleness_after",
    "ingestion_job_key",
]
