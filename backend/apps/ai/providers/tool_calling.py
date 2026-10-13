"""The tool-calling port (IR-465, ADR-035 §2).

A second, separate port beside `LLMProvider`, because the grounded answer path
keeps `generate(system, user)` untouched (ADR-035 §2): the call that carries
retrieved text keeps the narrow port, and this one exists for a call that
carries none.

**Abstract, with no default body.** `LLMProvider.stream` is concrete and wraps
`generate`, which is safe there because a decorator that forgets to override it
still yields a correct answer. Here a default would be the opposite: every
resilience decorator implements the port methods explicitly, so a defaulted
method would be bypassed by all of them and the feature would silently never run
in a real configuration. An abstract method makes forgetting a decorator a
`TypeError` at construction, not a missing feature in production.

**Two forms, both abstract.** `complete_with_tools` is one request and one
completion, which is all the evidence decision needs (ADR-035 §4).
`converse_with_tools` takes a message list carrying the model's earlier tool
calls and their results, for the research planner (IR-511, ADR-038 §4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Union


@dataclass(frozen=True)
class ToolDefinition:
    """A tool offered to the model: a name, a description and a JSON schema."""

    name: str
    description: str
    #: A JSON Schema object. The default is the empty one, which is what a
    #: tool declaring no parameters sends.
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass(frozen=True)
class ToolCall:
    """One call the model made, exactly as the vendor reported it.

    `arguments` is the raw string. It is **not parsed here**: reading it is a
    decision for the caller, and the evidence decision (ADR-035 §2) never reads
    it at all.
    """

    name: str
    arguments: str = ""
    #: The vendor's id for this call; a tool result answers it by this id.
    id: str = ""


@dataclass(frozen=True)
class ToolCompletion:
    """What a tool-offering call returned: text, reasoning and raw calls.

    `text` and `reasoning` are separate channels, never joined, for the same
    reason `StreamDelta` keeps them apart (IR-327). Neither is ever retained by
    the evidence decision (ADR-035 §10).
    """

    text: str = ""
    reasoning: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    #: Vendor-reported token counts, or `None` when the vendor said nothing.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass(frozen=True)
class SystemMessage:
    content: str


@dataclass(frozen=True)
class UserMessage:
    content: str


@dataclass(frozen=True)
class AssistantMessage:
    """An earlier model turn, fed back. Reasoning is never sent back."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    @classmethod
    def from_completion(cls, completion: ToolCompletion) -> "AssistantMessage":
        return cls(text=completion.text, tool_calls=completion.tool_calls)


@dataclass(frozen=True)
class ToolResultMessage:
    """The result of one tool call, answering it by its id."""

    tool_call_id: str
    content: str


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolResultMessage]


class ToolCallingLLM(ABC):
    """A provider that can be offered tools and report what it called."""

    @abstractmethod
    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[ToolDefinition],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ToolCompletion:
        """Answer `user` under `system`, with `tools` on offer.

        `timeout_seconds` bounds the vendor call. A decision that has to fall
        back to retrieval on a timeout (ADR-035 §3) needs the timeout to be
        reachable, and the vendor client's own default is minutes.

        Raises the same `LLMUnavailable` `generate` does, with the same `kind`.
        An empty or malformed completion is **returned, not raised**: whether
        it is an error is the caller's reading, and the evidence decision
        routes each shape to its own reason code.
        """

    @abstractmethod
    def converse_with_tools(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ToolCompletion:
        """Continue `messages`, with `tools` on offer (IR-511).

        Same failure contract as `complete_with_tools`. Executing a returned
        call and appending its result is the caller's job.
        """
