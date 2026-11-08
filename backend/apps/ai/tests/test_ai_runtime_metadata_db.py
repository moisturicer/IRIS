"""Resolving named papers and exact metadata counts, on real PostgreSQL (IR-750, ADR-049 §5, §9).

Driven through the run routes with a scripted executor calling the tools,
under a restricted `iris_ai_runtime` login and Django-issued grants, so the
population every answer is computed over is the row policy's, not the tool's.
"""

import asyncio
import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.executor import Result  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.records.models import Classification, Record, RecordOwner  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from .corpus import make_user  # noqa: E402
from . import test_ai_runtime_agent_loop_db as loop_db  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402
from .test_ai_runtime_research_db import FLOOD, ask, paper  # noqa: E402
from .test_ai_runtime_runs_db import as_reader, submit  # noqa: E402

api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def research(api, runtime):
    client, holder = api
    holder["dsn"] = runtime
    return api


def bare(title, *, status=PipelineStatus.PUBLISHED, owner=None, **fields):
    """A Record with no Manuscript read yet."""
    record = Record.objects.create(title=title, abstract="", pipeline_status=status, **fields)
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


# --- Resolving named papers ------------------------------------------------------

def test_a_title_resolves_to_a_handle_the_reading_tools_accept(research):
    reader = make_user("resolve-exact@cit.edu")
    flood = paper("Flood forecasting with neural networks", {4: [("Methods", FLOOD)]})

    async def script(tools):
        found = await tools.resolve(["flood forecasting with neural networks."])
        await tools.outline(found.matches[0].records[0].handle)

    response, seen, _ = ask(research, reader, script, key="resolve-exact")
    assert response.json()["state"] == "completed"
    (_, found), (_, outline) = seen
    assert found.status == "ok"
    (match,) = found.matches
    assert (match.reference, match.kind, match.match) == (1, "title", "exact_title")
    assert [(r.record_id, r.title) for r in match.records] == [
        (flood.pk, "Flood forecasting with neural networks")]
    assert outline.status == "ok"


def test_a_short_name_shared_by_several_papers_is_ambiguous_and_never_shows_a_denied_one(research):
    owner, other = make_user("resolve-owner@cit.edu"), make_user("resolve-other@cit.edu")
    paper("MeshKV: caching for edge devices", {1: [("Intro", "edge caching")]})
    paper("MeshKV: routing across meshes", {1: [("Intro", "mesh routing")]})
    draft = bare("MeshKV: unpublished results", status=PipelineStatus.DRAFT, owner=owner)

    async def script(tools):
        await tools.resolve(["MeshKV"], record_ids=[draft.pk])

    _, seen, _ = ask(research, other, script, key="resolve-other")
    (_, found), = seen
    assert found.status == "ambiguous"
    by_name, by_id = found.matches
    assert by_name.match == "ambiguous" and by_name.kind == "title"
    assert sorted(r.title for r in by_name.records) == [
        "MeshKV: caching for edge devices", "MeshKV: routing across meshes"]
    # Withheld and unknown look the same: nothing says a draft exists.
    assert (by_id.kind, by_id.match, by_id.records) == ("record_id", "none", ())

    _, seen, _ = ask(research, owner, script, key="resolve-owner")
    (_, found), = seen
    assert sorted(r.title for r in found.matches[0].records) == [
        "MeshKV: caching for edge devices", "MeshKV: routing across meshes",
        "MeshKV: unpublished results"]
    assert [r.record_id for r in found.matches[1].records] == [draft.pk]


def test_a_paper_with_no_manuscript_is_named_but_has_nothing_to_read(research):
    reader = make_user("resolve-bare@cit.edu")
    record = bare("Coastal erosion survey")

    async def script(tools):
        found = await tools.resolve([], record_ids=[record.pk])
        await tools.read_page(found.matches[0].records[0].handle, 1)

    _, seen, _ = ask(research, reader, script, key="resolve-bare")
    (_, found), (_, page) = seen
    assert found.status == "ok"
    assert found.matches[0].match == "record_id"
    assert found.matches[0].records[0].source is None
    # Absent, not unmatched: the model can tell "no Manuscript" from "no such page" (IR-731).
    assert (page.status, page.reason) == ("no_match", "no_manuscript")


def test_paper_chat_resolves_only_its_own_record(research):
    reader = make_user("resolve-scope@cit.edu")
    scoped = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Flood risk maps", {1: [("Intro", "maps of flood risk")]})

    async def script(tools):
        await tools.resolve(["Flood risk maps", "Flood forecasting"])

    _, seen, _ = ask(research, reader, script, key="resolve-scope", record_id=scoped.pk)
    (_, found), = seen
    assert found.status == "partial"
    assert [m.match for m in found.matches] == ["none", "exact_title"]
    assert found.matches[1].records[0].record_id == scoped.pk


# --- Exact metadata counts -------------------------------------------------------

def area(name):
    return Classification.objects.get_or_create(name=name)[0]


def test_an_area_count_is_exact_over_each_readers_own_population(research):
    owner, other = make_user("count-owner@cit.edu"), make_user("count-other@cit.edu")
    hydrology, ecology = area("Hydrology"), area("Ecology")
    first = bare("Flood gauges", classification=hydrology, year_completed=2022)
    second = bare("River sediment", classification=hydrology, year_completed=2024)
    bare("Mangrove survey", classification=ecology, year_completed=2024)
    bare("Unfiled note", year_completed=2023)
    draft = bare("Private levee study", status=PipelineStatus.DRAFT, owner=owner,
                 classification=hydrology, year_completed=2024)

    async def script(tools):
        await tools.count({"classification": "hydrology"})
        await tools.count({}, group_by="classification")

    _, seen, _ = ask(research, other, script, key="count-other")
    (_, area_count), (_, grouped) = seen
    assert area_count.status == "ok"
    fact = area_count.count
    assert (fact.total, fact.filters, fact.scope_record_id) == (2, (("classification", "Hydrology"),), None)
    assert fact.population == frozenset({first.pk, second.pk})
    assert fact.relative_to == "of the records you can see"
    assert grouped.count.groups == (("Ecology", 1), ("Hydrology", 2))
    assert (grouped.count.total, grouped.count.ungrouped) == (4, 1)

    _, seen, _ = ask(research, owner, script, key="count-owner")
    (_, area_count), (_, grouped) = seen
    assert area_count.count.total == 3 and draft.pk in area_count.count.population
    assert grouped.count.groups == (("Ecology", 1), ("Hydrology", 3))


def test_filters_narrow_a_count_and_an_unknown_value_is_refused_not_zero(research):
    reader = make_user("count-filters@cit.edu")
    hydrology = area("Hydrology")
    area("Astronomy")
    bare("Flood gauges", classification=hydrology, year_completed=2022, is_ip=True)
    bare("River sediment", classification=hydrology, year_completed=2024)

    async def script(tools):
        await tools.count({"classification": "Hydrology", "year_from": 2023, "year_to": 2025})
        await tools.count({"classification": "Hydrology", "is_ip": True}, group_by="year")
        await tools.count({"classification": "Astronomy"})
        await tools.count({"classification": "Alchemy"})
        await tools.count({"region": "Visayas"})

    _, seen, _ = ask(research, reader, script, key="count-filters")
    (_, years), (_, ip), (_, empty), (_, unknown), (_, undeclared) = seen
    assert years.count.total == 1
    assert ip.count.total == 1 and ip.count.groups == ((2022, 1),)
    # An Area no readable paper is in is an exact zero, never a refusal.
    assert (empty.status, empty.count.total) == ("no_match", 0)
    assert (unknown.status, unknown.reason, unknown.count) == ("unavailable", "unknown_filter_value", None)
    assert (undeclared.status, undeclared.reason) == ("unavailable", "invalid_argument")


def test_a_name_two_catalogue_entries_share_but_for_case_is_refused_not_guessed(research):
    reader = make_user("count-case@cit.edu")
    bare("Flood gauges", classification=area("Hydrology"))
    bare("River sediment", classification=area("HYDROLOGY"))

    async def script(tools):
        await tools.count({"classification": "hydrology"})

    _, seen, _ = ask(research, reader, script, key="count-case")
    (_, refused), = seen
    assert (refused.status, refused.reason, refused.count) == ("unavailable", "ambiguous_filter_value", None)


def test_paper_chat_counts_only_its_own_record(research):
    reader = make_user("count-scope@cit.edu")
    hydrology = area("Hydrology")
    scoped = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    Record.objects.filter(pk=scoped.pk).update(classification=hydrology)
    bare("River sediment", classification=hydrology)

    async def script(tools):
        await tools.count({"classification": "Hydrology"})

    _, seen, _ = ask(research, reader, script, key="count-scope", record_id=scoped.pk)
    (_, scoped_count), = seen
    assert (scoped_count.count.total, scoped_count.count.scope_record_id) == (1, scoped.pk)


def test_a_revoked_paper_leaves_the_count_and_its_handle_is_refused(research):
    reader = make_user("count-revoked@cit.edu")
    hydrology = area("Hydrology")
    kept = bare("Flood gauges", classification=hydrology)
    revoked = bare("River sediment", classification=hydrology)

    def unpublish():
        Record.objects.filter(pk=revoked.pk).update(pipeline_status=PipelineStatus.DRAFT)

    async def script(tools):
        before = await tools.count({"classification": "Hydrology"})
        named = await tools.resolve([], record_ids=[revoked.pk])
        await asyncio.to_thread(unpublish)
        await tools.count({"classification": "Hydrology"})
        await tools.outline(named.matches[0].records[0].handle)
        return Result(answer=f"{before.count.total} papers.")

    _, seen, _ = ask(research, reader, script, key="count-revoked")
    (_, before), _, (_, after), (_, outline) = seen
    assert before.count.total == 2
    assert (after.count.total, after.count.population) == (1, frozenset({kept.pk}))
    assert (outline.status, outline.reason) == ("unavailable", "unknown_handle")


# --- Reopened Turns keep exact totals apart from samples ------------------------------

def counted_and_sampled(population):
    return Result(answer="Of the records you can see, 2 are in Hydrology; one study found floods.", facts=(
        {"kind": "exact_count", "total": 2, "filters": {"classification": "Hydrology"},
         "group_by": None, "groups": [], "ungrouped": 0, "scope_record_id": None,
         "relative_to": "of the records you can see", "population": sorted(population)},
        {"kind": "keyword_sample", "papers": 1, "exhaustive": False},
    ))


EXACT_SHOWN = {"kind": "exact_count", "total": 2, "filters": {"classification": "Hydrology"},
               "group_by": None, "groups": [], "ungrouped": 0, "scope": "readable_records",
               "relative_to": "of the records you can see"}
SAMPLE_SHOWN = {"kind": "keyword_sample", "papers": 1, "exhaustive": False}


def test_a_reopened_turn_keeps_its_exact_count_apart_from_its_sample_and_never_shows_ids(research):
    reader = make_user("facts-reopen@cit.edu")
    hydrology = area("Hydrology")
    counted = [bare("Flood gauges", classification=hydrology), bare("River sediment", classification=hydrology)]

    async def script(tools):
        return counted_and_sampled(r.pk for r in counted)

    response, _, grant = ask(research, reader, script, key="facts-reopen")
    client, holder = research
    # The reader protocol is served only for the agent executor; the script stands in for it.
    holder["service"].executor.name = "agent"
    url = f"/api/v1/ai/conversations/{response.json()['conversation_id']}"
    for headers in ({}, {"X-IRIS-Protocol": "runs-reader-1"}):
        turn = client.get(url, headers={**as_reader(grant), **headers}).json()["turns"][0]
        assert turn["facts"] == [EXACT_SHOWN, SAMPLE_SHOWN]
        assert "population" not in str(turn)


def test_a_turn_counting_a_paper_the_reader_lost_is_withheld_on_reopen(research):
    reader = make_user("facts-revoked@cit.edu")
    hydrology = area("Hydrology")
    counted = [bare("Flood gauges", classification=hydrology), bare("River sediment", classification=hydrology)]

    async def script(tools):
        return counted_and_sampled(r.pk for r in counted)

    response, _, grant = ask(research, reader, script, key="facts-revoked")
    Record.objects.filter(pk=counted[1].pk).update(pipeline_status=PipelineStatus.DRAFT)
    client, holder = research
    holder["service"].executor.name = "agent"
    url = f"/api/v1/ai/conversations/{response.json()['conversation_id']}"
    turn = client.get(url, headers=as_reader(grant)).json()["turns"][0]
    assert turn["answer"].startswith("This answer is unavailable")
    assert turn["facts"] == [] and turn["citations"] == []
    # The run's own status agrees with the reopened Turn.
    reopened = client.get(url, headers={**as_reader(grant), "X-IRIS-Protocol": "runs-reader-1"}).json()
    assert reopened["runs"][0]["sources_available"] is False
    status = client.get(f"/api/v1/ai/runs/{response.json()['id']}",
                        headers={**as_reader(grant), "X-IRIS-Protocol": "runs-reader-1"}).json()
    assert status["sources_available"] is False


# --- The ticket's demonstration: the AGENT, two readers -------------------------------

PIN_2 = dataclasses.replace(loop_db.PIN, prompt_version="agent-research-2", tool_version="research-2")


def agent_service(dsn, provider):
    cfg = runs_config.RunsConfig(database_url=dsn, executor="deterministic", limits=loop_db.LIMITS,
                                 dispatch=runs_db.DISPATCH)
    executor = AgentExecutor(provider, PIN_2, RESERVES, profiles=loop_db.PROFILES)
    built = RunService(RunStore(dsn), cfg, executor, runs_db.Drain())
    built.notifier.service = built
    return built


def named(payload):
    [match] = loop_db.last_result(payload)["matches"]
    [found] = match["papers"]
    return loop_db.reply(f"That is «{found['title']}».")


def total(payload):
    count = loop_db.last_result(payload)["count"]
    return loop_db.reply(f"Of the records you can see, there are {count['total']} Hydrology papers.")


def sampled(payload):
    found = loop_db.last_result(payload)
    titles = {p["paper"]: p["title"] for p in found["papers"]}
    cited = " and ".join(f"«{titles[p['paper']]}» [{p['passage']}]" for p in found["passages"])
    return loop_db.reply(f"A keyword search found {cited}; a search is a sample, not a total.")


def conversation_of(client, holder, dsn, grant, reader_key):
    turns = (
        ("Which paper is this? Flood forecasting",
         loop_db.tools(loop_db.call("r", "resolve_papers", references=["Flood forecasting"])), named),
        ("How many Hydrology papers are there?",
         loop_db.tools(loop_db.call("c", "count_records", classification="Hydrology")), total),
        ("Which of them study floods?", loop_db.tools(loop_db.call("s", "search", query="flood")), sampled),
    )
    conversation = None
    for n, (question, first, answer) in enumerate(turns):
        holder["service"] = agent_service(dsn, loop_db.recording(first, answer))
        body = {"conversation_id": conversation, "base_revision": n} if conversation else {}
        asked = submit(client, grant, f"{reader_key}-{n}", question, **body).json()
        assert asked["state"] == "completed", asked
        conversation = asked["conversation_id"]
    return client.get(f"/api/v1/ai/conversations/{conversation}", headers=as_reader(grant)).json()["turns"]


def test_two_readers_name_a_paper_count_an_area_and_get_a_sample_each_from_their_own_population(
        api, runtime):
    client, holder = api
    owner, other = make_user("demo-owner@cit.edu"), make_user("demo-other@cit.edu")
    hydrology = area("Hydrology")
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    levee = paper("Levee breach model", {2: [("Results", "levee breaches worsened the flood")]},
                  status=PipelineStatus.DRAFT, owner=owner)
    river = bare("River sediment")
    Record.objects.filter(pk__in=[flood.pk, levee.pk, river.pk]).update(classification=hydrology)

    for reader, key in ((other, "demo-other"), (owner, "demo-owner")):
        grant = issue.reader_session_grant(reader).token
        which, count, sample = conversation_of(client, holder, runtime, grant, key)
        # The authorized database result, by Django's own visibility predicate.
        expected = Record.objects.visible_to(reader).filter(classification=hydrology).count()

        assert which["answer"] == "That is «Flood forecasting»."
        assert count["answer"] == f"Of the records you can see, there are {expected} Hydrology papers."
        assert count["facts"] == [{
            "kind": "exact_count", "total": expected, "filters": {"classification": "Hydrology"},
            "group_by": None, "groups": [], "ungrouped": 0, "scope": "readable_records",
            "relative_to": "of the records you can see"}]
        cited = {c["record_id"] for c in sample["citations"]}
        assert sample["facts"] == [{"kind": "keyword_sample", "papers": len(cited), "exhaustive": False}]
        assert cited <= set(Record.objects.visible_to(reader).values_list("pk", flat=True))

    assert expected == 3 and cited == {flood.pk, levee.pk}


def test_a_listing_names_every_readable_match_with_an_exact_total(research):
    owner, other = make_user("list-owner@cit.edu"), make_user("list-other@cit.edu")
    hydrology, ecology = area("Hydrology"), area("Ecology")
    first = bare("River sediment", classification=hydrology, year_completed=2024)
    second = bare("Flood gauges", classification=hydrology, year_completed=2022)
    bare("Mangrove survey", classification=ecology, year_completed=2024)
    draft = bare("Private levee study", status=PipelineStatus.DRAFT, owner=owner,
                 classification=hydrology, year_completed=2023)

    async def script(tools):
        await tools.list_records({"classification": "hydrology"})
        await tools.list_records({"classification": "Hydrology"}, limit=1)
        await tools.list_records({"classification": "Alchemy"})

    _, seen, _ = ask(research, other, script, key="list-other")
    (_, listed), (_, short), (_, unknown) = seen
    assert listed.status == "ok"
    assert [(r.record_id, r.title, r.year) for r in listed.records] == [
        (second.pk, "Flood gauges", 2022), (first.pk, "River sediment", 2024)]
    assert all(r.handle.startswith("R") for r in listed.records)
    assert listed.count.total == 2 and listed.count.population == frozenset({first.pk, second.pk})
    assert (listed.coverage.returned, listed.coverage.total, listed.coverage.truncated) == (2, 2, False)
    assert (len(short.records), short.coverage.total, short.coverage.truncated) == (1, 2, True)
    assert (unknown.status, unknown.reason) == ("unavailable", "unknown_filter_value")

    _, seen, _ = ask(research, owner, script, key="list-owner")
    (_, listed), *_ = seen
    assert draft.pk in {r.record_id for r in listed.records} and listed.count.total == 3


# --- Forgiving names (IR-995) --------------------------------------------------------

def test_a_category_slug_is_found_by_its_spoken_name(research):
    reader = make_user("count-slug@cit.edu")
    hardware = area("hardware-architecture")
    bare("Adiabatic logic gates", classification=hardware)
    bare("Flash KV caches", classification=hardware)

    async def script(tools):
        await tools.count({"classification": "Hardware Architecture"})
        await tools.list_records({"classification": "hardware architecture"})

    _, seen, _ = ask(research, reader, script, key="count-slug")
    (_, counted), (_, listed) = seen
    assert (counted.count.total, counted.count.filters) == (2, (("classification", "hardware-architecture"),))
    assert listed.count.total == 2


def test_a_hyphenated_title_resolves_and_a_described_one_comes_back_as_a_choice(research):
    reader = make_user("resolve-close@cit.edu")
    ttm = paper("TTM-Bench A Framework for Text-to-Music Benchmarking", {1: [("Intro", "music systems")]})
    lrd = paper("Exploring JWST Little Red Dots with cosmological simulations", {1: [("Intro", "dust")]})

    async def script(tools):
        await tools.resolve(["TTM Bench", "the JWST Little Red Dots simulation paper"])

    _, seen, _ = ask(research, reader, script, key="resolve-close")
    (_, found), = seen
    by_phrase, by_description = found.matches
    assert (by_phrase.match, [r.record_id for r in by_phrase.records]) == ("title_phrase", [ttm.pk])
    assert (by_description.match, by_description.basis) == ("close", "close_title")
    assert [r.record_id for r in by_description.records] == [lrd.pk]
