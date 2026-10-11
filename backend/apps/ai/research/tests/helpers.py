import json
import logging
from contextlib import contextmanager
from dataclasses import replace

from apps.ai.composition import CompositionRoot
from apps.ai.providers.fakes import ScriptedReranker, ScriptedToolCallingLLM
from apps.ai.research.context import Budget, RunContext
from apps.ai.research.registry import ToolRun, research_tools

TOPIC = "rainfall flooding neural network"
TOOLS = research_tools()


def root(embedder, permits=lambda record: True):
    return CompositionRoot(embedder=embedder, reranker=ScriptedReranker(), permits=permits)


def start_run(user, root, conversation=None, **limits):
    # Roomy limits, so tests exercise tools rather than the budget.
    limits = {"max_calls_per_subtask": 100, "max_tool_calls": 100, **limits}
    ctx = RunContext.for_request(
        user=user, root=root, lane="research", conversation=conversation,
        budget=replace(Budget.from_settings(), **limits),
    )
    return ToolRun.start(ctx, root)


def call(run, name, **arguments):
    return TOOLS.call(run, name, json.dumps(arguments))


def record_ids(result):
    return {e.record_id for e in result.evidence}


def sent_to_planner(*results):
    """What a planner request carries, as captured by the scripted vendor."""
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.answering()])
    planner.complete_with_tools(
        "plan", "\n".join(r.planner_message() for r in results), TOOLS.definitions()
    )
    return planner.tool_requests[0].user


@contextmanager
def registry_logs(caplog):
    # `apps` does not propagate to the root logger caplog listens on.
    logger = logging.getLogger("apps.ai.research.registry")
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
