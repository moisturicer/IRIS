"""Application-owned lane workflows; models never choose listing row identity."""

from dataclasses import replace
import logging
import re
import time

from django.conf import settings

from apps.ai.admission.scope import stepwise
from apps.ai.answers.citations import (
    GroundedAnswer, NO_SOURCES, SYSTEM_PROMPT, UNAVAILABLE, build_prompt,
)
from apps.ai.answers.events import INCLUDED
from apps.ai.answers.service import generate_cited, model_that_answered, UNAVAILABLE_TEXT
from apps.ai.inference import InferenceTask
from apps.ai.providers.deadline import model_call_deadline
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.research.context import RunContext
from apps.ai.research.listing import screen_listing
from apps.ai.research.planner import ResearchPlanner
from apps.ai.research.registry import ToolRun
from apps.ai.research.titles import exact_title_matches, title_key
from apps.ai.research.tools.common import disclosable, readable_records
from apps.ai.research.tools.records import _relevant
from apps.ai.research.schema import ArgumentsRejected
from apps.ai.research.budget import BudgetExhausted
from apps.ai.research import metadata_count
from apps.ai.resilience.circuit import CircuitOpen

logger = logging.getLogger(__name__)


def _empty(text="No readable sources were found for this question."):
    return GroundedAnswer(text=text, citations=(), state=NO_SOURCES)


def _unavailable(text="The requested corpus workflow is unavailable right now.", sources=()):
    return GroundedAnswer(text=text, citations=(), state=UNAVAILABLE,
                          sources=tuple(sources), degraded=True)


def _screened_events(run, question, *, count):
    """Preview, screen and describe at most twenty candidates (IR-546, IR-547).

    Yields the candidate events; returns `(answer, listing)`. The answer text
    is the listing's wording, written in code, and a count is the include
    decisions among those candidates. No model writes a sentence or a number.
    """
    try:
        outcome = yield from screen_listing(run, question, count=count)
    except Exception as exc:
        # Selection or the final read failed: say so, never "nothing found".
        logger.warning("listing failed", extra={"run_id": run.ctx.run_id, "error": type(exc).__name__})
        return _unavailable(), None
    listing = outcome.wire()
    text = listing["wording"]
    if not any(c.state == INCLUDED for c in outcome.candidates):
        return _empty(text), listing
    return GroundedAnswer(text=text, citations=(), degraded=outcome.degraded), listing


def _listing_events(run, question):
    return (yield from _screened_events(run, question, count=False))


def _count_events(run, question):
    # A metadata inventory question is a database count and uses no model
    # (IR-543); anything with a topic in it is a screened subset count (IR-547).
    metadata = metadata_count.answer(run.ctx, question)
    if metadata is not None:
        return metadata
    return (yield from _screened_events(run, question, count=True))


def _named_records(ctx, question):
    """Resolve exact quoted titles or complete known titles in reader text."""
    quoted = [match[0] or match[1] for match in re.findall(r'"([^"\n]+)"|“([^”\n]+)”', question)]
    records = list(readable_records(ctx).only("pk", "title"))
    lowered = question.casefold()
    exact = {r.pk for title in quoted for r in exact_title_matches(records, title)}
    matched = [record for record in records if record.title and (
        record.pk in exact
        or re.search(r"(?<!\w)" + re.escape(record.title.casefold()) + r"(?!\w)", lowered)
    )]
    known = {title_key(record.title) for record in matched}
    missing = [title for title in quoted if title_key(title) not in known]
    remainder = re.sub(r'"[^"\n]+"|“[^”\n]+”', "", question)
    for record in sorted(matched, key=lambda record: len(record.title), reverse=True):
        remainder = re.sub(re.escape(record.title), "", remainder, flags=re.IGNORECASE)
    # A trailing comparison criterion is not another paper title.
    remainder = re.split(r"\b(?:on|in terms of|regarding|focusing on|by|for|their)\b",
                         remainder, maxsplit=1, flags=re.IGNORECASE)[0]
    # Unresolved text may be another title, including mixed quoted/unquoted
    # input. Ask for explicit names before comparing an ambiguous subset.
    remainder = re.sub(r"\b(compare|comparison|contrast|with|and|vs|versus|to|of|the|papers|paper)\b", "", remainder, flags=re.IGNORECASE)
    if remainder.strip(" ,.;:?!"):
        return [], [remainder.strip(" ,.;:?!")]
    return matched, missing


def _comparison(run, question, maximum):
    records, missing = _named_records(run.ctx, question)
    if not records:
        text = "No readable named papers were resolved. Name each paper by its full title."
        if missing:
            text += " No readable evidence was found for: " + "; ".join(missing) + "."
        return _empty(text), None
    if len(records) > maximum:
        return _empty("There are more named papers than the source limit permits. Compare fewer papers."), None
    groups, degraded = [], False
    for record in records:
        if not run.ctx.permits(record):
            missing.append(record.title)
            continue
        result = run.root.retriever(records=frozenset({record.pk})).retrieve(
            question, run.ctx.user, limit=maximum,
        )
        degraded = degraded or result.degraded
        allowed = disclosable(run.ctx, {record.pk})
        passages = [p for p in run.root.source_selection(maximum).apply(_relevant(result))
                    if p.record_id == record.pk and p.record_id in allowed]
        if passages:
            groups.append(passages)
        else:
            missing.append(record.title)
    if not groups:
        return _empty("No readable passage evidence was found for the named papers: "
                      + "; ".join(missing) + "."), None
    # Reserve one slot per paper before adding any second passage.
    sources = [group[0] for group in groups]
    for depth in range(1, maximum):
        for group in groups:
            if len(sources) < maximum and depth < len(group):
                sources.append(group[depth])
    current = disclosable(run.ctx, [p.record_id for p in sources])
    if any(p.record_id not in current for p in sources):
        return _unavailable("The readable papers changed during comparison. Please try again."), None
    missing_note = ("\n\nNo readable passage evidence was found for: " + "; ".join(missing) + ".") if missing else ""
    try:
        llm = run.root.llm_for(InferenceTask.ANSWER)
    except (LLMUnavailable, CircuitOpen):
        return _unavailable(UNAVAILABLE_TEXT + missing_note, sources), None
    generated = generate_cited(llm, build_prompt(question, sources), sources,
        system=SYSTEM_PROMPT + "\nCompare only the named papers with supplied evidence. "
        "Cite at least one passage from every supplied paper. Do not infer findings for missing papers.")
    if generated is None:
        return _unavailable(UNAVAILABLE_TEXT + missing_note, sources), None
    text, citations = generated
    current = disclosable(run.ctx, [p.record_id for p in sources])
    if any(p.record_id not in current for p in sources):
        return _unavailable("The readable papers changed during comparison. Please try again."), None
    required = {p.record_id for p in sources}
    if not required.issubset({citation.record_id for citation in citations}):
        return _unavailable("The comparison could not be verified for every named paper. "
                            "The retrieved passages can be read directly." + missing_note, sources), None
    if missing:
        text += "\n\nNo readable passage evidence was found for: " + "; ".join(missing) + "."
    return GroundedAnswer(text=text, citations=citations, sources=tuple(sources),
                          degraded=degraded or bool(missing), model=model_that_answered(llm)), None


def _context(lane, user, *, root, conversation, scope_record, max_sources, history_before_turn_id):
    if max_sources < 1:
        raise ValueError("max_sources must be positive")
    ctx = RunContext.for_request(user=user, root=root, lane=lane, conversation=conversation)
    return replace(ctx, scope_record_id=scope_record.pk if scope_record is not None else None,
                   history_before_turn_id=history_before_turn_id)


def research_run(question, user, *, root, conversation=None, scope_record=None,
                 max_sources=8, history_before_turn_id=None):
    """Yield the planner's steps; return its `ResearchAnswer` (IR-504)."""
    ctx = _context("research", user, root=root, conversation=conversation,
                   scope_record=scope_record, max_sources=max_sources,
                   history_before_turn_id=history_before_turn_id)
    ctx = replace(ctx, budget=replace(ctx.budget,
        max_ledger_passages=min(ctx.budget.max_ledger_passages, max_sources)))
    return (yield from ResearchPlanner(root).run(question, ctx))


def lane_events(lane, question, user, *, root, conversation=None, scope_record=None,
                max_sources=8, history_before_turn_id=None, clock=time.monotonic):
    """Run a bounded corpus workflow, yielding what a reader can watch.

    A listing and a topic count yield their candidates (IR-546, IR-547); a
    comparison returns at once. Returns `(answer, listing)`. Research goes
    through `research_run`.
    """
    if lane not in ("listing", "count", "comparison"):
        raise ValueError(f"No application workflow for lane {lane!r}")
    ctx = _context(lane, user, root=root, conversation=conversation, scope_record=scope_record,
                   max_sources=max_sources, history_before_turn_id=history_before_turn_id)
    run = ToolRun.start(ctx, root)
    seconds = ctx.budget.wall_clock_seconds
    if lane in ("listing", "count"):
        seconds = min(seconds, settings.AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS)
    end = clock() + seconds

    def deadline():
        # One end time, re-entered at every step: a generator never holds a
        # `with` open across its yields (see `admission.scope`).
        return model_call_deadline(max(0.0, end - clock()), clock=clock)

    try:
        if lane == "listing":
            return (yield from stepwise(_listing_events(run, question), deadline))
        if lane == "count":
            return (yield from stepwise(_count_events(run, question), deadline))
        with deadline():
            return _comparison(run, question, max_sources)
    except (LLMUnavailable, CircuitOpen, TimeoutError, ArgumentsRejected, BudgetExhausted):
        return _unavailable(), None
