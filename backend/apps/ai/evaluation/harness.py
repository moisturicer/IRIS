"""One run: a root, a question set, a configuration, a report (IR-133 / IR-394).

**The one new seam.** A run is a function over a `CompositionRoot`, which is
what makes it testable with the deterministic fakes and no vendor account — the
same property `test_ask_http.py` relies on. The management command is a thin
wrapper that prints the report and writes it to a file.

**One retrieval call per question, not two.** Both measures come out of the
same `RetrievalResult`: recall@k reads its first k passages, and the final-set
measure applies `SourceSelection` to it. Retrieving `max(k, max_sources)` and
capping to `max_sources` gives exactly the passages the answer service's own
`limit=max_sources` call would have — both paths recall wide and trim at the
end, so the prefix is the same — and it halves what a run spends on reranking.

**Unanswerable questions run through the same retriever (IR-454).** Each
retrieves exactly as an answerable one does; its outcome goes to the report's
`refusals` list instead of `outcomes`, so correct refusal is measured under the
same configuration as recall and never averaged into it.

Nothing here calls a model. A retrieval measurement that needed an answering
vendor would be unrunnable on a deployment with no generation configured, which
is every deployment today.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from .labels import Question, QuestionSet, QuestionSetError, hits
from .report import EvalReport, QuestionOutcome, RunConfig
from .techniques import ResolvedTechniques, resolve


def _outcome(
    question: Question,
    retrieved: Sequence,
    final: Sequence,
    *,
    degraded: bool,
    mode: Optional[str],
    expects_refusal: bool = False,
    scope_record: Optional[str | int] = None,
) -> QuestionOutcome:
    retrieved_hits = hits(question.expected, retrieved)
    final_hits = hits(question.expected, final)
    found = set(retrieved_hits)

    page_mismatches = []
    for label in retrieved_hits:
        if label.page is None:
            continue
        pages = {
            p.source_page
            for p in retrieved
            if label.matches(p) and p.source_page is not None
        }
        if pages and label.page not in pages:
            page_mismatches.append(
                f"{label.quote[:60]} (labelled p{label.page}, found on "
                f"p{sorted(pages)[0]})"
            )

    return QuestionOutcome(
        question_id=question.id,
        question=question.question,
        expected=len(question.expected),
        retrieved_hits=len(retrieved_hits),
        final_hits=len(final_hits),
        retrieved_count=len(retrieved),
        final_count=len(final),
        degraded=degraded,
        mode=mode,
        missed=tuple(
            label.quote[:80]
            for label in question.expected
            if label not in found
        ),
        page_mismatches=tuple(page_mismatches),
        expects_refusal=expects_refusal,
        scope_record=scope_record,
    )


def _resolve_scopes(question_set: QuestionSet) -> dict[str | int, Any]:
    """Each scoped question's Record, resolved before anything is spent."""
    from .validation import resolve_record

    resolved: dict[str | int, Any] = {}
    for question in question_set.record_scoped:
        scope = question.scope_record
        if scope in resolved:
            continue
        record, problem = resolve_record(scope)
        if record is None:
            raise QuestionSetError(f"question {question.id}: scope_record {problem}")
        resolved[scope] = record
    return resolved


def run(
    root,
    question_set: QuestionSet,
    config: RunConfig,
    *,
    user,
    provenance: Optional[dict[str, Any]] = None,
) -> EvalReport:
    """Measure ``question_set`` through ``root`` under ``config``.

    ``user`` is required and is not a formality: retrieval filters by
    `Record.objects.visible_to(user)`, so a run is a measurement of what *that
    user* can retrieve. An anonymous user can read nothing and would score
    zero on a working stack.
    """
    limit = max(config.retrieval_limit, config.max_sources)
    scopes = _resolve_scopes(question_set)
    outcomes: list[QuestionOutcome] = []
    refusals: list[QuestionOutcome] = []
    spaces: set[int] = set()
    modes: set[str] = set()

    with config.techniques.applied():
        active = root if config.reranking else root.without_reranking()
        retriever = active.retriever()
        # Paper Chat's narrowing: one retriever per paper (IR-1052).
        scoped = {key: active.retriever(record=r) for key, r in scopes.items()}
        selection = active.source_selection(config.max_sources)
        for question in (*question_set.scored, *question_set.unanswerable):
            chosen = scoped.get(question.scope_record, retriever)
            result = chosen.retrieve(question.question, user, limit=limit)
            passages = list(result.passages)
            final = selection.apply(passages)
            if result.embedding_space_id is not None:
                spaces.add(result.embedding_space_id)
            if result.mode:
                modes.add(result.mode)
            outcome = _outcome(
                question,
                passages[: config.retrieval_limit],
                final,
                degraded=result.degraded,
                mode=result.mode,
                expects_refusal=question.unanswerable,
                scope_record=question.scope_record,
            )
            (refusals if question.unanswerable else outcomes).append(outcome)

    return EvalReport(
        question_set=question_set,
        config=config,
        outcomes=tuple(outcomes),
        refusals=tuple(refusals),
        provenance={
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "embedding_spaces": sorted(spaces),
            "retrieval_modes": sorted(modes),
            "embedder": type(active.embedder()).__name__,
            "reranker": type(active.reranker()).__name__,
            "retrieved_with_limit": limit,
            "techniques_moved": list(config.changed_techniques),
            **(provenance or {}),
        },
    )


def run_both(
    root,
    question_set: QuestionSet,
    *,
    user,
    retrieval_limit: int = 10,
    max_sources: int = 8,
    techniques: Optional[ResolvedTechniques] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> list[EvalReport]:
    """The with-and-without-reranking comparison IR-133 asks for.

    Reranking off is the baseline and comes first, because the delta a reader
    wants is what reranking added, not what removing it cost.
    """
    return [
        run(
            root,
            question_set,
            RunConfig(
                reranking=reranking,
                techniques=techniques if techniques is not None else resolve(),
                retrieval_limit=retrieval_limit,
                max_sources=max_sources,
                baseline=None if not reranking else "no-reranking",
            ),
            user=user,
            provenance=provenance,
        )
        for reranking in (False, True)
    ]
