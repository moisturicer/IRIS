"""The controller's hand-off to the shared ANSWER boundary (spec §2, §5).

`AnswerComposer` drafts, validates (`answers/assurance.py`), spends at most
one repair, then keeps only supported sentences (ADR-042). Nothing here
publishes planner text or a tool result as the answer, and the answer is
returned whole: no unvalidated token reaches a reader.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence

from apps.ai.admission import scope as admission_scope
from apps.ai.answers.assurance import FENCED, check, parse_draft, safe_summary, units, without_units
from apps.ai.answers.citations import GroundedAnswer, NO_SOURCES, UNAVAILABLE, build_prompt, parse_citations
from apps.ai.answers.reasoning import without_leaked_reasoning
from apps.ai.answers.service import UNAVAILABLE_TEXT, model_that_answered
from apps.ai.inference import InferenceTask
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.retrieval.ports import RetrievedChunk

logger = logging.getLogger(__name__)

ANSWER = "answer"
CLARIFY = "clarify"
EVIDENCE = "evidence"
GENERAL = "general"

NO_SOURCES_TEXT = "No readable sources were found for this question."
UNSUPPORTED_TEXT = (
    "No answer could be written that the sources support, so none is shown. "
    "The sources found are listed below and can be read directly."
)
LEFT_OUT = "Some statements were left out because the cited sources did not support them."
WITHDRAWN = "Some statements were left out because a source is no longer available."

_IDENTITY = "You are IRIS, the research assistant for Cebu Institute of Technology - University.\n"
PRESENTATION = (
    "Format the answer as GitHub-flavoured Markdown. Use prose, bullets or a table as "
    "the task needs; a table may compare two or more papers. Use '## ' headings only "
    "for a multi-part answer.\n"
    "Write mathematics as LaTeX: $x_i$ inline and $$...$$ on its own lines.\n"
    "Never write an image, a link or a URL."
)
ANSWER_POLICY = _IDENTITY + (
    "Answer the reader's actual request first, at the depth they ask for; a request "
    "for detail deserves a detailed, structured answer.\n"
    "Paper findings and repository facts come only from the numbered sources and the "
    "computed facts. Cite sources inline as [1] or [2] with nothing else inside the "
    "brackets. Computed facts are not sources: never cite them by number.\n"
    "Choose sensibly from the conversation instead of asking for exact titles. Explain "
    "why papers are relevant, and whether their results are comparable, from the evidence.\n"
    "Keep findings, interpretation and general background apart where it matters, and "
    "say when something is general background.\n"
    "Preserve uncertainty, missing data, disagreement and limits of comparability. Where "
    "a limitation is listed, say plainly what could not be checked, and distinguish a "
    "field a paper does not report, a bounded search that found no match, and a service "
    "that could not be used. Never call a search exhaustive unless an exact count "
    "establishes it.\n"
    "Never invent a title, author, finding or number. Never describe your tools, "
    "searches, steps or process, and never apologise for them.\n"
) + PRESENTATION
CONTRACT = (
    "\nAfter the answer you may add one fenced block tagged bindings holding JSON, "
    "which is removed before the reader sees the answer:\n"
    "```bindings\n"
    '{"facts": [{"value": 92.4, "metric": "accuracy", "source": 1}, '
    '{"value": 12, "fact": "total"}], '
    '"papers": [{"title": "exact source title", "source": 1}], "summary": "..."}\n'
    "```\n"
    "Under facts, bind each research number you state to the source that reports it "
    "(with its metric) or to the computed fact's name. Under papers, bind each paper "
    "you name to its source. summary is optional: one to three sentences on the "
    "assumptions and evidence limits behind the answer, with no citations, no new "
    "numbers and no account of your process; omit it when there is nothing useful to say."
)
_GENERAL_SYSTEM = _IDENTITY + (
    "Answer from the conversation and general knowledge only. Make no claim about any "
    "particular paper, the repository's holdings or research findings; where a reader "
    "could confuse general background with a paper finding, say it is general background.\n"
) + PRESENTATION
_CLARIFY_SYSTEM = _IDENTITY + (
    "Ask the reader one short, focused question that resolves the ambiguity described. "
    "Do not answer the request and do not name papers that are not in the conversation."
)
_HELP = {
    "unknown_citation": "cites a source number or label that does not exist",
    "unsupported_number": "states a number that its cited sources and the computed facts do not contain",
    "unsupported_count": "states a count that no computed fact or cited source supports",
    "wrong_binding": "binds a value or title to the wrong source, metric or fact",
    "completeness_overclaim": "claims a complete or exhaustive result that the evidence does not establish",
    "malformed_bindings": "has a bindings block that is not valid JSON in the required shape",
}


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
    #: Repairs the composer may spend; reserved before research began.
    repair_attempts: int = 0
    degraded: bool = False
    pins: dict = field(default_factory=dict)
    #: Chunk ids among the given sources still readable and current; None
    #: treats every source as current.
    current: Optional[Callable[[Sequence[RetrievedChunk]], set]] = None


class Composer(Protocol):
    def compose(self, ready: ReadyToCompose) -> GroundedAnswer: ...


class AnswerComposer:
    """Draft, validate, repair at most once, then keep what is supported."""

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
            return _unavailable(_live(ready, sources))
        system, prompt = _prompt(ready, sources)
        raw = _draft(llm, system, prompt)
        if raw is None:
            return _unavailable(_live(ready, sources))
        draft, issues, live = self._checked(ready, raw, sources)
        repaired = False
        repairable = [i for i in issues if i.code not in FENCED]
        if (repairable and not any(i.code in FENCED for i in issues)
                and ready.repair_attempts > 0 and not cancelled()):
            again = _draft(llm, system, prompt + _feedback(draft, issues))
            if again is not None:
                draft, issues, live = self._checked(ready, again, sources)
                repaired = True
        drop = {i.unit for i in issues if i.unit is not None}
        text = without_units(draft.text, drop)
        if not text:
            return GroundedAnswer(UNSUPPORTED_TEXT, (), state=UNAVAILABLE, sources=live,
                                  degraded=True, validation=_codes(issues, repaired))
        notes = [WITHDRAWN if any(i.code in FENCED for i in issues if i.unit is not None) else "",
                 LEFT_OUT if any(i.code not in FENCED for i in issues if i.unit is not None) else ""]
        text = "\n\n".join([text, *filter(None, notes)])
        text, citations = parse_citations(text, sources)
        return GroundedAnswer(
            text=text, citations=citations, sources=live, model=model_that_answered(llm),
            degraded=ready.degraded or bool(ready.limitations) or bool(issues),
            reasoning_summary="" if issues else safe_summary(draft.summary, text),
            validation=_codes(issues, repaired),
        )

    def _checked(self, ready, raw, sources):
        draft, live = parse_draft(raw), _live(ready, sources)
        issues = check(draft, sources, facts=ready.facts, limitations=ready.limitations,
                       live={s.chunk_id for s in live})
        return draft, issues, live


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
    return ANSWER_POLICY + CONTRACT, prompt


def _draft(llm, system: str, prompt: str) -> Optional[str]:
    """One completion, or None on an outage or a reasoning-only reply."""
    try:
        raw = llm.generate(system=system, user=prompt)
    except (LLMUnavailable, CircuitOpen, TimeoutError) as exc:
        logger.warning("controller answer unavailable: %s", exc)
        return None
    raw = without_leaked_reasoning(raw or "")
    return raw if raw.strip() else None


def _feedback(draft, issues) -> str:
    """Codes and the draft's own failing sentences; no withheld content."""
    parts = units(draft.text)
    lines = []
    for issue in issues:
        where = f': "{parts[issue.unit].text[:300]}"' if issue.unit is not None else ""
        lines.append(f"- The draft {_HELP.get(issue.code, issue.code)}{where}")
    return (
        "\n\nYour previous draft:\n" + draft.text
        + "\n\nIt failed these checks:\n" + "\n".join(dict.fromkeys(lines))
        + "\nRevise it once: correct or remove only these statements, keep every supported "
          "statement, and return the whole answer with its bindings block."
    )


def _live(ready, sources) -> tuple:
    if ready.current is None or not sources:
        return tuple(sources)
    keep = ready.current(sources)
    return tuple(s for s in sources if s.chunk_id in keep)


def _codes(issues, repaired) -> tuple[str, ...]:
    codes = sorted({i.code for i in issues})
    return tuple((["repaired"] if repaired else []) + codes)


def cancelled() -> bool:
    current = admission_scope.current_run()
    return current is not None and current.halted()


def _unavailable(sources) -> GroundedAnswer:
    return GroundedAnswer(UNAVAILABLE_TEXT, (), state=UNAVAILABLE, sources=tuple(sources),
                          degraded=True)
