"""The general research tools: read and extract (IR-591, spec §3.2).

Acceptance scenarios A05 and A07 at the registry boundary, with fakes.
"""

import json

import pytest

from apps.ai.briefs.reading import FIELDS, PROMPT_VERSION
from apps.ai.briefs.service import _profile_hash
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask, profile_for
from apps.ai.models import ChunkSet, DocumentChunk, PaperBrief
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.providers.ports import LLMProvider
from apps.ai.research.results import Status
from apps.ai.research.tools.read import section_id
from apps.records.models import Record
from core.enums import PipelineStatus

from .test_general_tools import general_run, invoke, payload

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SECTIONS = ("Introduction", "Related work", "Method", "Experiments", "Results", "Discussion")


@pytest.fixture(autouse=True)
def model_settings(settings):
    settings.LLM_ANSWER_MODEL = "cheap"
    settings.LLM_ANSWER_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "local-fake"
    settings.LLM_ANSWER_FALLBACK_MODELS = ""
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192}'
    settings.LLM_ANSWER_PROVIDER_PINS = ""
    settings.LLM_ANSWER_PROVIDER_ONLY = ""


def long_paper(title="Long survey", version="v1", record=None):
    """Two chunks per section, one page per chunk, sixty words each."""
    record = record or Record.objects.create(
        title=title, abstract="About long papers.", pipeline_status=PipelineStatus.PUBLISHED)
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash=f"e-{version}", strategy_id="s", options={},
        content_hash=f"{title}-{version}", is_active=True)
    for index in range(len(SECTIONS) * 2):
        heading = SECTIONS[index // 2]
        text = f"{heading} part {index}: " + " ".join(["word"] * 60)
        if heading == "Results":
            text += " Accuracy was 91.4% on CIFAR-10."
        DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=index, max_sequence=index,
            text=text, content=text, context_path=[title, heading],
            token_count=len(text.split()), text_hash=f"t-{version}-{index}",
            source_page=index + 1)
    return record


def read_run(corpus, embedder, llm=None, permits=lambda r: True, **limits):
    # A fake is always injected, so no test can reach a configured vendor.
    stack = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                            llm=llm or Extractor({}, failure=True), permits=permits)
    return general_run(corpus["student"], stack, **limits), stack


def resolve(run, title):
    return invoke(run, "resolve_papers", references=[title]).items[0]["record"]


# -- read_papers (A05) ------------------------------------------------------


def test_an_outline_lists_actual_section_identifiers_and_pages(corpus, embedder):
    long_paper()
    run, _ = read_run(corpus, embedder)
    result = invoke(run, "read_papers", records=[resolve(run, "Long survey")], view="outline")
    sections = result.items[0]["sections"]
    assert [s["heading"] for s in sections] == list(SECTIONS)
    assert sections[4] == {"section": section_id(("Results",)), "heading": "Results",
                           "level": 1, "first_page": 9, "last_page": 10}
    assert result.items[0]["pages"] == [1, 12]
    assert result.evidence[0]["content_kind"] == "abstract"


def test_a_late_section_is_read_directly_not_after_the_prefix(corpus, embedder):
    long_paper()
    run, _ = read_run(corpus, embedder, read_token_cap=70)
    handle = resolve(run, "Long survey")
    result = invoke(run, "read_papers", records=[handle], view="sections",
                    sections=[section_id(("Results",))])
    passages = [e for e in result.evidence if e["content_kind"] == "passage"]
    assert passages[0]["page"] == 9 and passages[0]["section"].endswith("Results")
    assert result.items[0]["state"] == "partial"
    following = invoke(run, "read_papers", records=[handle], view="sections",
                       sections=[section_id(("Results",))], cursor=result.continuation)
    assert [e["page"] for e in following.evidence if e["content_kind"] == "passage"] == [10]
    assert following.status is Status.OK and following.continuation is None


def test_a_continuation_resumes_without_replaying_the_prefix(corpus, embedder):
    long_paper()
    run, _ = read_run(corpus, embedder, read_token_cap=140)
    handle = resolve(run, "Long survey")
    pages, cursor = [], None
    for _ in range(12):
        arguments = {"records": [handle], "view": "sections"}
        if cursor:
            arguments["cursor"] = cursor
        result = invoke(run, "read_papers", **arguments)
        read = [e["page"] for e in result.evidence if e["content_kind"] == "passage"]
        assert not set(read) & set(pages)
        pages += read
        cursor = result.continuation
        if cursor is None:
            break
    assert pages == list(range(1, 13))


def test_each_paper_gets_its_own_continuation(corpus, embedder):
    long_paper("First long")
    long_paper("Second long")
    run, _ = read_run(corpus, embedder, read_token_cap=280)
    handles = [resolve(run, "First long"), resolve(run, "Second long")]
    result = invoke(run, "read_papers", records=handles, view="sections")
    assert result.continuation is None
    continuations = [item["continuation"] for item in result.items]
    assert all(continuations) and len(set(continuations)) == 2
    resumed = invoke(run, "read_papers", records=[handles[1]], view="sections",
                     cursor=continuations[1])
    assert {e["record"] for e in resumed.evidence} == {handles[1]}
    crossed = invoke(run, "read_papers", records=[handles[0]], view="sections",
                     cursor=continuations[1])
    assert crossed.status is Status.DENIED


def test_guessed_headings_unknown_pages_and_mixed_selectors_are_rejected(corpus, embedder):
    long_paper()
    run, _ = read_run(corpus, embedder)
    handle = resolve(run, "Long survey")
    for arguments in (
        {"view": "sections", "sections": ["Results  "]},
        {"view": "sections", "sections": ["S00000000"]},
        {"view": "pages", "pages": [99]},
        {"view": "outline", "pages": [1]},
        {"view": "pages"},
    ):
        result = invoke(run, "read_papers", records=[handle], **arguments)
        assert result.status is Status.UNAVAILABLE, arguments
    pages = invoke(run, "read_papers", records=[handle], view="pages", pages=[12, 3])
    assert [e["page"] for e in pages.evidence if e["content_kind"] == "passage"] == [3, 12]


def test_a_re_chunked_paper_makes_its_continuation_stale(corpus, embedder):
    record = long_paper()
    run, _ = read_run(corpus, embedder, read_token_cap=70)
    handle = resolve(run, "Long survey")
    first = invoke(run, "read_papers", records=[handle], view="sections")
    ChunkSet.objects.filter(record=record).update(is_active=False)
    long_paper(version="v2", record=record)
    stale = invoke(run, "read_papers", records=[handle], view="sections",
                   cursor=first.continuation)
    assert (stale.status, stale.limitations) == (Status.UNAVAILABLE, ("stale_continuation",))


def test_a_paper_revoked_mid_run_reads_as_unavailable(corpus, embedder):
    run, _ = read_run(corpus, embedder)
    handle = resolve(run, "Tilapia ponds")
    corpus["pond"].pipeline_status = PipelineStatus.DRAFT
    corpus["pond"].save()
    result = invoke(run, "read_papers", records=[handle], view="sections")
    assert result.status is Status.EMPTY
    assert result.items == ({"record": handle, "state": "unavailable"},)
    assert "tilapia" not in payload(result).casefold()


# -- briefs ------------------------------------------------------------------


def ready_brief(record, requested_by, quote="Accuracy was 91.4% on CIFAR-10."):
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    fields = {name: {"state": "not_reported", "values": []} for name in FIELDS}
    chunk = DocumentChunk.objects.get(chunk_set=chunk_set, sequence=9)
    fields["findings"] = {"state": "reported", "values": [{
        "value": "Accuracy was 91.4% on CIFAR-10.",
        "citations": [{"page": 10, "quote": quote, "chunk_id": chunk.pk}]}]}
    return PaperBrief.objects.create(
        record=record, chunk_set=chunk_set, content_hash=chunk_set.content_hash,
        prompt_version=PROMPT_VERSION, state="ready", fields=fields, requested_by=requested_by,
        profile_hash=_profile_hash(profile_for(InferenceTask.BRIEF)))


def test_a_brief_view_reuses_the_cached_brief_and_never_generates_one(
        corpus, embedder, settings):
    settings.AI_PAPER_BRIEFS_ENABLED = True
    record = long_paper()
    run, stack = read_run(corpus, embedder)
    handle = resolve(run, "Long survey")
    with use_composition_root(stack):
        missing = invoke(run, "read_papers", records=[handle], view="brief")
    assert missing.items[0]["state"] == "brief_unavailable"
    assert "brief_unavailable" in missing.limitations[0]
    assert not PaperBrief.objects.filter(record=record).exists()
    ready_brief(record, corpus["student"])

    run, stack = read_run(corpus, embedder)
    with use_composition_root(stack):
        result = invoke(run, "read_papers", records=[resolve(run, "Long survey")], view="brief")
    findings = next(f for f in result.facts if f["name"] == "findings")
    assert findings["state"] == "reported"
    assert findings["provenance"]["kind"] == "paper_brief"
    assert findings["provenance"]["cached"] is True
    citation = findings["values"][0]["citations"][0]
    assert citation["page"] == 10 and citation["ref"].startswith("E")
    assert next(f for f in result.facts if f["name"] == "method")["state"] == "not_reported"


def test_a_new_paper_version_invalidates_the_cached_brief(corpus, embedder, settings):
    settings.AI_PAPER_BRIEFS_ENABLED = True
    record = long_paper()
    ready_brief(record, corpus["student"])
    ChunkSet.objects.filter(record=record).update(is_active=False)
    long_paper(version="v2", record=record)
    run, stack = read_run(corpus, embedder)
    with use_composition_root(stack):
        result = invoke(run, "read_papers", records=[resolve(run, "Long survey")], view="brief")
    assert result.items[0]["state"] == "brief_unavailable"
    assert result.facts == ()


# -- extract_evidence (A07) -------------------------------------------------


class Extractor(LLMProvider):
    """Answers each requested key from a script, when its batch holds the page."""

    def __init__(self, script, failure=False):
        self.script, self.failure, self.requests = script, failure, []

    def generate(self, system, user):
        self.requests.append(user)
        if self.failure:
            raise TimeoutError("scripted outage")
        keys = json.loads(user[user.index("{"):user.index("}") + 1])
        title = user.split("Extract these details from ", 1)[1].split(":", 1)[0]
        absent = {"state": "not_reported", "values": []}

        def answer(name):
            field = self.script.get((title, name), absent)
            pages = {c["page"] for v in field["values"] for c in v["citations"]}
            return field if all(f"[p. {p}]" in user for p in pages) else absent

        return json.dumps({key: answer(name) for key, name in keys.items()})


def reported(value, page, quote, metric=None):
    entry = {"value": value, "citations": [{"page": page, "quote": quote}]}
    if metric:
        entry["metric"] = metric
    return {"state": "reported", "values": [entry]}


def test_requested_fields_come_back_sourced_with_typed_metrics(corpus, embedder):
    long_paper()
    llm = Extractor({("Long survey", "headline accuracy"): reported(
        "91.4% accuracy", 10, "Accuracy was 91.4% on CIFAR-10.",
        {"name": "accuracy", "value": 91.4, "unit": "%", "context": "CIFAR-10"})})
    run, _ = read_run(corpus, embedder, llm=llm)
    result = invoke(run, "extract_evidence", records=[resolve(run, "Long survey")],
                    purpose="describe", fields=["headline accuracy", "energy use"])
    assert result.status is Status.OK
    accuracy, energy = result.facts
    assert accuracy["name"] == "headline accuracy" and accuracy["state"] == "reported"
    value = accuracy["values"][0]
    assert value["metric"] == {"name": "accuracy", "value": 91.4, "unit": "%",
                               "context": "CIFAR-10"}
    assert value["citations"][0]["page"] == 10
    assert accuracy["provenance"] == {"kind": "extraction", "source_version": "Long survey-",
                                      "cached": False}
    assert energy["state"] == "not_reported" and energy["values"] == []


def test_an_unprinted_metric_or_invented_quote_is_unsupported(corpus, embedder):
    long_paper()
    llm = Extractor({
        ("Long survey", "accuracy"): reported(
            "95% accuracy", 10, "Accuracy was 91.4% on CIFAR-10.",
            {"name": "accuracy", "value": 95, "unit": "%"}),
        ("Long survey", "dataset"): reported("ImageNet", 10, "Trained on ImageNet."),
    })
    run, _ = read_run(corpus, embedder, llm=llm)
    result = invoke(run, "extract_evidence", records=[resolve(run, "Long survey")],
                    purpose="describe", fields=["accuracy", "dataset"])
    assert [(f["state"], f["values"]) for f in result.facts] == [
        ("unsupported", []), ("unsupported", [])]


def test_two_papers_keep_their_own_metric_context_and_no_winner(corpus, embedder):
    long_paper("Paper A")
    long_paper("Paper B")
    quote = "Accuracy was 91.4% on CIFAR-10."
    llm = Extractor({
        ("Paper A", "accuracy"): reported("91.4%", 10, quote,
                                          {"name": "accuracy", "value": 91.4, "context": "CIFAR-10"}),
        ("Paper B", "accuracy"): reported("91.4%", 10, quote,
                                          {"name": "accuracy", "value": 91.4, "context": "CIFAR-10 subset"}),
    })
    run, _ = read_run(corpus, embedder, llm=llm)
    result = invoke(run, "extract_evidence", purpose="compare", fields=["accuracy"],
                    records=[resolve(run, "Paper A"), resolve(run, "Paper B")])
    contexts = [f["values"][0]["metric"]["context"] for f in result.facts]
    assert contexts == ["CIFAR-10", "CIFAR-10 subset"]
    assert len({f["record"] for f in result.facts}) == 2
    assert not {"winner", "comparison", "better"} & set(json.dumps(result.public()).split('"'))


def test_brief_fields_reuse_the_cached_brief_with_no_model_call(corpus, embedder, settings):
    settings.AI_PAPER_BRIEFS_ENABLED = True
    record = long_paper()
    ready_brief(record, corpus["student"])
    llm = Extractor({})
    run, stack = read_run(corpus, embedder, llm=llm)
    with use_composition_root(stack):
        result = invoke(run, "extract_evidence", records=[resolve(run, "Long survey")],
                        purpose="describe", fields=["Findings"])
    assert llm.requests == []
    (findings,) = result.facts
    assert findings["name"] == "Findings" and findings["provenance"]["kind"] == "paper_brief"


def test_a_model_outage_is_unavailable_not_absent(corpus, embedder):
    long_paper()
    run, _ = read_run(corpus, embedder, llm=Extractor({}, failure=True))
    result = invoke(run, "extract_evidence", records=[resolve(run, "Long survey")],
                    purpose="describe", fields=["dataset"])
    assert result.status is Status.UNAVAILABLE
    assert result.items[0]["state"] == "extraction_unavailable"
    assert result.facts == ()


def test_screening_covers_the_issued_records_only(corpus, embedder, settings):
    screened = []

    class Screener(LLMProvider):
        def generate(self, system, user):
            rows = json.loads(user)["records"]
            screened.extend(rows)
            return json.dumps({"decisions": [
                {"record": r["record"], "decision": "include", "quote": r["title"]}
                for r in rows]})

    run, _ = read_run(corpus, embedder, llm=Screener())
    invoke(run, "search_research", query="rainfall", target="papers")
    pond = resolve(run, "Tilapia ponds")
    result = invoke(run, "extract_evidence", records=[pond], purpose="screen",
                    criterion="Is about aquaculture")
    assert [row["record"] for row in screened] == [pond]
    assert result.items == ({"record": pond, "decision": "include", "quote": "Tilapia ponds"},)
    assert result.coverage.subject.value == "screened_subset"
    assert result.coverage.assessed == 1 and result.coverage.complete
    assert "subset_classification" in result.limitations
    assert invoke(run, "extract_evidence", records=[pond], purpose="screen",
                  fields=["x"], criterion="y").status is Status.UNAVAILABLE

    settings.AI_SCREEN_MAX_RECORDS = 1
    too_many = invoke(run, "extract_evidence", purpose="screen", criterion="Is about fish",
                      records=[pond, resolve(run, "Flood forecasting")])
    assert too_many.status is Status.UNAVAILABLE


def test_describe_rejects_too_many_records_and_missing_fields(corpus, embedder, monkeypatch):
    monkeypatch.setattr("apps.ai.research.tools.extract.MAX_RECORDS", 1)
    run, _ = read_run(corpus, embedder, llm=ScriptedLLM(reply="{}"))
    pond = resolve(run, "Tilapia ponds")
    assert invoke(run, "extract_evidence", records=[pond],
                  purpose="describe").status is Status.UNAVAILABLE
    assert invoke(run, "extract_evidence", records=[pond, resolve(run, "Flood forecasting")],
                  purpose="describe", fields=["x"]).status is Status.UNAVAILABLE


def test_repeated_headings_under_different_parents_get_distinct_ids(corpus, embedder):
    record = Record.objects.create(title="Two studies", pipeline_status=PipelineStatus.PUBLISHED)
    chunk_set = ChunkSet.objects.create(record=record, extraction_hash="e", strategy_id="s",
                                        options={}, content_hash="two-v1", is_active=True)
    for index, parent in enumerate(("Study A", "Study B")):
        DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=index, max_sequence=index,
            text=f"{parent} results", content=f"{parent} results", token_count=2,
            context_path=["Two studies", parent, "Results"], text_hash=f"t{index}",
            source_page=index + 1)
    run, _ = read_run(corpus, embedder)
    handle = resolve(run, "Two studies")
    outline = invoke(run, "read_papers", records=[handle], view="outline").items[0]["sections"]
    results = [s for s in outline if s["heading"] == "Results"]
    assert len({s["section"] for s in results}) == 2
    read = invoke(run, "read_papers", records=[handle], view="sections",
                  sections=[section_id(("Study B", "Results"))])
    assert [e["text"] for e in read.evidence if e["content_kind"] == "passage"] == [
        "Study B results"]
    empty = invoke(run, "read_papers", records=[handle], view="sections", sections=[])
    assert empty.status is Status.UNAVAILABLE


def test_no_paid_read_is_sent_for_a_paper_withheld_before_extraction(corpus, embedder):
    long_paper()
    llm = Extractor({})
    withheld = {"on": False}
    run, _ = read_run(corpus, embedder, llm=llm,
                      permits=lambda r: not (withheld["on"] and r.title == "Long survey"))
    handle = resolve(run, "Long survey")
    withheld["on"] = True
    result = invoke(run, "extract_evidence", records=[handle], purpose="describe",
                    fields=["dataset"])
    assert llm.requests == []
    assert result.items == ({"record": handle, "state": "unavailable"},)
