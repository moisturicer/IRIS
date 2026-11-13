"""What a run produces: two numbers per configuration, and its provenance.

**Two measures, never one** (ADR-023 §Amendment). Retrieval recall is recall@k
over what retrieval returned. Final-set recall is recall over the passages the
model was actually given — after the disclosure gate, the source cap, and
whatever selection ADR-033 §3–§4 later puts there. A run reporting only the
first can show a healthy number for a configuration that sends the model
nothing useful.

Macro is the headline: per-question recall, averaged over questions, so a
question with four labels does not outvote three questions with one. Micro
(labels found over labels total) is reported beside it because the two
diverging is informative.

**A third measure, correct refusal, beside them and never blended in (IR-454).**
Both recall measures can only fall when a precision technique (ADR-033 §3's
relevance cut-off, §4's cap and budget) removes a passage, so on recall alone a
floor shows what it costs and never what it buys. Correct refusal is computed
over the questions the corpus cannot answer: the share where the model was
given no passage. Those questions sit in their own `refusals` list, so they
cannot enter a recall average, and ADR-027 §2's rule against combining two
signals into one score holds by construction.

**The false-refusal guard** is the dangerous direction: an answerable question
for which the model was given nothing. ADR-033 §3 never shows a reader the
score, so a floor set too high fails silently. The report names every one by
question id, not just a count.

"Given nothing" is read off the final set, the passages the model receives:
that empty set is what ADR-034's no-sources path branches on.

A report is a value that serializes. The management command prints it and
writes it; nothing here does I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

from .labels import QuestionSet
from .techniques import ResolvedTechniques
from .techniques import resolve as _resolve


@dataclass(frozen=True)
class RunConfig:
    """One point of comparison. Recorded verbatim in the results file.

    ``retrieval_limit`` is the k in recall@k — 10, per ADR-023. ``max_sources``
    is how many passages the model is given, and is the answer service's own
    default unless a run says otherwise.

    ``techniques`` is ADR-033 §5's six switches at the values this run used.
    It defaults to this deployment's own settings, so *every* run records all
    six — unbuilt ones included, because a results file that omits a switch
    cannot be compared with a later one that moved it. A run moving one passes
    `techniques.resolve([(name, value)])`.
    """

    reranking: bool = True
    retrieval_limit: int = 10
    max_sources: int = 8
    name: Optional[str] = None
    baseline: Optional[str] = None
    techniques: ResolvedTechniques = field(default_factory=_resolve)

    @property
    def changed_techniques(self) -> tuple[str, ...]:
        return self.techniques.changes

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        base = "with-reranking" if self.reranking else "no-reranking"
        moved = self.changed_techniques
        return f"{base}+{','.join(moved)}" if moved else base

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "techniques": self.techniques.as_dict(),
            "label": self.label,
        }


@dataclass(frozen=True)
class QuestionOutcome:
    question_id: str
    question: str
    expected: int
    retrieved_hits: int
    final_hits: int
    retrieved_count: int
    final_count: int
    degraded: bool = False
    mode: Optional[str] = None
    #: The quotes retrieval never found. The debugging half of the report:
    #: a number says the stack got worse, these say which passage it lost.
    missed: tuple[str, ...] = ()
    #: Found, but on a different page than the label claims. Never scored —
    #: a signal that a label needs its page corrected.
    page_mismatches: tuple[str, ...] = ()
    #: The corpus cannot answer this question, so the right result is an empty
    #: final set (IR-454). Such an outcome is scored by correct refusal only.
    expects_refusal: bool = False
    #: The Record retrieval was narrowed to, as Paper Chat narrows (IR-1052).
    scope_record: Optional[str | int] = None

    @property
    def given_nothing(self) -> bool:
        """The model would receive no passage for this question."""
        return self.final_count == 0

    @property
    def retrieval_recall(self) -> float:
        return self.retrieved_hits / self.expected if self.expected else 0.0

    @property
    def final_set_recall(self) -> float:
        return self.final_hits / self.expected if self.expected else 0.0

    def as_dict(self) -> dict[str, Any]:
        if self.expects_refusal:
            return {**asdict(self), "refused": self.given_nothing}
        return {
            **asdict(self),
            "retrieval_recall": round(self.retrieval_recall, 4),
            "final_set_recall": round(self.final_set_recall, 4),
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _slice(outcomes: Sequence[QuestionOutcome], k: int) -> Optional[dict[str, Any]]:
    """Recall over one slice, with its own denominator. None when empty."""
    if not outcomes:
        return None
    expected = sum(o.expected for o in outcomes)
    return {
        "questions": len(outcomes),
        f"recall@{k}": round(_mean([o.retrieval_recall for o in outcomes]), 4),
        "final_set_recall": round(_mean([o.final_set_recall for o in outcomes]), 4),
        f"micro_recall@{k}": round(
            sum(o.retrieved_hits for o in outcomes) / expected, 4
        ),
        "false_refusals": [o.question_id for o in outcomes if o.given_nothing],
    }


@dataclass(frozen=True)
class EvalReport:
    question_set: QuestionSet
    config: RunConfig
    #: The answerable questions; every recall measure averages these only.
    outcomes: tuple[QuestionOutcome, ...]
    provenance: dict[str, Any] = field(default_factory=dict)
    #: The unanswerable questions; correct refusal reads these only (IR-454).
    refusals: tuple[QuestionOutcome, ...] = ()

    # -- the numbers --------------------------------------------------------

    @property
    def retrieval_recall(self) -> float:
        return _mean([o.retrieval_recall for o in self.outcomes])

    @property
    def final_set_recall(self) -> float:
        return _mean([o.final_set_recall for o in self.outcomes])

    @property
    def micro_retrieval_recall(self) -> float:
        expected = sum(o.expected for o in self.outcomes)
        return sum(o.retrieved_hits for o in self.outcomes) / expected if expected else 0.0

    @property
    def micro_final_set_recall(self) -> float:
        expected = sum(o.expected for o in self.outcomes)
        return sum(o.final_hits for o in self.outcomes) / expected if expected else 0.0

    @property
    def correct_refusal(self) -> Optional[float]:
        """Share of unanswerable questions for which the model got nothing.
        None, not 0.0, when the set holds no such question: nothing was
        measured, and a zero would read as "refused nothing"."""
        if not self.refusals:
            return None
        return sum(1 for o in self.refusals if o.given_nothing) / len(self.refusals)

    @property
    def missed_refusals(self) -> tuple[str, ...]:
        """Unanswerable questions the stack should have refused, but for which
        the model was still given passages."""
        return tuple(o.question_id for o in self.refusals if not o.given_nothing)

    @property
    def false_refusals(self) -> tuple[str, ...]:
        """Answerable questions for which the model was given nothing, by id."""
        return tuple(o.question_id for o in self.outcomes if o.given_nothing)

    @property
    def degraded_questions(self) -> int:
        """Answerable and unanswerable questions alike: a degraded refusal is
        no more a measurement of vector retrieval than a degraded recall."""
        return sum(1 for o in (*self.outcomes, *self.refusals) if o.degraded)

    @property
    def k(self) -> int:
        return self.config.retrieval_limit

    @property
    def slices(self) -> dict[str, Any]:
        """Corpus-wide and in-paper recall apart (IR-1052).

        The headline averages every answerable question; a slice averages only
        its own, so the in-paper number is never diluted by the corpus one.
        """
        k = self.k
        corpus = _slice([o for o in self.outcomes if o.scope_record is None], k)
        scoped = _slice([o for o in self.outcomes if o.scope_record is not None], k)
        if corpus and scoped:
            scoped["in_paper_minus_corpus_recall@" + str(k)] = round(
                scoped[f"recall@{k}"] - corpus[f"recall@{k}"], 4
            )
        return {"corpus": corpus, "record_scoped": scoped}

    # -- serialization ------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "question_set": self.question_set.as_dict(),
            "config": self.config.as_dict(),
            "measures": {
                f"recall@{self.k}": round(self.retrieval_recall, 4),
                "final_set_recall": round(self.final_set_recall, 4),
                f"micro_recall@{self.k}": round(self.micro_retrieval_recall, 4),
                "micro_final_set_recall": round(self.micro_final_set_recall, 4),
                "correct_refusal": (
                    None
                    if self.correct_refusal is None
                    else round(self.correct_refusal, 4)
                ),
                "unanswerable_questions": len(self.refusals),
                "false_refusals": list(self.false_refusals),
                "degraded_questions": self.degraded_questions,
            },
            "slices": self.slices,
            "provenance": self.provenance,
            "questions": [o.as_dict() for o in self.outcomes],
            "refusals": [o.as_dict() for o in self.refusals],
        }

    # -- the operator's view ------------------------------------------------

    def summary_line(self) -> str:
        return (
            f"{self.config.label:<16} "
            f"recall@{self.k}={self.retrieval_recall:.3f}  "
            f"final-set={self.final_set_recall:.3f}  "
            f"(micro {self.micro_retrieval_recall:.3f}/"
            f"{self.micro_final_set_recall:.3f})"
        )

    def render(self) -> str:
        lines = [
            f"Question set: {self.question_set.name} "
            f"({len(self.question_set)} questions, "
            f"{self.question_set.label_count} labels, tier "
            f"{self.question_set.tier})",
            f"Configuration: {self.config.label} "
            f"(reranking={'on' if self.config.reranking else 'off'}, "
            f"k={self.k}, max_sources={self.config.max_sources})",
            "Techniques: "
            + (
                ", ".join(self.config.changed_techniques)
                + " — everything else at this deployment's own setting"
                if self.config.changed_techniques
                else "none moved (ADR-033 §5 defaults)"
            ),
            "",
            f"  recall@{self.k}          {self.retrieval_recall:.3f}"
            f"   (micro {self.micro_retrieval_recall:.3f})",
            f"  final-set recall   {self.final_set_recall:.3f}"
            f"   (micro {self.micro_final_set_recall:.3f})",
            self._refusal_line(),
            *self._slice_lines(),
            "",
        ]
        if self.false_refusals:
            lines.append(
                f"  ! False refusals ({len(self.false_refusals)}) — answerable, "
                f"but the model would be given no passage:"
            )
            lines.extend(f"    {qid}" for qid in self.false_refusals)
            lines.append("")
        if self.missed_refusals:
            lines.append(
                f"  Unanswerable but given passages "
                f"({len(self.missed_refusals)}):"
            )
            lines.extend(f"    {qid}" for qid in self.missed_refusals)
            lines.append("")
        if self.degraded_questions:
            lines.append(
                f"  ! {self.degraded_questions} question(s) ran degraded "
                f"(full-text fallback) — the vendor was unavailable, so these "
                f"numbers are not a measurement of vector retrieval"
            )
            lines.append("")

        misses = [(o.question_id, q) for o in self.outcomes for q in o.missed]
        if misses:
            lines.append(f"  Missed passages ({len(misses)}):")
            lines.extend(f"    {qid}: {quote}" for qid, quote in misses[:20])
            if len(misses) > 20:
                lines.append(f"    ... and {len(misses) - 20} more")
            lines.append("")

        mismatches = [(o.question_id, q) for o in self.outcomes for q in o.page_mismatches]
        if mismatches:
            lines.append(
                f"  Page mismatches ({len(mismatches)}) — found, but not on the "
                f"labelled page; correct the label:"
            )
            lines.extend(f"    {qid}: {quote}" for qid, quote in mismatches[:10])
            lines.append("")
        return "\n".join(lines)

    def _slice_lines(self) -> list[str]:
        scoped = self.slices["record_scoped"]
        if scoped is None:
            return []
        corpus = self.slices["corpus"]
        k = self.k
        lines = [
            f"  record-scoped      {scoped[f'recall@{k}']:.3f}"
            f"   final-set {scoped['final_set_recall']:.3f}"
            f"   ({scoped['questions']} questions, each inside one paper)"
        ]
        if corpus is not None:
            lines.append(
                f"  corpus-wide        {corpus[f'recall@{k}']:.3f}"
                f"   final-set {corpus['final_set_recall']:.3f}"
                f"   ({corpus['questions']} questions)"
            )
        return lines

    def _refusal_line(self) -> str:
        if self.correct_refusal is None:
            return (
                "  correct refusal    n/a     (the set holds no unanswerable "
                "question)"
            )
        refused = sum(1 for o in self.refusals if o.given_nothing)
        return (
            f"  correct refusal    {self.correct_refusal:.3f}"
            f"   ({refused} of {len(self.refusals)} unanswerable questions "
            f"given no passage; reported apart from recall)"
        )


def compare(reports: Sequence[EvalReport]) -> str:
    """Side-by-side numbers, and the delta against the first report.

    The first report is the baseline by position, which is what "one change at
    a time against a fixed baseline" means in practice — the deltas are only
    meaningful because exactly one setting differs between the rows.
    """
    if not reports:
        return "no runs"
    baseline = reports[0]
    lines = [
        f"{'configuration':<16} {'recall@' + str(baseline.k):>10} "
        f"{'Δ':>8} {'final-set':>10} {'Δ':>8} {'refusal':>8} {'false-ref':>10}",
        "-" * 76,
    ]
    for report in reports:
        d_retrieval = report.retrieval_recall - baseline.retrieval_recall
        d_final = report.final_set_recall - baseline.final_set_recall
        refusal = (
            "n/a" if report.correct_refusal is None else f"{report.correct_refusal:.3f}"
        )
        lines.append(
            f"{report.config.label:<16} {report.retrieval_recall:>10.3f} "
            f"{d_retrieval:>+8.3f} {report.final_set_recall:>10.3f} "
            f"{d_final:>+8.3f} {refusal:>8} {len(report.false_refusals):>10}"
        )
    lines.append("")
    lines.append(
        f"Baseline is {baseline.config.label}. "
        f"{len(baseline.question_set)} questions: one question is "
        f"{1 / len(baseline.question_set):.3f} of the score, so a delta "
        f"smaller than that moved nothing."
    )
    lines.append(
        "Refusal is the share of unanswerable questions given no passage; "
        "false-ref counts answerable questions given none, named in each "
        "configuration's report. Neither enters a recall figure."
    )
    return "\n".join(lines)
