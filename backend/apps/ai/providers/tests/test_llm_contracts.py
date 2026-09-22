"""The `LLMProvider` contract, and what the adapter puts on the wire (IR-131).

IR-131 notes the port existed with no contract suite at all, unlike
`EmbeddingProvider`. This adds one, and runs it against the deterministic fake
always and against the configured vendor when a key is present.

The adapter takes an injectable client, so the part with judgement in it --
which model is asked, how the prompt is shaped, what happens when the vendor
returns nothing -- is tested without a network or an account.
"""

import os

import httpx
import openai
import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.openai_compatible import (
    LLMUnavailable,
    OpenAICompatibleAdapter,
)
from apps.ai.providers.ports import LLMProvider, StreamDelta

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

    def __init__(
        self,
        reply="An answer [1].",
        fail=None,
        empty=False,
        stream_chunks=None,
        stream_fail=None,
    ):
        self.calls = []
        self._reply = reply
        self._fail = fail
        self._empty = empty
        self._stream_chunks = stream_chunks
        self._stream_fail = stream_fail

    def _stream_response(self):
        chunks = (
            self._stream_chunks
            if self._stream_chunks is not None
            else [(self._reply, "")]
        )

        def generator():
            for text, reasoning in chunks:
                delta = type(
                    "D", (), {"content": text or None, "reasoning": reasoning or None}
                )()
                choice = type("C", (), {"delta": delta})()
                yield type("Chunk", (), {"choices": [choice]})()
            if self._stream_fail:
                raise self._stream_fail

        return generator()

    class _Completions:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            if kwargs.get("stream"):
                if self._outer._fail:
                    raise self._outer._fail
                return self._outer._stream_response()
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

    def test_streaming_yields_at_least_one_delta_whose_text_concatenates_to_an_answer(
        self, provider
    ):
        deltas = list(provider.stream(system="You answer questions.", user="A question?"))
        assert deltas
        assert all(isinstance(d, StreamDelta) for d in deltas)
        assert "".join(d.text for d in deltas).strip()


class DefaultStreamWrappingTests:
    """`LLMProvider.stream`'s default (IR-325): every existing fake and
    resilience decorator implements only `generate`, and must keep working
    unmodified, wrapping the whole answer as one delta."""

    def test_a_provider_with_no_stream_override_yields_exactly_one_delta(self):
        provider = ScriptedLLM(reply="Based on the sources, yes [1].")
        deltas = list(provider.stream(system="s", user="u"))
        assert len(deltas) == 1
        assert deltas[0] == StreamDelta(text="Based on the sources, yes [1].", reasoning="")

    def test_the_default_still_calls_generate_with_the_same_arguments(self):
        provider = ScriptedLLM()
        list(provider.stream(system="rules", user="question"))
        assert provider.calls == [("rules", "question")]


class StreamingAdapterTests:
    """`OpenAICompatibleAdapter.stream` (IR-325): genuine streaming, not the
    default's one-shot wrap -- multiple deltas, a separate reasoning channel,
    and the vendor error handling `generate` already has."""

    def test_multiple_chunks_arrive_as_separate_deltas(self):
        client = _FakeClient(stream_chunks=[("Based ", ""), ("on the sources", ""), (" [1].", "")])
        deltas = list(OpenAICompatibleAdapter(client=client).stream(system="s", user="u"))

        assert [d.text for d in deltas] == ["Based ", "on the sources", " [1]."]
        assert "".join(d.text for d in deltas) == "Based on the sources [1]."

    def test_reasoning_deltas_arrive_on_their_own_channel(self):
        client = _FakeClient(
            stream_chunks=[("", "Let me check the sources."), ("The answer is yes [1].", "")]
        )
        deltas = list(
            OpenAICompatibleAdapter(client=client, reasoning_effort="medium").stream(
                system="s", user="u"
            )
        )

        assert deltas[0].reasoning == "Let me check the sources."
        assert deltas[0].text == ""
        assert deltas[1].text == "The answer is yes [1]."
        assert deltas[1].reasoning == ""

    def test_reasoning_effort_is_sent_as_extra_body_once_iteration_starts(self):
        client = _FakeClient()
        deltas = OpenAICompatibleAdapter(client=client, reasoning_effort="high").stream(
            system="s", user="u"
        )
        list(deltas)

        assert client.calls[0]["extra_body"] == {
            "reasoning_effort": "high",
            "include_reasoning": True,
        }
        assert client.calls[0]["stream"] is True

    def test_no_extra_body_when_reasoning_effort_is_not_configured(self):
        client = _FakeClient()
        list(OpenAICompatibleAdapter(client=client).stream(system="s", user="u"))

        assert "extra_body" not in client.calls[0]

    def test_a_vendor_error_mid_stream_becomes_one_domain_exception(self):
        client = _FakeClient(
            stream_chunks=[("Based ", "")], stream_fail=RuntimeError("connection reset")
        )
        with pytest.raises(LLMUnavailable):
            list(OpenAICompatibleAdapter(client=client).stream(system="s", user="u"))

    def test_a_vendor_error_before_the_stream_opens_becomes_one_domain_exception(self):
        client = _FakeClient(fail=RuntimeError("429 rate limited"))
        with pytest.raises(LLMUnavailable):
            list(OpenAICompatibleAdapter(client=client).stream(system="s", user="u"))

    def test_an_empty_stream_is_an_error_not_a_silent_no_op(self):
        client = _FakeClient(stream_chunks=[])
        with pytest.raises(LLMUnavailable):
            list(OpenAICompatibleAdapter(client=client).stream(system="s", user="u"))

    def test_it_refuses_to_stream_without_a_key(self, settings):
        settings.LLM_API_KEY = ""
        with pytest.raises(LLMUnavailable, match="LLM_API_KEY"):
            list(OpenAICompatibleAdapter().stream(system="s", user="u"))


class AdapterRequestTests:
    def test_the_configured_model_is_requested(self, settings):
        client = _FakeClient()
        settings.LLM_MODEL = "openai/gpt-oss-120b"
        OpenAICompatibleAdapter(client=client).generate(system="s", user="u")

        assert client.calls[0]["model"] == "openai/gpt-oss-120b"

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


def _status_error(cls, status: int, **kwargs):
    """A real ``openai`` SDK exception, not a stand-in for one -- IR-320's
    classifier reads the SDK's own hierarchy, so the test has to hand it a
    genuine instance rather than something that merely looks like one.
    ``openai``'s exception constructors only read ``.status_code`` and
    ``.headers`` off the response they're given, so a real ``httpx.Response``
    satisfies them without reaching for the vendored ``httpx2`` the SDK uses
    internally -- this file has no reason to depend on that implementation
    detail when the repo's own ``httpx`` already does the job.
    """
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return cls(response=httpx.Response(status, request=request), **kwargs)


class VendorFailureClassificationTests:
    """`LLMUnavailable.kind` is read from the vendor's own exception type or
    status code first, and only falls back to a message heuristic when the
    SDK gives nothing better (IR-320)."""

    def test_an_authentication_error_is_classified_as_auth(self):
        exc = _status_error(openai.AuthenticationError, 401, message="bad key", body=None)
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.AUTH

    def test_a_permission_denied_error_is_classified_as_auth(self):
        exc = _status_error(
            openai.PermissionDeniedError, 403, message="no access", body=None
        )
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.AUTH

    def test_a_rate_limit_error_is_classified_as_rate_limit(self):
        exc = _status_error(openai.RateLimitError, 429, message="slow down", body=None)
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.RATE_LIMIT

    def test_an_api_timeout_is_classified_as_timeout(self):
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        exc = openai.APITimeoutError(request=request)
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.TIMEOUT

    def test_a_connection_error_is_classified_as_network(self):
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        exc = openai.APIConnectionError(request=request)
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.NETWORK

    def test_a_context_length_bad_request_is_classified_as_context_overflow(self):
        exc = _status_error(
            openai.BadRequestError,
            400,
            message="too long",
            body={"code": "context_length_exceeded"},
        )
        client = _FakeClient(fail=exc)
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.CONTEXT_OVERFLOW

    def test_an_unclassified_exception_falls_back_to_the_message_heuristic(self):
        """A test double, or a vendor failure the SDK does not wrap, carries
        no status code -- the message is all there is to classify."""
        client = _FakeClient(fail=RuntimeError("429 rate limited"))
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter(client=client).generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.RATE_LIMIT

    def test_a_missing_key_is_classified_as_auth(self, settings):
        settings.LLM_API_KEY = ""
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleAdapter().generate(system="s", user="u")
        assert excinfo.value.kind == ErrorKind.AUTH
