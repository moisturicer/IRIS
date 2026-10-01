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

    @property
    def retrieval_recall(self) -> float:
        return self.retrieved_hits / self.expected if self.expected else 0.0

    @property
    def final_set_recall(self) -> float:
        return self.final_hits / self.expected if self.expected else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "retrieval_recall": round(self.retrieval_recall, 4),
            "final_set_recall": round(self.final_set_recall, 4),
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True)
class EvalReport:
    question_set: QuestionSet
    config: RunConfig
    outcomes: tuple[QuestionOutcome, ...]
    provenance: dict[str, Any] = field(default_factory=dict)

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
    def degraded_questions(self) -> int:
        return sum(1 for o in self.outcomes if o.degraded)

    @property
    def k(self) -> int:
        return self.config.retrieval_limit

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
                "degraded_questions": self.degraded_questions,
            },
            "provenance": self.provenance,
            "questions": [o.as_dict() for o in self.outcomes],
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
            "",
        ]
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
        f"{'Δ':>8} {'final-set':>10} {'Δ':>8}",
        "-" * 56,
    ]
    for report in reports:
        d_retrieval = report.retrieval_recall - baseline.retrieval_recall
        d_final = report.final_set_recall - baseline.final_set_recall
        lines.append(
            f"{report.config.label:<16} {report.retrieval_recall:>10.3f} "
            f"{d_retrieval:>+8.3f} {report.final_set_recall:>10.3f} "
            f"{d_final:>+8.3f}"
        )
    lines.append("")
    lines.append(
        f"Baseline is {baseline.config.label}. "
        f"{len(baseline.question_set)} questions: one question is "
        f"{1 / len(baseline.question_set):.3f} of the score, so a delta "
        f"smaller than that moved nothing."
    )
    return "\n".join(lines)
