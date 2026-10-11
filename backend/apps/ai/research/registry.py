"""The closed tool set; the one place a model's call runs (ADR-038 §2.4, §2.5)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from apps.ai.providers.tool_calling import ToolDefinition

from .budget import BudgetExhausted, Spend
from .context import RunContext
from .ledger import HandleRejected, Ledger
from .results import NO_COVERAGE, ToolResult, ToolStatus
from .schema import ArgumentsRejected, check_schema, validate

if TYPE_CHECKING:
    from apps.ai.composition import CompositionRoot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolRun:
    """One run's fixed context, ledger, spend and stack, handed to every tool."""

    ctx: RunContext
    ledger: Ledger
    root: "CompositionRoot"
    spend: Spend
    cache: dict[tuple[str, str], ToolResult] = field(default_factory=dict)

    @classmethod
    def start(cls, ctx: RunContext, root: "CompositionRoot") -> "ToolRun":
        return cls(
            ctx=ctx, ledger=Ledger(ctx.budget.max_ledger_passages),
            root=root, spend=Spend(ctx.budget),
        )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: Mapping[str, Any]
    execute: Callable[[ToolRun, dict[str, Any]], ToolResult]

    def __post_init__(self) -> None:
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

    def call(self, run: ToolRun, name: str, arguments: Any) -> ToolResult:
        # Every call counts, malformed and duplicate ones included (ADR-038 §5).
        try:
            run.spend.charge_call()
        except BudgetExhausted as exc:
            logger.info(
                "research run budget exhausted",
                extra={"run_id": run.ctx.run_id, "tool": name, "limit": str(exc)},
            )
            return ToolResult(ToolStatus.REFUSED, NO_COVERAGE, reason=f"budget:{exc}")

        tool = self._tools.get(name)
        if tool is None:
            return self._reject(run, name, "unknown_tool")
        try:
            args = validate(arguments, tool.parameters)
            key = (name, json.dumps(args, sort_keys=True))
            cached = run.cache.get(key)
            if cached is not None:
                return replace(cached, duplicate=True)
            result = tool.execute(run, args)
            run.cache[key] = result
            return result
        except (ArgumentsRejected, HandleRejected) as exc:
            return self._reject(run, name, str(exc))
        except Exception as exc:
            logger.warning(
                "research tool failed",
                extra={"run_id": run.ctx.run_id, "tool": name,
                       "error": type(exc).__name__},
            )
            return ToolResult.failed(type(exc).__name__)

    @staticmethod
    def _reject(run: ToolRun, name: str, reason: str) -> ToolResult:
        logger.warning(
            "research tool call rejected",
            extra={"run_id": run.ctx.run_id, "tool": name, "reason": reason},
        )
        return ToolResult.rejected(reason)


def research_tools() -> ToolRegistry:
    """The five corpus tools. `screen_records` joins in IR-501."""
    from .tools import TOOLS

    return ToolRegistry(TOOLS)
