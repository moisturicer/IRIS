"""The closed tool set; the one place a model's call runs (ADR-038 §2.4, §2.5).

`call` returns the legacy `ToolResult`; `invoke` returns IR-590's `Envelope`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Sequence

from apps.ai.providers.tool_calling import ToolDefinition

from .budget import BudgetExhausted, Spend
from .context import RunContext
from .ledger import PASSAGE, RECORD, HandleRejected, Ledger
from .results import (
    NO_COVERAGE, CoverageSubject, Envelope, ToolResult, ToolStatus, Trace, envelope_of,
)
from .schema import ArgumentsRejected, check_schema, validate

if TYPE_CHECKING:
    from apps.ai.composition import CompositionRoot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Presentation:
    """Records last shown to the reader, in display order (IR-591).

    Supplied by the application from committed conversation state; a model
    names one only by its ordinal.
    """

    revision: int
    record_ids: tuple[int, ...]


@dataclass(frozen=True)
class ToolRun:
    """One run's fixed context, ledger, spend and stack, handed to every tool."""

    ctx: RunContext
    ledger: Ledger
    root: "CompositionRoot"
    spend: Spend
    cache: dict[tuple[str, str], ToolResult] = field(default_factory=dict)
    # Workflow-owned candidate IDs; never a tool argument or vendor payload.
    screen_candidate_ids: tuple[int, ...] | None = None
    presented: Presentation | None = None

    @classmethod
    def start(
        cls, ctx: RunContext, root: "CompositionRoot", *, scoped_handles: bool = False,
    ) -> "ToolRun":
        """`scoped_handles` tags every handle with this run (IR-590)."""
        tag = hashlib.sha256(ctx.run_id.encode()).hexdigest()[:6] if scoped_handles else ""
        return cls(
            ctx=ctx, ledger=Ledger(ctx.budget.max_ledger_passages, tag=tag),
            root=root, spend=Spend(ctx.budget),
        )

    def issue_cursor(
        self, tool: str, args: Mapping[str, Any], *, source_version: str, position: int,
    ) -> Optional[str]:
        return self.ledger.issue_cursor(
            tool=tool, query=_query_digest(args), caller=self.ctx.caller,
            source_version=source_version, position=position,
        )

    def resume_cursor(
        self, token: object, tool: str, args: Mapping[str, Any], *, source_version: str,
    ) -> int:
        return self.ledger.resume(
            token, tool=tool, query=_query_digest(args), caller=self.ctx.caller,
            source_version=source_version,
        )


def _query_digest(args: Mapping[str, Any]) -> str:
    query = {name: value for name, value in args.items() if name != "cursor"}
    return hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: Mapping[str, Any]
    execute: Callable[[ToolRun, dict[str, Any]], ToolResult]
    # Stateful inputs owned by the application, absent from vendor schemas.
    cache_context: Callable[[ToolRun], Any] | None = None
    #: What this tool's coverage counts (general-tools spec §3.3).
    subject: CoverageSubject = CoverageSubject.NONE

    def __post_init__(self) -> None:
        if self.parameters.get("type") != "object":
            raise ValueError("tool parameters must be an object schema")
        check_schema(self.parameters)

    def definition(self) -> ToolDefinition:
        return ToolDefinition(self.name, self.description, dict(self.parameters))


class ToolRegistry:
    """Rejections are logged with the run id and a reason code, never text."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition() for tool in self._tools.values())

    def subject(self, name: str) -> CoverageSubject:
        tool = self._tools.get(name)
        return tool.subject if tool is not None else CoverageSubject.NONE

    def call(self, run: ToolRun, name: str, arguments: Any) -> ToolResult:
        return self._dispatch(run, name, arguments)[0]

    def invoke(self, run: ToolRun, name: str, arguments: Any) -> Envelope:
        """One call as the versioned envelope; diagnostics stay in its trace."""
        started = time.monotonic()
        result, args, recomputed = self._dispatch(run, name, arguments)
        subject = self.subject(name)
        trace = Trace(
            run_id=run.ctx.run_id, tool=name[:64], recomputed=recomputed,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        predicate = args if subject is CoverageSubject.METADATA_POPULATION else None
        envelope = envelope_of(result, subject, trace, predicate=predicate)
        logger.info("research tool envelope", extra={
            "run_id": trace.run_id, "tool": trace.tool, "status": envelope.status.value,
            "reason": envelope.trace.reason, "duplicate": envelope.trace.duplicate,
            "recomputed": trace.recomputed, "elapsed_ms": trace.elapsed_ms,
        })
        return envelope

    def _dispatch(
        self, run: ToolRun, name: str, arguments: Any,
    ) -> tuple[ToolResult, Optional[dict[str, Any]], bool]:
        # Every call counts, malformed and duplicate ones included (ADR-038 §5).
        try:
            run.spend.charge_call()
        except BudgetExhausted as exc:
            logger.info(
                "research run budget exhausted",
                extra={"run_id": run.ctx.run_id, "tool": name, "limit": str(exc)},
            )
            refused = ToolResult(ToolStatus.REFUSED, NO_COVERAGE, reason=f"budget:{exc}")
            return refused, None, False

        tool = self._tools.get(name)
        if tool is None:
            return self._reject(run, name, "unknown_tool"), None, False
        args, recomputed = None, False
        try:
            args = validate(arguments, tool.parameters)
            identity = args
            if tool.cache_context is not None:
                identity = {"arguments": args, "context": tool.cache_context(run)}
            key = (name, json.dumps(identity, sort_keys=True))
            cached = run.cache.get(key)
            if cached is not None:
                if _still_current(run, cached):
                    return replace(cached, duplicate=True), args, False
                # Reauthorized before reuse (IR-590): stale or withheld, run again.
                del run.cache[key]
                recomputed = True
            result = tool.execute(run, args)
            run.cache[key] = result
            return result, args, recomputed
        except (ArgumentsRejected, HandleRejected) as exc:
            return self._reject(run, name, str(exc)), args, recomputed
        except Exception as exc:
            logger.warning(
                "research tool failed",
                extra={"run_id": run.ctx.run_id, "tool": name,
                       "error": type(exc).__name__},
            )
            return ToolResult.failed(type(exc).__name__), args, recomputed

    @staticmethod
    def _reject(run: ToolRun, name: str, reason: str) -> ToolResult:
        logger.warning(
            "research tool call rejected",
            extra={"run_id": run.ctx.run_id, "tool": name, "reason": reason},
        )
        return ToolResult.rejected(reason)


def _still_current(run: ToolRun, result: ToolResult) -> bool:
    """Every source still readable, disclosable and on its recorded version."""
    # Local imports: the tools package imports this module.
    from apps.ai.models.chunk import DocumentChunk

    from .tools.common import disclosable, visible_record_ids

    allowed = disclosable(run.ctx, {item.record_id for item in result.evidence})
    for item in result.evidence:
        record = allowed.get(item.record_id)
        if record is None:
            return False
        if item.kind == RECORD and (item.record_title, item.text) != (record.title, record.abstract):
            return False
    passages = {item.chunk_id: item.chunk_set_hash
                for item in result.evidence if item.kind == PASSAGE}
    if passages:
        active = dict(
            DocumentChunk.objects.filter(
                pk__in=passages, chunk_set__is_active=True, deleted_at__isnull=True,
            ).values_list("pk", "chunk_set__content_hash")
        )
        if any(active.get(chunk) != version for chunk, version in passages.items()):
            return False
    return (result.visible_record_ids is None
            or result.visible_record_ids == visible_record_ids(run.ctx))


def reissue(run: ToolRun, record_ids: Sequence[int]) -> tuple[str, ...]:
    """Handles for canonical references still readable; others drop silently."""
    from .tools.common import collect_record, disclosable

    allowed = disclosable(run.ctx, record_ids)
    return tuple(
        collect_record(run.ledger, allowed[pk]).handle
        for pk in dict.fromkeys(record_ids) if pk in allowed
    )


def research_tools() -> ToolRegistry:
    """The six corpus tools (ADR-038 §2)."""
    from .tools import TOOLS

    return ToolRegistry(TOOLS)


def general_tools() -> ToolRegistry:
    """The five general research tools (general-tools spec §3.2, IR-591)."""
    from .tools import GENERAL_TOOLS

    return ToolRegistry(GENERAL_TOOLS)
