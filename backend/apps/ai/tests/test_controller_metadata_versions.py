"""Aggregate facts expire when metadata changes without visibility changes."""
import json
from dataclasses import replace

import pytest

from apps.ai.composition import use_composition_root
from apps.ai.models import Turn
from apps.ai.models.chunk import ChunkSet
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.research.context import RunContext
from apps.ai.research.registry import ToolRun, general_tools
from apps.ai.research.tools.common import visible_record_ids
from apps.records.models import Record

from .test_controller_http import asked_flood, call, compose, controller_root

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _years(scene):
    Record.objects.filter(pk=scene["flood"].pk).update(year_completed=2021)
    Record.objects.filter(pk=scene["pond"].pk).update(year_completed=2022)


def test_changed_year_after_count_reaches_neither_next_plan_nor_answer(
    flood_scene, monkeypatch, embedder,
):
    from apps.ai.research import tools

    _years(flood_scene)
    original = tools.AGGREGATE_RECORDS.execute

    def count_then_change(run, args):
        result = original(run, args)
        Record.objects.filter(pk=flood_scene["flood"].pk).update(year_completed=2023)
        return result

    monkeypatch.setattr(tools, "GENERAL_TOOLS", tuple(
        replace(tool, execute=count_then_change) if tool.name == "aggregate_records" else tool
        for tool in tools.GENERAL_TOOLS))
    planner = ScriptedToolCallingLLM([
        call("aggregate_records", {"operation": "count", "year_to": 2021}, "count"),
        compose(basis="evidence"),
    ])
    writer = ScriptedLLM(reply="There is one paper completed by 2021.")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert json.loads(planner.conversation_requests[-1].messages[1].content)["results"] == []
    assert not any(getattr(message, "tool_call_id", None)
                   for message in planner.conversation_requests[-1].messages)
    assert writer.calls == []
    assert body["answer"] is None and body["mode"] == "no_results"


def test_changed_year_during_answer_withdraws_stale_count(
    flood_scene, monkeypatch, embedder,
):
    _years(flood_scene)
    planner = ScriptedToolCallingLLM([
        call("aggregate_records", {"operation": "count", "year_to": 2021}, "count"),
        compose(basis="evidence"),
    ])
    claim = "There is one paper completed by 2021."
    writer = ScriptedLLM(reply=claim)
    original = writer.generate

    def change_during_answer(system, user):
        reply = original(system, user)
        Record.objects.filter(pk=flood_scene["flood"].pk).update(year_completed=2023)
        return reply

    monkeypatch.setattr(writer, "generate", change_during_answer)
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(writer.calls) == 1
    assert '"total", "value": 1' in writer.calls[0][1]
    assert body["answer"] is None and body["mode"] == "unavailable"
    assert claim not in json.dumps(body)
    assert claim not in Turn.objects.get(conversation=flood_scene["conversation"]).answer


@pytest.mark.parametrize("change", ["year", "index"])
def test_cached_aggregate_recomputes_for_same_ids_changed_dependencies(
    flood_scene, monkeypatch, embedder, change,
):
    _years(flood_scene)
    root = controller_root(monkeypatch, embedder=embedder,
                           planner=ScriptedToolCallingLLM([]), writer=ScriptedLLM())
    ctx = RunContext.for_request(user=flood_scene["reader"], root=root, lane="research")
    run = ToolRun.start(ctx, root)
    registry = general_tools()
    args = json.dumps({"operation": "count", "year_to": 2021})
    first = registry.invoke(run, "aggregate_records", args)
    visible = visible_record_ids(ctx)
    if change == "year":
        Record.objects.filter(pk=flood_scene["flood"].pk).update(year_completed=2023)
    else:
        ChunkSet.objects.filter(record=flood_scene["flood"], is_active=True).update(is_active=False)
    second = registry.invoke(run, "aggregate_records", args)

    assert visible_record_ids(ctx) == visible
    assert second.trace.recomputed and not second.trace.duplicate
    assert first.metadata_version != second.metadata_version
    assert "metadata_version" not in json.dumps(first.public())
    before = {fact["name"]: fact for fact in first.facts}
    after = {fact["name"]: fact for fact in second.facts}
    assert before["total"]["provenance"]["snapshot"] == after["total"]["provenance"]["snapshot"]
    changed_fact = "total" if change == "year" else "ai_readable"
    assert before[changed_fact]["value"] == 1 and after[changed_fact]["value"] == 0
