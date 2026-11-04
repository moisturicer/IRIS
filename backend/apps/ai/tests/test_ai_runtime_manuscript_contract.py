"""Whole-Manuscript reading in the AGENT Conversation (IR-733, ADR-049 §9, §17).

The executor with the recording provider and an in-memory stand-in for the
research tools. A deterministic provider proves the contract, never a
vendor's behaviour or answer quality.
"""

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import checkpoint  # noqa: E402
from ai.agent.context import Capacity  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.protocol import ToolCall, ToolResult as Answered  # noqa: E402
from ai.agent.tools import Investigation  # noqa: E402
from ai.research.tools import (  # noqa: E402
    OK, PARTIAL, PAGE_ENTRY_BYTES, PASSAGE_FRAME_BYTES, READING_FRAME_BYTES, Coverage, PassageRef, Reading,
    Source, Span, ToolResult, overlap, shown_bytes,
)
from ai.runs.executor import Unavailable  # noqa: E402
from ai.runs.store import shown_facts  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    ALLOWANCE, ORDINARY, PIN, PROFILES, Corpus, call, context, handle, recording, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402

PIN_2 = dataclasses.replace(PIN, prompt_version="agent-research-2", tool_version="research-2")
PIN_3 = dataclasses.replace(PIN, prompt_version="agent-research-3", tool_version="research-3")
PAPER = handle("R", 7)
LONG = Source(7, 77, "e7")
MIDDLE = "The middle finding: soil moisture rose by 42 percent after the first monsoon week."
LATE = "The closing finding: 19 villages adopted the flood alert within one season."
# Fixture capacity only; it describes no vendor.
WINDOW = Capacity(context_tokens=12_000, max_output_tokens=400, max_reasoning_tokens=None,
                  max_request_bytes=256_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)


def texts(n=30):
    body = [f"Section {i} reviews earlier monsoon work and the siting of rain gauges." for i in range(1, n + 1)]
    body[n // 2 - 1] = MIDDLE
    body[-1] = LATE
    return body


def at(n):
    """The passage handle at 1-based position `n`."""
    return handle("P", 100 + n)


class Manuscript(Corpus):
    """The two-paper corpus plus one long paper, read as the real tool reads it."""

    def __init__(self, body=None, *, pages=None, formulas=0, captions=0, page_count=None):
        super().__init__()
        body = body or texts()
        pages = pages or [1 + i // 3 for i in range(len(body))]
        self.long = [PassageRef(at(i + 1), 7, pages[i], "Results", text, LONG) for i, text in enumerate(body)]
        self.papers[7] = ("Long monsoon study", LONG, self.long[0])
        self.formulas, self.captions = formulas, captions
        self.page_count = page_count if page_count is not None else max(pages)

    async def open_passage(self, passage):
        for p in self.long:
            if p.handle == passage:
                self.calls.append(("open_passage", passage))
                if 7 in self.replaced:
                    return ToolResult.unavailable("source_replaced")
                return ToolResult(OK, passages=(p,), coverage=Coverage(1, 1))
        return await super().open_passage(passage)

    async def read_manuscript(self, paper, after=None, *, max_bytes):
        self.calls.append(("read_manuscript", paper, after, max_bytes))
        if paper != PAPER:
            return ToolResult.unavailable("unknown_handle")
        if 7 in self.replaced:
            return ToolResult.unavailable("source_replaced")
        handles = [p.handle for p in self.long]
        if after is not None and after not in handles:
            return ToolResult.unavailable("foreign_continuation")
        start = handles.index(after) + 1 if after else 0
        repeats = [0, *(overlap(a.text, b.text) for a, b in zip(self.long, self.long[1:]))]
        with_text = {p.page for p in self.long}
        unstarted = tuple(p for p in range(1, self.page_count + 1) if p not in with_text)
        end, used = start, READING_FRAME_BYTES + PAGE_ENTRY_BYTES * len(unstarted)
        while end < len(self.long):
            cost = shown_bytes(self.long[end].text[repeats[end]:]) + PASSAGE_FRAME_BYTES
            if used + cost > max_bytes:
                break
            used, end = used + cost, end + 1
        chosen = [dataclasses.replace(p, overlap=repeats[start + i]) for i, p in enumerate(self.long[start:end])]

        def span(a, b):
            return Span(a + 1, b + 1, self.long[a].page, self.long[b].page)

        remaining = end < len(self.long)
        reading = Reading(
            passages=len(self.long), covered=span(start, end - 1) if chosen else None,
            missing=tuple(span(a, b) for a, b in ((0, start - 1), (end, len(self.long) - 1)) if a <= b),
            pages=self.page_count,
            pages_no_passage_starts_on=unstarted,
            formulas=self.formulas, captions=self.captions, overlap_chars=sum(p.overlap for p in chosen),
            continue_after=(chosen[-1].handle if chosen else after) if remaining else None,
            title="Long monsoon study",
        )
        return ToolResult(PARTIAL if remaining else OK, passages=tuple(chosen), reading=reading,
                          coverage=Coverage(len(chosen), len(self.long), remaining),
                          dependencies=frozenset({LONG}))


def ask(provider, corpus=None, *, pin=PIN_3, question="What did the long monsoon study find late on?",
        ctx=None):
    corpus = corpus or Manuscript()
    agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    return run(agent.answer(question, corpus, ctx or context())), corpus


def windowed(*responses, capacity=WINDOW):
    provider = recording(*responses)
    provider.capacities = {"scripted-model": capacity}
    return provider


def offered(request):
    return {t["function"]["name"] for t in request["tools"]}


def sent(request, call_id):
    return json.loads(next(m for m in request["messages"] if m.get("tool_call_id") == call_id)["content"])


def reads(corpus):
    return [c for c in corpus.calls if c[0] == "read_manuscript"]


# --- The pinned tool set ------------------------------------------------------------

def test_only_the_research_3_pin_offers_read_manuscript_and_keeps_the_earlier_tools():
    provider = recording(reply("General background."))
    ask(provider)
    assert {"read_manuscript", "resolve_papers", "count_records", "search"} <= offered(provider.requests[0])

    for pin in (PIN, PIN_2):
        older = recording(reply("General background."))
        ask(older, pin=pin)
        assert "read_manuscript" not in offered(older.requests[0])


# --- Middle and late sections ----------------------------------------------------------

def test_a_paper_that_fits_is_read_whole_in_order_and_its_middle_and_end_are_cited_at_their_pages():
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"Soil moisture rose by 42 percent [{at(15)}], and 19 villages adopted the alert [{at(30)}]. "
              "I read the whole extracted text; figures and formulas were not interpreted."),
    )
    result, corpus = ask(provider)

    [(_, _, after, max_bytes)] = reads(corpus)
    assert after is None and max_bytes > 0
    body = sent(provider.requests[1], "r")
    assert body["status"] == "ok"
    # Document order, all of it: never a fixed first-passage prefix.
    assert [p["passage"] for p in body["passages"]] == [at(n) for n in range(1, 31)]
    assert body["reading"]["covered"] == {"passages": [1, 30], "pages": [1, 10]}
    assert body["reading"]["missing"] == [] and body["reading"]["continue_after"] is None
    assert body["reading"]["read_so_far"] == {"passages": 30, "read": [[1, 30]], "not_read": []}

    assert result.answer.startswith("Soil moisture rose by 42 percent [1], and 19 villages adopted the alert [2].")
    middle, late = result.citations
    assert (middle.quote, middle.page, middle.revision) == (MIDDLE, 5, "77:e7")
    assert (late.quote, late.page, late.revision) == (LATE, 10, "77:e7")
    [coverage] = [f for f in result.facts if f["kind"] == "reading_coverage"]
    assert coverage == {
        "kind": "reading_coverage", "title": "Long monsoon study", "passages": 30, "read": 30,
        "complete": True, "pages": 10, "pages_no_passage_starts_on": 0, "formula_passages": 0,
        "caption_passages": 0, "visual_interpretation": False, "exhaustive": False}


def test_a_small_window_reads_a_bounded_stretch_then_continues_from_where_it_stopped():
    def first_stop(request):
        return sent(request, "r1")["reading"]["continue_after"]

    provider = windowed(tools(call("r1", "read_manuscript", paper=PAPER)), reply("placeholder"))
    ask(provider)
    stop = first_stop(provider.requests[1])
    assert stop is not None

    provider = windowed(
        tools(call("r1", "read_manuscript", paper=PAPER)),
        tools(call("r2", "read_manuscript", paper=PAPER, continue_after=stop)),
        reply(f"Section 1 reviews earlier monsoon work [{at(1)}]. I did not read every passage of the paper."),
    )
    result, corpus = ask(provider)

    (_, _, none, first_room), (_, _, cursor, second_room) = reads(corpus)
    assert none is None and cursor == stop
    # Each read is sized to what the window still holds, never beyond it.
    assert first_room < WINDOW.context_tokens - RESERVES.total
    assert second_room < first_room

    first, second = sent(provider.requests[1], "r1"), sent(provider.requests[2], "r2")
    assert first["status"] == "partial"
    last = first["reading"]["covered"]["passages"][1]
    assert first["reading"]["missing"][0]["passages"] == [last + 1, 30]
    assert second["reading"]["covered"]["passages"][0] == last + 1
    upto = second["reading"]["covered"]["passages"][1]
    assert second["reading"]["read_so_far"]["read"] == [[1, upto]]
    if upto < 30:
        assert second["reading"]["read_so_far"]["not_read"] == [[upto + 1, 30]]
        assert second["reading"]["continue_after"] == at(upto)
    # Nothing was withheld: the reads were sized to fit.
    assert "withheld" not in first and "withheld" not in second

    [coverage] = [f for f in result.facts if f["kind"] == "reading_coverage"]
    assert coverage["read"] == upto and coverage["complete"] is (upto == 30)


def test_the_run_allowance_bounds_a_read_so_the_answer_still_fits():
    allowance = {**ALLOWANCE, "max_input_tokens": 24_000}
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"Section 1 reviews earlier monsoon work [{at(1)}]. I read only the opening of the paper."),
    )
    result, corpus = ask(provider, ctx=context(allowance=allowance))

    [(_, _, _, max_bytes)] = reads(corpus)
    # The million-token window would hold the whole paper; the allowance does not.
    assert max_bytes < allowance["max_input_tokens"] // 2
    assert result.citations[0].quote.startswith("Section 1 reviews")


def test_a_window_filled_by_reading_still_answers_and_says_what_was_not_read():
    body = [f"Section {i} reviews earlier monsoon work and the siting of rain gauges. " + "x" * 300
            for i in range(1, 31)]

    def read_on(payload):
        last = payload["messages"][-1]
        if last["role"] == "tool" and json.loads(last["content"]).get("passages"):
            after = json.loads(last["content"])["reading"]["continue_after"]
            if after:
                return tools(call(f"r{len(payload['messages'])}", "read_manuscript", paper=PAPER,
                                  continue_after=after))
        return reply(f"Section 1 reviews earlier monsoon work [{at(1)}]. I could not read the rest of the paper.")

    provider = windowed(tools(call("r0", "read_manuscript", paper=PAPER)), *[read_on] * 6)
    result, corpus = ask(provider, Manuscript(body))

    # The window filled before the paper ended; the run answered rather than failing.
    assert result.answer.startswith("Section 1 reviews earlier monsoon work [1].")
    final = provider.requests[-1]
    shown = [json.loads(m["content"]) for m in final["messages"] if m["role"] == "tool"]
    assert all("withheld" not in r for r in shown)
    assert shown[-1]["reading"]["read_so_far"]["not_read"]
    [coverage] = [f for f in result.facts if f["kind"] == "reading_coverage"]
    assert coverage["complete"] is False and 0 < coverage["read"] < 30
    assert len(reads(corpus)) >= 2


def test_a_read_with_no_room_left_returns_nothing_and_says_so():
    found = Investigation(Manuscript(), manuscripts=True)
    outcome = run(found.execute(ToolCall("r", "read_manuscript", json.dumps({"paper": PAPER})), room=50))
    body = json.loads(outcome.content)
    assert body["status"] == "partial" and "passages" not in body
    assert body["reading"]["covered"] is None
    assert body["reading"]["missing"] == [{"passages": [1, 30], "pages": [1, 10]}]


# --- Overlap and canonical bindings ------------------------------------------------------

def test_overlap_is_shown_once_while_the_citation_keeps_its_whole_passage():
    body = texts()
    tail = "and the gauges were recalibrated every fortnight during the season."
    body[1] = "Section 2 notes " + tail
    body[2] = tail + " Calibration drift stayed under 3 percent."
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"Calibration drift stayed under 3 percent [{at(3)}]."),
    )
    result, corpus = ask(provider, Manuscript(body))

    shown = sent(provider.requests[1], "r")
    third = shown["passages"][2]
    assert third["text"] == " Calibration drift stayed under 3 percent."
    assert third["repeats_previous_chars"] == len(tail)
    assert shown["reading"]["repeated_chars_omitted"] == len(tail)
    # The citation binds the canonical passage, not the shown remainder.
    [citation] = result.citations
    assert (citation.quote, citation.page, citation.revision) == (body[2], 1, "77:e7")


def test_a_read_withheld_by_packing_is_inspected_and_recoverable_but_never_counted_as_shown():
    found = Investigation(Manuscript(), manuscripts=True)
    run(found.execute(ToolCall("r", "read_manuscript", json.dumps({"paper": PAPER})), room=1_000_000))
    found.packed([Answered("r", json.dumps({"withheld": "exceeds_context", "bytes": 9, "coverage": "none"}))])
    [read] = found.readings.values()
    assert read.inspected == set(range(1, 31))
    assert read.visible == set()
    assert read.recoverable == read.inspected
    # Each recoverable passage is reopenable by its own handle.
    assert {read.handles[n] for n in read.recoverable} == {at(n) for n in range(1, 31)}

    shown = Investigation(Manuscript(), manuscripts=True)
    run(shown.execute(ToolCall("r", "read_manuscript", json.dumps({"paper": PAPER})), room=1_000_000))
    shown.packed([Answered("r", "{}")])
    [read] = shown.readings.values()
    assert read.visible == read.inspected and read.recoverable == set()


def test_a_source_replaced_after_the_read_fences_delivery_of_a_late_citation():
    class Replaced(Manuscript):
        async def read_manuscript(self, *args, **kw):
            result = await super().read_manuscript(*args, **kw)
            self.replaced.add(7)
            return result

    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"19 villages adopted the alert [{at(30)}]."),
    )
    with pytest.raises(Unavailable) as refused:
        ask(provider, Replaced())
    assert refused.value.code == "source_changed"


# --- Honest limitations ---------------------------------------------------------------

def test_extraction_gaps_and_uninterpreted_formulas_are_reported_never_interpreted():
    corpus = Manuscript(page_count=12, formulas=2, captions=3)
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"19 villages adopted the alert [{at(30)}]. Pages 11 and 12 had no extracted text, and the "
              "2 formulas and 3 captioned figures were not interpreted."),
    )
    result, _ = ask(provider, corpus)

    reading = sent(provider.requests[1], "r")["reading"]
    assert reading["pages"] == 12 and reading["pages_no_passage_starts_on"] == [11, 12]
    assert (reading["formula_passages"], reading["caption_passages"]) == (2, 3)
    assert reading["visual_content"] == "not_interpreted"
    # The gap's own numbers are supported, so the limitation can be stated.
    assert "Pages 11 and 12 had no extracted text" in result.answer
    [coverage] = [f for f in result.facts if f["kind"] == "reading_coverage"]
    assert (coverage["pages_no_passage_starts_on"], coverage["formula_passages"], coverage["caption_passages"]) == (2, 2, 3)
    assert coverage["visual_interpretation"] is False and coverage["exhaustive"] is False
    # Reopened, the reader sees the same allowlisted coverage.
    [reopened] = [f for f in shown_facts(result.facts) if f["kind"] == "reading_coverage"]
    assert reopened == coverage


def test_reading_one_paper_never_licenses_a_claim_about_every_paper():
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        reply(f"All the papers agree that 19 villages adopted the alert [{at(30)}]."),
        reply(f"The long monsoon study reports that 19 villages adopted the alert [{at(30)}]."),
    )
    result, _ = ask(provider)
    # The overclaim is repaired once in the same Conversation, never delivered.
    assert "All the papers" not in result.answer
    assert "[IRIS validation]" in provider.requests[2]["messages"][-1]["content"]


@pytest.mark.parametrize("arguments", [
    {"paper": PAPER, "continue_after": 5},
    {"paper": PAPER, "start": 10},
    {"paper": PAPER, "max_bytes": 10_000_000},
    {"continue_after": at(3)},
])
def test_a_read_cannot_choose_its_own_size_position_or_omit_its_paper(arguments):
    provider = recording(tools(call("r", "read_manuscript", **arguments)), reply("I could not read it."))
    _, corpus = ask(provider)
    assert reads(corpus) == []
    assert sent(provider.requests[1], "r") == {"error": "invalid_arguments"}


def test_reading_coverage_survives_a_checkpoint_round_trip():
    # IR-724's checkpoint must carry IR-733's coverage, or a resumed run reports a different read.
    body = texts()
    tail = "and the gauges were recalibrated every fortnight during the season."
    body[1] = "Section 2 notes " + tail
    body[2] = tail + " Calibration drift stayed under 3 percent."
    found = Investigation(Manuscript(body), metadata=True, manuscripts=True)
    run(found.execute(ToolCall("r", "read_manuscript", json.dumps({"paper": PAPER})), room=3_000))
    found.packed([Answered("r", "{}")])
    [read] = found.readings.values()
    assert read.reading.missing and read.reading.continue_after and read.visible

    class Spent:
        input, output, reported, attempts = 0, 0, 0, 0

    saved = json.loads(json.dumps(checkpoint.dump(
        pin=PIN_3, bounds=ORDINARY, task="t", history=[], investigation=found, budget=Spent, steps=1, stale=0)))
    again = Investigation(None, metadata=True, manuscripts=True)
    checkpoint.load(saved, pin=PIN_3, bounds=ORDINARY, task="t").apply(again)
    assert again.readings == found.readings
    assert again.passages == found.passages
    assert any(p.overlap for p in again.passages.values())
