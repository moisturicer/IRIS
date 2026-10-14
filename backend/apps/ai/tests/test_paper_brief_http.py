"""On-demand whole-paper reading through the authorized HTTP/worker seam."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.urls import reverse

from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.admission.tests.support import MeteredAdapter, enforce
from apps.ai.briefs.reading import FIELDS
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import ChunkSet, DocumentChunk, PaperBrief
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.tasks import generate_paper_brief
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True, databases=["default", "admission"])]


def extraction(*, quote="Accuracy was 92%.", page=4):
    fields = {name: {"state": "not_reported", "values": []} for name in FIELDS}
    fields["findings"] = {"state": "reported", "values": [
        {"value": "Reported accuracy was 92%.", "citations": [{"page": page, "quote": quote}]},
    ]}
    return json.dumps(fields)


@pytest.fixture(autouse=True)
def brief_settings(settings):
    settings.AI_PAPER_BRIEFS_ENABLED = True
    settings.LLM_ANSWER_MODEL = "cheap"
    settings.LLM_ANSWER_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "local-fake"
    settings.LLM_ANSWER_FALLBACK_MODELS = ""
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192}'
    settings.LLM_ANSWER_PROVIDER_PINS = ""
    settings.LLM_ANSWER_PROVIDER_ONLY = ""
    enforce(settings)


@pytest.fixture
def queued(monkeypatch):
    tasks = []
    monkeypatch.setattr("apps.ai.tasks.generate_paper_brief.delay", lambda *args: tasks.append(args))
    return tasks


def add_chunk(paper, sequence, text, page=4):
    return DocumentChunk.objects.create(
        chunk_set=paper, record=paper.record, sequence=sequence, max_sequence=sequence,
        text=text, content=text, source_page=page, text_hash=f"text-{sequence}",
        token_count=len(text.split()), context_path=[f"Section {sequence}"],
    )


@pytest.fixture
def paper():
    record = Record.objects.create(title="Rice prediction", pipeline_status=PipelineStatus.PUBLISHED)
    chunks = ChunkSet.objects.create(
        record=record, extraction_hash="extraction", content_hash="content-v1",
        strategy_id="test", options={}, is_active=True,
    )
    add_chunk(chunks, 0, "Accuracy was 92%.")
    return chunks


@pytest.fixture
def reader_client(client_for):
    return client_for(make_user("brief-reader@cit.edu"))


def request(client, paper, **data):
    return client.post(reverse("ai-paper-brief", args=[paper.record_id]), data, format="json")


def run_task(args):
    result = generate_paper_brief.apply(args=args)
    assert result.successful(), result.result


def test_first_use_queues_and_second_use_reuses_cited_brief(paper, reader_client, queued):
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        first = request(reader_client, paper)
        assert first.status_code == 200
        assert first.json()["state"] == "generating"
        assert len(queued) == 1 and not llm.calls
        run_task(queued[0])
        second = request(reader_client, paper)
    assert second.json()["state"] == "ready"
    brief = second.json()["brief"]
    assert brief["fields"]["findings"]["values"][0]["citations"][0]["page"] == 4
    assert brief["fields"]["method"] == {"state": "not_reported", "values": []}
    assert brief["model"] == "cheap"
    assert len(queued) == len(llm.calls) == 1


@pytest.mark.parametrize("change", ["content", "prompt", "model", "fallback"])
def test_changed_version_or_generation_policy_reads_again(paper, reader_client, queued, settings, monkeypatch, change):
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        if change == "content":
            paper.content_hash = "content-v2"
            paper.save(update_fields=["content_hash"])
        elif change == "prompt":
            monkeypatch.setattr("apps.ai.briefs.service.PROMPT_VERSION", 2)
        elif change == "model":
            settings.LLM_ANSWER_MODEL = "dear"
            settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"dear":8192}'
        else:
            settings.LLM_ANSWER_FALLBACK_MODELS = "dear"
            settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192,"dear":6000}'
        assert request(reader_client, paper).json()["state"] == "generating"
        run_task(queued[1])
        assert request(reader_client, paper).json()["state"] == "ready"
    assert len(llm.calls) == 2


def test_long_paper_reads_every_section_in_order_and_preserves_citations(paper, reader_client, queued, settings):
    settings.AI_OVERVIEW_TOKEN_CEILING = 1
    add_chunk(paper, 2, "Final result. " * 180 + "Accuracy was 92%.", page=12)
    add_chunk(paper, 1, "Middle section. " * 180 + "Accuracy was 92%.", page=8)

    class SectionLLM(ScriptedLLM):
        def generate(self, system, user):
            super().generate(system, user)
            page = 12 if "[p. 12]" in user else (8 if "[p. 8]" in user else 4)
            return extraction(page=page)

    llm = SectionLLM()
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        final = request(reader_client, paper).json()
    assert final["state"] == "ready"
    assert len(llm.calls) == 3
    assert "[p. 4]" in llm.calls[0][1]
    assert "[p. 8]" in llm.calls[1][1]
    assert "[p. 12]" in llm.calls[2][1]
    assert {value["citations"][0]["page"] for value in final["brief"]["fields"]["findings"]["values"]} == {4, 8, 12}


def test_oversized_single_chunk_is_fully_read(paper, reader_client, queued):
    text = "Section prose. " * 1000
    paper.chunks.update(text=text, content=text)
    llm = ScriptedLLM(reply=json.dumps({name: {"state": "not_reported", "values": []} for name in FIELDS}))
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        assert request(reader_client, paper).json()["state"] == "ready"
    assert len(llm.calls) > 1
    payloads = [user.split("(Section 0)\n", 1)[1] for _, user in llm.calls]
    # Page-prompt framing trims outer whitespace, but no words may be omitted.
    assert " ".join(" ".join(payloads).split()) == " ".join(text.split())


@pytest.mark.parametrize("quote,page", [("Invented result.", 4), ("Accuracy was 92%.", 99)])
def test_invalid_quote_or_page_is_dropped_and_field_unsupported(paper, reader_client, queued, quote, page):
    llm = ScriptedLLM(reply=extraction(quote=quote, page=page))
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        final = request(reader_client, paper).json()
    assert final["brief"]["fields"]["findings"] == {"state": "unsupported", "values": []}


def test_cache_does_not_bypass_disclosure(paper, reader_client, queued):
    llm = ScriptedLLM(reply=extraction())
    permits = [True]
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: permits[0])):
        request(reader_client, paper)
        run_task(queued[0])
        permits[0] = False
        assert request(reader_client, paper).json()["brief"] is None
    assert len(llm.calls) == 1


def test_worker_checks_revoked_access_and_cached_brief_remains_private(paper, reader_client, queued):
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        paper.record.pipeline_status = PipelineStatus.DRAFT
        paper.record.save(update_fields=["pipeline_status"])
        run_task(queued[0])
        response = request(reader_client, paper)
    assert response.status_code == 404
    assert not llm.calls
    assert PaperBrief.objects.get().state == "unavailable"


def test_duplicate_worker_delivery_and_pending_reads_generate_once(paper, reader_client, queued):
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        request(reader_client, paper)
        run_task(queued[0])
        run_task(queued[0])
    assert len(queued) == len(llm.calls) == 1


def test_simultaneous_first_uses_claim_one_background_job(paper, queued):
    readers = [make_user(f"reader-{n}@cit.edu") for n in range(2)]
    barrier = Barrier(2)

    def first_use(user):
        from rest_framework.test import APIClient
        close_old_connections()
        client = APIClient()
        client.force_authenticate(user=user)
        try:
            barrier.wait(timeout=10)
            return request(client, paper).json()["state"]
        finally:
            close_old_connections()

    with use_composition_root(CompositionRoot(permits=lambda r: True)):
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(first_use, readers)) == ["generating", "generating"]
    assert len(queued) == PaperBrief.objects.count() == 1


def test_broker_failure_is_retryable_and_old_delivery_cannot_write(paper, reader_client, queued, monkeypatch):
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        old = queued[0]
        PaperBrief.objects.update(state="unavailable")
        request(reader_client, paper, retry=True)
        run_task(old)
        assert not llm.calls
        run_task(queued[1])
        assert request(reader_client, paper).json()["state"] == "ready"


def test_broker_failure_marks_claim_unavailable(paper, reader_client, monkeypatch):
    def fail(*args):
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.ai.tasks.generate_paper_brief.delay", fail)
    with use_composition_root(CompositionRoot(permits=lambda r: True)):
        assert request(reader_client, paper).json()["state"] == "generating"
        assert request(reader_client, paper).json()["reason"] == "queue_unavailable"


@pytest.mark.parametrize("change", ["access", "disclosure", "content", "model"])
def test_mid_generation_change_cannot_save_a_ready_brief(paper, reader_client, queued, settings, change):
    permits = [True]

    class ChangingLLM(ScriptedLLM):
        def generate(self, system, user):
            super().generate(system, user)
            if change == "access":
                Record.objects.filter(pk=paper.record_id).update(pipeline_status=PipelineStatus.DRAFT)
            elif change == "disclosure":
                permits[0] = False
            elif change == "content":
                ChunkSet.objects.filter(pk=paper.pk).update(content_hash="newer-content")
            else:
                settings.LLM_ANSWER_MODEL = "dear"
                settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"dear":8192}'
            return extraction()

    with use_composition_root(CompositionRoot(llm=ChangingLLM(), permits=lambda r: permits[0])):
        request(reader_client, paper)
        run_task(queued[0])
    assert PaperBrief.objects.get().state == "unavailable"


def test_each_prompt_fits_main_model_window(paper, reader_client, queued, settings):
    from apps.ai.admission.ledger import estimate_tokens

    settings.LLM_ANSWER_FALLBACK_MODELS = "dear"
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":16000,"dear":6000}'
    paper.chunks.update(text="Prose. " * 4000, content="Prose. " * 4000)
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
    assert len(llm.calls) > 1
    assert all(estimate_tokens(system, user) + 4096 <= 16000 for system, user in llm.calls)


def test_uses_only_current_undeleted_chunks(paper, reader_client, queued):
    from django.utils import timezone

    old = ChunkSet.objects.create(
        record=paper.record, extraction_hash="old", content_hash="old",
        strategy_id="test", options={}, is_active=False,
    )
    add_chunk(old, 0, "OLD PAPER TEXT")
    deleted = add_chunk(paper, 1, "DELETED TEXT")
    deleted.deleted_at = timezone.now()
    deleted.save(update_fields=["deleted_at"])
    llm = ScriptedLLM(reply=extraction())
    with use_composition_root(CompositionRoot(llm=llm, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
    assert len(llm.calls) == 1
    assert "OLD PAPER TEXT" not in llm.calls[0][1] and "DELETED TEXT" not in llm.calls[0][1]


def test_shared_admission_records_tokens_and_refuses_exhaustion(paper, reader_client, queued, settings):
    adapter = MeteredAdapter(text=extraction(), usage=(120, 30))
    provider = AdmittedLLMProvider(adapter, lane="research")
    with use_composition_root(CompositionRoot(llm=provider, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        assert request(reader_client, paper).json()["brief"]["usage"] == {
            "input_tokens": 120, "output_tokens": 30, "complete": True,
        }
        paper.content_hash = "next-content"
        paper.save(update_fields=["content_hash"])
        settings.AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS = "1"
        request(reader_client, paper)
        run_task(queued[1])
        assert request(reader_client, paper).json()["state"] == "unavailable"
    assert adapter.sent == 1


def test_unknown_window_and_disabled_controls_call_no_provider(paper, reader_client, queued, settings):
    with use_composition_root(CompositionRoot(permits=lambda r: True)):
        settings.LLM_ANSWER_CONTEXT_WINDOWS = ""
        assert request(reader_client, paper).json()["reason"] == "context_window_unknown"
        settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192}'
        settings.AI_PROVIDER_ADMISSION = "off"
        assert request(reader_client, paper).json()["reason"] == "admission_required"
        settings.AI_PAPER_BRIEFS_ENABLED = False
        assert request(reader_client, paper).json()["reason"] == "not_enabled"
    assert not queued


def test_retry_keeps_the_same_spending_run_and_totals(paper, reader_client, queued):
    invalid = AdmittedLLMProvider(MeteredAdapter(text="invalid json", usage=(120, 30)), lane="research")
    with use_composition_root(CompositionRoot(llm=invalid, permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        assert request(reader_client, paper).json()["state"] == "unavailable"
    valid = AdmittedLLMProvider(MeteredAdapter(text=extraction(), usage=(120, 30)), lane="research")
    with use_composition_root(CompositionRoot(llm=valid, permits=lambda r: True)):
        request(reader_client, paper, retry=True)
        run_task(queued[1])
        assert request(reader_client, paper).json()["brief"]["usage"] == {
            "input_tokens": 240, "output_tokens": 60, "complete": True,
        }


def test_generating_model_is_recorded_after_fallback_and_reused(paper, reader_client, queued, settings):
    settings.LLM_ANSWER_FALLBACK_MODELS = "dear"
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192,"dear":8192}'
    adapter = MeteredAdapter(model="dear", text=extraction())
    with use_composition_root(CompositionRoot(llm=AdmittedLLMProvider(adapter), permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        final = request(reader_client, paper).json()
    assert final["brief"]["model"] == "dear"
    assert final["brief"]["models_used"] == ["dear"]
    assert len(queued) == adapter.sent == 1


@pytest.mark.parametrize("path", ["retry", "fallback"])
@pytest.mark.parametrize("revocation", ["access", "disclosure"])
def test_revocation_blocks_every_later_physical_send(paper, reader_client, queued, settings, path, revocation):
    from apps.ai.admission.scope import mark_sent
    from apps.ai.providers.errors import ErrorKind
    from apps.ai.providers.openai_compatible import LLMUnavailable
    from apps.ai.resilience.llm import FallbackLLMProvider, RetryingLLMProvider

    settings.LLM_ANSWER_FALLBACK_MODELS = "dear"
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192,"dear":8192}'
    permits = [True]

    class RevokingAdapter(MeteredAdapter):
        def generate(self, system, user):
            mark_sent(model=self.model)
            self.sent += 1
            if revocation == "access":
                Record.objects.filter(pk=paper.record_id).update(pipeline_status=PipelineStatus.DRAFT)
            else:
                permits[0] = False
            raise LLMUnavailable("response lost", kind=ErrorKind.NETWORK)

    first, second = RevokingAdapter(), MeteredAdapter(model="dear", text=extraction())
    admitted = AdmittedLLMProvider(first)
    provider = (
        RetryingLLMProvider(admitted, attempts=2, sleep=lambda s: None)
        if path == "retry"
        else FallbackLLMProvider([admitted, AdmittedLLMProvider(second)])
    )
    with use_composition_root(CompositionRoot(llm=provider, permits=lambda r: permits[0])):
        request(reader_client, paper)
        run_task(queued[0])
    assert first.sent == 1 and second.sent == 0
    assert PaperBrief.objects.get().state == "unavailable"


def test_response_model_without_usage_does_not_inherit_previous_section_model(paper, reader_client, queued, settings):
    from types import SimpleNamespace
    from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

    add_chunk(paper, 1, "Prose. " * 800 + "Accuracy was 92%.", page=8)
    settings.LLM_ANSWER_FALLBACK_MODELS = "dear"
    settings.LLM_ANSWER_CONTEXT_WINDOWS = '{"cheap":8192,"dear":8192}'
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        page = 4 if len(sent) == 1 else 8
        return SimpleNamespace(
            model="cheap" if page == 4 else "dear",
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30) if page == 4 else None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=extraction(page=page)))],
        )

    adapter = OpenAICompatibleAdapter(
        model="cheap", fallback_models=("dear",), max_tokens=500,
        api_key="local-fake", client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    with use_composition_root(CompositionRoot(llm=AdmittedLLMProvider(adapter), permits=lambda r: True)):
        request(reader_client, paper)
        run_task(queued[0])
        final = request(reader_client, paper).json()
    assert final["state"] == "ready"
    assert final["brief"]["model"] == "dear"
    assert final["brief"]["models_used"] == ["cheap", "dear"]
    assert final["brief"]["usage"]["complete"] is False
