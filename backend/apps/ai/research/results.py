"""Tool results and the planner's view of them (ADR-038 §2.7, §4.1).

`Envelope` is the versioned contract of general-tools spec §3.3 (IR-590);
`ToolResult` stays as the legacy lane's result and `envelope_of` adapts it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
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
    #: An envelope-native result from a general tool (IR-591).
    shaped: Optional["Shaped"] = None

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


# -- IR-590: the versioned envelope ------------------------------------------

SCHEMA_VERSION = "1"


class Status(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"


class CoverageSubject(str, Enum):
    """What a coverage count is about; "complete" means complete for this."""

    SEARCH_CANDIDATES = "search_candidates"
    REQUESTED_SELECTION = "requested_selection"
    SCREENED_SUBSET = "screened_subset"
    METADATA_POPULATION = "metadata_population"
    NONE = "none"


_CODE = re.compile(r"[a-z][a-z0-9_]*")
#: Answer prose, UI routing and raw identity never ride in a tool result.
_FORBIDDEN_KEYS = frozenset({
    "answer", "wording", "markdown", "narrative", "summary", "route", "routing", "lane",
    "ui", "uihint", "display", "suggestedreply", "reasoning",
    "id", "pk", "uuid", "recordid", "chunkid", "userid", "runid",
})
_COUNTS = ("selected", "assessed", "uncertain", "unassessed")


@dataclass(frozen=True)
class SubjectCoverage:
    subject: CoverageSubject
    returned: int = 0
    #: Unknown is `None`, never zero.
    total: Optional[int] = None
    complete: bool = False
    selected: Optional[int] = None
    assessed: Optional[int] = None
    uncertain: Optional[int] = None
    unassessed: Optional[int] = None

    def __post_init__(self) -> None:
        if self.complete and self.subject is CoverageSubject.NONE:
            raise ValueError("complete must name a scope")

    @property
    def counted(self) -> bool:
        return bool(self.returned) or self.total is not None or any(
            getattr(self, name) is not None for name in _COUNTS)

    def public(self) -> dict[str, Any]:
        out: dict[str, Any] = {"subject": self.subject.value, "returned": self.returned,
                               "total": self.total, "complete": self.complete}
        out.update({name: getattr(self, name) for name in _COUNTS
                    if getattr(self, name) is not None})
        return out


@dataclass(frozen=True)
class Trace:
    """Private diagnostics: logs and audit only, never a model or a reader."""

    run_id: str
    tool: str
    reason: Optional[str] = None
    duplicate: bool = False
    #: A cached result failed reauthorization and was computed again.
    recomputed: bool = False
    elapsed_ms: Optional[int] = None


@dataclass(frozen=True)
class Envelope:
    status: Status
    coverage: SubjectCoverage
    trace: Trace
    items: tuple[Mapping[str, Any], ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    continuation: Optional[str] = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for code in self.limitations:
            if not isinstance(code, str) or not _CODE.fullmatch(code):
                raise ValueError(f"limitation must be a code: {code!r}")
        for entry in (*self.items, *self.evidence, *self.facts):
            _check_keys(entry)
        if self.status is Status.DENIED and (
            self.items or self.evidence or self.facts or self.continuation
            or self.coverage.counted
        ):
            raise ValueError("a denied result carries no content or counts")

    def public(self) -> dict[str, Any]:
        """The model-visible payload; the trace stays behind."""
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "items": [dict(i) for i in self.items],
            "evidence": [dict(e) for e in self.evidence],
            "facts": [dict(f) for f in self.facts],
            "coverage": self.coverage.public(),
            "continuation": self.continuation,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class Shaped:
    """What a general tool (IR-591) states directly; evidence stays in the result."""

    status: Status
    coverage: SubjectCoverage
    items: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    continuation: Optional[str] = None
    limitations: tuple[str, ...] = ()


def _normal(key: object) -> str:
    return re.sub(r"[_\-\s]", "", str(key)).casefold()


def _check_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        forbidden = {key for key in value if _normal(key) in _FORBIDDEN_KEYS}
        if forbidden:
            raise ValueError(f"forbidden key in a tool result: {sorted(forbidden)}")
        for child in value.values():
            _check_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _check_keys(child)


#: Rejection reasons a model may see, as public codes; the rest are arguments.
_REFERENCE_CODES = {
    "unissued_handle": "invalid_reference",
    "not_a_record_handle": "invalid_reference",
    "unissued_cursor": "invalid_reference",
    "cursor_mismatch": "invalid_reference",
}
#: Detail keys that are planner wording, not facts.
_WORDING = frozenset({"relative_to"})


def envelope_of(
    result: ToolResult,
    subject: CoverageSubject,
    trace: Trace,
    *,
    predicate: Optional[Mapping[str, Any]] = None,
) -> Envelope:
    """Adapt a legacy result; internal reasons move to the private trace."""
    trace = replace(trace, reason=result.reason, duplicate=result.duplicate)
    empty = SubjectCoverage(subject)
    if result.status is ToolStatus.REJECTED:
        if result.reason in _REFERENCE_CODES:
            return Envelope(Status.DENIED, empty, trace,
                            limitations=(_REFERENCE_CODES[result.reason],))
        code = {"unknown_tool": "unknown_tool", "stale_cursor": "stale_continuation"}.get(
            result.reason, "invalid_arguments")
        return Envelope(Status.UNAVAILABLE, empty, trace, limitations=(code,))
    if result.status is ToolStatus.REFUSED:
        # A policy refusal, such as ADR-027's floor, not an access denial.
        if (result.reason or "").startswith("budget:"):
            return Envelope(Status.UNAVAILABLE, empty, trace, limitations=("budget_exhausted",))
        note = result.coverage.note or "refused"
        return Envelope(Status.UNAVAILABLE, empty, trace, limitations=(note,))
    if result.status is ToolStatus.FAILED:
        return Envelope(Status.UNAVAILABLE, empty, trace, limitations=("tool_unavailable",))
    if result.shaped is not None:
        shaped = result.shaped
        return Envelope(
            shaped.status, shaped.coverage, trace, items=shaped.items,
            evidence=_items_and_evidence(result)[1], facts=shaped.facts,
            continuation=shaped.continuation, limitations=shaped.limitations,
        )

    limitations = []
    if result.status is ToolStatus.DEGRADED:
        limitations.append("degraded")
    if result.coverage.truncated:
        limitations.append("truncated")
    status = {ToolStatus.OK: Status.OK, ToolStatus.EMPTY: Status.EMPTY,
              ToolStatus.DEGRADED: Status.PARTIAL}[result.status]
    if status is Status.OK and result.coverage.truncated:
        status = Status.PARTIAL
    items, evidence = _items_and_evidence(result)
    return Envelope(
        status, _coverage(result, subject), trace,
        items=items, evidence=evidence, facts=_facts(result, subject, predicate),
        limitations=tuple(limitations),
    )


def _items_and_evidence(result: ToolResult):
    records = {e.record_id: e.handle for e in result.evidence if e.kind == RECORD}
    items, evidence = [], []
    for e in result.evidence:
        if e.kind == RECORD:
            items.append({"record": e.handle, "title": e.record_title,
                          **result.annotations.get(e.handle, {})})
            if e.text:
                evidence.append({"ref": e.handle, "record": e.handle,
                                 "content_kind": "abstract",
                                 "source_version": e.source_version, "text": e.text})
        elif e.kind == PASSAGE:
            evidence.append({
                "ref": e.handle, "record": records.get(e.record_id),
                "content_kind": "passage", "source_version": e.source_version[:12],
                "page": e.page, "section": " > ".join(e.context_path) or None,
                "text": e.text,
            })
    return tuple(items), tuple(evidence)


def _coverage(result: ToolResult, subject: CoverageSubject) -> SubjectCoverage:
    legacy = result.coverage
    if subject is CoverageSubject.REQUESTED_SELECTION:
        return SubjectCoverage(subject, returned=legacy.returned, complete=(
            legacy.label is Completeness.EXHAUSTIVE and not legacy.truncated))
    if subject is CoverageSubject.SCREENED_SUBSET:
        decisions = [row.get("decision") for row in result.detail.get("rows", ())]
        assessed = sum(d in ("include", "exclude") for d in decisions)
        uncertain = decisions.count("uncertain")
        unassessed = max(0, legacy.returned - assessed - uncertain)
        return SubjectCoverage(
            subject, returned=legacy.returned,
            complete=not legacy.truncated and unassessed == 0,
            selected=legacy.returned, assessed=assessed, uncertain=uncertain,
            unassessed=unassessed,
        )
    if subject is CoverageSubject.METADATA_POPULATION:
        total = result.detail.get("total", result.detail.get("sample_size"))
        return SubjectCoverage(subject, returned=legacy.returned, total=total, complete=True)
    return SubjectCoverage(subject, returned=legacy.returned)


def _facts(result: ToolResult, subject: CoverageSubject, predicate) -> tuple[dict, ...]:
    if subject is CoverageSubject.METADATA_POPULATION:
        snapshot = None
        if result.visible_record_ids is not None:
            ids = ",".join(str(pk) for pk in sorted(result.visible_record_ids))
            snapshot = hashlib.sha256(ids.encode()).hexdigest()[:12]
        provenance = {"kind": "metadata", "population": "records_visible_to_reader",
                      "predicate": dict(predicate or {}), "snapshot": snapshot}
    elif subject is CoverageSubject.SCREENED_SUBSET:
        provenance = {"kind": "screening", "method": result.detail.get("method")}
    elif subject is CoverageSubject.REQUESTED_SELECTION:
        provenance = {"kind": "document_structure"}
    else:
        provenance = {"kind": "computed"}
    return tuple({"name": name, "value": value, "provenance": provenance}
                 for name, value in result.detail.items() if name not in _WORDING)
