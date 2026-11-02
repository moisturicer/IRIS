"""Research bounds and the run allowance's answer reserve (IR-728, ADR-049 §12, §14, §16).

Gathering stops while the final answer and one repair still fit. Every
bound is required; none here is a production value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Mapping, Optional

from ai.admission.limits import Price, micros
from ai.runs.config import DEPTHS


@dataclass(frozen=True)
class Bounds:
    #: Model turns that may gather evidence.
    max_steps: int
    max_tool_calls: int
    #: Consecutive gathering turns that found nothing new.
    max_no_progress: int
    #: Time held back for the final answer and one repair.
    final_seconds: float
    #: Earlier Turns carried into the Conversation.
    history_turns: int

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "history_turns" and value == 0:
                continue
            if not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0):
                raise ValueError(f"bound {f.name} must be positive")


def profiles(by_depth: Mapping[str, Bounds]) -> dict[str, Bounds]:
    """One configured profile per depth; "deep" is the more thorough one."""
    if set(by_depth) != set(DEPTHS):
        raise ValueError(f"profiles are required for exactly {', '.join(DEPTHS)}")
    return dict(by_depth)


class Budget:
    """What the run has spent and whether planned requests still fit its allowance."""

    def __init__(self, allowance: Mapping, price: Optional[Price]):
        self.max_input = int(allowance["max_input_tokens"])
        self.max_output = int(allowance["max_output_tokens"])
        self.max_cost = micros(float(allowance["max_cost_usd"]))
        #: None bills nothing.
        self.price = price
        self.input = 0
        self.output = 0
        self.reported = 0

    def spend(self, turn, estimated_input: int, cap: int) -> None:
        """Missing usage counts at its estimate and cap, never as zero."""
        self.input += estimated_input if turn.input_tokens is None else turn.input_tokens
        self.output += cap if turn.output_tokens is None else turn.output_tokens
        self.reported += (turn.input_tokens or 0) + (turn.output_tokens or 0)

    def fits(self, planned) -> bool:
        tokens_in = self.input + sum(i for i, _ in planned)
        tokens_out = self.output + sum(o for _, o in planned)
        if tokens_in > self.max_input or tokens_out > self.max_output:
            return False
        if self.price is None:
            return True
        return math.ceil(tokens_in * self.price.input + tokens_out * self.price.output) <= self.max_cost

    def can_gather(self, occupancy: int, cap: int, reserves) -> bool:
        """This gathering turn, then a final answer and one repair after its result."""
        final = occupancy + cap + reserves.next_result_tokens
        return self.fits([(occupancy, cap), (final, cap), (final + cap + reserves.repair_tokens, cap)])

    def can_finish(self, occupancy: int, cap: int, reserves) -> bool:
        return self.fits([(occupancy, cap), (occupancy + cap + reserves.repair_tokens, cap)])
