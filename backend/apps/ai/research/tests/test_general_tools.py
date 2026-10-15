"""The general research tools: resolve, search, aggregate (IR-591, spec §3.2).

Acceptance scenarios A04 and A06 at the registry boundary, with fakes.
"""

import json
from dataclasses import replace

import pytest

from apps.ai.models.conversation import Conversation
from apps.ai.research.context import Budget, RunContext
from apps.ai.research.registry import Presentation, ToolRun, general_tools
from apps.ai.research.results import Status
from apps.ai.tests.corpus import FLOOD_TEXT, POND_TEXT, make_record
from core.enums import PipelineStatus

from .helpers import root, scalars

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

TOOLS = general_tools()


def general_run(user, stack, conversation=None, presented=None, **limits):
    limits = {"max_calls_per_subtask": 100, "max_tool_calls": 100, **limits}
    ctx = RunContext.for_request(
        user=user, root=stack, lane="research", conversation=conversation,
        budget=replace(Budget.from_settings(), **limits),
    )
    return replace(ToolRun.start(ctx, stack, scoped_handles=True), presented=presented)


def invoke(run, name, **arguments):
    return TOOLS.invoke(run, name, json.dumps(arguments))


def payload(envelope):
    return json.dumps(envelope.public(), ensure_ascii=False)


@pytest.fixture
def mesh(corpus, embedder, space):
    """Two papers sharing a short name, for alias ambiguity."""
    caching = make_record(title="MeshKV: Caching attention for long contexts",
                          text=FLOOD_TEXT, embedder=embedder, space=space)
    routing = make_record(title="MeshKV: Routing keys across devices",
                          text=POND_TEXT, embedder=embedder, space=space)
    return {**corpus, "caching": caching, "routing": routing}


# -- the registry -----------------------------------------------------------


def test_the_general_set_is_the_five_spec_tools():
    assert TOOLS.names == ("resolve_papers", "search_research", "read_papers",
                           "aggregate_records", "extract_evidence")
    for definition in TOOLS.definitions():
        assert definition.parameters["additionalProperties"] is False


def test_unknown_fields_and_another_runs_handle_fail_predictably(corpus, embedder):
    stack = root(embedder)
    first = general_run(corpus["student"], stack)
    handle = invoke(first, "resolve_papers", references=["Flood forecasting"]).items[0]["record"]

    unknown = invoke(general_run(corpus["student"], stack), "search_research",
                     query="flood", target="papers", user=1)
    assert (unknown.status, unknown.limitations) == (Status.UNAVAILABLE, ("invalid_arguments",))
    foreign = invoke(general_run(corpus["student"], stack), "read_papers",
                     records=[handle], view="outline")
    assert (foreign.status, foreign.limitations) == (Status.DENIED, ("invalid_reference",))


# -- resolve_papers (A04) ---------------------------------------------------


def test_an_exact_title_resolves_on_the_fast_path(corpus, embedder):
    result = invoke(general_run(corpus["student"], root(embedder)), "resolve_papers",
                    references=["  flood FORECASTING. "])
    assert result.status is Status.OK
    assert result.items[0]["match"] == "exact_title"
    assert result.items[0]["title"] == "Flood forecasting"
    assert result.coverage.complete and result.coverage.total == 1


def test_an_alias_is_an_ambiguity_group_beside_a_clear_title_and_an_unknown(mesh, embedder):
    run = general_run(mesh["student"], root(embedder))
    result = invoke(run, "resolve_papers", topic="attention caching",
                    references=["MeshKV", "Tilapia ponds", "Nonexistent paper"])
    assert result.status is Status.AMBIGUOUS
    alias, clear, unknown = result.items
    assert alias["match"] == "ambiguous" and alias["basis"] == "short_title"
    # The topic hint orders candidates; neither is chosen silently.
    assert [c["title"] for c in alias["candidates"]] == [
        "MeshKV: Caching attention for long contexts", "MeshKV: Routing keys across devices"]
    assert "record" not in alias
    assert clear["match"] == "exact_title" and clear["title"] == "Tilapia ponds"
    assert unknown == {"reference": 3, "kind": "title", "match": "none"}
    assert not result.coverage.complete


def test_a_hidden_or_withheld_paper_looks_exactly_like_an_unknown_one(corpus, embedder):
    stack = root(embedder, permits=lambda r: r.title != "Tilapia ponds")
    run = general_run(corpus["student"], stack)
    result = invoke(run, "resolve_papers",
                    references=["Secret flood draft", "Tilapia ponds", "No such paper"])
    assert result.status is Status.EMPTY
    assert [{k: v for k, v in item.items() if k != "reference"} for item in result.items] \
        == [{"kind": "title", "match": "none"}] * 3
    assert "Secret" not in payload(result) and "Tilapia" not in payload(result)


def test_duplicate_titles_are_ambiguous_not_merged(corpus, embedder, space):
    make_record(title="Flood forecasting", text=POND_TEXT, embedder=embedder, space=space)
    result = invoke(general_run(corpus["student"], root(embedder)), "resolve_papers",
                    references=["Flood forecasting"])
    assert result.status is Status.AMBIGUOUS
    assert len({c["record"] for c in result.items[0]["candidates"]}) == 2


def test_ordinals_resolve_only_against_the_presented_list(corpus, embedder):
    stack = root(embedder)
    shown = Presentation(revision=3, record_ids=(corpus["pond"].pk, corpus["draft"].pk,
                                                  corpus["public"].pk))
    result = invoke(general_run(corpus["student"], stack, presented=shown),
                    "resolve_papers", ordinals=[1, 2, 3, 4])
    first, hidden, third, beyond = result.items
    assert (first["match"], first["title"]) == ("presented_order", "Tilapia ponds")
    assert third["title"] == "Flood forecasting"
    # A presented paper no longer readable, or one never shown, resolves to nothing.
    assert hidden["match"] == beyond["match"] == "none"
    assert result.status is Status.PARTIAL

    none = invoke(general_run(corpus["student"], stack), "resolve_papers", ordinals=[1])
    assert none.items[0]["match"] == "none"
    assert none.limitations == ("no_presented_list",)


def test_resolution_needs_a_reference(corpus, embedder):
    result = invoke(general_run(corpus["student"], root(embedder)), "resolve_papers",
                    topic="flooding")
    assert result.status is Status.UNAVAILABLE


# -- search_research --------------------------------------------------------


def test_discovery_needs_no_titles_and_is_never_exhaustive(mesh, embedder):
    result = invoke(general_run(mesh["student"], root(embedder)), "search_research",
                    query="neural network rainfall flooding", target="papers")
    assert result.status is Status.OK and result.items
    assert "non_exhaustive" in result.limitations
    assert result.coverage.total is None and result.coverage.complete is False
    assert mesh["draft"].title not in payload(result)


def test_an_exactly_named_paper_leads_apart_from_related_candidates(mesh, embedder):
    result = invoke(general_run(mesh["student"], root(embedder)), "search_research",
                    query="Tilapia ponds", target="papers")
    assert result.items[0]["title"] == "Tilapia ponds"
    assert result.items[0]["match_kind"] == "exact_title"
    assert {i["match_kind"] for i in result.items[1:]} <= {"related"}


def test_passage_search_honours_issued_records_and_real_metadata_filters(corpus, embedder):
    run = general_run(corpus["student"], root(embedder))
    pond = invoke(run, "resolve_papers", references=["Tilapia ponds"]).items[0]["record"]
    scoped = invoke(run, "search_research", query="flooding rainfall", target="passages",
                    records=[pond])
    assert {e["record"] for e in scoped.public()["evidence"]} == {pond}

    dated = invoke(run, "search_research", query="flooding rainfall", target="passages",
                   year_from=2021, year_to=2021)
    assert {e["text"] for e in dated.evidence if e["content_kind"] == "passage"} == {FLOOD_TEXT}
    assert invoke(run, "search_research", query="flooding", target="passages",
                  year_from=2030).status is Status.EMPTY


def test_paper_chat_scope_cannot_be_widened_by_search(corpus, embedder):
    chat = Conversation.objects.create(user=corpus["student"], record=corpus["pond"])
    result = invoke(general_run(corpus["student"], root(embedder), conversation=chat),
                    "search_research", query="rainfall flooding", target="papers")
    assert [i["title"] for i in result.items] == ["Tilapia ponds"]


def test_a_continuation_pages_the_same_ranking_and_is_bound_to_its_query(mesh, embedder):
    run = general_run(mesh["student"], root(embedder))
    first = invoke(run, "search_research", query="neural network rainfall", target="papers",
                   limit=1)
    assert first.continuation is not None
    second = invoke(run, "search_research", query="neural network rainfall", target="papers",
                    limit=1, cursor=first.continuation)
    assert second.items[0]["rank"] == 2
    assert second.items[0]["record"] != first.items[0]["record"]

    other = invoke(run, "search_research", query="tilapia", target="papers", limit=1,
                   cursor=first.continuation)
    assert other.status is Status.DENIED
    foreign = invoke(general_run(mesh["student"], root(embedder)), "search_research",
                     query="neural network rainfall", target="papers", limit=1,
                     cursor=first.continuation)
    assert foreign.status is Status.DENIED


def test_a_visibility_change_makes_a_continuation_stale(corpus, embedder):
    run = general_run(corpus["student"], root(embedder))
    first = invoke(run, "search_research", query="rainfall flooding", target="papers", limit=1)
    corpus["pond"].pipeline_status = PipelineStatus.DRAFT
    corpus["pond"].save()
    stale = invoke(run, "search_research", query="rainfall flooding", target="papers",
                   limit=1, cursor=first.continuation)
    assert (stale.status, stale.limitations) == (Status.UNAVAILABLE, ("stale_continuation",))


# -- aggregate_records (A06) ------------------------------------------------


def test_a_metadata_count_is_exact_over_distinct_visible_records(corpus, embedder):
    result = invoke(general_run(corpus["student"], root(embedder)), "aggregate_records",
                    operation="count", classification="Engineering")
    facts = {f["name"]: f for f in result.facts}
    assert facts["total"]["value"] == 1
    provenance = facts["total"]["provenance"]
    assert provenance["kind"] == "metadata"
    assert provenance["predicate"] == {"operation": "count", "classification": "Engineering"}
    assert provenance["population"] == "records_visible_to_reader"
    assert result.coverage.subject.value == "metadata_population" and result.coverage.complete
    # How many Ask IRIS could read is its own fact, not the count.
    assert facts["ai_readable"]["value"] == 1


def test_ai_readability_is_reported_apart_from_the_count(corpus, embedder):
    stack = root(embedder, permits=lambda r: r.title != "Tilapia ponds")
    result = invoke(general_run(corpus["student"], stack), "aggregate_records",
                    operation="count")
    facts = {f["name"]: f["value"] for f in result.facts}
    assert (facts["total"], facts["ai_readable"]) == (2, 1)


def test_there_is_no_topic_count_and_facets_take_no_filters(corpus, embedder, settings):
    settings.AI_LANDSCAPE_MIN_RECORDS = 1
    settings.AI_LANDSCAPE_MAX_UNCLASSIFIED_SHARE = 1.0
    run = general_run(corpus["student"], root(embedder))
    assert invoke(run, "aggregate_records", operation="count",
                  topic="flooding").status is Status.UNAVAILABLE
    assert invoke(run, "aggregate_records", operation="facets", dimension="classification",
                  year_from=2020).status is Status.UNAVAILABLE
    facets = invoke(run, "aggregate_records", operation="facets", dimension="classification")
    assert facets.status is Status.OK


def test_no_tool_result_carries_reader_prose_or_raw_ids(mesh, embedder):
    run = general_run(mesh["student"], root(embedder))
    envelopes = [
        invoke(run, "resolve_papers", references=["MeshKV", "Flood forecasting"]),
        invoke(run, "search_research", query="rainfall", target="passages"),
        invoke(run, "aggregate_records", operation="count", group_by="year"),
    ]
    for envelope in envelopes:
        public = envelope.public()
        assert set(public) == {"schema_version", "status", "items", "evidence", "facts",
                               "coverage", "continuation", "limitations"}
        handles = {str(v) for v in scalars(public["items"])
                   if isinstance(v, str) and v.startswith("R")}
        assert all("-" in h for h in handles)
        assert mesh["draft"].title not in payload(envelope)


def test_the_authenticated_command_runs_the_general_tools_as_its_user(corpus, embedder):
    from io import StringIO

    from django.core.management import call_command

    from apps.ai.composition import use_composition_root

    out = StringIO()
    with use_composition_root(root(embedder)):
        call_command("run_research_tool", "--user", "student@cit.edu", "--general",
                     "--call", 'resolve_papers={"references": ["Secret flood draft"]}',
                     "--call", 'aggregate_records={"operation": "count"}', stdout=out)
    printed = out.getvalue()
    assert '"match": "none"' in printed and "Secret" not in printed.split("\n", 1)[1]
    assert '"value": 2' in printed
