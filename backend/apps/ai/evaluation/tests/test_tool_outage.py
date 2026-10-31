"""A09's outage turn gets a real tool outage during in-process replay."""

import json

from apps.ai.controller import loop
from apps.ai.evaluation.faults import OUTAGE_TASK, InjectedToolOutage, ToolOutage
from apps.ai.evaluation.replay import ASK_STREAM, CONVERSATIONS, collect_case
from apps.ai.research.registry import Tool, ToolRegistry

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def registry(calls):
    def tool(name):
        return Tool(name, name, SCHEMA, lambda run, args: calls.append(name) or name)
    return ToolRegistry([tool("search_research"), tool("read_papers"), tool("extract_evidence")])


def run_tool(reg, name):
    return reg._tools[name].execute(None, {})


def test_after_the_first_read_every_read_fails_while_armed():
    calls = []
    outage = ToolOutage()
    reg = outage.wrap(registry(calls))
    outage.plan({"intended_task": OUTAGE_TASK})
    assert run_tool(reg, "read_papers") == "read_papers"
    assert run_tool(reg, "search_research") == "search_research"
    for name in ("extract_evidence", "read_papers"):
        try:
            run_tool(reg, name)
        except InjectedToolOutage:
            pass
        else:
            raise AssertionError(f"{name} should have failed")
    assert outage.report() == {"kind": "tool_outage", "tools": ["extract_evidence", "read_papers"],
                               "reads": 3, "failed": 2, "fired": True}
    assert calls == ["read_papers", "search_research"]


def test_other_turns_are_untouched_and_carry_no_fault():
    calls = []
    outage = ToolOutage()
    reg = outage.wrap(registry(calls))
    outage.plan({"intended_task": "compare_pair"})
    assert [run_tool(reg, "read_papers") for _ in range(3)] == ["read_papers"] * 3
    assert outage.report() is None


def test_a_planned_outage_that_never_fires_says_so():
    outage = ToolOutage()
    reg = outage.wrap(registry([]))
    outage.plan({"intended_task": OUTAGE_TASK})
    run_tool(reg, "read_papers")
    assert outage.report()["fired"] is False


def test_installed_wraps_the_controller_registry_and_restores_it():
    original = loop.general_tools
    outage = ToolOutage()
    with outage.installed():
        assert loop.general_tools is not original
        assert set(loop.general_tools().names) == set(original().names)
    assert loop.general_tools is original


class Reply:
    def __init__(self, status, body=None, events=""):
        self.status_code, self.body, self.text = status, body or {}, events

    def json(self):
        return self.body


class Reader:
    def __init__(self):
        self.turns = []

    def post(self, path, payload):
        if path == CONVERSATIONS:
            return Reply(201, {"id": 1})
        assert path == ASK_STREAM
        self.turns.append({"id": len(self.turns) + 1, "question": payload["question"]})
        return Reply(200, events="event: done\ndata: " + json.dumps(
            {"answer": "An answer", "citations": [], "sources": []}) + "\n\n")

    def get(self, path):
        return Reply(200, {"turns": list(self.turns)})


def test_the_run_file_records_the_fault_only_on_the_outage_turn():
    case = {"id": "A09-D01", "family": "A09", "split": "development", "turns": [
        {"user": "missing field?", "intended_task": "missing_field"},
        {"user": "still explain", "intended_task": OUTAGE_TASK},
    ]}
    result = collect_case(Reader(), case, faults=ToolOutage())
    first, second = result["turns"]
    assert "fault" not in first
    assert second["fault"] == {"kind": "tool_outage", "tools": [], "reads": 0,
                               "failed": 0, "fired": False}


def test_the_registry_reports_an_injected_failure_as_tool_unavailable():
    from types import SimpleNamespace

    from apps.ai.research.results import Status

    outage = ToolOutage(succeed_first=0)
    reg = outage.wrap(registry([]))
    run = SimpleNamespace(ctx=SimpleNamespace(run_id="r1"), cache={},
                          spend=SimpleNamespace(charge_call=lambda: None))
    outage.plan({"intended_task": OUTAGE_TASK})
    envelope = reg.invoke(run, "extract_evidence", {})
    assert envelope.status is Status.UNAVAILABLE
    assert envelope.limitations == ("tool_unavailable",)


def test_the_manifest_names_the_injection():
    from apps.ai.evaluation.replay import collect_run

    case = {"id": "A09-D01", "family": "A09", "split": "development",
            "turns": [{"user": "q", "intended_task": OUTAGE_TASK}]}
    run = collect_run(Reader(), [case], set_id="s", set_digests={},
                      corpus={"paper_set_sha256": "x", "snapshot_id": "p"}, model_ids={},
                      limits={}, data_policy="fake", cache="cold", faults=ToolOutage())
    assert run["manifest"]["fault_injection"]["tool_outage"]["task"] == OUTAGE_TASK
    assert run["conversations"][0]["turns"][0]["fault"]["fired"] is False
