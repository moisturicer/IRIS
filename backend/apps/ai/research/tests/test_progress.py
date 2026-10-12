"""IR-504: the planner reports each step as it happens, and logs no content."""
import json
import logging

import pytest

from apps.ai.answers.events import AgentStep
from apps.ai.models import ResearchRun
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.research.context import RunContext
from apps.ai.research.planner import ResearchPlanner

from .helpers import TOPIC, root
from .test_context_loop import script

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def start(corpus, embedder, model):
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    return ResearchPlanner(stack, planner=model, answer_llm=ScriptedLLM()).run(TOPIC, ctx)


def collect(events):
    seen = []
    while True:
        try:
            seen.append(next(events))
        except StopIteration as stop:
            return seen, stop.value


def test_each_step_is_announced_running_then_reported_with_its_outcome(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["Find findings"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""),
        ("finish", {}, ""),
    )
    events, result = collect(start(corpus, embedder, model))
    assert all(isinstance(event, AgentStep) for event in events)
    search = [e for e in events if e.tool == "search_passages"]
    assert [e.status for e in search] == ["running", "ok"]
    assert search[0].position == search[1].position
    assert search[1].coverage and search[1].found >= 1
    finished = [e for e in events if e.status != "running"]
    assert finished == list(result.steps)
    assert [e.position for e in finished] == list(range(len(finished)))
    assert events[-1].kind == "answer" and events[-2] == AgentStep(events[-1].position, "answer", "running")


def test_a_reader_leaving_mid_run_closes_the_audit(corpus, embedder):
    model = script(("plan_research", {"subtasks": ["Find findings"]}, ""),
                   ("search_passages", {"query": TOPIC}, ""))
    events = start(corpus, embedder, model)
    while next(events).tool != "search_passages":
        pass
    events.close()
    run = ResearchRun.objects.get()
    assert (run.status, run.stop_reason) == ("interrupted", "interrupted")


@pytest.fixture
def run_logs(caplog):
    # `apps` does not propagate, so the handler goes on the planner's logger.
    logger = logging.getLogger("apps.ai.research.planner")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger=logger.name)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_one_log_line_per_run_with_codes_and_measurements_only(corpus, embedder, run_logs):
    model = script(("plan_research", {"subtasks": ["Find findings"]}, ""),
                   ("search_passages", {"query": TOPIC}, "A PRIVATE NOTE"),
                   ("subtask_done", {}, ""), ("finish", {}, ""))
    collect(start(corpus, embedder, model))
    [record] = [r for r in run_logs.records if r.getMessage().startswith("research run finished ")]
    assert record.stop_reason == "finish" and record.limit_hit is False
    assert record.tool_calls == 4 and record.malformed_calls == 0
    assert record.latency_ms >= 0 and record.prompt_tokens > 0
    logged = json.dumps({k: str(v) for k, v in vars(record).items()})
    assert TOPIC not in logged and "PRIVATE NOTE" not in logged


def test_a_limit_hit_is_logged_as_one(corpus, embedder, run_logs, settings):
    settings.AI_RESEARCH_MAX_TOOL_CALLS = 2
    model = script(("plan_research", {"subtasks": ["Find findings"]}, ""),
                   ("search_passages", {"query": TOPIC}, ""), ("search_passages", {"query": "x"}, ""))
    _, result = collect(start(corpus, embedder, model))
    [record] = [r for r in run_logs.records if r.getMessage().startswith("research run finished ")]
    assert record.limit_hit is True and record.stop_reason == result.stop_reason
    assert result.coverage_notes[0]["code"] == "stopped_early"
