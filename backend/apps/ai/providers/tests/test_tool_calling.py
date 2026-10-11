"""The tool-calling port, its adapter and its scripted fake (IR-465, ADR-035 §2).

No vendor account and no network: the adapter takes an injected client, so what
it puts on the wire and what it reads back are asserted directly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import (
    LLMUnavailable,
    OpenAICompatibleAdapter,
)
from apps.ai.providers.tool_calling import (
    ToolCall,
    ToolCallingLLM,
    ToolCompletion,
    ToolDefinition,
)

pytestmark = pytest.mark.django_required

SEARCH = ToolDefinition(name="search_corpus", description="Search the corpus.")


class _Client:
    """Records every `chat.completions.create` call and replies from a script."""

    def __init__(self, message=None, usage=None, choices=None, fail=None):
        self.calls: list[dict] = []
        self._message = message or SimpleNamespace(content="text", tool_calls=None)
        self._usage = usage
        self._choices = choices
        self._fail = fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail:
            raise self._fail
        if kwargs.get("stream"):
            return iter(())
        choices = (
            self._choices
            if self._choices is not None
            else [SimpleNamespace(message=self._message)]
        )
        return SimpleNamespace(choices=choices, usage=self._usage)


def _call(name="search_corpus", arguments=""):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class ThePortIsAbstractTests:
    def test_the_methods_are_abstract_and_have_no_default(self):
        assert ToolCallingLLM.__abstractmethods__ == {
            "complete_with_tools",
            "converse_with_tools",
        }

    def test_a_provider_that_does_not_implement_it_cannot_be_built(self):
        class Forgetful(ToolCallingLLM):
            pass

        with pytest.raises(TypeError, match="complete_with_tools"):
            Forgetful()

    def test_the_adapter_is_a_tool_calling_provider(self):
        assert issubclass(OpenAICompatibleAdapter, ToolCallingLLM)
        assert isinstance(OpenAICompatibleAdapter(client=_Client()), ToolCallingLLM)


class TheAdapterSendsTheSchemaTests:
    def test_the_tool_schema_and_both_turns_reach_the_wire(self):
        client = _Client()
        adapter = OpenAICompatibleAdapter(client=client, model="m")

        adapter.complete_with_tools("the system", "the user", [SEARCH])

        (sent,) = client.calls
        assert sent["model"] == "m"
        assert sent["messages"] == [
            {"role": "system", "content": "the system"},
            {"role": "user", "content": "the user"},
        ]
        assert sent["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "search_corpus",
                    "description": "Search the corpus.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        assert sent["tool_choice"] == "auto"
        assert "stream" not in sent

    def test_the_tool_declares_no_parameters(self):
        assert SEARCH.parameters == {"type": "object", "properties": {}}

    def test_a_timeout_reaches_the_client_and_defaults_when_unset(self, settings):
        # IR-511: an unset timeout is the default, never the SDK's minutes.
        settings.LLM_TIMEOUT_SECONDS = 42
        client = _Client()
        adapter = OpenAICompatibleAdapter(client=client)

        adapter.complete_with_tools("s", "u", [SEARCH], timeout_seconds=7.5)
        adapter.complete_with_tools("s", "u", [SEARCH])

        assert client.calls[0]["timeout"] == 7.5
        assert client.calls[1]["timeout"] == 42

    def test_it_sends_the_reasoning_configuration_generate_sends(self):
        client = _Client()
        adapter = OpenAICompatibleAdapter(client=client, reasoning_effort="medium")

        adapter.complete_with_tools("s", "u", [SEARCH])
        adapter.generate("s", "u")

        assert client.calls[0]["extra_body"] == client.calls[1]["extra_body"]
        assert client.calls[0]["extra_body"]["reasoning_effort"] == "medium"


class TheUnusedToolPathIsUntouchedTests:
    """`generate` and `stream` never offer a tool, so the answer path sends
    exactly what it sent before this port existed."""

    def test_generate_offers_no_tool(self):
        client = _Client()
        OpenAICompatibleAdapter(client=client).generate("s", "u")

        assert "tools" not in client.calls[0]
        assert "tool_choice" not in client.calls[0]

    def test_stream_offers_no_tool(self):
        client = _Client()
        with pytest.raises(LLMUnavailable):
            list(OpenAICompatibleAdapter(client=client).stream("s", "u"))

        assert "tools" not in client.calls[0]
        assert "tool_choice" not in client.calls[0]


class TheAdapterReadsWhatCameBackTests:
    def test_a_tool_call_is_returned_raw(self):
        message = SimpleNamespace(
            content=None, tool_calls=[_call(arguments='{"query": "x"}')]
        )
        completion = OpenAICompatibleAdapter(client=_Client(message)).complete_with_tools(
            "s", "u", [SEARCH]
        )

        # IR-511: a vendor call with no id is given a stable one.
        assert completion.tool_calls == (
            ToolCall("search_corpus", '{"query": "x"}', "call_0"),
        )
        assert completion.text == ""

    def test_text_reasoning_and_token_counts_are_carried(self):
        message = SimpleNamespace(
            content="an answer", tool_calls=None, reasoning="thinking"
        )
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=5)
        completion = OpenAICompatibleAdapter(
            client=_Client(message, usage)
        ).complete_with_tools("s", "u", [SEARCH])

        assert completion.text == "an answer"
        assert completion.reasoning == "thinking"
        assert (completion.input_tokens, completion.output_tokens) == (11, 5)

    def test_several_calls_are_all_returned(self):
        message = SimpleNamespace(content="", tool_calls=[_call(), _call("other")])
        completion = OpenAICompatibleAdapter(client=_Client(message)).complete_with_tools(
            "s", "u", [SEARCH]
        )

        assert [c.name for c in completion.tool_calls] == ["search_corpus", "other"]

    def test_an_empty_completion_is_returned_not_raised(self):
        """Whether it is an error is the caller's reading: the evidence
        decision gives it its own reason code."""
        message = SimpleNamespace(content=None, tool_calls=None)
        completion = OpenAICompatibleAdapter(client=_Client(message)).complete_with_tools(
            "s", "u", [SEARCH]
        )

        assert completion == ToolCompletion()

    def test_missing_usage_is_none_not_zero(self):
        completion = OpenAICompatibleAdapter(client=_Client()).complete_with_tools(
            "s", "u", [SEARCH]
        )
        assert (completion.input_tokens, completion.output_tokens) == (None, None)

    def test_no_choices_is_a_vendor_failure(self):
        adapter = OpenAICompatibleAdapter(client=_Client(choices=[]))
        with pytest.raises(LLMUnavailable, match="no choices"):
            adapter.complete_with_tools("s", "u", [SEARCH])

    @pytest.mark.parametrize(
        "failure, kind",
        [
            (RuntimeError("rate limit exceeded"), ErrorKind.RATE_LIMIT),
            (RuntimeError("request timed out"), ErrorKind.TIMEOUT),
        ],
    )
    def test_a_transport_failure_is_classified_like_generates(self, failure, kind):
        adapter = OpenAICompatibleAdapter(client=_Client(fail=failure))
        with pytest.raises(LLMUnavailable) as caught:
            adapter.complete_with_tools("s", "u", [SEARCH])
        assert caught.value.kind is kind


class TheScriptedFakeTests:
    def test_it_serves_the_text_port_unchanged(self):
        fake = ScriptedToolCallingLLM(reply="hello")
        assert isinstance(fake, ScriptedLLM) and isinstance(fake, ToolCallingLLM)
        assert fake.generate("s", "u") == "hello"
        assert fake.calls == [("s", "u")]

    def test_it_can_produce_every_shape_the_decision_must_survive(self):
        fake = ScriptedToolCallingLLM(
            [
                ScriptedToolCallingLLM.calling(),
                ScriptedToolCallingLLM.calling(arguments='{"query":"x"}'),
                ScriptedToolCallingLLM.calling(arguments="{not json"),
                ScriptedToolCallingLLM.calling("web_search"),
                ScriptedToolCallingLLM.calling_twice(),
                ScriptedToolCallingLLM.answering("text"),
                ScriptedToolCallingLLM.empty(),
                ScriptedToolCallingLLM.calling(text="and text"),
                LLMUnavailable("slow", kind=ErrorKind.TIMEOUT),
            ]
        )
        seen = []
        for _ in range(8):
            seen.append(fake.complete_with_tools("s", "u", [SEARCH]))
        with pytest.raises(LLMUnavailable):
            fake.complete_with_tools("s", "u", [SEARCH])

        assert seen[0].tool_calls == (ToolCall("search_corpus"),)
        assert seen[1].tool_calls[0].arguments == '{"query":"x"}'
        assert seen[3].tool_calls[0].name == "web_search"
        assert len(seen[4].tool_calls) == 2
        assert seen[5].text == "text" and not seen[5].tool_calls
        assert seen[6] == ToolCompletion()
        assert seen[7].text == "and text" and seen[7].tool_calls

    def test_it_raises_when_called_more_often_than_scripted(self):
        fake = ScriptedToolCallingLLM([ScriptedToolCallingLLM.empty()])
        fake.complete_with_tools("s", "u", [SEARCH])
        with pytest.raises(AssertionError, match="scripted 1"):
            fake.complete_with_tools("s", "u", [SEARCH])

    def test_it_records_each_request_as_sent(self):
        fake = ScriptedToolCallingLLM(lambda request: ScriptedToolCallingLLM.empty())
        fake.complete_with_tools("sys", "usr", [SEARCH], timeout_seconds=3)

        (request,) = fake.tool_requests
        assert (request.system, request.user, request.tools) == ("sys", "usr", (SEARCH,))
        assert request.timeout_seconds == 3
