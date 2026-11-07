"""Reading whole Manuscripts with honest coverage, on real PostgreSQL (IR-733, ADR-049 §9, §17).

Driven through the run routes under a restricted `iris_ai_runtime` login and
Django-issued grants: first with a scripted executor calling the tool, then
with the real AGENT executor and a recording provider. A deterministic
provider proves the contract, never a vendor's behaviour or answer quality.
"""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

import pytest
from django.db import transaction

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.context import Capacity  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.research.tools import PASSAGE_FRAME_BYTES, READING_FRAME_BYTES, shown_bytes  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.ai.models.chunk import ChunkSet, DocumentChunk  # noqa: E402
from apps.records.models import Record, RecordOwner  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from .corpus import make_user  # noqa: E402
from . import test_ai_runtime_agent_loop_db as loop_db  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .test_ai_runtime_context_contract import MILLION, RESERVES  # noqa: E402
from .test_ai_runtime_research_db import ask  # noqa: E402
from .test_ai_runtime_runs_db import as_reader, submit  # noqa: E402

api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

MIDDLE_A = "Midway through, the gauges showed soil moisture rising by 42 percent in the upland plots."
LATE_A = "In closing, 19 villages had adopted the flood alert within one season."
MIDDLE_B = "Halfway in, the pond survey found tilapia growth slowed by 8 percent in brackish water."
LATE_B = "Finally, 6 farms switched to recirculating tanks after the survey."


@pytest.fixture
def research(api, runtime):
    client, holder = api
    holder["dsn"] = runtime
    return api


def filler(title, n):
    return f"{title}: part {n} reviews earlier work on the catchment, its gauges and their siting."


def manuscript(title, passages, *, page_sizes=None, revision="1", status=PipelineStatus.PUBLISHED):
    """A Record whose active Manuscript holds `passages`: (page, text[, element kinds]) in order."""
    record = Record.objects.create(title=title, abstract="", pipeline_status=status)
    write(record, passages, page_sizes=page_sizes, revision=revision)
    return record


def write(record, passages, *, page_sizes=None, revision="1"):
    """A new active chunk set; the previous one is retired, like ChunkRepository.save."""
    pages = {p for p, *_ in passages}
    with transaction.atomic():
        ChunkSet.objects.filter(record=record, is_active=True).update(is_active=False)
        chunk_set = ChunkSet.objects.create(
            record=record, extraction_hash=f"e-{record.pk}-{revision}", strategy_id="s", options={},
            content_hash=f"c-{record.pk}-{revision}", is_active=True,
            page_sizes=page_sizes if page_sizes is not None else {str(p): [612, 792] for p in pages},
        )
        for n, (page, text, *kinds) in enumerate(passages):
            DocumentChunk.objects.create(
                chunk_set=chunk_set, record=record, sequence=n, max_sequence=len(passages) - 1,
                text=text, content=text, context_path=[record.title, "Results"],
                token_count=len(text.split()), text_hash=f"t{record.pk}-{revision}-{n}",
                source_page=page, element_kinds=list(kinds[0]) if kinds else ["paragraph"],
            )
    return chunk_set


def long_paper(title, middle, late, n=30):
    body = [(1 + i // 3, filler(title, i + 1)) for i in range(n)]
    body[n // 2 - 1] = (body[n // 2 - 1][0], middle)
    body[-1] = (body[-1][0], late)
    return manuscript(title, body)


# --- The research tool -------------------------------------------------------------

def test_a_whole_manuscript_is_read_in_document_order_including_its_middle_and_end(research):
    reader = make_user("read-whole@cit.edu")
    record = long_paper("Upland catchment study", MIDDLE_A, LATE_A)
    source = ChunkSet.objects.get(record=record, is_active=True)

    async def script(tools):
        found = await tools.resolve(["Upland catchment study"])
        await tools.read_manuscript(found.records[0].handle, max_bytes=1_000_000)

    response, seen, _ = ask(research, reader, script, key="read-whole")
    assert response.json()["state"] == "completed"
    _, (_, read) = seen
    assert read.status == "ok" and read.reason is None
    assert [p.text for p in read.passages][14] == MIDDLE_A and read.passages[-1].text == LATE_A
    assert [p.page for p in read.passages] == [1 + i // 3 for i in range(30)]
    assert {p.source.revision for p in read.passages} == {f"{source.pk}:{source.extraction_hash}"}
    reading = read.reading
    assert (reading.passages, reading.covered.first, reading.covered.last) == (30, 1, 30)
    assert (reading.covered.first_page, reading.covered.last_page) == (1, 10)
    assert reading.missing == () and reading.continue_after is None
    assert reading.pages == 10 and reading.pages_no_passage_starts_on == ()
    assert reading.title == "Upland catchment study"

    # The journal keeps numbers and the source revision, never text.
    [event] = [e["data"] for e in response.json()["events"]
               if e["name"] == "tool" and e["data"]["tool"] == "read_manuscript"]
    assert event["reading"]["covered"] == [1, 30] and event["reading"]["missing"] == []
    assert event["sources"] == [f"{source.pk}:{source.extraction_hash}"]
    assert MIDDLE_A not in json.dumps(event)


def test_a_small_window_reads_bounded_stretches_from_its_cursor_to_the_end(research):
    reader = make_user("read-window@cit.edu")
    long_paper("Upland catchment study", MIDDLE_A, LATE_A)
    window = READING_FRAME_BYTES + 3 * (shown_bytes(filler("Upland catchment study", 10)) + PASSAGE_FRAME_BYTES)

    async def script(tools):
        found = await tools.resolve(["Upland catchment study"])
        paper, after = found.records[0].handle, None
        for _ in range(20):
            read = await tools.read_manuscript(paper, after, max_bytes=window)
            after = read.reading.continue_after
            if after is None:
                break

    _, seen, _ = ask(research, reader, script, key="read-window")
    reads = [r for name, r in seen if name == "read_manuscript"]
    assert len(reads) > 3
    spans = [(r.reading.covered.first, r.reading.covered.last) for r in reads]
    # Contiguous, never overlapping, never skipping, and each within the window.
    assert spans[0][0] == 1 and spans[-1][1] == 30
    assert all(b[0] == a[1] + 1 for a, b in zip(spans, spans[1:]))
    assert all(len(r.passages) <= 3 for r in reads)
    assert [r.status for r in reads] == ["partial"] * (len(reads) - 1) + ["ok"]
    first = reads[0].reading
    assert [(m.first, m.last) for m in first.missing] == [(spans[0][1] + 1, 30)]
    assert first.continue_after == reads[0].passages[-1].handle


def test_overlapping_chunks_are_shown_once_and_keep_their_canonical_text(research):
    reader = make_user("read-overlap@cit.edu")
    tail = "and the gauges were recalibrated every fortnight during the season."
    manuscript("Gauge calibration", [
        (1, "The method notes " + tail),
        (2, tail + " Calibration drift stayed under 3 percent."),
        (2, "Short."),
    ])

    async def script(tools):
        found = await tools.resolve(["Gauge calibration"])
        await tools.read_manuscript(found.records[0].handle, max_bytes=1_000_000)

    _, seen, _ = ask(research, reader, script, key="read-overlap")
    _, (_, read) = seen
    first, second, third = read.passages
    assert (first.overlap, second.overlap, third.overlap) == (0, len(tail), 0)
    assert second.text == tail + " Calibration drift stayed under 3 percent."
    assert second.text[second.overlap:] == " Calibration drift stayed under 3 percent."
    assert (second.page, second.handle != first.handle) == (2, True)
    assert read.reading.overlap_chars == len(tail)


def test_extraction_gaps_and_uninterpreted_formulas_and_captions_are_reported(research):
    reader = make_user("read-gaps@cit.edu")
    manuscript("Rainfall regression", [
        (1, "Introduction to the rainfall regression.", ["paragraph"]),
        (2, "y = a + b x", ["formula"]),
        (2, "Figure 1: rainfall against runoff.", ["caption"]),
        (4, "Conclusion of the rainfall regression.", ["paragraph"]),
    ], page_sizes={str(p): [612, 792] for p in range(1, 6)})

    async def script(tools):
        found = await tools.resolve(["Rainfall regression"])
        await tools.read_manuscript(found.records[0].handle, max_bytes=1_000_000)

    _, seen, _ = ask(research, reader, script, key="read-gaps")
    _, (_, read) = seen
    reading = read.reading
    assert reading.pages == 5 and reading.pages_no_passage_starts_on == (3, 5)
    assert (reading.formulas, reading.captions) == (1, 1)


def test_a_continuation_cannot_move_a_read_to_another_paper_revision_or_run(research):
    reader = make_user("read-foreign@cit.edu")
    upland = long_paper("Upland catchment study", MIDDLE_A, LATE_A, n=6)
    long_paper("Pond survey", MIDDLE_B, LATE_B, n=6)
    small = READING_FRAME_BYTES + shown_bytes(filler("Upland catchment study", 1)) + PASSAGE_FRAME_BYTES
    kept = {}

    async def first(tools):
        found = await tools.resolve(["Upland catchment study", "Pond survey"])
        upland_h, pond_h = (m.records[0].handle for m in found.matches)
        pond = await tools.read_manuscript(pond_h, max_bytes=small)
        # A cursor from the pond survey cannot continue the upland study.
        await tools.read_manuscript(upland_h, pond.passages[0].handle, max_bytes=small)
        read = await tools.read_manuscript(upland_h, max_bytes=small)
        kept["cursor"] = read.reading.continue_after
        await asyncio.to_thread(write, upland, [(1, "A replaced revision.")], revision="2")
        # The paper handle and the cursor were bound to the old revision.
        await tools.read_manuscript(upland_h, read.reading.continue_after, max_bytes=small)
        again = await tools.resolve(["Upland catchment study"])
        await tools.read_manuscript(again.records[0].handle, read.reading.continue_after, max_bytes=small)

    _, seen, _ = ask(research, reader, first, key="read-foreign-1")
    reads = [r for name, r in seen if name == "read_manuscript"]
    assert (reads[1].status, reads[1].reason) == ("unavailable", "foreign_continuation")
    assert (reads[3].status, reads[3].reason) == ("unavailable", "source_replaced")
    assert (reads[4].status, reads[4].reason) == ("unavailable", "source_replaced")

    async def later(tools):
        found = await tools.resolve(["Upland catchment study"])
        await tools.read_manuscript(found.records[0].handle, kept["cursor"], max_bytes=small)

    # Another run's cursor is unknown here: handles are run-bound.
    _, seen, _ = ask(research, reader, later, key="read-foreign-2")
    _, (_, read) = seen
    assert (read.status, read.reason) == ("unavailable", "unknown_handle")


def test_access_revoked_mid_run_stops_the_read_and_its_continuation(research):
    reader = make_user("read-revoked@cit.edu")
    record = long_paper("Upland catchment study", MIDDLE_A, LATE_A, n=6)
    small = READING_FRAME_BYTES + shown_bytes(filler("Upland catchment study", 1)) + PASSAGE_FRAME_BYTES

    async def script(tools):
        found = await tools.resolve(["Upland catchment study"])
        paper = found.records[0].handle
        first = await tools.read_manuscript(paper, max_bytes=small)
        await asyncio.to_thread(
            Record.objects.filter(pk=record.pk).update, pipeline_status=PipelineStatus.DRAFT)
        await tools.read_manuscript(paper, first.reading.continue_after, max_bytes=small)
        await tools.read_manuscript(paper, max_bytes=1_000_000)

    _, seen, _ = ask(research, reader, script, key="read-revoked")
    first, after, again = (r for name, r in seen if name == "read_manuscript")
    assert first.status == "partial" and len(first.passages) == 1
    # Unreadable now is indistinguishable from never issued; nothing more is returned.
    for refused in (after, again):
        assert (refused.status, refused.reason, refused.passages) == ("unavailable", "unknown_handle", ())


def test_a_paper_the_reader_cannot_read_is_never_read(research):
    owner, other = make_user("read-owner@cit.edu"), make_user("read-other@cit.edu")
    draft = manuscript("Private levee study", [(1, "levee breaches worsened the flood")],
                       status=PipelineStatus.DRAFT)
    RecordOwner.objects.create(record=draft, user=owner, is_primary=True)
    kept = {}

    async def owned(tools):
        found = await tools.resolve([], record_ids=[draft.pk])
        kept["paper"] = found.records[0].handle
        await tools.read_manuscript(kept["paper"], max_bytes=1_000_000)

    _, seen, _ = ask(research, owner, owned, key="read-owned")
    assert seen[1][1].status == "ok"

    async def foreign(tools):
        await tools.read_manuscript(kept["paper"], max_bytes=1_000_000)

    _, seen, _ = ask(research, other, foreign, key="read-not-owned")
    [(_, read)] = seen
    assert (read.status, read.reason, read.passages) == ("unavailable", "unknown_handle", ())


# --- The ticket's demonstration: the AGENT reads, cites and reopens --------------------

PIN_3 = dataclasses.replace(loop_db.PIN, prompt_version="agent-research-3", tool_version="research-3")
# Fixture capacity only; it describes no vendor.
WINDOW = Capacity(context_tokens=26_500, max_output_tokens=400, max_reasoning_tokens=None,
                  max_request_bytes=256_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)


def agent_service(dsn, provider):
    cfg = runs_config.RunsConfig(database_url=dsn, executor="deterministic", limits=loop_db.LIMITS,
                                 dispatch=runs_db.DISPATCH)
    executor = AgentExecutor(provider, PIN_3, RESERVES, profiles=loop_db.PROFILES)
    built = RunService(RunStore(dsn), cfg, executor, runs_db.Drain())
    built.notifier.service = built
    return built


def recording(capacity, *responses):
    return RecordingAgentProvider(responses=list(responses), capacities={"scripted-model": capacity})


def resolved(payload):
    return [m["papers"][0]["paper"] for m in loop_db.last_result(payload)["matches"]]


def read_both(payload):
    first, second = resolved(payload)
    return loop_db.tools(loop_db.call("a", "read_manuscript", paper=first),
                         loop_db.call("b", "read_manuscript", paper=second))


def passage_with(payload, text):
    return next(p["passage"] for r in loop_db.results(payload) for p in r.get("passages", ())
                if p["text"].endswith(text))


def cite_planted(payload):
    cited = {t: passage_with(payload, t) for t in (MIDDLE_A, LATE_A, MIDDLE_B, LATE_B)}
    return loop_db.reply(
        f"The upland study reports soil moisture rising by 42 percent midway [{cited[MIDDLE_A]}] and 19 "
        f"villages adopting the alert at its close [{cited[LATE_A]}]. The pond survey reports growth "
        f"slowed by 8 percent [{cited[MIDDLE_B]}] and 6 farms switching to tanks [{cited[LATE_B]}]. "
        "Figures and formulas were not interpreted.")


def read_on(payload):
    """Continue the last read while it says there is more, then answer from what was read."""
    if payload["messages"][-1]["role"] == "tool":
        last = loop_db.last_result(payload)
        if "matches" in last:
            return loop_db.tools(loop_db.call("r0", "read_manuscript", paper=resolved(payload)[0]))
        after = last.get("reading", {}).get("continue_after")
        if after is not None and last.get("passages"):
            n = len(loop_db.results(payload))
            return loop_db.tools(loop_db.call(f"r{n}", "read_manuscript", paper=resolved_paper(payload),
                                              continue_after=after))
    return loop_db.reply(f"In closing, 19 villages had adopted the flood alert [{passage_with(payload, LATE_A)}]. "
                         "Page 11 had no extracted text, and figures and formulas were not interpreted.")


def resolved_paper(payload):
    return next(r["matches"][0]["papers"][0]["paper"] for r in loop_db.results(payload) if "matches" in r)


def reopened(client, grant, conversation):
    return client.get(f"/api/v1/ai/conversations/{conversation}", headers=as_reader(grant)).json()["turns"]


def test_the_agent_answers_from_the_middle_and_end_of_two_long_papers_then_reads_on_through_a_small_window(
        api, runtime):
    client, holder = api
    upland = long_paper("Upland catchment study", MIDDLE_A, LATE_A)
    pond = long_paper("Pond survey", MIDDLE_B, LATE_B)
    grant = issue.reader_session_grant(make_user("read-demo@cit.edu")).token

    # Both papers fit: each is read whole, and the middle and end of each are cited.
    whole = recording(MILLION, loop_db.tools(loop_db.call(
        "n", "resolve_papers", references=["Upland catchment study", "Pond survey"])), read_both, cite_planted)
    holder["service"] = agent_service(runtime, whole)
    asked = submit(client, grant, "read-demo-1", "What did the two long papers find midway and at the end?").json()
    assert asked["state"] == "completed", asked
    [turn] = reopened(client, grant, asked["conversation_id"])
    assert [(c["record_id"], c["page"], c["quote"]) for c in turn["citations"]] == [
        (upland.pk, 5, MIDDLE_A), (upland.pk, 10, LATE_A), (pond.pk, 5, MIDDLE_B), (pond.pk, 10, LATE_B)]
    revisions = {r.pk: f"{c.pk}:{c.extraction_hash}" for r in (upland, pond)
                 for c in [ChunkSet.objects.get(record=r, is_active=True)]}
    assert all(c["revision"] == revisions[c["record_id"]] for c in turn["citations"])
    coverage = [f for f in turn["facts"] if f["kind"] == "reading_coverage"]
    assert sorted(f["title"] for f in coverage) == ["Pond survey", "Upland catchment study"]
    assert all(f["complete"] and f["read"] == f["passages"] == 30 for f in coverage)
    assert all(f["visual_interpretation"] is False and f["exhaustive"] is False for f in coverage)

    # A small verified window, overlap and an extraction gap: read in stretches, said honestly.
    tail = "and the gauges were recalibrated every fortnight during the season."
    body = [(1 + i // 3, filler("Gap study", i + 1) + " " + "x" * 300) for i in range(30)]
    body[3] = (2, filler("Gap study", 4) + " " + tail)
    body[4] = (2, tail + " Calibration drift stayed under 3 percent.")
    body[-1] = (10, LATE_A)
    gap = manuscript("Gap study", body, page_sizes={str(p): [612, 792] for p in range(1, 12)})
    windowed = recording(WINDOW, loop_db.tools(loop_db.call("n", "resolve_papers", references=["Gap study"])),
                         *[read_on] * 8)
    holder["service"] = agent_service(runtime, windowed)
    asked = submit(client, grant, "read-demo-2", "What did the gap study conclude?").json()
    assert asked["state"] == "completed", asked

    shown = [r for r in loop_db.results(windowed.requests[-1]) if "reading" in r]
    assert len(shown) > 1
    assert all("withheld" not in r for r in loop_db.results(windowed.requests[-1]))
    assert shown[0]["status"] == "partial" and shown[0]["reading"]["missing"]
    assert shown[-1]["reading"]["read_so_far"]["not_read"] == []
    assert shown[0]["reading"]["pages_no_passage_starts_on"] == [11]
    overlapped = next(p for r in shown for p in r["passages"] if "repeats_previous_chars" in p)
    assert overlapped["text"] == " Calibration drift stayed under 3 percent."

    [turn] = reopened(client, grant, asked["conversation_id"])
    [citation] = turn["citations"]
    assert (citation["record_id"], citation["page"], citation["quote"]) == (gap.pk, 10, LATE_A)
    [coverage] = [f for f in turn["facts"] if f["kind"] == "reading_coverage"]
    assert coverage["title"] == "Gap study" and coverage["complete"] is True
    assert coverage["pages"] == 11 and coverage["pages_no_passage_starts_on"] == 1
