"""Brief-backed comparisons through queued HTTP and reopened conversations."""

import json
import re

import pytest
from django.urls import reverse

from apps.ai.admission.tests.support import enforce
from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.admission.tests.support import MeteredAdapter
from apps.ai.briefs.reading import FIELDS
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import AskRun, ChunkSet, Conversation, DocumentChunk, PaperBrief, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.tasks import answer_queued_question
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import make_user
from .test_durable_ask_http import _follow
from .test_routed_chat_http import route

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(databases=["default", "admission"])]


@pytest.fixture
def comparison_scene(settings, monkeypatch, client_for):
    settings.AI_COMPARISON_ENABLED = True
    settings.AI_COMPARISON_MAX_RECORDS = 4
    settings.AI_COMPARISON_MAX_ATTEMPTS = 100
    settings.AI_COMPARISON_MAX_INPUT_TOKENS = 500000
    settings.AI_COMPARISON_MAX_OUTPUT_TOKENS = 50000
    settings.AI_COMPARISON_MAX_COST_USD = "10"
    settings.AI_PAPER_BRIEFS_ENABLED = True
    settings.AI_DURABLE_ASK = True
    settings.AI_RESEARCH_LANE = "on"
    settings.LLM_ANSWER_MODEL = "cheap"
    settings.LLM_ANSWER_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "local-fake"
    settings.LLM_ANSWER_FALLBACK_MODELS = ""
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":16000}'
    enforce(settings)
    route(monkeypatch, "comparison")
    monkeypatch.setattr(answer_queued_question, "apply_async", lambda *a, **kw: None)
    reader = make_user("comparison-reader@cit.edu")
    records = []
    for title in ("Rice Prediction", "Flood Prediction"):
        record = Record.objects.create(title=title, pipeline_status=PipelineStatus.PUBLISHED)
        paper = ChunkSet.objects.create(record=record, extraction_hash=title, content_hash=title,
                                        strategy_id="test", options={}, is_active=True)
        DocumentChunk.objects.create(record=record, chunk_set=paper, sequence=0,
            max_sequence=0, text="Accuracy was 92%.", content="Accuracy was 92%.",
            source_page=4, text_hash=title, token_count=5)
        records.append(record)
    return client_for(reader), Conversation.objects.create(user=reader), records


class ComparisonLLM(ScriptedLLM):
    def generate(self, system, user):
        super().generate(system, user)
        if "Extract a paper brief" in system:
            fields = {name: {"state": "not_reported", "values": []} for name in FIELDS}
            fields["findings"] = {"state": "reported", "values": [{"value": "Accuracy was 92%.",
                "citations": [{"page": 4, "quote": "Accuracy was 92%."}]}]}
            return json.dumps(fields)
        return "«Rice Prediction» reports accuracy of 92% [1].\n«Flood Prediction» reports accuracy of 92% [2]."


def completed(client, conversation, records, callbacks, question=None, *, selected=True):
    with callbacks(execute=True):
        body = {
            "question": question or 'Compare "Rice Prediction" and "Flood Prediction"',
            "conversation_id": conversation.pk,
        }
        if selected:
            body["comparison_record_ids"] = [record.pk for record in records]
        response = client.post(reverse("ai-ask-stream"), body, format="json")
    assert response.status_code == 200
    first = next(iter(response.streaming_content)).decode()
    response._iterator.close()
    run_id = json.loads(next(line[6:] for line in first.splitlines() if line.startswith("data: ")))["run_id"]
    answer_queued_question(run_id)
    _, frames = _follow(client, run_id)
    return next(data for _, name, data in frames if name == "done"), frames


def test_first_comparison_reads_each_paper_and_reopens_same_table(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    llm = ComparisonLLM()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        done, frames = completed(client, conversation, records, django_capture_on_commit_callbacks)
        reopened = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()
    table = done["comparison"]
    assert table["records"] == [{"record_id": r.pk, "title": r.title} for r in records]
    assert [c["state"] for c in table["coverage"]] == ["read_fully", "read_fully"]
    finding = next(row for row in table["rows"] if row["dimension"] == "findings")
    assert [cell["values"][0]["value"] for cell in finding["cells"]] == ["Accuracy was 92%."] * 2
    assert reopened["turns"][0]["comparison"] == table
    assert "source_versions" not in table
    stored = Turn.objects.get().comparison
    assert "quote" not in stored["rows"][4]["cells"][0]["values"][0]["citations"][0]
    assert len(llm.calls) == 3
    assert [data["kind"] for _, name, data in frames if name == "agent_step"][:2] == ["Reading paper 1 of 2"] * 2


@pytest.mark.parametrize("selection", [[1], [1, 2, 3, 4, 5], [1, 1], [1, True], "1,2"])
def test_selected_ids_are_validated_before_queueing(comparison_scene, selection):
    client, conversation, _ = comparison_scene
    response = client.post(reverse("ai-ask-stream"), {
        "question": "Compare selected papers", "conversation_id": conversation.pk,
        "comparison_record_ids": selection,
    }, format="json")
    assert response.status_code == 400
    assert not AskRun.objects.exists()


def test_ambiguous_named_list_never_compares_a_resolved_subset(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    llm = ComparisonLLM()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks,
                            'Compare "Rice Prediction" and "Unknown Paper"', selected=False)
    assert "unambiguous titles" in done["message"]
    assert "comparison" not in done
    assert not llm.calls


def test_duplicate_titles_require_a_choice(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    Record.objects.create(title=records[0].title, pipeline_status=PipelineStatus.PUBLISHED)
    llm = ComparisonLLM()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks, selected=False)
    assert "comparison" not in done
    assert not llm.calls


def test_cached_readings_make_no_second_brief_call(comparison_scene, django_capture_on_commit_callbacks, monkeypatch):
    client, conversation, records = comparison_scene
    llm = ComparisonLLM()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        completed(client, conversation, records, django_capture_on_commit_callbacks)
        route(monkeypatch, "comparison")
        second, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert len(llm.calls) == 4
    assert PaperBrief.objects.count() == 2
    assert len(second["comparison"]["records"]) == 2


@pytest.mark.parametrize("unavailable", ["hidden", "missing", "gated"])
def test_unreadable_record_has_no_identity_hint(comparison_scene, django_capture_on_commit_callbacks, unavailable):
    client, conversation, records = comparison_scene
    denied_id = records[1].pk
    if unavailable == "hidden":
        records[1].pipeline_status = PipelineStatus.DRAFT
        records[1].save(update_fields=["pipeline_status"])
    elif unavailable == "missing":
        records[1].delete()
        records[1].pk = denied_id  # Submit the original, now-missing ID.
    root = CompositionRoot(llm=ComparisonLLM(), permits=lambda r: unavailable != "gated" or r.pk != denied_id)
    with use_composition_root(root):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    comparison = done["comparison"]
    assert comparison["records"] == [{"record_id": records[0].pk, "title": records[0].title}]
    assert comparison["coverage"][1] == {"state": "not_permitted", "reason": "disclosure_or_access"}
    assert "Flood Prediction" not in json.dumps(comparison)


def test_failed_paper_keeps_other_papers_verified_cells(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    class FailingPaper(ComparisonLLM):
        def generate(self, system, user):
            if "Extract a paper brief" in system and "Flood Prediction" in user:
                raise LLMUnavailable("fake failure")
            return super().generate(system, user)
    with use_composition_root(CompositionRoot(llm=FailingPaper(), permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert [c["state"] for c in done["comparison"]["coverage"]] == ["read_fully", "could_not_read"]
    assert done["mode"] == "partial"
    assert len(done["citations"]) == 1


@pytest.mark.parametrize("fabrication", [
    "«Rice Prediction» reports accuracy of 99% [1].",
    "«Rice Prediction» uses convolutional neural networks [1].",
    "«Flood Prediction» reports accuracy of 92% [1].",
])
def test_invented_claim_is_removed_and_counted(comparison_scene, django_capture_on_commit_callbacks, fabrication):
    client, conversation, records = comparison_scene
    class InventedClaim(ComparisonLLM):
        def generate(self, system, user):
            result = super().generate(system, user)
            return result if "Extract a paper brief" in system else result + "\n" + fabrication
    with use_composition_root(CompositionRoot(llm=InventedClaim(), permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert done["comparison"]["removed_claims"] == 1
    assert fabrication not in done["answer"]
    assert "92%" in done["answer"]


def test_source_changed_during_generation_withholds_output(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    class ChangingSource(ComparisonLLM):
        def generate(self, system, user):
            result = super().generate(system, user)
            if "Describe ONLY" in system:
                ChunkSet.objects.filter(record=records[0]).update(is_active=False)
            return result
    with use_composition_root(CompositionRoot(llm=ChangingSource(), permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert "comparison" not in done
    assert not done["citations"]
    assert done["mode"] == "unavailable"


@pytest.mark.parametrize("change", ["version", "permission", "gate", "quote"])
def test_reopened_comparison_rechecks_sources(comparison_scene, django_capture_on_commit_callbacks, change):
    client, conversation, records = comparison_scene
    root = CompositionRoot(llm=ComparisonLLM(), permits=lambda r: True)
    with use_composition_root(root):
        completed(client, conversation, records, django_capture_on_commit_callbacks)
        if change == "version":
            ChunkSet.objects.filter(record=records[0]).update(is_active=False)
        elif change == "permission":
            records[0].pipeline_status = PipelineStatus.DRAFT
            records[0].save(update_fields=["pipeline_status"])
        elif change == "quote":
            DocumentChunk.objects.filter(record=records[0]).update(text="Changed evidence")
        else:
            root = CompositionRoot(llm=ComparisonLLM(), permits=lambda r: False)
        with use_composition_root(root):
            reopened = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][0]
    assert "comparison" not in reopened
    assert reopened["answer"] is None and reopened["citations"] == []
    assert reopened["state"] == "unavailable"


def test_explicit_comparison_budget_and_deadline_survive_submission(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    with use_composition_root(CompositionRoot(llm=ComparisonLLM(), permits=lambda r: True)):
        completed(client, conversation, records, django_capture_on_commit_callbacks)
    run = AskRun.objects.get()
    assert (run.deadline_at - run.created_at).total_seconds() == pytest.approx(300, abs=1)
    assert run.request["comparison_ceiling"]["input_tokens"] == 500000
    assert run.request["comparison_record_ids"] == [r.pk for r in records]
    assert not Turn.objects.in_model_history().exists()


def test_router_selected_named_comparison_gets_its_own_budget(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    with use_composition_root(CompositionRoot(llm=ComparisonLLM(), permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks,
                            '"Rice Prediction" versus "Flood Prediction"', selected=False)
    assert "comparison" in done
    run = AskRun.objects.get()
    assert (run.deadline_at - run.created_at).total_seconds() == pytest.approx(300, abs=1)


def test_metered_briefs_keep_individual_usage_under_comparison_ceiling(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    class MeteredComparison(MeteredAdapter):
        def generate(self, system, user):
            self._text = ComparisonLLM().generate(system, user)
            return super().generate(system, user)
    adapter = MeteredComparison()
    with use_composition_root(CompositionRoot(llm=AdmittedLLMProvider(adapter), permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert len(done["comparison"]["records"]) == 2
    assert [brief.usage for brief in PaperBrief.objects.order_by("pk")] == [
        {"input_tokens": 120, "output_tokens": 30, "complete": True},
        {"input_tokens": 120, "output_tokens": 30, "complete": True},
    ]


def test_exhausted_comparison_preserves_the_checked_table(comparison_scene, settings, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    settings.AI_COMPARISON_MAX_ATTEMPTS = 2
    class MeteredComparison(MeteredAdapter):
        def generate(self, system, user):
            self._text = ComparisonLLM().generate(system, user)
            return super().generate(system, user)
    adapter = MeteredComparison()
    with use_composition_root(CompositionRoot(llm=AdmittedLLMProvider(adapter), permits=lambda r: True)):
        done, frames = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert done["mode"] == "unavailable"
    assert len(done["comparison"]["records"]) == 2 and len(done["citations"]) == 2
    assert adapter.sent == 2
    assert any(name == "capacity_limited" for _, name, _ in frames)


def test_missing_comparison_budget_refuses_before_dispatch(comparison_scene, settings):
    client, conversation, records = comparison_scene
    settings.AI_COMPARISON_MAX_INPUT_TOKENS = ""
    response = client.post(reverse("ai-ask-stream"), {
        "question": "Compare papers", "conversation_id": conversation.pk,
        "comparison_record_ids": [r.pk for r in records],
    }, format="json")
    assert response.status_code == 503
    assert response.json()["reason"] == "comparison_not_configured"
    assert not AskRun.objects.exists()


def test_question_specific_read_adds_cited_dimension(comparison_scene, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    class SpecificReading(ComparisonLLM):
        def generate(self, system, user):
            result = super().generate(system, user)
            if "question-specific read" in system:
                return json.dumps({"question_specific": {
                    "state": "reported", "values": [{"value": "Accuracy was 92%.",
                    "citations": [{"page": 4, "quote": "Accuracy was 92%."}]}],
                }})
            return result
    llm = SpecificReading()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks,
                            'Compare "Rice Prediction" and "Flood Prediction" on accuracy')
    row = next(row for row in done["comparison"]["rows"] if row["dimension"] == "question_specific")
    assert row["label"] == "accuracy"
    assert all(cell["values"][0]["citations"][0]["page"] == 4 for cell in row["cells"])
    assert len(llm.calls) == 5


def test_large_papers_are_read_by_section_independently(comparison_scene, settings, django_capture_on_commit_callbacks):
    client, conversation, records = comparison_scene
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":20000}'
    for record in records:
        paper = record.chunk_sets.get(is_active=True)
        chunk = paper.chunks.get()
        chunk.content = chunk.text = "Accuracy was 92%. " + "reading " * 2100
        chunk.context_path = ["Evaluation"]
        chunk.save()
        DocumentChunk.objects.create(record=record, chunk_set=paper, sequence=1,
            max_sequence=1, text="Accuracy was 92%. " + "reading " * 2100,
            content="Accuracy was 92%. " + "reading " * 2100, source_page=5,
            text_hash=record.title + "-second", token_count=2105, context_path=["Findings"])
    class SectionReading(ComparisonLLM):
        def generate(self, system, user):
            result = super().generate(system, user)
            if "Extract a paper brief" in system:
                fields = json.loads(result)
                page = int(re.search(r"\[p\. (\d+)\]", user).group(1))
                fields["findings"]["values"][0]["citations"][0]["page"] = page
                return json.dumps(fields)
            return result
    llm = SectionReading()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        done, _ = completed(client, conversation, records, django_capture_on_commit_callbacks)
    assert [c["state"] for c in done["comparison"]["coverage"]] == ["read_by_section"] * 2
    findings = next(row for row in done["comparison"]["rows"] if row["dimension"] == "findings")
    assert [{c["page"] for value in cell["values"] for c in value["citations"]} for cell in findings["cells"]] == [{4, 5}, {4, 5}]
