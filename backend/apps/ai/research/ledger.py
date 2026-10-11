"""The run's evidence and its per-run handles (ADR-038 §2.5, §4.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

PASSAGE = "passage"
RECORD = "record"

_RECORD_HANDLE = re.compile(r"R[1-9][0-9]*")


class HandleRejected(ValueError):
    """A value that is not a handle this run issued for that kind."""


@dataclass(frozen=True)
class EvidenceItem:
    handle: str
    kind: str
    record_id: int
    record_title: str
    text: str
    chunk_id: Optional[int] = None
    chunk_set_hash: Optional[str] = None
    page: Optional[int] = None
    context_path: tuple[str, ...] = ()
    score: float = 0.0

    @property
    def pointer(self) -> tuple[int, Optional[int], Optional[str]]:
        """What is stored (ADR-026 §10): never the text."""
        return (self.record_id, self.chunk_id, self.chunk_set_hash)


class Ledger:
    """Collected passages and records; a model sees handles, never ids."""

    def __init__(self, max_passages: int = 30) -> None:
        self._max_passages = max_passages
        self._passages: dict[int, EvidenceItem] = {}
        self._passage_handles: dict[int, str] = {}
        self._records: dict[int, EvidenceItem] = {}
        self._record_by_handle: dict[str, int] = {}
        self.truncated = False

    def add_passage(
        self,
        *,
        record_id: int,
        chunk_id: int,
        chunk_set_hash: str,
        record_title: str,
        text: str,
        page: Optional[int],
        context_path: tuple[str, ...],
        score: float,
    ) -> EvidenceItem:
        existing = self._passages.get(chunk_id)
        if existing is not None:
            return existing
        # A dropped passage collected again keeps the handle it was issued.
        handle = self._passage_handles.setdefault(
            chunk_id, f"E{len(self._passage_handles) + 1}"
        )
        item = EvidenceItem(
            handle=handle, kind=PASSAGE,
            record_id=record_id, record_title=record_title, text=text,
            chunk_id=chunk_id, chunk_set_hash=chunk_set_hash, page=page,
            context_path=tuple(context_path), score=score,
        )
        self._passages[chunk_id] = item
        self._drop_weakest()
        return item

    def add_record(self, *, record_id: int, title: str, abstract: str) -> EvidenceItem:
        existing = self._records.get(record_id)
        if existing is not None:
            if existing.record_title != title or existing.text != abstract:
                existing = replace(existing, record_title=title, text=abstract)
                self._records[record_id] = existing
            return existing
        item = EvidenceItem(
            handle=f"R{len(self._records) + 1}", kind=RECORD,
            record_id=record_id, record_title=title, text=abstract,
        )
        self._records[record_id] = item
        self._record_by_handle[item.handle] = record_id
        return item

    def record_id(self, handle: object) -> int:
        """The record behind an issued `R` handle; anything else raises."""
        if not isinstance(handle, str) or not _RECORD_HANDLE.fullmatch(handle):
            raise HandleRejected("not_a_record_handle")
        try:
            return self._record_by_handle[handle]
        except KeyError:
            raise HandleRejected("unissued_handle") from None

    def holds(self, item: EvidenceItem) -> bool:
        """False for a passage the cap has dropped, even the one just added."""
        if item.kind == RECORD:
            return self._records.get(item.record_id) is item
        return self._passages.get(item.chunk_id) is item

    def passages(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._passages.values())

    def records(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._records.values())

    def _drop_weakest(self) -> None:
        # ADR-038 §5; records are never dropped.
        while len(self._passages) > self._max_passages:
            self.drop_weakest()

    def drop_weakest(self) -> bool:
        """Remove one whole passage for a prompt budget; preserve issued handles."""
        if not self._passages:
            return False
        weakest = min(self._passages.values(), key=lambda p: p.score)
        del self._passages[weakest.chunk_id]
        self.truncated = True
        return True
