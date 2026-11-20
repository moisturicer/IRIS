"""Local research tools in the AI runtime, on real PostgreSQL (IR-719, ADR-049 §5, §9).

Driven through the run routes with a scripted executor calling the tools,
under a restricted `iris_ai_runtime` login and Django-issued grants.
"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from django.db import connection, transaction

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.research import tools as research_tools  # noqa: E402
from ai.runs.executor import Citation, Result  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.ai.models.chunk import ChunkSet, DocumentChunk  # noqa: E402
from apps.records.models import Record, RecordOwner  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from .corpus import make_user, released_for_ai  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .test_ai_runtime_runs_db import as_reader, service, submit  # noqa: E402

# The run suite's fixtures, shared by name.
api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

FLOOD = "we trained a neural network on rainfall gauges to predict flooding in the catchment"
POND = "sampling procedure for tilapia ponds stocked in brackish water"


def paper(title, pages, *, status=PipelineStatus.PUBLISHED, owner=None, revision="1"):
    record = released_for_ai(
        Record.objects.create(added_by=owner, title=title, abstract="", pipeline_status=status))
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    write_source(record, pages, revision)
    return record


def write_source(record, pages, revision):
    """A new active chunk set; the previous one is retired, like ChunkRepository.save."""
    with transaction.atomic():
        ChunkSet.objects.filter(record=record, is_active=True).update(is_active=False)
        chunk_set = ChunkSet.objects.create(
            record=record, extraction_hash=f"e-{record.pk}-{revision}", strategy_id="s",
            options={}, content_hash=f"c-{record.pk}-{revision}", is_active=True,
        )
        texts = [(page, section, text) for page, items in pages.items() for section, text in items]
        for n, (page, section, text) in enumerate(texts):
            DocumentChunk.objects.create(
                chunk_set=chunk_set, record=record, sequence=n, max_sequence=len(texts) - 1,
                text=text, content=text, context_path=[record.title, section],
                token_count=len(text.split()), text_hash=f"t{record.pk}-{revision}-{n}",
                source_page=page, element_kinds=["paragraph"],
            )
    return chunk_set


class ScriptedResearch:
    """Runs `script(tools)` as the run's executor and keeps every tool result."""

    name = "scripted-research"
    version = "1"
    reserved_units = 0

    def __init__(self, script):
        self.script = script
        self.seen = []

    async def answer(self, question, tools):
        result = await self.script(Recording(tools, self.seen))
        return result or Result(answer="Scripted.")


class Recording:
    def __init__(self, tools, seen):
        self._tools, self._seen = tools, seen

    def __getattr__(self, name):
        call = getattr(self._tools, name)

        async def recorded(*args, **kwargs):
            result = await call(*args, **kwargs)
            self._seen.append((name, result))
            return result

        return recorded


def ask(api, reader, script, *, key, record_id=None, **body):
    client, holder = api
    executor = ScriptedResearch(script)
    holder["service"] = service(holder["dsn"], executor)
    grant = issue.reader_session_grant(reader, record_id).token
    response = submit(client, grant, key, **body)
    return response, executor.seen, grant


@pytest.fixture
def research(api, runtime):
    client, holder = api
    holder["dsn"] = runtime
    return api


# --- Finding and reading ------------------------------------------------------

def test_a_reader_finds_a_paper_and_opens_its_passage_at_the_exact_revision(research):
    reader = make_user("tools-find@cit.edu")
    flood = paper("Flood forecasting", {3: [("Introduction", "rivers rise in the wet season")],
                                        4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    source = ChunkSet.objects.get(record=flood, is_active=True)

    async def script(tools):
        found = await tools.search("neural network flooding catchment")
        passage = found.passages[0]
        opened = await tools.open_passage(passage.handle)
        await tools.read_page(found.records[0].handle, 4)
        await tools.outline(found.records[0].handle)
        return Result(answer="Floods.", citations=(
            Citation(record_id=opened.passages[0].record_id, quote=opened.passages[0].text,
                     page=opened.passages[0].page, revision=opened.passages[0].source.revision),))

    response, seen, grant = ask(research, reader, script, key="tools-find-1")
    assert response.status_code == 201 and response.json()["state"] == "completed"
    (_, found), (_, opened), (_, page), (_, outline) = seen

    assert found.status == "ok"
    assert [r.record_id for r in found.records] == [flood.pk]
    assert found.records[0].title == "Flood forecasting"
    hit = found.passages[0]
    assert (hit.record_id, hit.page, hit.text, hit.section) == (flood.pk, 4, FLOOD, "Methods")
    assert hit.source.chunk_set_id == source.pk
    assert hit.source.extraction_hash == source.extraction_hash
    assert found.dependencies == {hit.source}
    assert found.coverage.returned == 1 and found.coverage.total == 1
    assert found.coverage.inspected_records == 2

    assert opened.status == "ok"
    assert (opened.passages[0].text, opened.passages[0].page) == (FLOOD, 4)
    assert opened.dependencies == {hit.source}
    assert page.status == "ok" and [p.text for p in page.passages] == [FLOOD]
    assert outline.status == "ok"
    assert [(s.heading, s.first_page, s.last_page) for s in outline.sections] == [
        ("Introduction", 3, 3), ("Methods", 4, 4)]

    client, _ = research
    turn = client.get(f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
                      headers=as_reader(grant)).json()["turns"][0]
    assert turn["citations"] == [{"record_id": flood.pk, "page": 4, "quote": FLOOD,
                                  "revision": hit.source.revision, "regions": [], "title": flood.title}]


def test_a_trial_chunk_set_is_never_searched_or_read(research):
    """IR-1051: an evaluation trial set beside the active one never reaches a reader."""
    reader = make_user("tools-trial@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    probe = "zebracorn migration across the floodplain during the wet season"
    trial = ChunkSet.objects.create(
        record=flood, extraction_hash="t", strategy_id="s", options={}, content_hash="trial",
        trial_variant="probe", trial_spec="::",
    )
    DocumentChunk.objects.create(
        chunk_set=trial, record=flood, sequence=0, max_sequence=0, text=probe, content=probe,
        context_path=[flood.title, "Methods"], token_count=len(probe.split()),
        text_hash="trial", source_page=4, element_kinds=["paragraph"],
    )

    async def script(tools):
        await tools.search("zebracorn migration floodplain")
        found = await tools.search("neural network flooding catchment")
        await tools.read_page(found.records[0].handle, 4)

    response, seen, _ = ask(research, reader, script, key="tools-trial-1")
    assert response.status_code == 201
    (_, probed), (_, found), (_, page) = seen
    assert probe not in [p.text for p in probed.passages]
    assert [p.text for p in found.passages] == [FLOOD]
    assert [p.text for p in page.passages] == [FLOOD]


def test_tool_calls_are_journalled_as_names_and_codes(research):
    reader = make_user("tools-journal@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def script(tools):
        await tools.search("flooding")
        await tools.search("nothing matches this")

    response, seen, _ = ask(research, reader, script, key="tools-journal")
    tools_ = [e["data"] for e in response.json()["events"] if e["name"] == "tool"]
    revision = seen[0][1].passages[0].source.revision
    assert tools_ == [
        {"tool": "search", "status": "ok", "returned": 1, "total": 1, "truncated": False,
         "inspected_records": 1, "sources": [revision]},
        {"tool": "search", "status": "no_match", "returned": 0, "total": 0, "truncated": False,
         "inspected_records": 1, "sources": []},
    ]


def test_a_bounded_page_read_says_it_is_partial(research, monkeypatch):
    monkeypatch.setattr(research_tools, "PAGE_PASSAGES", 2)
    reader = make_user("tools-partial@cit.edu")
    paper("Long page", {5: [("Results", f"flooding result {n}") for n in range(3)]})

    async def script(tools):
        found = await tools.search("flooding")
        await tools.read_page(found.records[0].handle, 5)
        await tools.read_page(found.records[0].handle, 99)

    _, seen, _ = ask(research, reader, script, key="tools-partial")
    (_, page), (_, empty) = seen[1], seen[2]
    assert page.status == "partial"
    assert [p.text for p in page.passages] == ["flooding result 0", "flooding result 1"]
    assert (page.coverage.returned, page.coverage.total, page.coverage.truncated) == (2, 3, True)
    assert empty.status == "no_match" and empty.passages == ()


# --- What a reader may not see ------------------------------------------------

def test_a_draft_discloses_nothing_even_to_its_owner(research):
    """Only a published paper reaches the AI (IR-1252), so a draft is hidden from
    the person who wrote it too, not only from another reader. Before IR-1252 its
    owner found it; that a handle can't cross runs is the next test's."""
    owner = make_user("tools-owner@cit.edu")
    reader = make_user("tools-stranger@cit.edu")
    draft = paper("Secret flooding draft", {4: [("Methods", FLOOD)]},
                  status=PipelineStatus.DRAFT, owner=owner)

    async def script(tools):
        await tools.search("flooding")
        await tools.open_passage("P" + "0" * 20)

    for person, key in ((owner, "tools-owner"), (reader, "tools-stranger")):
        _, seen, _ = ask(research, person, script, key=key)
        (_, search), (_, forged) = seen
        assert search.status == "no_match" and search.records == () and search.dependencies == set()
        assert search.coverage.inspected_records == 0
        assert (forged.status, forged.reason) == ("unavailable", "unknown_handle")
        assert forged.records == () and forged.passages == () and forged.dependencies == set()
        assert draft.title not in repr(seen)


# Every kind of paper that may not reach the AI (ADR-052 as amended, IR-1252),
# each given readable text, read by its own creator: none is found, counted,
# listed or resolved, while a published, released paper beside it still is.
REFUSED = {
    "in review": {"pipeline_status": PipelineStatus.IN_REVIEW},
    "kept unlisted": {"pipeline_status": PipelineStatus.COMPLETED},
    "embargoed": {"is_embargoed": True, "embargo_released_at": None},
    "no consent": {"ai_consent": None},
    "said no": {"ai_consent": False},
    "IP not released": {"is_ip": True, "ip_released_at": None},
}


@pytest.mark.parametrize("kind", list(REFUSED))
def test_a_paper_that_may_not_reach_the_ai_is_never_found_even_by_its_owner(research, kind):
    owner = make_user("tools-refused@cit.edu")
    held = paper("Held flooding paper", {4: [("Methods", FLOOD)]}, owner=owner)
    Record.objects.filter(pk=held.pk).update(**REFUSED[kind])
    shown = paper("Shown flooding paper", {4: [("Methods", FLOOD)]})

    async def script(tools):
        await tools.search("flooding")
        await tools.count({})
        await tools.list_records({})
        await tools.resolve(["Held flooding paper"], record_ids=[held.pk])

    _, seen, _ = ask(research, owner, script, key=f"tools-refused-{kind}")
    (_, found), (_, counted), (_, listed), (_, resolved) = seen
    assert [r.record_id for r in found.records] == [shown.pk]
    assert counted.count.total == 1 and counted.count.population == frozenset({shown.pk})
    assert [r.record_id for r in listed.records] == [shown.pk]
    assert held.pk not in {r.record_id for r in resolved.records}
    assert "Held flooding paper" not in repr(seen)


def test_a_paper_embargoed_again_stops_being_read_but_stays_in_discover(research):
    """Its chunks stay stored; the AI stops reading them (IR-1252)."""
    from rest_framework.test import APIClient

    reader = make_user("tools-again@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def script(tools):
        await tools.search("flooding")

    _, seen, _ = ask(research, reader, script, key="tools-again-1")
    assert [r.record_id for r in seen[0][1].records] == [flood.pk]

    Record.objects.filter(pk=flood.pk).update(is_embargoed=True, embargo_released_at=None)
    _, seen, _ = ask(research, reader, script, key="tools-again-2")
    assert seen[0][1].records == () and seen[0][1].status == "no_match"

    assert DocumentChunk.objects.filter(record=flood, chunk_set__is_active=True).exists()
    client = APIClient()
    client.force_authenticate(reader)
    listed = client.get("/api/v1/records/").data
    assert flood.pk in {row["id"] for row in listed.get("results", listed)}


@pytest.mark.parametrize("change", [
    {"is_embargoed": True, "embargo_released_at": None},
    {"pipeline_status": PipelineStatus.PENDING_DELETE},
])
def test_a_paper_that_stops_qualifying_mid_run_is_refused_at_the_next_read(research, change):
    """Like a reader who loses access (IR-880): the next read refuses it."""
    reader = make_user("tools-midrun@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    def withdraw():
        try:
            Record.objects.filter(pk=flood.pk).update(**change)
        finally:
            connection.close()

    async def script(tools):
        found = await tools.search("flooding")
        await asyncio.to_thread(withdraw)
        await tools.open_passage(found.passages[0].handle)
        await tools.read_page(found.records[0].handle, 4)

    _, seen, _ = ask(research, reader, script, key="tools-midrun")
    (_, found), (_, opened), (_, page) = seen
    assert [r.record_id for r in found.records] == [flood.pk]
    for result in (opened, page):
        assert result.status == "unavailable"
        assert result.records == () and result.passages == ()
        assert FLOOD not in repr(result)


def test_another_readers_handles_disclose_nothing(research):
    """A handle is bound to the run that made it, so another reader can't use it.

    Before IR-1252 this was shown with the owner's draft; a draft now gives no handle."""
    first = make_user("tools-first@cit.edu")
    second = make_user("tools-second@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def finds(tools):
        await tools.search("flooding")

    _, seen, _ = ask(research, first, finds, key="tools-first")
    passage, record = seen[0][1].passages[0].handle, seen[0][1].records[0].handle

    async def borrows(tools):
        await tools.open_passage(passage)
        await tools.read_page(record, 4)

    _, seen, _ = ask(research, second, borrows, key="tools-second")
    for _, result in seen:
        assert (result.status, result.reason) == ("unavailable", "unknown_handle")
        assert result.records == () and result.passages == () and result.dependencies == set()


def test_a_handle_belongs_to_its_run_and_expires_with_it(research):
    reader = make_user("tools-reuse@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def first(tools):
        await tools.search("flooding")

    response, seen, _ = ask(research, reader, first, key="tools-reuse-1")
    handle = seen[0][1].passages[0].handle

    async def second(tools):
        await tools.open_passage(handle)

    _, again, _ = ask(research, reader, second, key="tools-reuse-2",
                      conversation_id=response.json()["conversation_id"], base_revision=1)
    assert (again[0][1].status, again[0][1].reason) == ("unavailable", "unknown_handle")

    def expire_handles():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE iris_ai.research_handle SET expires_at = now() - interval '1 second'")

    async def expiring(tools):
        found = await tools.search("flooding")
        await asyncio.to_thread(expire_handles)
        await tools.open_passage(found.passages[0].handle)

    _, seen, _ = ask(research, reader, expiring, key="tools-reuse-3")
    assert (seen[1][1].status, seen[1][1].reason) == ("unavailable", "unknown_handle")


def test_paper_chat_stays_on_its_record(research):
    reader = make_user("tools-paper-chat@cit.edu")
    chosen = paper("Pond sampling", {2: [("Methods", POND + " after flooding")]})
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def other_reads(tools):
        await tools.search("flooding")

    outside_response, outside, _ = ask(research, reader, other_reads, key="tools-chat-0")
    outside_run = outside_response.json()
    outside_handle = next(r.handle for r in outside[0][1].records if r.record_id != chosen.pk)

    async def scoped(tools):
        await tools.search("neural network flooding catchment")
        await tools.read_page(outside_handle, 4)

    response, seen, _ = ask(research, reader, scoped, key="tools-chat-1", record_id=chosen.pk)
    (_, search), (_, widened) = seen
    assert [r.record_id for r in search.records] == [chosen.pk]
    assert search.coverage.inspected_records == 1
    assert (widened.status, widened.reason) == ("unavailable", "unknown_handle")

    # A follow-up never moves the Conversation to another paper...
    client, _ = research
    other = next(r.record_id for r in outside[0][1].records if r.record_id != chosen.pk)
    elsewhere = issue.reader_session_grant(reader, other).token
    moved = submit(client, elsewhere, "tools-chat-2",
                   conversation_id=response.json()["conversation_id"], base_revision=1)
    assert moved.status_code == 409 and moved.json() == {"status": "scope_mismatch"}
    # ...but may widen it to every readable paper, in the same Conversation.
    unscoped = issue.reader_session_grant(reader).token
    follow = submit(client, unscoped, "tools-chat-3",
                    conversation_id=response.json()["conversation_id"], base_revision=1)
    assert follow.status_code == 201
    assert follow.json()["conversation_id"] == response.json()["conversation_id"]

    # A Paper Chat grant reaches no other Conversation of the reader's.
    general = outside_run["conversation_id"]
    scoped_grant = as_reader(issue.reader_session_grant(reader, chosen.pk).token)
    assert client.get(f"/api/v1/ai/conversations/{general}", headers=scoped_grant).status_code == 404
    assert client.get(f"/api/v1/ai/runs/{outside_run['id']}", headers=scoped_grant).status_code == 404
    assert client.get(f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
                      headers=scoped_grant).status_code == 200


def test_a_replaced_source_invalidates_its_read_handles(research):
    reader = make_user("tools-stale@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})

    async def script(tools):
        found = await tools.search("flooding")
        await asyncio.to_thread(
            write_source, flood, {4: [("Methods", "a revised flooding passage")]}, "2")
        await tools.open_passage(found.passages[0].handle)
        await tools.read_page(found.records[0].handle, 4)
        await tools.outline(found.records[0].handle)
        fresh = await tools.search("flooding")
        await tools.open_passage(fresh.passages[0].handle)

    _, seen, _ = ask(research, reader, script, key="tools-stale")
    stale = [result for _, result in seen[1:4]]
    for result in stale:
        assert (result.status, result.reason) == ("unavailable", "source_replaced")
        assert result.passages == ()
    fresh, reopened = seen[4][1], seen[5][1]
    assert fresh.passages[0].text == "a revised flooding passage"
    assert fresh.passages[0].source != seen[0][1].passages[0].source
    assert reopened.status == "ok"


def test_stop_admits_no_further_tool_call(research):
    from ai.runs.store import RunStore

    reader = make_user("tools-stop@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant_box = {}

    def running_run():
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM iris_ai.ask_run WHERE state = 'running'")
            return cursor.fetchone()[0]

    async def script(tools):
        await tools.search("flooding")
        run_id = await asyncio.to_thread(running_run)
        await RunStore(research[1]["dsn"]).cancel(grant_box["grant"], run_id)
        await tools.search("flooding")

    client, holder = research
    executor = ScriptedResearch(script)
    holder["service"] = service(holder["dsn"], executor)
    grant_box["grant"] = issue.reader_session_grant(reader).token
    response = submit(client, grant_box["grant"], "tools-stop")
    assert response.json()["state"] == "cancelled"
    (_, before), (_, after) = executor.seen
    assert before.status == "ok"
    assert (after.status, after.reason) == ("unavailable", "run_ended")


def test_tools_refuse_a_grant_for_another_reader(research):
    from ai.research.tools import ResearchTools

    reader = make_user("tools-bound@cit.edu")
    intruder = make_user("tools-bound-intruder@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    theirs = issue.reader_session_grant(intruder).token
    seen = {}

    async def script(tools):
        own = await tools.search("flooding")
        run_id, fence = tools._tools.run_id, tools._tools.fence
        borrowed = ResearchTools(research[1]["dsn"], theirs, run_id, fence)
        seen["borrowed"] = await borrowed.open_passage(own.passages[0].handle)

    ask(research, reader, script, key="tools-bound")
    assert (seen["borrowed"].status, seen["borrowed"].reason) == ("unavailable", "run_ended")


# --- No Django round trip, no provider ----------------------------------------

def test_tools_reach_only_postgresql_and_providers_stay_unavailable(research, monkeypatch):
    reader = make_user("tools-traffic@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    opened = []
    real = asyncio.BaseEventLoop.create_connection

    async def watched(self, protocol_factory, host=None, port=None, **kwargs):
        opened.append((host, int(port)))
        return await real(self, protocol_factory, host, port, **kwargs)

    def no_http(*args, **kwargs):
        raise AssertionError("a research tool made an HTTP request")

    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", watched)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_http)
    monkeypatch.setattr(httpx.Client, "send", no_http)

    async def script(tools):
        found = await tools.search("flooding")
        await tools.open_passage(found.passages[0].handle)
        await tools.read_page(found.records[0].handle, 4)
        await tools.outline(found.records[0].handle)
        await tools.semantic_search("flooding")

    response, seen, _ = ask(research, reader, script, key="tools-traffic")
    assert response.status_code == 201
    params = connection.settings_dict
    postgres = (params["HOST"] or "localhost", int(params["PORT"] or 5432))
    assert opened and set(opened) == {postgres}
    semantic = seen[-1][1]
    assert (semantic.status, semantic.reason) == ("unavailable", "provider_gated")
    assert semantic.provider_operations == ("embed_query", "rerank")
    assert all(result.provider_operations == () for _, result in seen[:-1])
