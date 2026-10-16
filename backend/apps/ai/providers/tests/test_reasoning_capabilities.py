"""IR-595: display-summary and continuation capabilities (spec §6.2).

An adapter declares what its vendor can return. A summary the vendor
supplies is a private candidate, never answer text; a continuation artifact
(an opaque signature) is echoed back verbatim and never rendered.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.ai.providers.dialects import GROQ, OPENROUTER
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.providers.ports import NO_CAPABILITIES, capabilities_of
from apps.ai.providers.tool_calling import (
    AssistantMessage,
    SystemMessage,
    ToolCall,
    ToolDefinition,
    ToolResultMessage,
    UserMessage,
)

pytestmark = pytest.mark.django_required

SIGNATURE = "opaque-signature-ZXhhbXBsZQ=="
DETAILS = [
    {"type": "reasoning.summary", "summary": "Compared the two evaluation settings."},
    {"type": "reasoning.encrypted", "data": SIGNATURE},
]
SEARCH = ToolDefinition(name="search_corpus", description="Search.")


class _Client:
    def __init__(self, message):
        self.calls: list[dict] = []
        self._message = message
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)], usage=None)


def vendor_message(**fields):
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="search_corpus", arguments="{}"))
    base = dict(content="", reasoning="raw working", tool_calls=[call], reasoning_details=DETAILS)
    return SimpleNamespace(**{**base, **fields})


def adapter(dialect, message):
    return OpenAICompatibleAdapter(client=_Client(message), model="m", dialect=dialect)


def test_capabilities_are_declared_per_dialect():
    assert not GROQ.capabilities.display_summary and not GROQ.capabilities.continuation_artifacts
    assert OPENROUTER.capabilities.display_summary and OPENROUTER.capabilities.continuation_artifacts
    assert capabilities_of(object()) == NO_CAPABILITIES


def test_a_supported_summary_is_a_private_candidate_and_the_signature_is_opaque():
    llm = adapter(OPENROUTER, vendor_message())
    completion = llm.complete_with_tools("s", "u", [SEARCH])

    assert completion.provider_summary == "Compared the two evaluation settings."
    assert completion.reasoning == "raw working" and completion.text == ""
    assert SIGNATURE not in completion.text + completion.reasoning + completion.provider_summary
    assert [artifact.field for artifact in completion.continuation] == ["reasoning_details"]
    assert SIGNATURE not in repr(completion)


def test_an_unsupported_vendor_yields_no_summary_and_no_artifacts():
    completion = adapter(GROQ, vendor_message()).complete_with_tools("s", "u", [SEARCH])
    assert completion.provider_summary == "" and completion.continuation == ()


def test_a_redacted_summary_is_absent_and_the_signature_still_round_trips():
    redacted = vendor_message(reasoning_details=[
        {"type": "reasoning.encrypted", "data": SIGNATURE}], reasoning="")
    llm = adapter(OPENROUTER, redacted)
    first = llm.complete_with_tools("s", "u", [SEARCH])
    assert first.provider_summary == ""

    llm.converse_with_tools(
        [SystemMessage("s"), UserMessage("u"), AssistantMessage.from_completion(first),
         ToolResultMessage("c1", "result")], [SEARCH])
    sent = llm._client.calls[-1]["messages"][2]
    assert sent["reasoning_details"] == [{"type": "reasoning.encrypted", "data": SIGNATURE}]


def test_an_assistant_message_without_artifacts_adds_no_field():
    llm = adapter(OPENROUTER, vendor_message(reasoning_details=None))
    llm.converse_with_tools(
        [UserMessage("u"), AssistantMessage(tool_calls=(ToolCall("search_corpus", "{}", "c1"),)),
         ToolResultMessage("c1", "r")], [SEARCH])
    assert "reasoning_details" not in llm._client.calls[-1]["messages"][1]
