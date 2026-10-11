"""Application-owned lane workflows; models never choose listing row identity."""

from dataclasses import replace
import re

from apps.ai.answers.citations import (
    GroundedAnswer, NO_SOURCES, SYSTEM_PROMPT, UNAVAILABLE, build_prompt,
)
from apps.ai.answers.service import generate_cited, model_that_answered, UNAVAILABLE_TEXT
from apps.ai.inference import InferenceTask
from apps.ai.providers.deadline import model_call_deadline
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.research.context import RunContext
from apps.ai.research.planner import ResearchPlanner
from apps.ai.research.registry import ToolRun, research_tools
from apps.ai.research.results import ToolStatus
from apps.ai.research.tools.common import disclosable, readable_records
from apps.ai.research.tools.records import _relevant
from apps.ai.research.schema import ArgumentsRejected
from apps.ai.research.budget import BudgetExhausted
from apps.ai.research.workflows import topic_count
from apps.ai.resilience.circuit import CircuitOpen

LIST_WORDING = "These are matches found, not a complete list of the papers you can see."
SUCCESS = (ToolStatus.OK, ToolStatus.EMPTY, ToolStatus.DEGRADED)


def _empty(text="No readable sources were found for this question."):
    return GroundedAnswer(text=text, citations=(), state=NO_SOURCES)


def _unavailable(text="The requested corpus workflow is unavailable right now.", sources=()):
    return GroundedAnswer(text=text, citations=(), state=UNAVAILABLE,
                          sources=tuple(sources), degraded=True)


def _rows(run, evidence, handles):
    """Recheck both gates and use current database titles, never model titles."""
    candidates = {e.handle: e for e in evidence}
    allowed = disclosable(run.ctx, [e.record_id for e in candidates.values()])
    rows, seen = [], set()
    for handle in handles:
        item = candidates.get(handle)
        if item is None or item.record_id not in allowed or item.record_id in seen:
            continue
        record = allowed[item.record_id]
        if item.record_title != record.title or item.text != record.abstract:
            continue
        seen.add(item.record_id)
        rows.append({"record_id": record.pk, "title": record.title})
    return rows


def _listing(run, question, maximum):
    registry = research_tools()
    found = registry.call(run, "find_records", {"topic": question, "k": min(10, maximum)})
    if found.status not in SUCCESS:
        return _unavailable(), None
    if not found.evidence:
        return _empty(), {"completeness": "matches_found", "wording": LIST_WORDING, "records": []}
    ids = tuple(e.record_id for e in found.evidence)
    screened = registry.call(replace(run, screen_candidate_ids=ids),
                             "screen_records", {"criterion": question})
    if screened.status not in SUCCESS:
        return _unavailable(), None
    included = [row["record"] for row in screened.detail.get("rows", ())
                if row.get("decision") == "include"]
    # A screened handle must also belong to the database finder result.
    rows = _rows(run, found.evidence, included)[:maximum]
    wording = LIST_WORDING
    if screened.detail.get("unassessed", 0):
        wording += " Some candidates could not be assessed."
    listing = {"completeness": "matches_found", "wording": wording, "records": rows}
    if not rows:
        return _empty("No assessed matching papers were found. " + wording), listing
    text = wording
    return GroundedAnswer(text=text, citations=(), degraded=screened.status is ToolStatus.DEGRADED), listing


def _count(run, question):
    result = topic_count(run, question)
    if result.status not in SUCCESS:
        return _unavailable(), None
    handles = [row["record"] for row in result.detail.get("matches", ())]
    rows = _rows(run, result.evidence, handles)
    if len(rows) != result.detail.get("total"):
        return _unavailable("The readable papers changed during counting. Please try again."), None
    wording = result.detail["wording"] + " This count is of the records you can see."
    text = wording
    return GroundedAnswer(text=text, citations=(), degraded=result.status is ToolStatus.DEGRADED), {
        "completeness": result.coverage.label.value, "wording": wording, "records": rows,
    }


def _named_records(ctx, question):
    """Resolve exact quoted titles or complete known titles in reader text."""
    quoted = [match[0] or match[1] for match in re.findall(r'"([^"\n]+)"|“([^”\n]+)”', question)]
    records = list(readable_records(ctx).only("pk", "title"))
    lowered = question.casefold()
    matched = [record for record in records if record.title and (
        record.title.casefold() in {title.casefold() for title in quoted}
        or re.search(r"(?<!\w)" + re.escape(record.title.casefold()) + r"(?!\w)", lowered)
    )]
    known = {record.title.casefold() for record in matched}
    missing = [title for title in quoted if title.casefold() not in known]
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


def answer_lane(lane, question, user, *, root, conversation=None, scope_record=None,
                max_sources=8, history_before_turn_id=None):
    """Run a bounded corpus workflow selected by the application router."""
    if lane not in ("listing", "count", "comparison", "research"):
        raise ValueError(f"No application workflow for lane {lane!r}")
    if max_sources < 1:
        raise ValueError("max_sources must be positive")
    ctx = RunContext.for_request(user=user, root=root, lane=lane, conversation=conversation)
    ctx = replace(ctx, scope_record_id=scope_record.pk if scope_record is not None else None,
                  history_before_turn_id=history_before_turn_id)
    if lane == "research":
        ctx = replace(ctx, budget=replace(ctx.budget,
            max_ledger_passages=min(ctx.budget.max_ledger_passages, max_sources)))
        return ResearchPlanner(root).answer(question, ctx).answer, None
    run = ToolRun.start(ctx, root)
    try:
        with model_call_deadline(ctx.budget.wall_clock_seconds):
            if lane == "listing":
                return _listing(run, question, max_sources)
            if lane == "count":
                return _count(run, question)
            return _comparison(run, question, max_sources)
    except (LLMUnavailable, CircuitOpen, TimeoutError, ArgumentsRejected, BudgetExhausted):
        return _unavailable(), None
