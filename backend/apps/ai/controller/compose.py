"""The controller's hand-off to the shared ANSWER boundary (spec §2, §5).

`ReadyToCompose` is the seam: IR-594 replaces `AnswerComposer` with its
validating, repairing composer and keeps this input. Nothing here publishes
planner text or a tool result as the answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

from apps.ai.answers.citations import (
    GroundedAnswer, NO_SOURCES, PRESENTATION_RULES, SYSTEM_PROMPT, UNAVAILABLE, build_prompt,
)
from apps.ai.answers.service import UNAVAILABLE_TEXT, generate_cited, model_that_answered
from apps.ai.inference import InferenceTask
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.retrieval.ports import RetrievedChunk

ANSWER = "answer"
CLARIFY = "clarify"
EVIDENCE = "evidence"
GENERAL = "general"

NO_SOURCES_TEXT = "No readable sources were found for this question."

_EVIDENCE_RULES = (
    "\nAnswer the reader's actual request at the depth they ask for. Computed "
    "facts carry their population and are not passages: never cite them by number. "
    "Where a limitation is listed, say plainly what could not be checked; never "
    "claim a search was exhaustive."
)
_GENERAL_SYSTEM = (
    "You are IRIS, the research assistant for Cebu Institute of Technology - "
    "University.\nAnswer from the conversation and general knowledge only. Make "
    "no claim about any particular paper, the repository's holdings or research "
    "findings; where a reader could confuse general background with a paper "
    "finding, say it is general background.\n" + PRESENTATION_RULES
)
_CLARIFY_SYSTEM = (
    "You are IRIS, the research assistant for Cebu Institute of Technology - "
    "University.\nAsk the reader one short, focused question that resolves the "
    "ambiguity described. Do not answer the request and do not name papers that "
    "are not in the conversation."
)


@dataclass(frozen=True)
class ReadyToCompose:
    """What the controller gathered; everything here is currently readable."""

    question: str
    resolved_question: Optional[str]
    intent: str
    basis: str
    passages: tuple[RetrievedChunk, ...] = ()
    #: Envelope facts whose sources are still readable, with provenance.
    facts: tuple[dict, ...] = ()
    #: Codes only: why the run stopped and what tools could not do.
    limitations: tuple[str, ...] = ()
    stop_reason: str = "ready"
    history: Sequence = ()
    clarify_about: str = ""
    #: Repairs IR-594 may spend; reserved before research began.
    repair_attempts: int = 0
    degraded: bool = False
    pins: dict = field(default_factory=dict)


class Composer(Protocol):
    def compose(self, ready: ReadyToCompose) -> GroundedAnswer: ...


class AnswerComposer:
    """One ANSWER call, cited against the gathered passages."""

    def __init__(self, root):
        self.root = root

    def compose(self, ready: ReadyToCompose) -> GroundedAnswer:
        sources = tuple(ready.passages)
        if ready.intent == ANSWER and ready.basis == EVIDENCE and not sources and not ready.facts:
            # Empty, withheld and irrelevant all read the same (ADR-042).
            return GroundedAnswer(NO_SOURCES_TEXT, (), state=NO_SOURCES, degraded=ready.degraded)
        try:
            llm = self.root.llm_for(InferenceTask.ANSWER)
        except (LLMUnavailable, CircuitOpen):
            return _unavailable(sources)
        system, prompt = _prompt(ready, sources)
        generated = generate_cited(llm, prompt, sources, system=system)
        if generated is None:
            return _unavailable(sources)
        text, citations = generated
        return GroundedAnswer(
            text=text, citations=citations, sources=sources, model=model_that_answered(llm),
            degraded=ready.degraded or bool(ready.limitations),
        )


def _prompt(ready: ReadyToCompose, sources) -> tuple[str, str]:
    if ready.intent == CLARIFY:
        prompt = build_prompt(ready.question, (), history=ready.history)
        return _CLARIFY_SYSTEM, f"{prompt}\n\nAmbiguity: {ready.clarify_about or 'unspecified'}"
    if ready.basis == GENERAL and not sources:
        return _GENERAL_SYSTEM, build_prompt(ready.question, (), history=ready.history)
    prompt = build_prompt(ready.question, sources, history=ready.history)
    if ready.resolved_question and ready.resolved_question != ready.question:
        prompt += f"\n\nThe request, read in context: {ready.resolved_question}"
    if ready.facts:
        prompt += "\n\nComputed facts:\n" + json.dumps(list(ready.facts), ensure_ascii=False)
    if ready.limitations:
        prompt += "\n\nLimitations: " + ", ".join(ready.limitations)
    return SYSTEM_PROMPT + _EVIDENCE_RULES, prompt


def _unavailable(sources) -> GroundedAnswer:
    return GroundedAnswer(UNAVAILABLE_TEXT, (), state=UNAVAILABLE, sources=tuple(sources),
                          degraded=True)
