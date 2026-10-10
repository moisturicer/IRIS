"""Raw completion facts for manual answer evaluation (IR-489)."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MeasuredCompletion:
    text: str
    reasoning: str = ""
    model: Optional[str] = None
    provider: Optional[str] = None
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cost: Optional[float] = None
    latency_seconds: float = 0.0
    response_id: Optional[str] = None
