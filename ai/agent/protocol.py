"""Typed model/tool exchange items and the run pin (IR-727, ADR-049 §14, §20).

A model turn is an ordered tuple of items. Nothing here drops, merges or
reorders them; an opaque continuation artifact hides its payload and may
only travel back under the pin binding that produced it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Union


class StopReason(str, Enum):
    END = "end"
    LENGTH = "length"
    TOOLS = "tool_calls"
    FILTERED = "content_filter"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    #: The raw argument string; never parsed here.
    arguments: str = "{}"


@dataclass(frozen=True)
class ToolGroup:
    """The calls of one model turn, in the order the model made them."""

    calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class Opaque:
    """A provider artifact required back unchanged; never read, rendered or logged."""

    #: `Pin.binding()` of the request that produced it.
    binding: tuple
    field: str
    payload: Any = field(default=None, repr=False, compare=False)


Item = Union[Text, ToolGroup, Opaque]


@dataclass(frozen=True)
class ModelTurn:
    items: tuple[Item, ...]
    stop: StopReason
    #: Whether the model reported reasoning; its text is never kept.
    reasoned: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Sources carried by text or opaque state derived from earlier evidence.
    dependencies: frozenset = frozenset()
    #: A persisted turn whose source manifest does not exist cannot be resent.
    unverified_provenance: bool = False

    @property
    def text(self) -> str:
        return "".join(i.text for i in self.items if isinstance(i, Text))


@dataclass(frozen=True)
class User:
    text: str
    #: Sources in application-supplied context, not the reader's own words.
    dependencies: frozenset = frozenset()
    #: Older derived context without a complete source manifest cannot be resent.
    unverified_provenance: bool = False


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    #: Original source revisions, kept outside the provider wire payload.
    #: Empty is not proof that arbitrary content is safe to send.
    dependencies: frozenset = frozenset()
    #: Set only by local tool/control paths that emit no Record content.
    control_only: bool = False
    #: An exact count or a list of titles: Record metadata, never Record text (IR-994).
    metadata_only: bool = False


Entry = Union[User, ModelTurn, ToolResult]


@dataclass(frozen=True)
class Pin:
    """Everything that fixes a run's interpretation; persisted at admission."""

    model: str
    endpoint: str
    adapter: str
    dialect: str
    prompt_version: str
    tool_version: str
    public_version: str
    state_version: str
    data_policy: str
    #: Capabilities the provider must have; none is ever substituted.
    requires: tuple[str, ...] = ()

    def __post_init__(self):
        for name, value in asdict(self).items():
            # The data policy is an optional label for the vendor's terms (IR-996).
            if name not in ("requires", "data_policy") and not value:
                raise ValueError(f"pin {name} is required")

    def as_dict(self) -> dict:
        return {**asdict(self), "requires": list(self.requires)}

    def binding(self) -> tuple:
        """What an opaque artifact stays valid under (ADR-049 §20)."""
        return (self.endpoint, self.model, self.dialect, self.prompt_version, self.tool_version)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True)
class AgentRequest:
    pin: Pin
    instructions: str
    history: tuple[Entry, ...]
    tools: tuple[ToolSpec, ...] = ()
    #: The completion cap sent, which admission reserved (IR-725).
    max_output_tokens: int | None = None
    #: "none" keeps the tools declared but closes research (IR-728).
    tool_choice: str = "auto"


class IncompatibleContinuation(Exception):
    """An opaque artifact would be sent under a pin binding that did not produce it."""


class BrokenExchange(Exception):
    """A tool group is not answered, completely and in order, before the next turn."""


class NotFinal(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def check_history(request: AgentRequest) -> None:
    """Refuse a history no provider could accept unchanged."""
    pending: list[str] = []
    for entry in request.history:
        if isinstance(entry, ToolResult):
            if not pending or pending[0] != entry.call_id:
                raise BrokenExchange(entry.call_id)
            pending.pop(0)
            continue
        if pending:
            raise BrokenExchange(pending[0])
        if isinstance(entry, ModelTurn):
            for item in entry.items:
                if isinstance(item, ToolGroup):
                    pending.extend(call.id for call in item.calls)
                elif isinstance(item, Opaque) and item.binding != request.pin.binding():
                    raise IncompatibleContinuation(item.field)


def final_answer(turn: ModelTurn) -> str:
    """The answer text of a completed turn; NotFinal for anything else."""
    if turn.stop is StopReason.MALFORMED:
        raise NotFinal("malformed")
    if turn.stop is StopReason.LENGTH:
        raise NotFinal("length")
    if turn.stop is StopReason.FILTERED:
        raise NotFinal("filtered")
    if turn.stop is StopReason.TOOLS or any(isinstance(i, ToolGroup) for i in turn.items):
        raise NotFinal("tool_only")
    text = turn.text.strip()
    if not text:
        reasoned = turn.reasoned or any(isinstance(i, Opaque) for i in turn.items)
        raise NotFinal("reasoning_only" if reasoned else "empty")
    return text
