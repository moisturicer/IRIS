"""The registry's evidence-only contract (IR-590, general-tools spec §3.1, §3.3)."""

import json
import re

import pytest

from apps.ai.models.chunk import ChunkSet
from apps.ai.research.ledger import HandleRejected
from apps.ai.research.registry import ToolRun, reissue
from apps.ai.research.results import CoverageSubject, Status

from .helpers import TOOLS, TOPIC, call, root, scalars, start_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def landscape(settings):
    settings.AI_LANDSCAPE_MIN_RECORDS = 1
    settings.AI_LANDSCAPE_MAX_UNCLASSIFIED_SHARE = 1.0


def scoped(user, stack, **limits):
    return ToolRun.start(start_run(user, stack, **limits).ctx, stack, scoped_handles=True)


def invoke(run, name, **arguments):
    return TOOLS.invoke(run, name, json.dumps(arguments))


def test_every_tool_names_what_its_coverage_is_about():
    subjects = {name: TOOLS.subject(name) for name in TOOLS.names}
    assert CoverageSubject.NONE not in subjects.values()
    assert subjects["count_records"] is CoverageSubject.METADATA_POPULATION
    assert subjects["screen_records"] is CoverageSubject.SCREENED_SUBSET
    assert subjects["read_record_sections"] is CoverageSubject.REQUESTED_SELECTION
    assert subjects["search_passages"] is CoverageSubject.SEARCH_CANDIDATES


def test_a_search_envelope_carries_handles_never_ids_or_hidden_records(corpus, embedder):
    run = scoped(corpus["student"], root(embedder))
    public = invoke(run, "find_records", topic=TOPIC).public()
    assert public["status"] == "ok"
    assert public["coverage"]["subject"] == "search_candidates"
    assert public["coverage"]["total"] is None and not public["coverage"]["complete"]
    assert all(re.fullmatch(r"R\d+-[0-9a-f]{6}", item["record"]) for item in public["items"])
    text = json.dumps(public)
    assert "Secret flood draft" not in text
    ids = {corpus[name].pk for name in ("public", "draft", "pond")}
    content = {"items": public["items"], "evidence": public["evidence"]}
    assert not ids & ({v for v in scalars(content) if isinstance(v, int)} - {2021})


@pytest.mark.parametrize("name, arguments, status, code", [
    ("find_records", {"topic": "x", "user": 1}, "unavailable", "invalid_arguments"),
    ("find_records", {"topic": "x" * 301}, "unavailable", "invalid_arguments"),
    ("drop_table", {}, "unavailable", "unknown_tool"),
    ("read_record_sections", {"record": "R1"}, "denied", "invalid_reference"),
    ("read_record_sections", {"record": "R1-ffffff"}, "denied", "invalid_reference"),
])
def test_malformed_and_unissued_calls_fail_predictably(corpus, embedder, name, arguments,
                                                       status, code):
    run = scoped(corpus["student"], root(embedder))
    envelope = invoke(run, name, **arguments)
    assert envelope.public() == {
        "schema_version": "1", "status": status, "items": [], "evidence": [], "facts": [],
        "coverage": {"subject": envelope.coverage.subject.value, "returned": 0,
                     "total": None, "complete": False},
        "continuation": None, "limitations": [code],
    }


def test_another_runs_handle_is_rejected_even_for_the_same_reader(corpus, embedder):
    stack = root(embedder)
    first = scoped(corpus["student"], stack)
    [handle, *_] = [i["record"] for i in invoke(first, "find_records", topic=TOPIC).public()["items"]]
    for other in (scoped(corpus["student"], stack), scoped(corpus["other"], stack)):
        invoke(other, "find_records", topic=TOPIC)
        envelope = invoke(other, "read_record_sections", record=handle)
        assert envelope.status is Status.DENIED
        assert envelope.limitations == ("invalid_reference",)


def test_reissue_validates_canonical_references_and_drops_the_rest_silently(corpus, embedder):
    blocked = set()
    stack = root(embedder, permits=lambda record: record.pk not in blocked)
    run = scoped(corpus["student"], stack)
    blocked.add(corpus["pond"].pk)
    handles = reissue(run, [corpus["draft"].pk, corpus["public"].pk, corpus["pond"].pk,
                            corpus["public"].pk])
    assert len(handles) == 1
    assert run.ledger.record_id(handles[0]) == corpus["public"].pk
    assert invoke(run, "read_record_sections", record=handles[0]).status is Status.OK


def test_a_metadata_count_is_an_exact_population_with_its_predicate(corpus, embedder):
    run = scoped(corpus["student"], root(embedder))
    public = invoke(run, "count_records", year_from=2020).public()
    assert public["coverage"] == {"subject": "metadata_population", "returned": 1,
                                  "total": 1, "complete": True}
    total = next(f for f in public["facts"] if f["name"] == "total")
    assert total["value"] == 1
    assert total["provenance"]["predicate"] == {"year_from": 2020}


def test_a_floor_refusal_is_unavailable_without_counts(corpus, embedder, settings):
    settings.AI_LANDSCAPE_MIN_RECORDS = 50
    envelope = invoke(scoped(corpus["student"], root(embedder)), "corpus_facets",
                      dimension="classification")
    assert envelope.status is Status.UNAVAILABLE and envelope.limitations == ("below_floor",)
    assert not envelope.facts and envelope.coverage.total is None


def test_an_exhausted_budget_is_unavailable(corpus, embedder):
    run = scoped(corpus["student"], root(embedder), max_tool_calls=1)
    invoke(run, "count_records")
    envelope = invoke(run, "count_records")
    assert (envelope.status, envelope.limitations) == (Status.UNAVAILABLE, ("budget_exhausted",))


# -- cached results are reauthorized before reuse ---------------------------


def test_a_repeat_call_reuses_a_still_current_result(corpus, embedder):
    run = scoped(corpus["student"], root(embedder))
    invoke(run, "search_passages", query=TOPIC)
    again = invoke(run, "search_passages", query=TOPIC)
    assert again.trace.duplicate and not again.trace.recomputed


def test_a_cached_result_whose_record_was_withheld_is_recomputed(corpus, embedder):
    blocked = set()
    run = scoped(corpus["student"], root(embedder, permits=lambda r: r.pk not in blocked))
    first = invoke(run, "search_passages", query=TOPIC)
    assert "Flood forecasting" in json.dumps(first.public())
    blocked.add(corpus["public"].pk)
    again = invoke(run, "search_passages", query=TOPIC)
    assert again.trace.recomputed and not again.trace.duplicate
    assert "Flood forecasting" not in json.dumps(again.public())


def test_the_legacy_call_reauthorizes_a_cached_result_too(corpus, embedder):
    blocked = set()
    run = start_run(corpus["student"], root(embedder, permits=lambda r: r.pk not in blocked))
    call(run, "search_passages", query=TOPIC)
    blocked.add(corpus["public"].pk)
    again = call(run, "search_passages", query=TOPIC)
    assert not again.duplicate
    assert corpus["public"].pk not in {e.record_id for e in again.evidence}


def test_a_cached_passage_from_a_replaced_chunk_set_is_recomputed(corpus, embedder):
    run = scoped(corpus["student"], root(embedder))
    invoke(run, "search_passages", query=TOPIC)
    ChunkSet.objects.filter(record=corpus["public"]).update(content_hash="b" * 64)
    again = invoke(run, "search_passages", query=TOPIC)
    assert again.trace.recomputed
    versions = {e["source_version"] for e in again.public()["evidence"]
                if e["content_kind"] == "passage"}
    assert "b" * 12 in versions


# -- cursors are bound to query, caller and source version --------------------


def test_a_cursor_resumes_only_the_call_it_was_issued_for(corpus, embedder):
    run = scoped(corpus["student"], root(embedder))
    args = {"record": "R1", "sections": ["Results"]}
    token = run.issue_cursor("read_record_sections", args, source_version="v1", position=7)
    assert run.resume_cursor(token, "read_record_sections", {**args, "cursor": token},
                             source_version="v1") == 7
    with pytest.raises(HandleRejected, match="cursor_mismatch"):
        run.resume_cursor(token, "read_record_sections", {**args, "sections": ["Methods"]},
                          source_version="v1")
    with pytest.raises(HandleRejected, match="stale_cursor"):
        run.resume_cursor(token, "read_record_sections", args, source_version="v2")
    other = scoped(corpus["other"], root(embedder))
    with pytest.raises(HandleRejected):
        other.resume_cursor(token, "read_record_sections", args, source_version="v1")
