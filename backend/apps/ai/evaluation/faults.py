"""Evaluation-only tool outage for A09's partial-answer turn.

In-process replay only: nothing here is reachable over HTTP. On a turn whose
`intended_task` is the outage task, the first paper read succeeds and every
later read raises, so the controller meets the registry's real failure path
(`tool_unavailable`). Each such turn records whether the outage fired.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from typing import Mapping

OUTAGE_TASK = "partial_answer_after_tool_failure"
READ_TOOLS = frozenset({"read_papers", "extract_evidence"})


class InjectedToolOutage(RuntimeError):
    """Raised inside a read tool; the registry turns it into tool_unavailable."""


class ToolOutage:
    def __init__(self, *, succeed_first: int = 1):
        self.succeed_first = succeed_first
        self._armed = False
        self._reads = 0
        self._failed: list[str] = []

    def plan(self, turn: Mapping) -> None:
        self._armed = turn.get("intended_task") == OUTAGE_TASK
        self._reads = 0
        self._failed = []

    def report(self) -> dict | None:
        if not self._armed:
            return None
        return {"kind": "tool_outage", "tools": sorted(set(self._failed)),
                "reads": self._reads, "failed": len(self._failed),
                "fired": bool(self._failed)}

    def describe(self) -> dict:
        return {"tool_outage": {"task": OUTAGE_TASK, "tools": sorted(READ_TOOLS),
                                "succeed_first": self.succeed_first}}

    def wrap(self, registry):
        from apps.ai.research.registry import ToolRegistry

        return ToolRegistry([self._wrap_tool(tool) if tool.name in READ_TOOLS else tool
                             for tool in registry._tools.values()])

    def _wrap_tool(self, tool):
        execute = tool.execute

        def failing(run, args):
            if self._armed:
                self._reads += 1
                if self._reads > self.succeed_first:
                    self._failed.append(tool.name)
                    raise InjectedToolOutage(tool.name)
            return execute(run, args)

        return replace(tool, execute=failing)

    @contextmanager
    def installed(self):
        from apps.ai.controller import loop

        original = loop.general_tools
        loop.general_tools = lambda: self.wrap(original())
        try:
            yield self
        finally:
            loop.general_tools = original
