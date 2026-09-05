"""The ingestion lifecycle, as a transition table.

::

    Uploaded → Extracted → Chunked → Indexed → (Stale | Chunked) → Indexed
                                        ↓
                                     Failed   (reachable from anywhere)

The table exists to answer one question in one place that would otherwise
be answered inconsistently in three: **can a record be re-chunked after it
has been approved and published?** Yes. Chunking is an index concern, not a
record-state concern — a published record's ``pipeline_status`` and its
ingestion state are independent, and nothing here consults the former.

``Stale`` is set only by comparing content hashes — never by a timestamp
and never by a user action. An idempotent re-run of the pipeline on
identical input bumps a timestamp without any semantic change, so a
timestamp would mark the whole corpus stale for nothing.

Pure: no Django, no I/O, no clock, no randomness.
"""

from enum import Enum
from types import MappingProxyType
from typing import Mapping, Union


class IngestionState(str, Enum):
    """Where a record is in the ingestion pipeline.

    ``str``-valued so a state round-trips through a ``CharField`` and a
    Celery message body without a conversion at either end.
    """

    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    STALE = "stale"
    FAILED = "failed"

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.value


StateLike = Union[IngestionState, str]


# Self-loops are permitted where the pipeline needs them: Extracted →
# Extracted for an idempotent re-extract, Indexed → Indexed for a re-push.
# Failed is appended to every row below rather than written out per state,
# so "reachable from anywhere" stays true when a state is added.
_TRANSITIONS: dict[IngestionState, set[IngestionState]] = {
    IngestionState.UPLOADED: {IngestionState.EXTRACTED},
    IngestionState.EXTRACTED: {IngestionState.EXTRACTED, IngestionState.CHUNKED},
    IngestionState.CHUNKED: {IngestionState.CHUNKED, IngestionState.INDEXED},
    IngestionState.INDEXED: {
        IngestionState.INDEXED,
        IngestionState.CHUNKED,
        IngestionState.STALE,
    },
    IngestionState.STALE: {IngestionState.CHUNKED},
    # A failed run is retried from the top of the pipeline, not resumed
    # mid-way: whatever partial state it left is not to be trusted.
    IngestionState.FAILED: {IngestionState.EXTRACTED},
}

ALLOWED_TRANSITIONS: Mapping[IngestionState, frozenset[IngestionState]] = (
    MappingProxyType(
        {
            state: frozenset(
                targets | ({IngestionState.FAILED} if state is not IngestionState.FAILED else set())
            )
            for state, targets in _TRANSITIONS.items()
        }
    )
)


class IllegalTransition(Exception):
    """Raised when a caller asks for a transition the table does not allow."""


def _coerce(state: StateLike) -> IngestionState:
    try:
        return IngestionState(state)
    except ValueError as exc:
        raise IllegalTransition(f"{state!r} is not an ingestion state") from exc


def is_allowed_transition(source: StateLike, target: StateLike) -> bool:
    """Whether ``source`` → ``target`` is in the table.

    An unrecognised state is not a transition anyone can make, so it is
    ``False`` rather than an error — ``assert_transition`` is the one that
    raises, and it says which half was wrong.
    """
    try:
        return _coerce(target) in ALLOWED_TRANSITIONS[_coerce(source)]
    except IllegalTransition:
        return False


def assert_transition(source: StateLike, target: StateLike) -> IngestionState:
    """Return ``target`` as an :class:`IngestionState`, or raise.

    Returning the coerced target rather than ``None`` is what lets a caller
    write ``job.state = assert_transition(job.state, INDEXED)`` and have the
    check be structurally impossible to forget.
    """
    source_state = _coerce(source)
    target_state = _coerce(target)
    if target_state not in ALLOWED_TRANSITIONS[source_state]:
        raise IllegalTransition(
            f"{source_state.value} cannot transition to {target_state.value}; "
            f"allowed: {sorted(s.value for s in ALLOWED_TRANSITIONS[source_state])}"
        )
    return target_state


def staleness_after(
    state: StateLike, *, stored_hash: str, current_hash: str
) -> IngestionState:
    """The state ``state`` becomes given a fresh content hash.

    The only path to ``Stale`` in the codebase. It is a comparison of two
    hashes and nothing else — no clock is read, and no argument is offered
    by which a user could ask for a document to be marked stale.
    """
    current = _coerce(state)
    if current is not IngestionState.INDEXED:
        return current
    return current if stored_hash == current_hash else IngestionState.STALE
