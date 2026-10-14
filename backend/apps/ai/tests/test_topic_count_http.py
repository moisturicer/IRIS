"""IR-547: topic-match counts and the screening cache, through the public HTTP boundary.

A reader asks how many retrieved Records match a topic. They get a count of
application-owned include decisions over at most twenty distinct, currently
authorized candidates, worded as a classified subset with its coverage -- never
a model-written number and never a claim about the whole catalogue. Screening
verdicts are cached per reader and re-checked on every reuse.

Every vendor is a deterministic fake from the composition override. Nothing here
measures real-provider quality, latency, cost or capacity, and a warm run proves
nothing about a fresh model's capacity.
"""

import json
import threading

import httpx
import pytest
from django.db import IntegrityError, connection
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.models.chunk import ChunkSet
from apps.ai.models.screening import ScreeningJudgment
from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.routing.router import LANES
from apps.ai.tasks import answer_queued_question
from apps.records.models import Record
from .corpus import make_user
from .test_listing_workflow_http import (
    Down, Screener, _frames, done_of, make_root, papers, revoke, watch,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

QUESTION = "How many papers are about flooding?"
LISTING_QUESTION = "Which papers are about flooding?"


class RepeatingJev(ScriptedDecisionModel):
    """The same routing answer for every question, so a test may ask many."""

    def __init__(self, step):
        super().__init__(step)
        self._answer = step

    def nouls(self, state, *, questions, timeout_seconds=None):
        self._steps = [self._answer]
        return super().nouls(state, questions=questions, timeout_seconds=timeout_seconds)


@pytest.fixture(autouse=True)
def lane(settings, monkeypatch):
    settings.AI_RESEARCH_LANE = "on"
    settings.AI_DURABLE_ASK = False
    settings.AI_SCREEN_BATCH_SIZE = 20
    settings.AI_SCREEN_CONCURRENCY = 3
    settings.AI_SCREEN_RECHECK_MAX_RECORDS = 0
    settings.AI_SCREEN_RECHECK_PASSAGES = 2
    settings.AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS = 30
    settings.AI_SCREEN_CACHE = False
    probabilities = {name: 0.01 for name in LANES}
    probabilities["count"] = 0.95
    probabilities["injection"] = 0.01
    jev = RepeatingJev(probabilities)
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda **kwargs: (jev, None))

    def refuse(*args, **kwargs):
        pytest.fail("a topic count reached the network; no paid provider call is allowed")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def reader(client_for):
    user = make_user("reader@cit.edu")
    return user, client_for(user)


@pytest.fixture
def cached(settings):
    settings.AI_SCREEN_CACHE = True
    settings.AI_SCREEN_CACHE_POLICY = "approved-1"


class Silent(LLMProvider):
    """Any model but the screening one: a count is never written by a model."""

    def generate(self, system, user):
        pytest.fail("a model other than the screener was called for a topic count")


def root_for(embedder, screen, permits=lambda record: True):
    root = make_root(embedder, screen, permits)

    def llm_for(task):
        return screen if task == InferenceTask.SCREEN else Silent()

    root.llm_for = llm_for
    return root


def number(record):
    return int(record.title.rsplit(" ", 1)[1])


def seven_of_twenty(paper):
    """7 match, 9 do not, 4 cannot be assessed -- of exactly twenty papers."""
    n = int(paper["title"].rsplit(" ", 1)[1])
    return "include" if n < 7 else "exclude" if n < 16 else "unassessed"


def block(done):
    return done["listing"]["topic_count"]


def run_stream(client, root, question=QUESTION, **options):
    with use_composition_root(root):
        return list(watch(client, question, **options))


# -- the count, its wording and its provenance ------------------------------------


def test_seven_matches_among_sixteen_assessed_of_twenty_selected(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 20)
    conversation = Conversation.objects.create(user=user)
    screen = Screener(seven_of_twenty)

    events = run_stream(client, root_for(embedder, screen), question=QUESTION,
                        conversation_id=conversation.pk)
    done = done_of(events)
    listing, topic = done["listing"], block(done)

    assert done["routing"]["lane"] == "count"
    assert (topic["matches"], topic["assessed"], topic["excluded"], topic["uncertain"],
            topic["unassessed"], topic["selected"], topic["limit"]) == (7, 16, 9, 0, 4, 20, 20)
    assert "7 matches among 16 assessed of 20 selected candidate papers, with 4 not assessed" in listing["wording"]
    assert "Other relevant papers may exist" in listing["wording"]
    assert listing["wording"] == done["answer"], "the sentence is written in code, not by a model"
    assert listing["completeness"] == "matches_found"
    # The count and the list are the same decisions.
    assert len(listing["records"]) == 7
    assert [row["record_id"] for row in listing["records"]] == [
        row["record_id"] for row in listing["candidates"] if row["state"] == "included"]

    # Criterion, method and version are stated, and the basis is not a catalogue count.
    assert topic["criterion"] == QUESTION
    assert topic["method"] == "title_and_abstract_screening"
    assert topic["version"].startswith("screen-")
    assert topic["basis"] == "topic_classification_of_selected_candidates"
    assert "not a count of every paper" in listing["wording"]
    assert "catalogue" in listing["wording"] and QUESTION in listing["wording"]

    # The reopened conversation keeps the count.
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    assert turn["listing"] == listing and turn["answer"] == listing["wording"]


def test_candidates_are_pending_and_count_for_nothing_until_assessed(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 5)
    events = run_stream(client, root_for(embedder, Screener()))
    names = [name for name, _ in events]

    preview = next(data for name, data in events if name == "candidates_selected")
    assert {row["state"] for row in preview["candidates"]} == {"pending"}
    assert "topic_count" not in json.dumps(
        [(n, d) for n, d in events if n in ("candidates_selected", "candidates_updated")])
    assert names.index("candidates_selected") < names.index("candidates_updated") < names.index("done")
    assert block(done_of(events))["matches"] == 5


def test_the_model_cannot_write_or_extrapolate_the_count(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 3)

    class Boaster(Screener):
        def generate(self, system, user):
            payload = json.loads(user)
            return json.dumps({"count": 4000, "decisions": [
                {"record": p["record"], "decision": "include", "quote": p["title"]}
                for p in payload["records"]]})

    done = done_of(run_stream(client, root_for(embedder, Boaster())))
    assert block(done)["matches"] == 0 and block(done)["unassessed"] == 3
    assert "4000" not in json.dumps(done)
    assert done["listing"]["completeness"] == "inconclusive"


def test_all_unassessed_is_inconclusive_not_zero(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 6)
    done = done_of(run_stream(client, root_for(embedder, Down())))
    wording = done["listing"]["wording"]

    assert done["listing"]["completeness"] == "inconclusive"
    assert wording.startswith("Inconclusive: none of the 6 candidate papers could be assessed")
    assert "0 matches" not in wording and "No matches" not in wording
    assert block(done)["matches"] == 0 and block(done)["assessed"] == 0 and block(done)["unassessed"] == 6


@pytest.mark.parametrize("failure", ["malformed", "timeout", "unavailable"])
def test_malformed_timed_out_and_unavailable_screens_are_unassessed_not_excluded(
    embedder, space, reader, failure
):
    user, client = reader
    papers(embedder, space, 4)

    class Failing(Screener):
        def generate(self, system, user):
            if failure == "timeout":
                raise TimeoutError("screening timed out")
            if failure == "unavailable":
                raise LLMUnavailable("503")
            return "{\"decisions\": [{\"record\": "

    done = done_of(run_stream(client, root_for(embedder, Failing())))
    assert block(done)["unassessed"] == 4 and block(done)["excluded"] == 0 and block(done)["matches"] == 0
    assert done["listing"]["completeness"] == "inconclusive"


def test_zero_matches_among_assessed_papers_is_a_subset_statement(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 5)
    done = done_of(run_stream(client, root_for(embedder, Screener(lambda paper: "exclude"))))
    wording = done["listing"]["wording"]

    assert block(done)["matches"] == 0 and block(done)["assessed"] == 5
    assert "0 matches among 5 assessed of 5 selected candidate papers, with 0 not assessed" in wording
    assert "other relevant papers may exist" in wording.lower()
    assert done["listing"]["completeness"] == "matches_found"


def test_uncertain_papers_are_assessed_but_never_matches(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 4)
    done = done_of(run_stream(client, root_for(
        embedder, Screener(lambda p: "include" if number_of(p) == 0 else "uncertain"))))
    topic = block(done)
    assert (topic["matches"], topic["uncertain"], topic["assessed"], topic["unassessed"]) == (1, 3, 4, 0)
    assert "1 matches among 4 assessed" not in done["listing"]["wording"], "singular and plural are worded"
    assert "1 match among 4 assessed of 4 selected candidate papers, 3 of them uncertain" in done["listing"]["wording"]


def number_of(paper):
    return int(paper["title"].rsplit(" ", 1)[1])


def test_no_candidates_is_a_search_result_not_a_zero_count(embedder, space, reader):
    user, client = reader
    done = done_of(run_stream(client, root_for(embedder, Screener())))
    assert done["listing"]["wording"].startswith("No candidate papers were found")
    assert "0 matches" not in done["listing"]["wording"]
    assert block(done)["selected"] == 0 and block(done)["matches"] == 0


def test_at_most_twenty_candidates_and_the_rest_are_disclosed_never_scanned(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 25)
    screen = Screener()
    done = done_of(run_stream(client, root_for(embedder, screen)))

    assert block(done)["selected"] == 20 and block(done)["matches"] == 20
    assert len(screen.titles_sent) == 20 == len(set(screen.titles_sent))
    assert block(done)["more_available"] is True
    assert "More candidates were found than were screened (limit 20)" in done["listing"]["wording"]


def test_a_paper_with_many_owners_chunks_and_versions_is_counted_once(embedder, space, reader):
    from apps.ai.models.chunk import DocumentChunk

    user, client = reader
    many, other = papers(embedder, space, 2)
    template = DocumentChunk.objects.filter(record=many).first()
    for n in range(1, 5):
        DocumentChunk.objects.create(
            chunk_set=template.chunk_set, record=many, sequence=n, max_sequence=n,
            text=f"more flooding words {n}", content=f"more flooding words {n}",
            context_path=[many.title], token_count=4, text_hash=f"c{many.pk}{n}",
            source_page=n, element_kinds=["paragraph"], bboxes=[],
        )
    done = done_of(run_stream(client, root_for(embedder, Screener())))
    assert block(done)["selected"] == 2 and block(done)["matches"] == 2


def test_content_ai_may_not_read_is_unassessed_and_never_named_or_sent(embedder, space, reader):
    user, client = reader
    open_paper, closed = papers(embedder, space, 2)
    screen = Screener()
    events = run_stream(client, root_for(embedder, screen, lambda r: r.pk != closed.pk))
    done = done_of(events)

    assert closed.title not in json.dumps(events) and closed.title not in json.dumps(screen.requests)
    assert (block(done)["matches"], block(done)["unassessed"], block(done)["selected"]) == (1, 1, 2)
    assert {"record_id": closed.pk, "state": "unassessed", "restricted": True} in done["listing"]["candidates"]


def test_a_metadata_count_is_still_answered_without_any_model(embedder, space, reader):
    user, client = reader
    papers(embedder, space, 3)
    screen = Screener()
    done = done_of(run_stream(client, root_for(embedder, screen), question="How many papers are in the repository?"))
    assert done["listing"]["count"]["total"] == 3
    assert "topic_count" not in done["listing"] and not screen.requests


# -- the cache ------------------------------------------------------------------------


def observed(done):
    return done["listing"]["observed"]


def test_cold_then_warm_reuses_verdicts_without_a_model_call(embedder, space, reader, cached):
    user, client = reader
    papers(embedder, space, 20)
    screen = Screener(seven_of_twenty)

    cold = done_of(run_stream(client, root_for(embedder, screen)))
    assert len(screen.requests) == 1
    assert (observed(cold)["cache_hits"], observed(cold)["cache_misses"], observed(cold)["model_calls"]) == (0, 20, 1)
    # Only decisions are kept: a paper that could not be assessed is never remembered.
    assert ScreeningJudgment.objects.count() == 16

    warm = done_of(run_stream(client, root_for(embedder, screen)))
    assert (observed(warm)["cache_hits"], observed(warm)["cache_misses"]) == (16, 4)
    assert block(warm)["matches"] == block(cold)["matches"] == 7
    # An unassessed paper is asked again, never remembered as a failure -- and only it is sent.
    assert len(screen.requests) == 2 and observed(warm)["model_calls"] == 1
    assert sorted(p["title"] for p in screen.requests[1]["records"]) == [
        f"Flood Study {n:02d}" for n in range(16, 20)]
    assert block(warm)["unassessed"] == 4


def test_a_warm_run_still_streams_the_pending_preview_and_every_candidate_once(
    embedder, space, reader, cached
):
    user, client = reader
    papers(embedder, space, 5)
    run_stream(client, root_for(embedder, Screener()))
    events = run_stream(client, root_for(embedder, Screener()))

    preview = next(data for name, data in events if name == "candidates_selected")
    assert {row["state"] for row in preview["candidates"]} == {"pending"}
    final = done_of(events)["listing"]["candidates"]
    assert sorted(r["record_id"] for r in final) == sorted(r["record_id"] for r in preview["candidates"])
    assert observed(done_of(events))["model_calls"] == 0


def test_one_reader_never_reuses_anothers_verdicts(embedder, space, reader, cached, client_for):
    user, client = reader
    papers(embedder, space, 3)
    other = make_user("other@cit.edu")
    first, second = Screener(), Screener()

    run_stream(client, root_for(embedder, first))
    done = done_of(run_stream(client_for(other), root_for(embedder, second)))

    assert len(second.requests) == 1, "cross-user sharing is not enabled"
    assert observed(done)["cache_hits"] == 0
    assert set(ScreeningJudgment.objects.values_list("user_id", flat=True)) == {user.pk, other.pk}


def test_listing_and_topic_count_reuse_the_same_verdicts(embedder, space, reader, cached):
    user, client = reader
    papers(embedder, space, 6)
    screen = Screener()

    listing = done_of(run_stream(client, root_for(embedder, screen), question=QUESTION,
                                 route_override="listing"))
    count = done_of(run_stream(client, root_for(embedder, screen), question=QUESTION))

    assert listing["routing"]["lane"] == "listing" and count["routing"]["lane"] == "count"
    assert len(screen.requests) == 1
    assert observed(count)["cache_hits"] == 6 and block(count)["matches"] == 6


@pytest.mark.parametrize("change", ["abstract", "chunk_set", "model", "policy", "criterion", "prompt"])
def test_a_change_to_content_model_policy_criterion_or_prompt_is_not_served_from_cache(
    embedder, space, reader, cached, settings, monkeypatch, change
):
    from apps.ai.research import listing as listing_module
    from apps.ai.research.tools import screening as screening_module

    user, client = reader
    first, *rest = papers(embedder, space, 4)
    run_stream(client, root_for(embedder, Screener()))

    question = QUESTION
    if change == "abstract":
        Record.objects.filter(pk=first.pk).update(abstract="an abstract about flooding, revised")
    elif change == "chunk_set":
        ChunkSet.objects.filter(record=first, is_active=True).update(content_hash="f" * 64)
    elif change == "model":
        settings.LLM_SCREEN_MODEL = "a-different-screening-model"
    elif change == "policy":
        settings.AI_SCREEN_CACHE_POLICY = "approved-2"
    elif change == "criterion":
        question = "How many papers are about flooding in the catchment?"
    else:
        for module in (screening_module, listing_module):
            monkeypatch.setattr(module, "SYSTEM", screening_module.SYSTEM + " Be stricter.")

    screen = Screener()
    done = done_of(run_stream(client, root_for(embedder, screen), question=question))
    expected_misses = 1 if change in ("abstract", "chunk_set") else 4
    assert observed(done)["cache_misses"] == expected_misses
    assert observed(done)["cache_hits"] == 4 - expected_misses
    assert len(screen.titles_sent) == expected_misses


def test_the_cache_stores_decisions_apart_from_source_text(embedder, space, reader, cached):
    user, client = reader
    paper, = papers(embedder, space, 1)
    run_stream(client, root_for(embedder, Screener()))

    row = ScreeningJudgment.objects.get()
    assert row.record_id == paper.pk and row.user_id == user.pk and row.state == "included"
    assert row.quote == paper.title and row.source == {"field": "title"}
    # Nothing but a decision, where it was found and the verbatim quote is held.
    stored = {field.name for field in ScreeningJudgment._meta.get_fields()}
    assert not stored & {"abstract", "title", "text", "content", "answer", "reasoning"}


# -- access is read again on reuse and on output -----------------------------------------


def test_a_paper_revoked_after_it_was_cached_is_not_counted_or_shown(embedder, space, reader, cached):
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    run_stream(client, root_for(embedder, Screener()))
    revoke(lost)

    screen = Screener()
    events = run_stream(client, root_for(embedder, screen))
    done = done_of(events)
    assert block(done)["selected"] == 1 and block(done)["matches"] == 1
    assert lost.title not in json.dumps(events) and not screen.requests
    assert observed(done)["cache_hits"] == 1


def test_a_cache_hit_does_not_override_a_gate_that_now_refuses_the_paper(embedder, space, reader, cached):
    user, client = reader
    open_paper, gated = papers(embedder, space, 2)
    run_stream(client, root_for(embedder, Screener()))

    screen = Screener()
    events = run_stream(client, root_for(embedder, screen, lambda r: r.pk != gated.pk))
    done = done_of(events)
    assert {"record_id": gated.pk, "state": "unassessed", "restricted": True} in done["listing"]["candidates"]
    assert gated.title not in json.dumps(events)
    assert (block(done)["matches"], block(done)["unassessed"], block(done)["selected"]) == (1, 1, 2)
    assert observed(done)["cache_hits"] == 1, "the refused paper is never served from cache"


def test_a_paper_revoked_while_a_warm_run_is_streaming_is_dropped(embedder, space, reader, cached):
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    run_stream(client, root_for(embedder, Screener()))

    events = []
    with use_composition_root(root_for(embedder, Screener())):
        for name, data in watch(client, QUESTION):
            events.append((name, data))
            if name == "candidates_selected":
                revoke(lost)
    done = done_of(events)
    assert [row["record_id"] for row in done["listing"]["candidates"]] == [kept.pk]
    assert block(done)["selected"] == 1 and block(done)["matches"] == 1
    assert done["listing"]["coverage"]["changed"] is True


def test_a_quote_that_no_longer_holds_is_not_served_from_cache(embedder, space, reader, cached):
    user, client = reader
    paper, = papers(embedder, space, 1)
    run_stream(client, root_for(embedder, Screener()))
    Record.objects.filter(pk=paper.pk).update(title="Renamed Flood Study 00")

    screen = Screener()
    done = done_of(run_stream(client, root_for(embedder, screen)))
    assert len(screen.requests) == 1, "the changed title is a different document"
    assert observed(done)["cache_hits"] == 0


def test_cache_hits_do_not_escape_the_twenty_distinct_record_allowance(embedder, space, reader, cached):
    user, client = reader
    papers(embedder, space, 25)
    run_stream(client, root_for(embedder, Screener()))
    done = done_of(run_stream(client, root_for(embedder, Screener())))

    assert block(done)["selected"] == 20 and observed(done)["cache_hits"] == 20
    assert ScreeningJudgment.objects.count() == 20, "only selected candidates are ever screened or kept"


# -- races --------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_writers_leave_one_verdict_per_paper_and_never_fail(embedder, space, reader):
    from apps.ai.research.screening_cache import ScreeningCache, Verdict

    user, _ = reader
    paper, = papers(embedder, space, 1)
    cache = ScreeningCache(user, criterion="flooding", model="m", policy="p")
    gate, errors = threading.Barrier(6), []

    def write(state):
        try:
            gate.wait()
            cache.remember({paper.pk: Verdict(state, "", None)}, {paper.pk: (paper.title, paper.abstract)})
        except Exception as exc:  # pragma: no cover - the failure being proved absent
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=write, args=(s,)) for s in
               ("included", "excluded", "uncertain", "included", "excluded", "uncertain")]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert not errors
    assert ScreeningJudgment.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_a_lost_insert_race_is_resolved_by_the_row_that_won(embedder, space, reader, monkeypatch):
    from apps.ai.research.screening_cache import ScreeningCache, Verdict

    user, _ = reader
    paper, = papers(embedder, space, 1)
    cache = ScreeningCache(user, criterion="flooding", model="m", policy="p")
    evidence = {paper.pk: (paper.title, paper.abstract)}
    cache.remember({paper.pk: Verdict("excluded", paper.title, {"field": "title"})}, evidence)

    real = ScreeningJudgment.objects.filter
    calls = {"n": 0}

    def blind_first_read(*args, **kwargs):
        calls["n"] += 1
        return real(pk__in=[]) if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(ScreeningJudgment.objects, "filter", blind_first_read)
    cache.remember({paper.pk: Verdict("included", paper.title, {"field": "title"})}, evidence)
    monkeypatch.undo()

    assert ScreeningJudgment.objects.get().state in ("included", "excluded")


def test_a_cache_that_cannot_be_read_or_written_never_breaks_a_count(embedder, space, reader, cached, monkeypatch):
    user, client = reader
    papers(embedder, space, 3)

    def broken(*args, **kwargs):
        raise IntegrityError("cache unavailable")

    monkeypatch.setattr("apps.ai.research.screening_cache.ScreeningCache.recall", broken)
    monkeypatch.setattr("apps.ai.research.screening_cache.ScreeningCache.remember", broken)
    done = done_of(run_stream(client, root_for(embedder, Screener())))
    assert block(done)["matches"] == 3 and observed(done)["cache_hits"] == 0


# -- what is observed, and what is not claimed ------------------------------------------


def test_observed_usage_is_reported_without_claiming_capacity(embedder, space, reader, cached):
    user, client = reader
    papers(embedder, space, 5)
    cold = observed(done_of(run_stream(client, root_for(embedder, Screener()))))
    warm = observed(done_of(run_stream(client, root_for(embedder, Screener()))))

    for seen in (cold, warm):
        assert set(seen) == {"cache_hits", "cache_misses", "model_calls", "prompt_tokens_estimated",
                             "stage_ms", "note"}
        assert set(seen["stage_ms"]) == {"select", "screen", "finish", "total"}
        assert all(isinstance(v, int) and v >= 0 for v in seen["stage_ms"].values())
        assert "does not show" in seen["note"] and "capacity" in seen["note"]
    assert cold["model_calls"] == 1 and cold["prompt_tokens_estimated"] > 0
    assert warm["model_calls"] == 0 and warm["prompt_tokens_estimated"] == 0


# -- transcript and replay ----------------------------------------------------------------


def test_a_reopened_count_forgets_a_revoked_paper_and_rewords_the_count(embedder, space, reader):
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    conversation = Conversation.objects.create(user=user)
    run_stream(client, root_for(embedder, Screener()), conversation_id=conversation.pk)

    revoke(lost)
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    topic = turn["listing"]["topic_count"]
    assert (topic["selected"], topic["matches"]) == (1, 1)
    assert lost.title not in json.dumps(turn)
    assert "1 match among 1 assessed of 1 selected candidate paper" in turn["answer"]
    assert turn["answer"] == turn["listing"]["wording"]


def test_a_reopened_count_reads_a_changed_quote_as_unassessed(embedder, space, reader):
    user, client = reader
    paper, = papers(embedder, space, 1)
    conversation = Conversation.objects.create(user=user)
    run_stream(client, root_for(embedder, Screener()), conversation_id=conversation.pk)

    Record.objects.filter(pk=paper.pk).update(title="Renamed Study")
    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    topic = turn["listing"]["topic_count"]
    assert (topic["matches"], topic["unassessed"], topic["assessed"]) == (0, 1, 0)
    assert turn["listing"]["completeness"] == "inconclusive"


def test_a_queued_count_journals_its_candidates_and_replay_rechecks_access(
    embedder, space, reader, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    monkeypatch.setattr(answer_queued_question, "apply_async", lambda args, **limits: None)
    user, client = reader
    kept, lost = papers(embedder, space, 2)
    conversation = Conversation.objects.create(user=user)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("ai-ask-stream"),
                               {"question": QUESTION, "conversation_id": conversation.pk}, format="json")
    first = next(iter(response.streaming_content))
    response._iterator.close()
    run_id = _frames([first])[0][2]["run_id"]
    with use_composition_root(root_for(embedder, Screener())):
        answer_queued_question(run_id)

    def replay():
        return _frames(client.get(reverse("ai-ask-run-stream", args=[run_id])).streaming_content)

    frames = replay()
    names = [name for _, name, _ in frames]
    assert names.index("candidates_selected") < names.index("candidates_updated") < names.index("done")
    assert frames[-1][2]["listing"]["topic_count"]["matches"] == 2

    revoke(lost)
    again = replay()
    assert lost.title not in json.dumps(again)
    final = again[-1][2]["listing"]
    assert final["topic_count"]["matches"] == 1 and final["topic_count"]["selected"] == 1
    assert final["wording"].startswith("1 match among 1 assessed of 1 selected candidate paper")
