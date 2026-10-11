"""Tool calling that carries a conversation (IR-511, ADR-038 §5).

The planner feeds the model's own tool calls and their results back, so the
port takes a message list. No vendor account and no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.ai.providers.fakes import ConversationRequest, ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.providers.tool_calling import (
    AssistantMessage,
    SystemMessage,
    ToolCall,
    ToolCallingLLM,
    ToolCompletion,
    ToolDefinition,
    ToolResultMessage,
    UserMessage,
)

pytestmark = pytest.mark.django_required

SEARCH = ToolDefinition(name="search_corpus", description="Search the corpus.")


class _Client:
    def __init__(self, messages):
        self.calls: list[dict] = []
        self._messages = list(messages)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = self._messages.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)], usage=None
        )


def _vendor_call(call_id, name="search_corpus", arguments='{"q": "x"}'):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=arguments)
    )


def _conversation(first: ToolCompletion) -> list:
    return [
        SystemMessage("rules"),
        UserMessage("question"),
        AssistantMessage.from_completion(first),
        *(
            ToolResultMessage(call.id, f"result for {call.id}")
            for call in first.tool_calls
        ),
    ]


class ThePortTests:
    def test_a_provider_missing_the_conversation_method_cannot_be_built(self):
        class OneShotOnly(ToolCallingLLM):
            def complete_with_tools(self, system, user, tools, *, timeout_seconds=None):
                return ToolCompletion()

        with pytest.raises(TypeError, match="converse_with_tools"):
            OneShotOnly()

    def test_an_assistant_message_keeps_the_calls_and_drops_the_reasoning(self):
        completion = ToolCompletion(
            text="thinking aloud",
            reasoning="private",
            tool_calls=(ToolCall("search_corpus", "{}", id="c1"),),
        )

        message = AssistantMessage.from_completion(completion)

        assert message == AssistantMessage(
            text="thinking aloud",
            tool_calls=(ToolCall("search_corpus", "{}", id="c1"),),
        )

    def test_a_tool_call_built_without_an_id_still_compares_as_before(self):
        assert ToolCall("search_corpus") == ToolCall("search_corpus", "", "")


class TheAdapterCarriesTheConversationTests:
    def test_call_result_call_reply_round_trips_with_the_vendors_ids(self):
        client = _Client(
            [
                SimpleNamespace(content=None, tool_calls=[_vendor_call("call_A")]),
                SimpleNamespace(
                    content=None,
                    tool_calls=[_vendor_call("call_B"), _vendor_call("call_C")],
                ),
                SimpleNamespace(content="The answer.", tool_calls=None),
            ]
        )
        adapter = OpenAICompatibleAdapter(client=client, model="m")

        messages = [SystemMessage("rules"), UserMessage("question")]
        first = adapter.converse_with_tools(messages, [SEARCH])
        messages += [
            AssistantMessage.from_completion(first),
            ToolResultMessage("call_A", "three papers"),
        ]
        second = adapter.converse_with_tools(messages, [SEARCH])
        messages += [
            AssistantMessage.from_completion(second),
            ToolResultMessage("call_B", "one paper"),
            ToolResultMessage("call_C", "none"),
        ]
        reply = adapter.converse_with_tools(messages, [SEARCH])

        assert [c.id for c in first.tool_calls] == ["call_A"]
        assert [c.id for c in second.tool_calls] == ["call_B", "call_C"]
        assert reply.text == "The answer."
        assert client.calls[2]["messages"] == [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "question"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_A",
                        "type": "function",
                        "function": {"name": "search_corpus", "arguments": '{"q": "x"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_A", "content": "three papers"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_B",
                        "type": "function",
                        "function": {"name": "search_corpus", "arguments": '{"q": "x"}'},
                    },
                    {
                        "id": "call_C",
                        "type": "function",
                        "function": {"name": "search_corpus", "arguments": '{"q": "x"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_B", "content": "one paper"},
            {"role": "tool", "tool_call_id": "call_C", "content": "none"},
        ]

    def test_an_assistant_turn_with_text_and_no_calls_sends_no_tool_calls_key(self):
        client = _Client([SimpleNamespace(content="ok", tool_calls=None)])
        adapter = OpenAICompatibleAdapter(client=client)

        adapter.converse_with_tools(
            [UserMessage("q"), AssistantMessage(text="earlier"), UserMessage("more")],
            [SEARCH],
        )

        assert client.calls[0]["messages"][1] == {
            "role": "assistant",
            "content": "earlier",
        }

    def test_the_one_shot_form_sends_what_it_always_sent(self):
        client = _Client([SimpleNamespace(content="t", tool_calls=None)] * 2)
        adapter = OpenAICompatibleAdapter(client=client)

        adapter.complete_with_tools("s", "u", [SEARCH], timeout_seconds=5)
        adapter.converse_with_tools(
            [SystemMessage("s"), UserMessage("u")], [SEARCH], timeout_seconds=5
        )

        assert client.calls[0] == client.calls[1]


class TheScriptedFakeConversesTests:
    def test_it_records_each_conversation_and_shares_one_script(self):
        fake = ScriptedToolCallingLLM(
            [
                ScriptedToolCallingLLM.calling(call_id="c1"),
                ScriptedToolCallingLLM.answering("done"),
            ]
        )

        first = fake.converse_with_tools([UserMessage("q")], [SEARCH], timeout_seconds=4)
        reply = fake.converse_with_tools(_conversation(first), [SEARCH])

        assert first.tool_calls[0].id == "c1"
        assert reply.text == "done"
        assert fake.conversation_requests[0] == ConversationRequest(
            messages=(UserMessage("q"),), tools=(SEARCH,), timeout_seconds=4
        )
        assert fake.conversation_requests[1].messages[-1] == ToolResultMessage(
            "c1", "result for c1"
        )
        assert fake.tool_requests == []
