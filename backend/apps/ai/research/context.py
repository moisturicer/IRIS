"""What a run may touch, fixed by the request, never by a model (ADR-038 §2.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

from django.conf import settings

if TYPE_CHECKING:
    from apps.ai.composition import CompositionRoot
    from apps.ai.models.conversation import Conversation
    from apps.records.models import Record


class Lane(str, Enum):
    """The route outcomes of ADR-038 §3.2."""

    PASSAGE = "passage"
    LISTING = "listing"
    COUNT = "count"
    COMPARISON = "comparison"
    RESEARCH = "research"
    LANDSCAPE = "landscape"


@dataclass(frozen=True)
class Budget:
    """ADR-038 §5's limits, from settings. The planner (IR-502) enforces them."""

    max_outer_rounds: int
    max_calls_per_subtask: int
    max_tool_calls: int
    wall_clock_seconds: float
    max_prompt_tokens: int
    max_ledger_passages: int
    read_token_cap: int

    @classmethod
    def from_settings(cls) -> "Budget":
        return cls(
            max_outer_rounds=settings.AI_RESEARCH_MAX_OUTER_ROUNDS,
            max_calls_per_subtask=settings.AI_RESEARCH_MAX_CALLS_PER_SUBTASK,
            max_tool_calls=settings.AI_RESEARCH_MAX_TOOL_CALLS,
            wall_clock_seconds=settings.AI_RESEARCH_WALL_CLOCK_SECONDS,
            max_prompt_tokens=settings.AI_RESEARCH_MAX_PROMPT_TOKENS,
            max_ledger_passages=settings.AI_RESEARCH_MAX_LEDGER_PASSAGES,
            read_token_cap=settings.AI_RESEARCH_READ_TOKEN_CAP,
        )


@dataclass(frozen=True)
class RunContext:
    """Built by the view; tool schemas declare none of these fields."""

    user: object
    conversation_id: Optional[int]
    #: Paper Chat's Record. No argument can unset or widen it.
    scope_record_id: Optional[int]
    #: Whether a record's content may go to a vendor: the gate in force.
    permits: Callable[["Record"], bool]
    lane: Lane
    budget: Budget
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def for_request(
        cls,
        *,
        user,
        root: "CompositionRoot",
        lane: Lane,
        conversation: Optional["Conversation"] = None,
        budget: Optional[Budget] = None,
    ) -> "RunContext":
        return cls(
            user=user,
            conversation_id=conversation.pk if conversation else None,
            scope_record_id=conversation.record_id if conversation else None,
            permits=root.vendor_permits(),
            lane=Lane(lane),
            budget=budget or Budget.from_settings(),
        )
