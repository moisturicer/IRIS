"""The real adapters, admitted at their physical send (IR-545).

Each adapter is driven with an injected transport, so nothing leaves the
process; what is asserted is that the production code paths reserve before
sending, report what the vendor returned, and charge the right lane.
"""

from types import SimpleNamespace

import httpx
import pytest

from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.admission.scope import workload
from apps.ai.inference.providers import task_lane
from apps.ai.inference.tasks import InferenceTask
from apps.ai.models import ProviderReservation
from apps.ai.models.admission import SETTLED
from apps.ai.providers.decisions import DecisionUnavailable
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.providers.openrouter_decisions import OpenRouterDecisionsAdapter
from apps.ai.providers.tool_calling import SystemMessage, ToolDefinition, UserMessage
from apps.ai.resilience.llm import LLMProviderConfig, build_task_llm

from .support import enforce

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]


def _rows(**filters):
    return ProviderReservation.objects.using("admission").filter(**filters)


class _Completions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content="An answer [1].", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=77, completion_tokens=11),
            model="cheap",
        )


def _client():
    completions = _Completions()
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def _inner(provider):
    """Peel decorators down to the adapter, collecting their types."""
    seen = []
    while True:
        seen.append(type(provider).__name__)
        nested = getattr(provider, "_provider", None) or getattr(provider, "_adapter", None)
        if nested is None:
            return seen, provider
        provider = nested


def test_under_enforcement_the_adapter_is_admitted_inside_the_retry(settings):
    enforce(settings)
    chain = build_task_llm([LLMProviderConfig(model="cheap", api_key="k", lane="research")], "k")
    seen, adapter = _inner(chain)
    assert seen == [
        "CircuitBreakingLLMProvider", "RetryingLLMProvider", "AdmittedLLMProvider",
        "OpenAICompatibleAdapter",
    ]
    assert adapter.max_tokens == 500, "the admitted completion cap is sent"
    assert adapter._bounded_attempts is True


def test_a_task_cap_below_the_admitted_one_is_kept(settings):
    enforce(settings)
    chain = build_task_llm([LLMProviderConfig(model="cheap", api_key="k", max_tokens=256)], "k")
    assert _inner(chain)[1].max_tokens == 256


def test_with_admission_off_nothing_changes(settings):
    settings.AI_PROVIDER_ADMISSION = "off"
    chain = build_task_llm([LLMProviderConfig(model="cheap", api_key="k")], "k")
    seen, adapter = _inner(chain)
    assert "AdmittedLLMProvider" not in seen
    assert adapter.max_tokens is None and adapter._bounded_attempts is False


def test_the_sdks_hidden_retries_are_off_when_bounded(settings, monkeypatch):
    import openai

    built = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: built.update(kwargs) or SimpleNamespace())
    OpenAICompatibleAdapter(api_key="k", model="cheap", bounded_attempts=True)._build_client()
    assert built["max_retries"] == 0
    built.clear()
    OpenAICompatibleAdapter(api_key="k", model="cheap")._build_client()
    assert "max_retries" not in built


def test_the_real_adapter_reports_its_usage(settings):
    enforce(settings)
    client, completions = _client()
    adapter = OpenAICompatibleAdapter(
        api_key="k", model="cheap", client=client, max_tokens=500, bounded_attempts=True,
    )
    AdmittedLLMProvider(adapter).generate("system", "question")
    (row,) = _rows()
    assert (row.state, row.charge_input_tokens, row.charge_output_tokens) == (SETTLED, 77, 11)
    assert completions.calls[0]["max_tokens"] == 500


def test_a_bounded_tool_call_carries_the_cap(settings):
    enforce(settings)
    client, completions = _client()
    adapter = OpenAICompatibleAdapter(
        api_key="k", model="cheap", client=client, max_tokens=500, bounded_attempts=True,
    )
    AdmittedLLMProvider(adapter).converse_with_tools(
        [SystemMessage("s"), UserMessage("q")], [ToolDefinition("search_corpus", "Search.")]
    )
    assert completions.calls[0]["max_tokens"] == 500
    assert _rows().get().charge_input_tokens == 77


def test_voyage_requests_are_admitted_to_the_workload_lane(settings, monkeypatch):
    from apps.ai.providers import voyage

    enforce(settings)
    settings.VOYAGE_API_KEY = "voyage-key"
    sent = []

    def post(url, json, headers, timeout):
        sent.append(url)
        return httpx.Response(
            200, json={"data": [{"index": 0, "relevance_score": 0.5}], "usage": {"total_tokens": 42}},
        )

    monkeypatch.setattr(voyage.httpx, "post", post)
    voyage._post("/rerank", {"model": "rerank-3", "query": "q", "documents": ["d"]})
    with workload("ingestion"):
        voyage._post("/rerank", {"model": "rerank-3", "query": "q", "documents": ["d"]})

    assert len(sent) == 2
    assert sorted(_rows().values_list("lane", flat=True)) == ["ingestion", "reranking"]
    assert set(_rows().values_list("charge_input_tokens", flat=True)) == {42}


def test_a_refused_voyage_request_degrades_like_a_spent_rate_limit(settings, monkeypatch):
    from apps.ai.providers import voyage
    from apps.ai.retrieval.degraded import is_vendor_unavailable

    enforce(settings, AI_ADMISSION_PRICES='{"cheap": {"input": 1, "output": 1}}')
    settings.VOYAGE_API_KEY = "voyage-key"
    monkeypatch.setattr(voyage.httpx, "post", lambda *a, **k: pytest.fail("sent"))
    with pytest.raises(Exception) as refused:
        voyage._post("/rerank", {"model": "rerank-3", "query": "q", "documents": ["d"]})
    assert is_vendor_unavailable(refused.value)


def test_jev_decisions_are_admitted_and_a_refusal_routes_to_the_backup(settings):
    enforce(settings, AI_ADMISSION_PRICES='{"typesafe/jev-1.13": {"input": 0.1, "output": 0}}')
    body = {
        "model": "typesafe/jev-1.13-20261001",
        "answers": {"q": {"type": "noul", "noul": 0.9}},
        "usage": {"input_tokens": 30, "cost": 0.000003},
    }
    client = SimpleNamespace(post=lambda *a, **k: httpx.Response(200, json=body))
    jev = OpenRouterDecisionsAdapter("key", model="typesafe/jev-1.13", client=client)
    from apps.ai.providers.decisions import NoulQuestion

    jev.nouls({"question": "x"}, questions={"q": NoulQuestion("Is it?", {"yes": "yes"})})
    (row,) = _rows()
    assert (row.lane, row.charge_input_tokens, row.charge_cost_micros) == ("chat", 30, 3)

    enforce(settings, AI_ADMISSION_PRICES='{"cheap": {"input": 1, "output": 1}}')
    with pytest.raises(DecisionUnavailable):
        jev.nouls({"question": "x"}, questions={"q": NoulQuestion("Is it?", {"yes": "yes"})})


def test_each_inference_task_has_a_lane():
    assert {task: task_lane(task) for task in InferenceTask} == {
        InferenceTask.ANSWER: "chat", InferenceTask.RESOLVE: "chat", InferenceTask.ROUTE: "chat",
        InferenceTask.PLAN: "research", InferenceTask.SCREEN: "research",
        InferenceTask.SUMMARY: "overview", InferenceTask.DESCRIBE_FIGURE: "ingestion",
    }

