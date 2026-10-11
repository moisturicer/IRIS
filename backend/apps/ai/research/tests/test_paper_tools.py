"""The paper-level tools (IR-510, ADR-038 §2, §6; ADR-027 §1b, §1d, §3)."""

import pytest
from django.core.management import call_command

from apps.ai.composition import use_composition_root
from apps.ai.models.chunk import ChunkSet, DocumentChunk
from apps.ai.models.conversation import Conversation
from apps.ai.research.results import Completeness, ToolStatus
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.records.models import RecordOwner, RecordVersion
from core.enums import PipelineStatus, VersionCause
from core.permissions import ROLE_KTTO

from .helpers import TOOLS, TOPIC, call, record_ids, root, sent_to_planner, start_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def landscape(settings):
    settings.AI_LANDSCAPE_MIN_RECORDS = 1
    settings.AI_LANDSCAPE_MAX_UNCLASSIFIED_SHARE = 1.0


def _handle(run, record):
    found = call(run, "find_records", topic=TOPIC)
    return next(e.handle for e in found.evidence if e.record_id == record.pk)


def test_the_closed_set_is_the_six_corpus_tools():
    assert set(TOOLS.names) == {
        "search_passages", "find_records", "read_record_sections",
        "count_records", "corpus_facets", "screen_records",
    }


# -- find_records ---------------------------------------------------------


def test_find_records_never_returns_an_unreadable_paper(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    for topic in (TOPIC, "Secret flood draft"):
        result = call(run, "find_records", topic=topic)
        assert corpus["draft"].pk not in record_ids(result)
        assert "Secret" not in result.planner_message()


def test_the_owner_and_office_staff_find_the_draft(corpus, embedder):
    for user in (corpus["other"], make_user("ktto@cit.edu", ROLE_KTTO)):
        found = call(start_run(user, root(embedder)), "find_records", topic=TOPIC)
        assert corpus["draft"].pk in record_ids(found)


def test_find_records_reports_matches_found_and_why(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    result = call(run, "find_records", topic=TOPIC)
    assert result.coverage.label is Completeness.MATCHES_FOUND
    flood = run.ledger.records()[0]
    assert flood.record_id == corpus["public"].pk
    facts = result.annotations[flood.handle]
    assert set(facts["matched_by"]) == {"vector", "keyword", "passage"}
    assert (facts["year"], facts["area"]) == (2021, "Engineering")


def test_find_records_filters_and_rejects_an_unknown_filter_value(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    filtered = call(run, "find_records", topic=TOPIC, classification="engineering")
    assert record_ids(filtered) == {corpus["public"].pk}
    assert call(run, "find_records", topic=TOPIC, year_from=2022).evidence == ()
    assert call(run, "find_records", topic=TOPIC, classification="Nope").status \
        is ToolStatus.REJECTED


def test_every_metadata_filter_narrows(corpus, embedder):
    from apps.records.models import PSCEDClassification, RecordType

    public = corpus["public"]
    public.psced = PSCEDClassification.objects.get_or_create(name="Engineering and technology")[0]
    public.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
    public.is_ip = True
    public.save()
    run = start_run(corpus["student"], root(embedder))

    for filters in ({"psced": "engineering and technology"},
                    {"record_type": "thesis / research"}, {"year_to": 2021}):
        assert record_ids(call(run, "find_records", topic=TOPIC, **filters)) == {public.pk}
        assert call(run, "count_records", **filters).detail["total"] == 1
    assert call(run, "count_records", is_ip=True).detail["total"] == 1
    assert call(run, "count_records", is_ip=False).detail["total"] == 1
    assert call(run, "count_records", group_by="psced").detail["groups"] == [
        {"value": "Engineering and technology", "count": 1}]
    assert call(run, "count_records", record_type="Nope").status is ToolStatus.REJECTED


def test_a_filter_matching_nothing_recalls_nothing(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    result = call(run, "find_records", topic=TOPIC, year_from=2030)
    assert result.evidence == () and result.status is ToolStatus.EMPTY


def test_passage_hits_must_clear_the_relevance_cut_off(corpus, embedder, settings):
    pond = corpus["pond"].pk

    def matched_by_passage(result):
        return {e.record_id for e in result.evidence
                if "passage" in result.annotations[e.handle]["matched_by"]}

    run = start_run(corpus["student"], root(embedder))
    assert pond in matched_by_passage(call(run, "find_records", topic=TOPIC))

    # IR-396 adds the setting; the tool honours it as soon as it exists.
    settings.AI_RELEVANCE_MIN_SCORE = 0.5
    run = start_run(corpus["student"], root(embedder))
    assert matched_by_passage(call(run, "find_records", topic=TOPIC)) == {corpus["public"].pk}


def test_find_records_leaves_no_gap_for_a_withheld_paper(corpus, embedder):
    refuse = corpus["public"].pk
    gated = call(start_run(corpus["student"], root(embedder, lambda r: r.pk != refuse)),
                 "find_records", topic=TOPIC, k=1)
    corpus["public"].delete()
    absent = call(start_run(corpus["student"], root(embedder)), "find_records", topic=TOPIC, k=1)
    assert (gated.status, gated.coverage) == (absent.status, absent.coverage)
    assert record_ids(gated) == record_ids(absent) == {corpus["pond"].pk}


# -- the gate on planner-bound text ----------------------------------------


def test_titles_abstracts_and_sections_pass_the_gate_first(corpus, embedder):
    withheld = corpus["public"]
    run = start_run(corpus["student"], root(embedder, lambda r: r.pk != withheld.pk))
    found = call(run, "find_records", topic=TOPIC)
    # A handle issued before the gate changed still reads nothing.
    stale = run.ledger.add_record(record_id=withheld.pk, title="x", abstract="")
    read = call(run, "read_record_sections", record=stale.handle)

    sent = sent_to_planner(found, read)
    assert "Flood forecasting" not in sent and FLOOD_TEXT not in sent
    assert "An abstract for Flood forecasting." not in sent
    assert "An abstract for Tilapia ponds." in sent
    assert read.evidence == ()


# -- read_record_sections -------------------------------------------------


def _add_results_section(record):
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    for sequence in (1, 2):
        DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=sequence, max_sequence=2,
            text="results " * 15, content="results " * 15,
            context_path=[record.title, "Results"], token_count=15,
            text_hash=f"r{sequence}", source_page=5, element_kinds=["paragraph"],
        )


def test_a_read_follows_sections_and_pages_and_reports_truncation(corpus, embedder, settings):
    settings.AI_RESEARCH_READ_TOKEN_CAP = 20
    _add_results_section(corpus["public"])
    run = start_run(corpus["student"], root(embedder))
    handle = _handle(run, corpus["public"])

    whole = call(run, "read_record_sections", record=handle)
    assert whole.coverage.truncated and whole.coverage.label is Completeness.SAMPLE
    assert whole.detail["headings"] == ["Methods", "Results"]

    methods = call(run, "read_record_sections", record=handle, sections=["methods"])
    assert methods.coverage.label is Completeness.EXHAUSTIVE
    assert [e.context_path[-1] for e in methods.evidence if e.kind == "passage"] == ["Methods"]

    page = call(run, "read_record_sections", record=handle, pages=[4])
    assert [e.page for e in page.evidence if e.kind == "passage"] == [4]

    assert call(run, "read_record_sections", record=handle, sections=["Appendix"]).status \
        is ToolStatus.REJECTED


@pytest.mark.parametrize("handle", ["R9", "E1", "R0"])
def test_a_read_rejects_a_handle_the_run_did_not_issue(corpus, embedder, handle):
    run = start_run(corpus["student"], root(embedder))
    call(run, "find_records", topic=TOPIC)
    assert call(run, "read_record_sections", record=handle).status is ToolStatus.REJECTED


def test_a_read_rejects_a_raw_database_id(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    call(run, "find_records", topic=TOPIC)
    pk = corpus["public"].pk
    assert call(run, "read_record_sections", record=str(pk)).status is ToolStatus.REJECTED
    assert TOOLS.call(run, "read_record_sections", {"record": pk}).status is ToolStatus.REJECTED


# -- count_records and corpus_facets --------------------------------------


def test_counts_are_relative_to_the_asker(corpus, embedder):
    student = start_run(corpus["student"], root(embedder))
    office = start_run(make_user("ktto@cit.edu", ROLE_KTTO), root(embedder))

    counted = call(student, "count_records")
    assert counted.detail == {"total": 2, "relative_to": "of the records you can see"}
    assert counted.coverage.label is Completeness.EXHAUSTIVE
    assert call(office, "count_records").detail["total"] == 3
    assert call(student, "count_records", classification="engineering").detail["total"] == 1

    grouped = call(student, "count_records", group_by="classification").detail
    assert grouped["groups"] == [{"value": "Engineering", "count": 1}]
    assert grouped["unclassified"] == 1


def test_a_paper_counts_once_whatever_its_owners_versions_and_chunks(corpus, embedder, space):
    student = corpus["student"]
    shared = make_record(title="Shared draft", text="a b c", embedder=embedder, space=space,
                         status=PipelineStatus.DRAFT, owner=student)
    RecordOwner.objects.create(record=shared, user=corpus["other"])
    for number, cause in ((1, VersionCause.SUBMISSION), (2, VersionCause.REVISION)):
        RecordVersion.objects.create(record=shared, number=number, cause=cause)
    _add_results_section(shared)

    run = start_run(student, root(embedder))
    assert call(run, "count_records").detail["total"] == 3
    assert call(run, "count_records", group_by="year").detail["undated"] == 2


def test_an_aggregate_reveals_nothing_about_a_paper_the_asker_cannot_see(corpus, embedder):
    queries = (
        ("count_records", {}),
        ("count_records", {"group_by": "classification"}),
        ("count_records", {"classification": "Engineering"}),
        ("corpus_facets", {"dimension": "classification"}),
    )

    def answers():
        run = start_run(corpus["student"], root(embedder))
        return [call(run, name, **args) for name, args in queries]

    with_draft = answers()
    corpus["draft"].delete()
    without_draft = answers()
    for a, b in zip(with_draft, without_draft):
        assert (a.status, a.coverage, a.detail) == (b.status, b.coverage, b.detail)


def test_facets_count_areas_over_time(corpus, embedder):
    result = call(start_run(corpus["student"], root(embedder)), "corpus_facets",
                  dimension="classification")
    assert result.coverage.label is Completeness.EXHAUSTIVE
    assert result.detail["areas"] == [
        {"value": "Engineering", "count": 1, "by_year": [{"year": 2021, "count": 1}]}
    ]
    assert (result.detail["sample_size"], result.detail["unclassified"]) == (2, 1)
    assert result.detail["unclassified_share"] == 0.5


def test_facets_refuse_below_the_floor(corpus, embedder, settings):
    settings.AI_LANDSCAPE_MIN_RECORDS = 50
    result = call(start_run(corpus["student"], root(embedder)), "corpus_facets",
                  dimension="classification")
    assert (result.status, result.coverage.note) == (ToolStatus.REFUSED, "below_floor")
    assert "areas" not in result.detail


def test_facets_refuse_above_the_unclassified_share(corpus, embedder, settings):
    settings.AI_LANDSCAPE_MAX_UNCLASSIFIED_SHARE = 0.4
    result = call(start_run(corpus["student"], root(embedder)), "corpus_facets",
                  dimension="classification")
    assert (result.status, result.coverage.note) == (ToolStatus.REFUSED, "unclassified_share")
    assert result.detail["unclassified_share"] == 0.5 and "areas" not in result.detail


# -- Paper Chat scope -----------------------------------------------------


def test_paper_chat_scope_holds_for_every_paper_tool(corpus, embedder):
    student, public, pond = corpus["student"], corpus["public"], corpus["pond"]
    chat = Conversation.objects.create(user=student, record=pond)
    run = start_run(student, root(embedder), conversation=chat)
    other = run.ledger.add_record(record_id=public.pk, title=public.title, abstract="")

    assert record_ids(call(run, "find_records", topic=TOPIC)) <= {pond.pk}
    assert call(run, "read_record_sections", record=other.handle).evidence == ()
    assert call(run, "count_records").detail["total"] == 1
    assert call(run, "corpus_facets", dimension="psced").detail["sample_size"] == 1


# -- the command ----------------------------------------------------------


def test_the_command_chains_calls_in_one_run(corpus, embedder, capsys):
    with use_composition_root(root(embedder)):
        call_command(
            "run_research_tool", "--user", "student@cit.edu",
            "--call", f'find_records={{"topic": "{TOPIC}"}}',
            "--call", 'read_record_sections={"record": "R1"}',
            "--call", 'count_records={"group_by": "year"}',
            "--call", 'corpus_facets={"dimension": "classification"}',
        )
    out = capsys.readouterr().out
    assert out.count("== ") == 4
    assert '"label": "matches_found"' in out and '"label": "exhaustive"' in out
    assert '"rejected"' not in out and FLOOD_TEXT in out
