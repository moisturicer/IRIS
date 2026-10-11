"""Tool results and the planner's view of them (ADR-038 §2.7, §4.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

from .ledger import PASSAGE, RECORD, EvidenceItem


class Completeness(str, Enum):
    EXHAUSTIVE = "exhaustive"
    SCREENED = "screened"
    MATCHES_FOUND = "matches_found"
    SAMPLE = "sample"


class ToolStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    DEGRADED = "degraded"
    FAILED = "failed"
    REJECTED = "rejected"
    #: The tool declined by rule, such as ADR-027 §1d's floor.
    REFUSED = "refused"


def status_for(found: int, degraded: bool = False) -> "ToolStatus":
    if degraded:
        return ToolStatus.DEGRADED
    return ToolStatus.OK if found else ToolStatus.EMPTY


@dataclass(frozen=True)
class Coverage:
    label: Completeness
    returned: int = 0
    truncated: bool = False
    #: A reason code, such as `below_floor`. Never free text.
    note: Optional[str] = None


#: What a call that produced nothing claims: a sample of nothing.
NO_COVERAGE = Coverage(Completeness.SAMPLE)


@dataclass(frozen=True)
class ToolResult:
    status: ToolStatus
    coverage: Coverage
    evidence: tuple[EvidenceItem, ...] = ()
    #: Computed facts: counts, groups, headings. Code-produced only.
    detail: Mapping[str, Any] = field(default_factory=dict)
    #: Per-handle facts for the planner, such as year or how a record matched.
    annotations: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    reason: Optional[str] = None
    #: The same call again: the cached result, still counted (ADR-038 §5).
    duplicate: bool = False
    # Private provenance for metadata aggregates, never rendered for a vendor.
    visible_record_ids: frozenset[int] | None = None

    @classmethod
    def rejected(cls, reason: str) -> "ToolResult":
        return cls(ToolStatus.REJECTED, NO_COVERAGE, reason=reason)

    @classmethod
    def failed(cls, reason: str) -> "ToolResult":
        return cls(ToolStatus.FAILED, NO_COVERAGE, reason=reason)

    def planner_message(self) -> str:
        """The only rendering of a result for a vendor; gated inside each tool."""
        records = {e.record_id: e.handle for e in self.evidence if e.kind == RECORD}
        message: dict[str, Any] = {
            "status": self.status.value,
            "coverage": {
                "label": self.coverage.label.value,
                "returned": self.coverage.returned,
                "truncated": self.coverage.truncated,
                "note": self.coverage.note,
            },
        }
        if self.reason:
            message["reason"] = self.reason
        if self.duplicate:
            message["duplicate"] = True
        passages = [
            {
                "handle": e.handle,
                "record": records.get(e.record_id),
                "title": e.record_title,
                "section": " > ".join(e.context_path),
                "page": e.page,
                "text": e.text,
            }
            for e in self.evidence
            if e.kind == PASSAGE
        ]
        if passages:
            message["passages"] = passages
        record_rows = [
            {
                "handle": e.handle,
                "title": e.record_title,
                "abstract": e.text,
                **self.annotations.get(e.handle, {}),
            }
            for e in self.evidence
            if e.kind == RECORD
        ]
        if record_rows:
            message["records"] = record_rows
        if self.detail:
            message["detail"] = dict(self.detail)
        return json.dumps(message, ensure_ascii=False)
