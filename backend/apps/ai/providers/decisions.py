"""The decision-model port (IR-482).

A decision model answers named typed questions about a state and returns
probabilities, never text. It is not an `LLMProvider` (nothing here generates)
and not an ADR-036 Inference task, so it has its own small port rather than a
widened one. Today it serves the evidence-decision evaluation only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from apps.ai.providers.errors import ErrorKind


class DecisionUnavailable(RuntimeError):
    """The vendor could not answer: a timeout, rate limit, outage or refusal."""

    def __init__(self, message: str, kind: ErrorKind = ErrorKind.UNKNOWN) -> None:
        super().__init__(message)
        self.kind = kind


class DecisionMalformed(RuntimeError):
    """The vendor answered, in a shape other than the one promised."""


@dataclass(frozen=True)
class NoulAnswer:
    """The probability that the condition holds, and how it was produced."""

    probability: float
    model: str = ""
    input_tokens: Optional[int] = None
    cost_usd: Optional[float] = None


@dataclass(frozen=True)
class NoulQuestion:
    instructions: str
    criteria: Mapping[str, str]


class DecisionModel(ABC):
    """Abstract on purpose: no default body for a decorator to bypass."""

    @abstractmethod
    def noul(
        self,
        state: Any,
        *,
        instructions: str,
        criteria: Mapping[str, str],
        timeout_seconds: Optional[float] = None,
    ) -> NoulAnswer:
        """The probability, from 0 to 1, that the condition holds for `state`."""

    def nouls(
        self, state: Any, *, questions: Mapping[str, NoulQuestion],
        timeout_seconds: Optional[float] = None,
    ) -> Mapping[str, NoulAnswer]:
        """Score named questions. The default supports providers with one question per call."""
        return {
            name: self.noul(
                state, instructions=question.instructions,
                criteria=question.criteria, timeout_seconds=timeout_seconds,
            )
            for name, question in questions.items()
        }


class ScriptedDecisionModel(DecisionModel):
    """Deterministic stand-in: each step is a probability, a `NoulAnswer` or an
    exception to raise. Records every request it was sent."""

    def __init__(self, *steps: Any, model: str = "scripted/decision") -> None:
        self._steps = list(steps)
        self._model = model
        self.calls: list[dict[str, Any]] = []

    def noul(self, state, *, instructions, criteria, timeout_seconds=None):
        self.calls.append(
            {
                "state": state,
                "instructions": instructions,
                "criteria": dict(criteria),
                "timeout_seconds": timeout_seconds,
            }
        )
        step = self._steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, NoulAnswer):
            return step
        return NoulAnswer(probability=float(step), model=self._model)

    def nouls(self, state, *, questions, timeout_seconds=None):
        self.calls.append({
            "state": state,
            "questions": dict(questions),
            "timeout_seconds": timeout_seconds,
        })
        step = self._steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        if not isinstance(step, Mapping) or set(step) != set(questions):
            raise DecisionMalformed("scripted answer has the wrong question names")
        return {
            name: value if isinstance(value, NoulAnswer) else NoulAnswer(float(value), self._model)
            for name, value in step.items()
        }
