"""The `LLMProvider` contract, and what the adapter puts on the wire (IR-131).

IR-131 notes the port existed with no contract suite at all, unlike
`EmbeddingProvider`. This adds one, and runs it against the deterministic fake
always and against the configured vendor when a key is present.

The adapter takes an injectable client, so the part with judgement in it --
which model is asked, how the prompt is shaped, what happens when the vendor
returns nothing -- is tested without a network or an account.
"""

import os

import pytest

from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.openai_compatible import (
    LLMUnavailable,
    OpenAICompatibleAdapter,
)
from apps.ai.providers.ports import LLMProvider

pytestmark = pytest.mark.django_required


def _providers():
    yield pytest.param(ScriptedLLM(), id="fake")
    if os.environ.get("LLM_API_KEY"):
        yield pytest.param(OpenAICompatibleAdapter(), id="configured-vendor")


@pytest.fixture(params=list(_providers()))
def provider(request) -> LLMProvider:
    return request.param


class _FakeClient:
    """The one call the adapter makes, and a record of how it was made."""

    def __init__(self, reply="An answer [1].", fail=None, empty=False):
        self.calls = []
        self._reply = reply
        self._fail = fail
        self._empty = empty

    class _Completions:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            if self._outer._fail:
                raise self._outer._fail
            if self._outer._empty:
                return type("R", (), {"choices": []})()
            message = type("M", (), {"content": self._outer._reply})()
            choice = type("C", (), {"message": message})()
            return type("R", (), {"choices": [choice]})()

    @property
    def chat(self):
        return type("Chat", (), {"completions": self._Completions(self)})()


class LLMProviderContractTests:
    def test_generating_returns_text(self, provider):
        answer = provider.generate(system="You answer questions.", user="A question?")
        assert isinstance(answer, str)
        assert answer.strip()

    def test_the_same_inputs_are_answered_consistently_in_shape(self, provider):
        first = provider.generate(system="s", user="u")
        second = provider.generate(system="s", user="u")
        assert isinstance(first, str) and isinstance(second, str)


class AdapterRequestTests:
    def test_the_configured_model_is_requested(self, settings):
        client = _FakeClient()
        settings.LLM_MODEL = "llama-3.3-70b-versatile"
        OpenAICompatibleAdapter(client=client).generate(system="s", user="u")

        assert client.calls[0]["model"] == "llama-3.3-70b-versatile"

    def test_the_system_prompt_and_user_message_are_sent_as_separate_roles(self):
        """Folding the instructions into the user turn makes them look like
        something the asker said, which is how a prompt-injection in a document
        ends up outranking the system prompt."""
        client = _FakeClient()
        OpenAICompatibleAdapter(client=client).generate(system="rules", user="question")

        messages = client.calls[0]["messages"]
        assert [m["role"] for m in messages] == ["system", "user"]
        assert messages[0]["content"] == "rules"
        assert messages[1]["content"] == "question"

    def test_a_vendor_error_becomes_one_domain_exception(self):
        """Anti-corruption at the seam: a Groq 429 and an OpenRouter timeout
        become the same thing, so the resilience stack has one type to catch
        and the domain never learns a vendor's exception hierarchy."""
        client = _FakeClient(fail=RuntimeError("429 rate limited"))
        with pytest.raises(LLMUnavailable):
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")

    def test_an_empty_response_is_an_error_not_an_empty_answer(self):
        """Returning "" would render as an answer with no content and no
        indication anything went wrong."""
        client = _FakeClient(empty=True)
        with pytest.raises(LLMUnavailable):
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")

    def test_it_refuses_to_run_without_a_key(self, settings):
        """No unauthenticated lane, and no local model to fall back to
        (ADR-008, ADR-021)."""
        settings.LLM_API_KEY = ""
        with pytest.raises(LLMUnavailable, match="LLM_API_KEY"):
            OpenAICompatibleAdapter().generate(system="s", user="u")

    def test_temperature_is_pinned_low_for_a_grounded_answer(self):
        """This is extraction from supplied sources, not composition. A high
        temperature buys variety nobody asked for and invites invention."""
        client = _FakeClient()
        OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert client.calls[0]["temperature"] <= 0.3
