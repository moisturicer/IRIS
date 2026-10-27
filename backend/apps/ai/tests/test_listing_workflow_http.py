"""IR-546: presence/listing through the authenticated HTTP, SSE and conversation boundary.

A reader asks which papers are about a topic. They must see the selected
candidates at once (relevance pending), then a screened list whose every state
is reconciled, within twenty distinct Records, with access read again before
each send, update and output. Every vendor is a deterministic fake from the
composition override: nothing here measures real-provider quality or capacity.

A few tests use `transaction=True` because a model call runs on a worker
thread, and a worker's own database connection only sees committed rows.
"""

import json
import threading
import time

import httpx
import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import AskRun, Conversation
from apps.ai.models.chunk import DocumentChunk
from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.routing.router import LANES
from apps.ai.tasks import answer_queued_question
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import _BrokenEmbedder, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

QUESTION = "Which papers are about flooding?"


@pytest.fixture(autouse=True)
def lane(settings, monkeypatch):
    settings.AI_RESEARCH_LANE = "on"
    settings.AI_DURABLE_ASK = False
    # Pinned, so a developer's .env cannot change what these assert.
    settings.AI_SCREEN_BATCH_SIZE = 20
    settings.AI_SCREEN_CONCURRENCY = 3
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 0
    settings.AI_SCREEN_RECHECK_PASSAGES = 2
    settings.AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS = 30
    probabilities = {name: 0.01 for name in LANES}
    probabilities["listing"] = 0.95
    probabilities["injection"] = 0.01
    jev = ScriptedDecisionModel(probabilities)
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda **kwargs: (jev, None))

    def refuse(*args, **kwargs):
        pytest.fail("a listing reached the network; no paid provider call is allowed")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


# -- fakes ---------------------------------------------------------------------


class Screener(LLMProvider):
    """Decides each paper with ``decide(paper) -> "include" | "exclude" | "uncertain"``."""

    def __init__(self, decide=lambda paper: "include", quote=lambda paper: paper["title"]):
        self.decide, self.quote = decide, quote
        self.requests = []
        self._lock = threading.Lock()
        self.in_flight = self.peak = 0

    def generate(self, system, user):
        payload = json.loads(user)
        with self._lock:
            self.requests.append(payload)
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            self.before(payload)
            rows = []
            for paper in payload["records"]:
                verdict = self.decide(paper)
                rows.append({"record": paper["record"], "decision": verdict,
                             "quote": "" if verdict == "uncertain" else self.quote(paper)})
            return json.dumps({"decisions": rows})
        finally:
            with self._lock:
                self.in_flight -= 1

    def before(self, payload):
        """A hook for a test that needs the model to take time or change things."""

    @property
    def titles_sent(self):
        return [paper["title"] for request in self.requests for paper in request["records"]]


class Down(LLMProvider):
    def generate(self, system, user):
        raise LLMUnavailable("503 screening model unavailable")


def make_root(embedder, screen, permits=lambda record: True):
    root = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                           llm=ScriptedLLM(), permits=permits)
    real = root.llm_for
    root.llm_for = lambda task: screen if task == InferenceTask.SCREEN else real(task)
    return root


def papers(embedder, space, count, *, prefix="Flood Study", **options):
    return [
        make_record(title=f"{prefix} {n:02d}", text=f"flooding study number {n} in the catchment",
                    embedder=embedder, space=space, **options)
        for n in range(count)
    ]


def parse(chunks):
    events = []
    for block in b"".join(chunks).decode().split("\n\n"):
        if block.strip():
            fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def watch(client, question=QUESTION, **options):
    """Events as they arrive, so a test can act between two of them."""
    response = client.post(reverse("ai-ask-stream"), {"question": question, **options}, format="json")
    assert response.status_code == 200
    for block in response.streaming_content:
        yield from parse([block])


def run_stream(client, root, **options):
    with use_composition_root(root):
        return list(watch(client, **options))


def done_of(events):
    return next(data for name, data in events if name == "done")


@pytest.fixture
def reader(client_for):
    user = make_user("reader@cit.edu")
    return user, client_for(user)


def states(listing):
    return {row["record_id"]: row["state"] for row in listing["candidates"]}


# -- preview first, then every state reconciled ----------------------------------


def test_candidates_are_previewed_pending_before_any_decision_then_reconciled(
    embedder, space, reader, settings
):
    user, client = reader
    flood, hazard, tilapia, vague = (
        make_record(title=t, text=x, embedder=embedder, space=space) for t, x in [
            ("Flood Prediction", "neural network on rainfall gauges"),
            ("Flood Hazard Mapping", "hazard maps of the river"),
            ("Tilapia Ponds", "sampling of tilapia ponds"),
            ("Rainfall Note", "monthly rainfall totals"),
        ]
    )
    verdict = {"Flood Prediction": "include", "Flood Hazard Mapping": "include",
               "Tilapia Ponds": "exclude", "Rainfall Note": "uncertain"}
    screen = Screener(lambda paper: verdict[paper["title"]])
    conversation = Conversation.objects.create(user=user)

    events = run_stream(client, make_root(embedder, screen), conversation_id=conversation.pk)
    names = [name for name, _ in events]

    assert names.index("candidates_selected") < names.index("candidates_updated") < names.index("done")
    preview = next(data for name, data in events if name == "candidates_selected")
    assert {row["state"] for row in preview["candidates"]} == {"pending"}, "none is a match yet"
    assert {row["record_id"] for row in preview["candidates"]} == {
        r.pk for r in (flood, hazard, tilapia, vague)}
    assert preview["limit"] == 20 and preview["more_available"] is False

    listing = done_of(events)["listing"]
    assert states(listing) == {flood.pk: "included", hazard.pk: "included",
                               tilapia.pk: "excluded", vague.pk: "uncertain"}
    assert [r["record_id"] for r in listing["records"]] == [
        row["record_id"] for row in listing["candidates"] if row["state"] == "included"]
    assert listing["coverage"] == {
        "limit": 20, "selected": 4, "included": 2, "excluded": 1, "uncertain": 1, "unassessed": 0,
        "more_available": False, "search_degraded": False, "changed": False}
    assert listing["completeness"] == "matches_found"
    assert "2 matched, 1 did not match, 1 uncertain, 0 could not be assessed" in listing["wording"]
    assert "not a complete list of the papers you can see" in listing["wording"]

    # Every announced Record is in the final list exactly once.
    ids = [row["record_id"] for row in listing["candidates"]]
    assert sorted(ids) == sorted(row["record_id"] for row in preview["candidates"])
    assert len(ids) == len(set(ids))
    # Every update names a Record the preview announced, with a state and nothing else.
    for name, data in events:
        if name == "candidates_updated":
            for row in data["candidates"]:
                assert set(row) == {"record_id", "state"} and row["record_id"] in ids

    # A decided row carries the quote that decided it, found in the paper itself.
    by_id = {row["record_id"]: row for row in listing["candidates"]}
    assert by_id[flood.pk]["quote"] == "Flood Prediction" and by_id[flood.pk]["source"] == {"field": "title"}
    assert "quote" not in by_id[vague.pk]

    # The reopened conversation reads the same listing and the same sentence.
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    assert turn["listing"] == listing
    assert turn["answer"] == listing["wording"]


def test_the_json_endpoint_returns_the_same_final_listing(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 3)
    with use_composition_root(make_root(embedder, Screener())):
        body = client.post(reverse("ai-ask"), {"question": QUESTION}, format="json").json()
    assert body["routing"]["lane"] == "listing"
    assert body["listing"]["coverage"]["included"] == 3
    assert body["answer"] == body["listing"]["wording"]


# -- the twenty-candidate allowance --------------------------------------------


def test_at_most_twenty_distinct_candidates_are_selected_and_the_rest_are_disclosed(
    embedder, space, reader
):
    user, client = reader
    papers(embedder, space, 25)
    screen = Screener()
    events = run_stream(client, make_root(embedder, screen))
    preview = next(data for name, data in events if name == "candidates_selected")
    listing = done_of(events)["listing"]

    assert len(preview["candidates"]) == 20 and preview["more_available"] is True
    assert len(listing["candidates"]) == 20 == listing["coverage"]["selected"]
    assert len(screen.titles_sent) == 20 == len(set(screen.titles_sent))
    assert "More candidates were found than were screened (limit 20)" in listing["wording"]
    assert "not a complete list of the papers you can see" in listing["wording"]


def test_failed_assessments_stay_in_the_allowance_and_nothing_replaces_them(
    embedder, space, reader
):
    user, client = reader
    papers(embedder, space, 25)
    events = run_stream(client, make_root(embedder, Down()))
    preview = next(data for name, data in events if name == "candidates_selected")
    listing = done_of(events)["listing"]

    assert {row["record_id"] for row in listing["candidates"]} == {
        row["record_id"] for row in preview["candidates"]}, "a retry cannot widen the list"
    assert len(listing["candidates"]) == 20
    assert {row["state"] for row in listing["candidates"]} == {"unassessed"}
    assert listing["records"] == []
    assert listing["completeness"] == "inconclusive"
    assert "Inconclusive: none of the 20 candidate papers could be assessed" in listing["wording"]
    assert "No matches" not in listing["wording"], "a failure is not a zero"


def test_a_paper_with_many_chunks_is_one_candidate(embedder, space, reader):
    user, client = reader
    many, other = papers(embedder, space, 2)
    template = DocumentChunk.objects.filter(record=many).first()
    for n in range(1, 6):
        DocumentChunk.objects.create(
            chunk_set=template.chunk_set, record=many, sequence=n, max_sequence=n,
            text=f"more flooding words {n}", content=f"more flooding words {n}",
            context_path=[many.title], token_count=4, text_hash=f"x{many.pk}{n}",
            source_page=n, element_kinds=["paragraph"], bboxes=[],
        )
    listing = done_of(run_stream(client, make_root(embedder, Screener())))["listing"]
    assert sorted(row["record_id"] for row in listing["candidates"]) == sorted([many.pk, other.pk])


# -- what a model can and cannot decide -------------------------------------------


def test_a_model_cannot_invent_a_paper_a_title_or_a_quote(embedder, space, reader):
    user, client = reader
    real, = papers(embedder, space, 1)

    class Inventor(Screener):
        def generate(self, system, user):
            handle = json.loads(user)["records"][0]["record"]
            return json.dumps({"decisions": [
                {"record": "R99", "decision": "include", "quote": "Invented Paper"},
                {"record": handle, "decision": "include", "quote": "a sentence the paper never says"},
            ]})

    listing = done_of(run_stream(client, make_root(embedder, Inventor())))["listing"]
    assert [row["record_id"] for row in listing["candidates"]] == [real.pk]
    assert listing["candidates"][0]["state"] == "unassessed"
    assert "Invented Paper" not in json.dumps(listing)
    assert listing["candidates"][0]["title"] == real.title, "titles come from the database"


def test_content_a_model_may_not_read_is_counted_but_never_sent_or_named(embedder, space, reader):
    user, client = reader
    open_paper, closed = papers(embedder, space, 2)
    screen = Screener()
    root = make_root(embedder, screen, permits=lambda record: record.pk != closed.pk)
    events = run_stream(client, root)
    listing = done_of(events)["listing"]
    preview = next(data for name, data in events if name == "candidates_selected")

    assert closed.title not in json.dumps(events) and closed.title not in json.dumps(screen.requests)
    assert closed.abstract not in json.dumps(screen.requests)
    assert {"record_id": closed.pk, "state": "unassessed", "restricted": True} in preview["candidates"]
    assert listing["coverage"]["selected"] == 2 and listing["coverage"]["unassessed"] == 1
    assert listing["coverage"]["included"] == 1
    assert [r["record_id"] for r in listing["records"]] == [open_paper.pk]


# -- uncertain papers and bounded passages ----------------------------------------


def passage_aware(paper):
    if paper.get("passages"):
        return "include"
    return "uncertain"


def test_an_uncertain_paper_is_rechecked_with_a_passage_when_limits_allow(
    embedder, space, reader, settings
):
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 5
    user, client = reader
    paper, = papers(embedder, space, 1)
    screen = Screener(passage_aware,
                      quote=lambda p: p["passages"][0]["text"][:30] if p.get("passages") else p["title"])
    events = run_stream(client, make_root(embedder, screen))
    listing = done_of(events)["listing"]

    assert len(screen.requests) == 2
    assert "passages" not in screen.requests[0]["records"][0]
    sent = screen.requests[1]["records"][0]["passages"]
    assert 1 <= len(sent) <= settings.AI_SCREEN_RECHECK_PASSAGES and sent[0]["page"] == 4
    row, = listing["candidates"]
    assert row["state"] == "included"
    assert row["source"]["field"] == "passage" and row["source"]["page"] == 4
    assert row["quote"] in "flooding study number 0 in the catchment"
    assert [name for name, _ in events].count("candidates_updated") >= 2


def test_with_no_passage_allowance_an_uncertain_paper_stays_uncertain(embedder, space, reader, settings):
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 0
    user, client = reader
    papers(embedder, space, 1)
    screen = Screener(passage_aware)
    listing = done_of(run_stream(client, make_root(embedder, screen)))["listing"]
    assert len(screen.requests) == 1
    assert listing["candidates"][0]["state"] == "uncertain"


def test_a_failed_recheck_leaves_the_paper_uncertain_not_unassessed(embedder, space, reader, settings):
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 5
    user, client = reader
    papers(embedder, space, 1)

    class RecheckFails(Screener):
        def before(self, payload):
            if len(self.requests) > 1:
                raise TimeoutError("scripted")

    listing = done_of(run_stream(client, make_root(embedder, RecheckFails(passage_aware))))["listing"]
    assert listing["candidates"][0]["state"] == "uncertain"


def test_the_recheck_is_skipped_when_too_little_time_is_left(embedder, space, reader, settings):
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 5
    settings.AI_SCREEN_TIMEOUT_SECONDS = 20
    settings.AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS = 5
    user, client = reader
    papers(embedder, space, 1)
    screen = Screener(passage_aware)
    listing = done_of(run_stream(client, make_root(embedder, screen)))["listing"]
    assert len(screen.requests) == 1, "a second call could outlive the deadline, so it is not made"
    assert listing["candidates"][0]["state"] == "uncertain"


# -- access, read again ----------------------------------------------------------


def revoke(record):
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)


def test_a_paper_that_becomes_unreadable_after_the_preview_is_never_sent_or_shown_again(
    embedder, space, reader
):
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    screen = Screener()
    events = []
    with use_composition_root(make_root(embedder, screen)):
        for name, data in watch(client):
            events.append((name, data))
            if name == "candidates_selected":
                revoke(lost)

    assert lost.title not in screen.titles_sent
    after = [(n, d) for n, d in events if n != "candidates_selected"]
    assert lost.title not in json.dumps(after) and str(lost.pk) not in json.dumps(
        [d for n, d in after if n == "candidates_updated"])
    listing = done_of(events)["listing"]
    assert [row["record_id"] for row in listing["candidates"]] == [kept.pk]
    assert listing["coverage"]["selected"] == 1 and listing["coverage"]["changed"] is True
    assert "changed while this ran" in listing["wording"]
    assert listing["wording"].startswith("Screened 1 candidate papers"), "the lost paper is not counted"


@pytest.mark.django_db(transaction=True)
def test_a_paper_edited_while_its_batch_was_out_loses_its_decision(embedder, space, reader):
    user, client = reader
    edited, steady = papers(embedder, space, 2)

    class Edits(Screener):
        def before(self, payload):
            Record.objects.filter(pk=edited.pk).update(abstract="a different abstract entirely")

    listing = done_of(run_stream(client, make_root(embedder, Edits())))["listing"]
    got = states(listing)
    assert got[edited.pk] == "unassessed" and got[steady.pk] == "included"
    assert listing["coverage"]["changed"] is True


@pytest.mark.django_db(transaction=True)
def test_a_paper_that_loses_access_during_the_call_is_dropped_from_the_result(embedder, space, reader):
    user, client = reader
    lost, kept = papers(embedder, space, 2)

    class Revokes(Screener):
        def before(self, payload):
            revoke(lost)

    events = run_stream(client, make_root(embedder, Revokes()))
    listing = done_of(events)["listing"]
    assert [row["record_id"] for row in listing["candidates"]] == [kept.pk]
    updates = [row for name, data in events if name == "candidates_updated" for row in data["candidates"]]
    assert lost.pk not in [row["record_id"] for row in updates]


def test_a_paper_the_gate_refuses_after_the_preview_is_no_longer_named(embedder, space, reader):
    user, client = reader
    kept, gated = papers(embedder, space, 2)
    closed = []
    screen = Screener()
    root = make_root(embedder, screen, permits=lambda record: not (closed and record.pk == gated.pk))
    events = []
    with use_composition_root(root):
        for name, data in watch(client):
            events.append((name, data))
            if name == "candidates_selected":
                closed.append(True)

    assert gated.title not in screen.titles_sent
    listing = done_of(events)["listing"]
    assert {"record_id": gated.pk, "state": "unassessed", "restricted": True} in listing["candidates"]
    assert gated.title not in json.dumps(listing)
    assert states(listing)[kept.pk] == "included"


def test_a_retrieval_failure_is_unavailable_not_a_search_with_nothing_found(
    embedder, space, reader, monkeypatch
):
    user, client = reader
    papers(embedder, space, 2)

    def broken(run, args):
        raise RuntimeError("index unreachable")

    monkeypatch.setattr("apps.ai.research.listing.rank_record_candidates", broken)
    events = run_stream(client, make_root(embedder, Screener()))
    done = done_of(events)
    assert done["mode"] == "unavailable" and "listing" not in done
    assert "candidates_selected" not in [name for name, _ in events]


# -- honest coverage -------------------------------------------------------------


def test_no_candidates_is_a_search_result_not_proof_of_absence(embedder, space, reader):
    user, client = reader
    events = run_stream(client, make_root(embedder, Screener()))
    assert "candidates_selected" not in [name for name, _ in events]
    done = done_of(events)
    assert done["listing"]["candidates"] == [] and done["listing"]["records"] == []
    assert "not proof that none exist" in done["listing"]["wording"]
    assert done["answer"] is None and done["message"] == done["listing"]["wording"]


def test_zero_matches_among_assessed_papers_is_worded_as_a_subset(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 3)
    listing = done_of(run_stream(client, make_root(embedder, Screener(lambda p: "exclude"))))["listing"]
    assert listing["records"] == [] and listing["completeness"] == "matches_found"
    assert listing["wording"].startswith("No matches found among the assessed candidates; "
                                         "other relevant papers may exist.")


def test_word_matching_only_search_is_disclosed(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 2)
    root = make_root(_BrokenEmbedder(), Screener())
    events = run_stream(client, root)
    preview = next(data for name, data in events if name == "candidates_selected")
    listing = done_of(events)["listing"]
    assert preview["degraded"] is True and listing["coverage"]["search_degraded"] is True
    assert "word matching only" in listing["wording"]
    assert "exhaustive" not in listing["wording"]


# -- bounded parallel screening and the deadline -----------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_screening_call_on_a_worker_is_charged_to_the_research_lane_and_the_questions_run(
    embedder, space, reader
):
    from apps.ai.admission import scope

    user, client = reader
    papers(embedder, space, 1)
    seen = []

    class Records(Screener):
        def before(self, payload):
            seen.append((scope.lane_for("default"), scope.current_run()))

    done_of(run_stream(client, make_root(embedder, Records())))
    (lane_name, run_scope), = seen
    assert lane_name == "research", "a worker thread carries the workload of the question"
    assert run_scope is not None and run_scope.key.startswith("req:")


@pytest.mark.django_db(transaction=True)
def test_batches_run_in_parallel_but_never_beyond_the_configured_bound(embedder, space, reader, settings):
    settings.AI_SCREEN_BATCH_SIZE = 2
    settings.AI_SCREEN_CONCURRENCY = 2
    user, client = reader
    papers(embedder, space, 8)

    class Slow(Screener):
        def before(self, payload):
            time.sleep(0.15)

    screen = Slow()
    listing = done_of(run_stream(client, make_root(embedder, screen)))["listing"]
    assert len(screen.requests) == 4 and listing["coverage"]["included"] == 8
    assert screen.peak == 2, "two batches in flight, never three"


@pytest.mark.django_db(transaction=True)
def test_at_the_deadline_decided_papers_are_kept_and_the_rest_are_unassessed(
    embedder, space, reader, settings
):
    settings.AI_SCREEN_BATCH_SIZE = 3
    settings.AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS = 1.5
    user, client = reader
    papers(embedder, space, 6)

    class OneStalls(Screener):
        def before(self, payload):
            if len(self.requests) == 2:
                time.sleep(4)

    started = time.monotonic()
    listing = done_of(run_stream(client, make_root(embedder, OneStalls())))["listing"]
    assert time.monotonic() - started < 3.5, "the original deadline ends the wait"
    assert listing["coverage"]["included"] == 3 and listing["coverage"]["unassessed"] == 3
    assert listing["coverage"]["selected"] == 6
    assert listing["records"] and listing["completeness"] == "matches_found"


# -- the queued path: replay and revocation ---------------------------------------


def _frames(chunks):
    frames = []
    for block in b"".join(chunks).decode().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.strip().split("\n")
                      if line and not line.startswith(":"))
        if "event" in fields:
            frames.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return frames


def test_a_queued_listing_journals_the_candidates_and_replay_rechecks_access(
    embedder, space, reader, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    monkeypatch.setattr(answer_queued_question, "apply_async", lambda args, **limits: None)
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    conversation = Conversation.objects.create(user=user)
    root = make_root(embedder, Screener())

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("ai-ask-stream"),
                               {"question": QUESTION, "conversation_id": conversation.pk}, format="json")
    first = next(iter(response.streaming_content))
    response._iterator.close()
    run_id = _frames([first])[0][2]["run_id"]
    with use_composition_root(root):
        answer_queued_question(run_id)

    def replay():
        got = client.get(reverse("ai-ask-run-stream", args=[run_id]))
        return _frames(got.streaming_content)

    frames = replay()
    names = [name for _, name, _ in frames]
    assert [s for s, _, _ in frames] == sorted(s for s, _, _ in frames)
    assert names.index("candidates_selected") < names.index("candidates_updated") < names.index("done")
    preview = next(d for _, n, d in frames if n == "candidates_selected")
    assert {row["record_id"] for row in preview["candidates"]} == {kept.pk, lost.pk}
    assert states(frames[-1][2]["listing"]) == {kept.pk: "included", lost.pk: "included"}

    revoke(lost)
    again = replay()
    wire = json.dumps(again)
    assert lost.title not in wire
    preview = next(d for _, n, d in again if n == "candidates_selected")
    assert [row["record_id"] for row in preview["candidates"]] == [kept.pk]
    assert [row["record_id"] for _, n, d in again if n == "candidates_updated" for row in d["candidates"]
            ] == [kept.pk] * len([1 for _, n, _ in again if n == "candidates_updated"])
    listing = again[-1][2]["listing"]
    assert [row["record_id"] for row in listing["candidates"]] == [kept.pk]
    assert listing["wording"].startswith("Screened 1 candidate papers")
    assert AskRun.objects.get(pk=run_id).turn is not None


def test_a_reopened_conversation_forgets_a_paper_the_reader_can_no_longer_see(
    embedder, space, reader
):
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    conversation = Conversation.objects.create(user=user)
    run_stream(client, make_root(embedder, Screener()), conversation_id=conversation.pk)

    revoke(lost)
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    assert [row["record_id"] for row in turn["listing"]["candidates"]] == [kept.pk]
    assert turn["listing"]["coverage"]["selected"] == 1 and turn["listing"]["coverage"]["changed"] is True
    assert lost.title not in json.dumps(turn)
    assert turn["answer"].startswith("Screened 1 candidate papers"), "the sentence no longer counts it"


def test_a_decision_whose_quote_no_longer_holds_reads_as_unassessed(embedder, space, reader):
    user, client = reader
    paper, = papers(embedder, space, 1)
    conversation = Conversation.objects.create(user=user)
    run_stream(client, make_root(embedder, Screener()), conversation_id=conversation.pk)

    Record.objects.filter(pk=paper.pk).update(title="Renamed Study")
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    row, = turn["listing"]["candidates"]
    assert row["state"] == "unassessed" and row["title"] == "Renamed Study" and "quote" not in row
    assert turn["listing"]["records"] == []

