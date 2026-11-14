"""What should the reranker read? IR-1125's paired arm comparison.

Every arm reranks the same recalled candidates per question: recall runs once
per question and is shared, so a difference on a question is caused by the
arm. A rerank whose input list repeats one already sent for that question is
served from memory, so an arm identical to today costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import comb
from typing import Any, Optional, Sequence

from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.ai.retrieval.ports import RetrievalResult, Retriever
from apps.ai.retrieval.reranker_input import (
    ARM_LABELS,
    DESCRIBED,
    EMBEDDED,
    FALLBACK,
    READS,
    TODAY,
    changes_expected,
    reranker_text,
)

from .harness import _outcome
from .labels import QuestionSet
from .report import QuestionOutcome

TEXT_SET = "text"
FIGURE_SET = "figure"
SIGNIFICANCE = 0.05
COST_CEILING_USD = 2.0

#: Copied unchanged into every report, dry runs included (IR-1125).
DECISION_RULE = """\
1. C is the default winner: it is the smallest change.
2. A replaces C only if it wins on the text set by a paired exact (sign/McNemar) test at p < 0.05, and loses no figure question to C.
3. B vs C: if their figure recall differs by one question or less, retrieval cannot separate them; the choice is a product decision about showing AI-written text to readers, recorded as such, with C chosen meanwhile.
4. Any arm that is not identical to today on chunks with non-blank shown text, when it is meant to be, is a defect, not a result."""


def rerank_tokens(query: str, documents: Sequence[str]) -> int:
    """Voyage bills a rerank as query tokens per document plus the documents.

    Counted with the indexing tokenizer, so an estimate, not the invoice.
    """
    from apps.ai.chunking.tokens import count_tokens

    return count_tokens(query) * len(documents) + sum(count_tokens(d) for d in documents)


class SharedRecall(Retriever):
    """Recall once per question; every arm reranks what it returned."""

    def __init__(self, inner: Retriever) -> None:
        self._inner = inner
        self._memo: dict[tuple[str, int], RetrievalResult] = {}
        self.calls = 0

    def retrieve(self, question: str, user, limit: int = 20) -> RetrievalResult:
        key = (question, limit)
        if key not in self._memo:
            self.calls += 1
            self._memo[key] = self._inner.retrieve(question, user, limit=limit)
        return self._memo[key]

    def candidates(self, question: str):
        return tuple(p for (q, _), r in self._memo.items() if q == question for p in r.passages)


class MeteredReranker(Reranker):
    """Counts what a run sends; with no ``real`` reranker, sends nothing."""

    def __init__(self, real: Optional[Reranker]) -> None:
        self._real = real
        self.transmits_externally = real.transmits_externally if real else True
        self._memo: dict[tuple[str, tuple[str, ...]], list[RerankedCandidate]] = {}
        self.tokens = 0
        self.calls = 0
        self.sent: list[tuple[str, tuple[str, ...]]] = []

    def rerank(self, query: str, candidates: Sequence[str]) -> list[RerankedCandidate]:
        key = (query, tuple(candidates))
        if key in self._memo:
            return self._memo[key]
        self.calls += 1
        self.tokens += rerank_tokens(query, candidates)
        self.sent.append(key)
        if self._real is None:
            ranked = [
                RerankedCandidate(index=i, text=t, score=float(len(candidates) - i))
                for i, t in enumerate(candidates)
            ]
        else:
            ranked = self._real.rerank(query, candidates)
        self._memo[key] = ranked
        return ranked


@dataclass(frozen=True)
class Defect:
    set_name: str
    question_id: str
    arm: str
    chunk_id: int


@dataclass(frozen=True)
class Paired:
    """One arm against another over the same questions."""

    first: str
    second: str
    wins: tuple[str, ...]
    losses: tuple[str, ...]
    ties: int

    @property
    def p_value(self) -> float:
        """Two-sided exact sign test on the discordant questions."""
        n = len(self.wins) + len(self.losses)
        if n == 0:
            return 1.0
        k = min(len(self.wins), len(self.losses))
        return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)

    def as_dict(self) -> dict[str, Any]:
        return {
            "first": ARM_LABELS[self.first], "second": ARM_LABELS[self.second],
            "wins": list(self.wins), "losses": list(self.losses),
            "ties": self.ties, "p_value": round(self.p_value, 6),
        }


def _recall(outcome: QuestionOutcome) -> float:
    return outcome.retrieved_hits / outcome.expected if outcome.expected else 0.0


def _final(outcome: QuestionOutcome) -> float:
    return outcome.final_hits / outcome.expected if outcome.expected else 0.0


@dataclass
class ArmRun:
    sets: dict[str, QuestionSet]
    arms: tuple[str, ...]
    dry_run: bool
    outcomes: dict[tuple[str, str], list[QuestionOutcome]] = field(default_factory=dict)
    tokens: dict[tuple[str, str], int] = field(default_factory=dict)
    paid_calls: dict[tuple[str, str], int] = field(default_factory=dict)
    defects: list[Defect] = field(default_factory=list)
    recall_calls: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(self.tokens.values())

    def cost_usd(self, per_million: Optional[float]) -> Optional[float]:
        return None if per_million is None else self.total_tokens * per_million / 1_000_000

    def identical_to_today(self, set_name: str, arm: str) -> bool:
        """Whether ``arm`` sent no rerank today had not already sent."""
        return arm == TODAY or self.paid_calls.get((set_name, arm), 0) == 0

    def recall(self, set_name: str, arm: str, kind: Optional[str] = None) -> tuple[float, float, int]:
        rows = self._rows(set_name, arm, kind)
        if not rows:
            return 0.0, 0.0, 0
        return (
            sum(_recall(o) for o in rows) / len(rows),
            sum(_final(o) for o in rows) / len(rows),
            len(rows),
        )

    def _rows(self, set_name, arm, kind=None):
        rows = self.outcomes.get((set_name, arm), [])
        if kind is None:
            return rows
        kinds = {q.id: q.kind for q in self.sets[set_name].questions}
        return [o for o in rows if kinds.get(o.question_id) == kind]

    def kinds(self, set_name: str) -> list[str]:
        return sorted({q.kind for q in self.sets[set_name].scored if q.kind})

    def paired(self, set_name: str, first: str, second: str) -> Paired:
        a = {o.question_id: _recall(o) for o in self.outcomes.get((set_name, first), [])}
        b = {o.question_id: _recall(o) for o in self.outcomes.get((set_name, second), [])}
        shared = [q for q in a if q in b]
        return Paired(
            first=first, second=second,
            wins=tuple(q for q in shared if a[q] > b[q]),
            losses=tuple(q for q in shared if a[q] < b[q]),
            ties=sum(1 for q in shared if a[q] == b[q]),
        )

    def fully_recalled(self, set_name: str, arm: str) -> int:
        return sum(1 for o in self.outcomes.get((set_name, arm), []) if o.retrieved_hits == o.expected)

    def decision(self) -> list[str]:
        """The rule applied as written; a person still records the decision."""
        if self.defects:
            return [f"BLOCKED: {len(self.defects)} defect(s) under rule 4. A defect, not a result."]
        if self.dry_run:
            return ["No decision: a dry run reranks nothing."]
        if not ({TEXT_SET, FIGURE_SET} <= set(self.sets) and set(READS) <= set(self.arms)):
            return ["No decision: the rule needs both sets and all four arms."]
        lines = []
        text = self.paired(TEXT_SET, EMBEDDED, FALLBACK)
        figure = self.paired(FIGURE_SET, EMBEDDED, FALLBACK)
        a_wins = len(text.wins) > len(text.losses) and text.p_value < SIGNIFICANCE
        if a_wins and not figure.losses:
            lines.append(
                f"Rule 2: A replaces C (text p={text.p_value:.4f}, no figure question lost to C)."
            )
        else:
            lines.append(
                f"Rules 1-2: C stands (A vs C on text: {len(text.wins)} wins, "
                f"{len(text.losses)} losses, p={text.p_value:.4f}; figure losses to C: "
                f"{len(figure.losses)})."
            )
        gap = self.fully_recalled(FIGURE_SET, DESCRIBED) - self.fully_recalled(FIGURE_SET, FALLBACK)
        if abs(gap) <= 1:
            lines.append(
                f"Rule 3: B and C differ by {abs(gap)} figure question(s); retrieval cannot "
                "separate them. Showing AI-written text is a product decision; C meanwhile."
            )
        else:
            lines.append(
                f"Rule 3: B and C differ by {abs(gap)} figure questions "
                f"({'B' if gap > 0 else 'C'} ahead). The rule does not choose here; a person does."
            )
        return lines

    def as_dict(self, cost_per_million: Optional[float] = None) -> dict[str, Any]:
        recall = {}
        for name in self.sets:
            for arm in self.arms:
                r, f, n = self.recall(name, arm)
                entry = {"recall_at_10": round(r, 4), "final_set_recall": round(f, 4), "questions": n,
                         "tokens": self.tokens.get((name, arm), 0),
                         "paid_calls": self.paid_calls.get((name, arm), 0),
                         "identical_to_today": self.identical_to_today(name, arm)}
                for kind in self.kinds(name):
                    kr, kf, kn = self.recall(name, arm, kind)
                    entry.setdefault("by_kind", {})[kind] = {
                        "recall_at_10": round(kr, 4), "final_set_recall": round(kf, 4), "questions": kn,
                    }
                recall.setdefault(name, {})[ARM_LABELS[arm]] = entry
        cost = self.cost_usd(cost_per_million)
        return {
            "ticket": "IR-1125",
            "decision_rule": DECISION_RULE,
            "dry_run": self.dry_run,
            "arms": {ARM_LABELS[a]: a for a in self.arms},
            "sets": {name: qs.as_dict() for name, qs in self.sets.items()},
            "recall": recall,
            "comparisons": [p.as_dict() | {"set": name} for name, p in self._named_comparisons()],
            "per_question": {
                f"{name}/{ARM_LABELS[arm]}": {o.question_id: round(_recall(o), 4) for o in rows}
                for (name, arm), rows in self.outcomes.items()
            },
            "defects": [d.__dict__ for d in self.defects],
            "tokens": self.total_tokens,
            "cost_per_million_usd": cost_per_million,
            "cost_usd": None if cost is None else round(cost, 4),
            "recall_calls": self.recall_calls,
            "decision": self.decision(),
            "provenance": self.provenance,
        }

    def _named_comparisons(self):
        pairs = [(arm, TODAY) for arm in self.arms if arm != TODAY]
        pairs += [(EMBEDDED, FALLBACK), (DESCRIBED, FALLBACK)]
        return [
            (name, self.paired(name, first, second))
            for name in self.sets
            for first, second in pairs
            if first in self.arms and second in self.arms
        ]

    def render(self, cost_per_million: Optional[float] = None) -> str:
        lines = ["IR-1125: what the reranker reads", "", "Decision rule (fixed before any paid run):",
                 DECISION_RULE, ""]
        for name in self.sets:
            lines.append(f"{name} set")
            for arm in self.arms:
                r, f, n = self.recall(name, arm)
                same = "  (identical to today, not reranked)" if (
                    arm != TODAY and self.identical_to_today(name, arm)) else ""
                lines.append(
                    f"  {ARM_LABELS[arm]:<6} {arm:<10} recall@10 {r:.3f}  final {f:.3f}  "
                    f"n={n}  tokens {self.tokens.get((name, arm), 0)}{same}"
                )
                for kind in self.kinds(name):
                    kr, kf, kn = self.recall(name, arm, kind)
                    lines.append(f"         {kind:<22} recall@10 {kr:.3f}  final {kf:.3f}  n={kn}")
            lines.append("")
        lines.append("Paired comparisons (first vs second: wins / losses / ties, exact p)")
        for name, p in self._named_comparisons():
            lines.append(
                f"  {name:<7} {ARM_LABELS[p.first]} vs {ARM_LABELS[p.second]:<6} "
                f"{len(p.wins)} / {len(p.losses)} / {p.ties}  p={p.p_value:.4f}"
            )
        cost = self.cost_usd(cost_per_million)
        lines += ["", f"Rerank tokens {'estimated' if self.dry_run else 'sent'}: {self.total_tokens}"
                  + (f"  (~${cost:.4f})" if cost is not None else "  (unpriced: pass --cost-per-million)")]
        if self.defects:
            lines.append(f"Defects (rule 4): {len(self.defects)}")
            lines += [f"  {d.set_name}/{d.question_id} {ARM_LABELS[d.arm]} chunk {d.chunk_id}"
                      for d in self.defects[:20]]
        lines += ["", "Decision:", *[f"  {line}" for line in self.decision()]]
        return "\n".join(lines)


def compare(
    roots: dict[str, Any],
    sets: dict[str, QuestionSet],
    *,
    user,
    reranker: Optional[Reranker],
    arms: Sequence[str] = READS,
    retrieval_limit: int = 10,
    max_sources: int = 8,
) -> ArmRun:
    """Rerank each question's shared candidates under every arm.

    ``roots`` names the root each set retrieves through: the figure papers may
    live in a trial chunk set. ``reranker`` None is the dry run: recall still
    runs, so the inputs and the token estimate are real, but nothing is reranked.
    """
    arms = tuple(sorted(set(arms) | {TODAY}, key=READS.index))
    metered = MeteredReranker(reranker)
    limit = max(retrieval_limit, max_sources)
    run = ArmRun(sets=sets, arms=arms, dry_run=reranker is None)

    for name, question_set in sets.items():
        root = roots[name]
        shared = SharedRecall(root.recall_stage())
        selection = root.source_selection(max_sources)
        for question in question_set.scored:
            for arm in arms:
                retriever = root.reranking_over(shared, metered, arm)
                calls, tokens = metered.calls, metered.tokens
                result = retriever.retrieve(question.question, user, limit=limit)
                passages = list(result.passages)
                run.outcomes.setdefault((name, arm), []).append(_outcome(
                    question, passages[:retrieval_limit], selection.apply(passages),
                    degraded=result.degraded, mode=result.mode,
                ))
                run.paid_calls[(name, arm)] = run.paid_calls.get((name, arm), 0) + metered.calls - calls
                run.tokens[(name, arm)] = run.tokens.get((name, arm), 0) + metered.tokens - tokens
            for candidate in shared.candidates(question.question):
                for arm in arms:
                    changed = reranker_text(candidate, arm) != reranker_text(candidate, TODAY)
                    if changed and not changes_expected(candidate, arm):
                        run.defects.append(Defect(name, question.id, arm, candidate.chunk_id))
        run.recall_calls += shared.calls

    run.provenance = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reranker": type(reranker).__name__ if reranker else None,
        "retrieval_limit": retrieval_limit,
        "max_sources": max_sources,
    }
    return run
