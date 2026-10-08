"""The curated instrument for the evidence detector (IR-464, ADR-035 §10).

**Two instruments, never conflated.** This one supplies every accuracy number,
over the annotated question set, against `evidence_required` and
`institutional`. Production-shaped shadowing (IR-466) supplies integration and
operational figures only and carries no ground truth, because nobody labelled
real reader questions.

It creates no `Conversation`, no `Turn` and no shadow row. Given a decider
(IR-465, `--model-decision`) it also asks the model for its route on each
question and reports it in a `model` section beside the detector's: **detector
results and model decisions are separate sections, never one number**, and
their agreement, the union (ADR-035 §3) and each fallback reason code are
reported on their own. The model's hypothetical direct answer is measured for
length inside the decider and is never held here (ADR-035 §10).

Three reporting rules, because each one stops a misreading:

- **A per-rule miss is not a detector miss.** `sourcing_demand` not firing on a
  question about a paper is the rule working. Only the combined OR verdict can
  miss.
- **Raw and Resolved are separate lanes.** An over-fire is attributable to the
  text it came from, and the Resolved lane covers only the questions carrying
  one.
- **A category with too few examples is inconclusive, not accurate.** With two
  questions in a category, one question is fifty points.

Pure: no database and no vendor of its own. The decider it is handed does the
model call, and the command does the rest of the I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from apps.ai.evidence import REASON_CODES, SOURCE_RAW, SOURCE_RESOLVED, Verdict
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.jev_noul import REFERENCE_THRESHOLD
from apps.ai.evidence.model_decision import (
    REASONS as MODEL_REASONS,
    ModelDecision,
    ModelEvidenceDecision,
)

from .labels import Question, QuestionSet

#: Fewer labelled examples than this in a category and the category's numbers
#: are reported as inconclusive rather than as a measurement.
MIN_EXAMPLES = 5

LANE_RAW = SOURCE_RAW
LANE_RESOLVED = SOURCE_RESOLVED
LANE_COMBINED = "combined"
LANES = (LANE_RAW, LANE_RESOLVED, LANE_COMBINED)

#: A question of one of these kinds is too vague to answer, so the right reply
#: is a clarifying question and a retrieval beforehand costs nothing a reader
#: sees. Requiring evidence is therefore not an over-fire or an over-search
#: for it; answering directly is still correct. Recorded in every results file
#: as `scoring`, because it changes what an over-fire means.
SEARCH_TOLERATED_KINDS = ("ambiguous",)

#: The thresholds a probability is evaluated at (IR-482). A fixed grid; the
#: report draws the whole curve and chooses no point on it.
THRESHOLDS = tuple(round(0.05 * i, 2) for i in range(1, 20))

#: `evidence_required` to whether the question needs the corpus at all.
_NEEDS_CORPUS = {"none": False, "corpus": True, "corpus_multi": True}


def annotated(question_set: QuestionSet) -> tuple[Question, ...]:
    """The questions carrying an `evidence_required` annotation."""
    return tuple(
        q for q in question_set.questions if q.evidence_required in _NEEDS_CORPUS
    )


@dataclass(frozen=True)
class Judgement:
    """One question, its annotation, and the three verdicts."""

    question_id: str
    question: str
    kind: Optional[str]
    institutional: Optional[bool]
    expects_evidence: bool
    raw: Verdict
    combined: Verdict
    resolved: Optional[Verdict] = None
    resolved_question: Optional[str] = None
    search_tolerated: bool = False

    def verdict(self, lane: str) -> Optional[Verdict]:
        return {
            LANE_RAW: self.raw,
            LANE_RESOLVED: self.resolved,
            LANE_COMBINED: self.combined,
        }[lane]

    def correct(self, lane: str) -> Optional[bool]:
        verdict = self.verdict(lane)
        if verdict is None:
            return None
        if verdict.evidence_required and self.search_tolerated:
            return True
        return verdict.evidence_required == self.expects_evidence

    @property
    def counts_as_over_search(self) -> bool:
        """Needing evidence is an error only where it was not expected and
        searching was not tolerated."""
        return not self.expects_evidence and not self.search_tolerated

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.question_id,
            "question": self.question,
            "kind": self.kind,
            "institutional": self.institutional,
            "expects_evidence": self.expects_evidence,
            "search_tolerated": self.search_tolerated,
            "resolved_question": self.resolved_question,
            "raw": self.raw.as_dict(),
            "resolved": self.resolved.as_dict() if self.resolved else None,
            "combined": self.combined.as_dict(),
        }


@dataclass(frozen=True)
class RuleTally:
    """One rule in one lane: where it fired, and where it did not.

    `over_fires` are questions annotated as needing no corpus that this rule
    raised a requirement on; the cost is one retrieval. `silent_on_required`
    are questions that do need the corpus and this rule did not catch. Per
    rule that is ordinary, and it is named so a combined miss can be
    attributed to a gap rather than to a rule.
    """

    code: str
    fired: tuple[str, ...] = ()
    over_fires: tuple[str, ...] = ()
    silent_on_required: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "fired": len(self.fired),
            "over_fires": list(self.over_fires),
            "silent_on_required": list(self.silent_on_required),
        }


@dataclass(frozen=True)
class LaneResult:
    """One lane's numbers: the detector's own over-fires and misses."""

    lane: str
    judged: tuple[str, ...]
    over_fires: tuple[str, ...]
    misses: tuple[str, ...]
    undetermined: tuple[str, ...]
    rules: tuple[RuleTally, ...]

    @property
    def total(self) -> int:
        return len(self.judged)

    @property
    def correct(self) -> int:
        return self.total - len(self.over_fires) - len(self.misses)

    @property
    def accuracy(self) -> Optional[float]:
        return self.correct / self.total if self.total else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "judged": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4) if self.accuracy is not None else None,
            "over_fires": list(self.over_fires),
            "misses": list(self.misses),
            "undetermined": list(self.undetermined),
            "rules": [tally.as_dict() for tally in self.rules],
        }


@dataclass(frozen=True)
class CategoryResult:
    """One `kind`, and whether it holds enough examples to mean anything."""

    kind: str
    judged: int
    correct: int
    min_examples: int = MIN_EXAMPLES

    @property
    def inconclusive(self) -> bool:
        return self.judged < self.min_examples

    @property
    def accuracy(self) -> Optional[float]:
        return self.correct / self.judged if self.judged else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "judged": self.judged,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4) if self.accuracy is not None else None,
            "inconclusive": self.inconclusive,
            "min_examples": self.min_examples,
        }


def _percentile(values: Sequence[int], fraction: float) -> Optional[int]:
    """Nearest-rank percentile, so a small set reports a value it contains."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    return ordered[max(rank, 1) - 1]


@dataclass(frozen=True)
class ModelResult:
    """The model's route on every judged question, beside the detector's.

    Three things are scored, separately, because they answer different
    questions: the model alone, the detector and model **agreeing**, and the
    **union** (ADR-035 §3), where a direct answer needs both to permit it.

    A fallback is a route to evidence with its own reason code, so it can only
    show up as an over-search, never as a miss. `decided` therefore excludes
    them, which is the spike's "parsed accuracy": a call lost to a vendor 429
    is not the model being wrong about a question.
    """

    judgements: tuple[Judgement, ...]
    decisions: tuple[ModelDecision, ...]

    def _pairs(self) -> list[tuple[Judgement, ModelDecision]]:
        return list(zip(self.judgements, self.decisions))

    def _tally(self, requires) -> dict[str, Any]:
        over: list[str] = []
        missed: list[str] = []
        for judgement, decision in self._pairs():
            needed = requires(judgement, decision)
            if needed and judgement.counts_as_over_search:
                over.append(judgement.question_id)
            elif judgement.expects_evidence and not needed:
                missed.append(judgement.question_id)
        total = len(self.judgements)
        correct = total - len(over) - len(missed)
        return {
            "judged": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else None,
            "over_searches": over,
            "missed_searches": missed,
        }

    @property
    def alone(self) -> dict[str, Any]:
        return self._tally(lambda j, d: d.evidence_required)

    @property
    def union(self) -> dict[str, Any]:
        return self._tally(
            lambda j, d: d.evidence_required or j.combined.evidence_required
        )

    @property
    def decided(self) -> dict[str, Any]:
        """The model alone, over the calls where it actually ruled."""
        ruled = [(j, d) for j, d in self._pairs() if d.decided]
        correct = sum(
            1
            for j, d in ruled
            if d.evidence_required == j.expects_evidence
            or (d.evidence_required and j.search_tolerated)
        )
        return {
            "judged": len(ruled),
            "correct": correct,
            "accuracy": round(correct / len(ruled), 4) if ruled else None,
        }

    @property
    def agreement(self) -> dict[str, Any]:
        both_evidence = both_direct = detector_only = model_only = 0
        for judgement, decision in self._pairs():
            detector = judgement.combined.evidence_required
            model = decision.evidence_required
            if detector and model:
                both_evidence += 1
            elif not detector and not model:
                both_direct += 1
            elif detector:
                detector_only += 1
            else:
                model_only += 1
        total = len(self.judgements)
        return {
            "both_evidence": both_evidence,
            "both_direct": both_direct,
            "detector_only_evidence": detector_only,
            "model_only_evidence": model_only,
            "agreement": (
                round((both_evidence + both_direct) / total, 4) if total else None
            ),
        }

    @property
    def reasons(self) -> dict[str, int]:
        counts = {code: 0 for code in MODEL_REASONS}
        for decision in self.decisions:
            counts[decision.reason] = counts.get(decision.reason, 0) + 1
        return counts

    @property
    def fallbacks(self) -> int:
        return sum(1 for d in self.decisions if not d.decided)

    @property
    def anomalies(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for decision in self.decisions:
            for anomaly in decision.anomalies:
                counts[anomaly] = counts.get(anomaly, 0) + 1
        return counts

    @property
    def models(self) -> list[str]:
        return sorted({d.model for d in self.decisions if d.model})

    @property
    def has_probabilities(self) -> bool:
        return any(d.probability is not None for d in self.decisions)

    @property
    def curve(self) -> list[dict[str, Any]]:
        """Missed searches and over-searches at every threshold, by category.

        A decision searches when its probability reaches the threshold; a
        fallback has none and searches at every threshold, so it can only be an
        over-search. The union adds the detector as a floor (ADR-035 §3). Empty
        for a mode that returns no probability.
        """
        if not self.has_probabilities:
            return []

        def by_kind(ids: list[str]) -> dict[str, int]:
            kinds = {j.question_id: j.kind or "unspecified" for j in self.judgements}
            counts: dict[str, int] = {}
            for question_id in ids:
                counts[kinds[question_id]] = counts.get(kinds[question_id], 0) + 1
            return dict(sorted(counts.items()))

        rows = []
        for threshold in THRESHOLDS:
            missed, over, union_missed, union_over = [], [], [], []
            for judgement, decision in self._pairs():
                searches = (
                    decision.probability is None or decision.probability >= threshold
                )
                with_detector = searches or judgement.combined.evidence_required
                if judgement.expects_evidence:
                    if not searches:
                        missed.append(judgement.question_id)
                    if not with_detector:
                        union_missed.append(judgement.question_id)
                elif judgement.counts_as_over_search:
                    if searches:
                        over.append(judgement.question_id)
                    if with_detector:
                        union_over.append(judgement.question_id)
            rows.append(
                {
                    "threshold": threshold,
                    "missed_searches": missed,
                    "over_searches": over,
                    "missed_by_kind": by_kind(missed),
                    "over_by_kind": by_kind(over),
                    "union_missed_searches": union_missed,
                    "union_over_searches": union_over,
                }
            )
        return rows

    def _curve_dict(self) -> dict[str, Any]:
        return {
            "evidence_required": sum(1 for j in self.judgements if j.expects_evidence),
            "no_evidence_needed": sum(1 for j in self.judgements if j.counts_as_over_search),
            "thresholds": self.curve,
        }

    def as_dict(self) -> dict[str, Any]:
        latencies = [d.latency_ms for d in self.decisions]
        answers = [d for d in self.decisions if d.answer_present]
        curve = (
            {
                "threshold_curve": self._curve_dict(),
                "reference_threshold": REFERENCE_THRESHOLD,
                "operating_point": None,
            }
            if self.has_probabilities
            else {}
        )
        return {
            **curve,
            "models": self.models,
            "questions": len(self.decisions),
            "fallbacks": self.fallbacks,
            "model_alone": self.alone,
            "model_alone_decided_only": self.decided,
            "union": self.union,
            "agreement_with_detector": self.agreement,
            "reasons": self.reasons,
            "anomalies": self.anomalies,
            "latency_ms": {
                "mean": round(sum(latencies) / len(latencies)) if latencies else None,
                "p95": _percentile(latencies, 0.95),
            },
            "tokens": {
                "input": sum(d.input_tokens or 0 for d in self.decisions),
                "output": sum(d.output_tokens or 0 for d in self.decisions),
            },
            # Lengths only. The text was discarded inside the decider.
            "hypothetical_answers": {
                "count": len(answers),
                "chars_total": sum(d.answer_chars for d in answers),
            },
            "per_question": [
                {
                    "id": j.question_id,
                    "expects_evidence": j.expects_evidence,
                    "search_tolerated": j.search_tolerated,
                    "detector": j.combined.evidence_required,
                    **d.as_dict(),
                }
                for j, d in self._pairs()
            ],
        }

    def render_lines(self) -> list[str]:
        alone, union, decided = self.alone, self.union, self.decided
        agreement = self.agreement

        def fmt(tally: dict[str, Any]) -> str:
            if tally["accuracy"] is None:
                return "n/a"
            return f"{tally['correct']}/{tally['judged']} ({tally['accuracy']:.3f})"

        lines = [
            "Model decision - the model's route beside the detector "
            "(ADR-035 §3, §10)"
            + (
                f"; route at reference threshold {REFERENCE_THRESHOLD}, "
                "not an operating point"
                if self.has_probabilities
                else ""
            ),
            f"  model(s): {', '.join(self.models) or 'unknown'}; "
            f"{len(self.decisions)} calls, {self.fallbacks} fell back to evidence",
            f"  {'model alone':<28} {fmt(alone):>16}   "
            f"over-searches {len(alone['over_searches'])}, "
            f"missed searches {len(alone['missed_searches'])}",
            f"  {'model alone, decided only':<28} {fmt(decided):>16}   "
            f"(fallbacks excluded)",
            f"  {'union (detector OR model)':<28} {fmt(union):>16}   "
            f"over-searches {len(union['over_searches'])}, "
            f"missed searches {len(union['missed_searches'])}",
            f"  detector/model agreement {agreement['agreement']}: "
            f"both evidence {agreement['both_evidence']}, "
            f"both direct {agreement['both_direct']}, "
            f"detector only {agreement['detector_only_evidence']}, "
            f"model only {agreement['model_only_evidence']}",
            "  reason codes: "
            + ", ".join(f"{code} {n}" for code, n in self.reasons.items() if n),
        ]
        if alone["missed_searches"]:
            lines.append(f"  model missed: {', '.join(alone['missed_searches'])}")
        if union["missed_searches"]:
            lines.append(
                "  UNION missed (neither half caught): "
                f"{', '.join(union['missed_searches'])}"
            )
        if self.anomalies:
            lines.append(
                "  anomalies: "
                + ", ".join(f"{k} {v}" for k, v in self.anomalies.items())
                + " (recorded; the arguments were never read)"
            )
        answers = [d for d in self.decisions if d.answer_present]
        lines.append(
            f"  hypothetical direct answers: {len(answers)} generated, "
            f"{sum(d.answer_chars for d in answers)} characters in all; "
            "none retained."
        )
        if self.has_probabilities:
            curve = self._curve_dict()
            lines.append(
                f"  threshold curve: missed searches over the "
                f"{curve['evidence_required']} evidence-required, over-searches "
                f"over the {curve['no_evidence_needed']} others; fallbacks search at "
                "every threshold"
            )
            lines.append(
                f"    {'threshold':>9} {'missed':>7} {'over':>5} "
                f"{'union missed':>13} {'union over':>11}"
            )
            for row in curve["thresholds"]:
                lines.append(
                    f"    {row['threshold']:>9.2f} {len(row['missed_searches']):>7} "
                    f"{len(row['over_searches']):>5} "
                    f"{len(row['union_missed_searches']):>13} "
                    f"{len(row['union_over_searches']):>11}"
                )
            lines.append("  no operating point chosen.")
        return lines


@dataclass(frozen=True)
class EvidenceReport:
    """What a curated run produced. A value that serializes; no I/O here."""

    question_set: QuestionSet
    judgements: tuple[Judgement, ...]
    lanes: tuple[LaneResult, ...]
    categories: tuple[CategoryResult, ...]
    rule_set_digest: str
    rule_set: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    min_examples: int = MIN_EXAMPLES
    #: Model decisions, kept separate from detector results by construction.
    #: `None` unless the run was given a decider (IR-465, `--model-decision`).
    model: Optional["ModelResult"] = None

    def lane(self, name: str) -> Optional[LaneResult]:
        for result in self.lanes:
            if result.lane == name:
                return result
        return None

    @property
    def coverage(self) -> dict[str, Any]:
        total = len(self.question_set.questions)
        resolved = sum(1 for j in self.judgements if j.resolved is not None)
        return {
            "questions_in_set": total,
            "annotated": len(self.judgements),
            "annotated_fraction": (
                round(len(self.judgements) / total, 4) if total else 0.0
            ),
            "with_resolved_question": resolved,
            "unannotated": total - len(self.judgements),
        }

    @property
    def institutional(self) -> dict[str, Any]:
        """Reported separately: a miss here is the dangerous direction under
        ADR-027 §4, which is dormant rather than satisfied (ADR-035 §9)."""
        flagged = [j for j in self.judgements if j.institutional]
        missed = [j.question_id for j in flagged if j.correct(LANE_COMBINED) is False]
        return {"judged": len(flagged), "incorrect": missed}

    @property
    def inconclusive_categories(self) -> tuple[str, ...]:
        return tuple(c.kind for c in self.categories if c.inconclusive)

    def as_dict(self) -> dict[str, Any]:
        return {
            "instrument": "curated",
            "scoring": {"search_tolerated_kinds": list(SEARCH_TOLERATED_KINDS)},
            "question_set": self.question_set.as_dict(),
            "coverage": self.coverage,
            "rule_set_digest": self.rule_set_digest,
            "rule_set": self.rule_set,
            "detector": {
                "lanes": [lane.as_dict() for lane in self.lanes],
                "categories": [c.as_dict() for c in self.categories],
                "institutional": self.institutional,
            },
            "model": self.model.as_dict() if self.model else None,
            "provenance": self.provenance,
            "min_examples": self.min_examples,
            "questions": [j.as_dict() for j in self.judgements],
        }

    def render(self) -> str:
        coverage = self.coverage
        lines = [
            f"Question set: {self.question_set.name} "
            f"({coverage['questions_in_set']} questions, tier "
            f"{self.question_set.tier})",
            f"Rule set: {self.rule_set.get('summary', self.rule_set_digest[:12])}",
            f"Coverage: {coverage['annotated']}/{coverage['questions_in_set']} "
            f"questions carry an evidence annotation "
            f"({coverage['annotated_fraction']:.0%}); "
            f"{coverage['with_resolved_question']} carry a Resolved form",
            "",
            "Detector - over-fires and misses per lane",
            f"  {'lane':<10} {'judged':>7} {'correct':>8} {'accuracy':>9} "
            f"{'over-fires':>11} {'misses':>7}",
            "  " + "-" * 58,
        ]
        for lane in self.lanes:
            accuracy = f"{lane.accuracy:.3f}" if lane.accuracy is not None else "n/a"
            lines.append(
                f"  {lane.lane:<10} {lane.total:>7} {lane.correct:>8} "
                f"{accuracy:>9} {len(lane.over_fires):>11} {len(lane.misses):>7}"
            )
        lines.append("")

        for lane in self.lanes:
            if not lane.total:
                lines.append(f"  {lane.lane} lane: no question carries one.")
                lines.append("")
                continue
            lines.append(f"  {lane.lane} lane, per reason code:")
            lines.append(
                f"    {'code':<20} {'fired':>6} {'over-fires':>11} "
                f"{'silent on required':>20}"
            )
            for tally in lane.rules:
                lines.append(
                    f"    {tally.code:<20} {len(tally.fired):>6} "
                    f"{len(tally.over_fires):>11} "
                    f"{len(tally.silent_on_required):>20}"
                )
            if lane.misses:
                lines.append(f"    misses: {', '.join(lane.misses)}")
            if lane.over_fires:
                lines.append(f"    over-fires: {', '.join(lane.over_fires)}")
            if lane.undetermined:
                lines.append(
                    f"    undetermined, failed safe to a requirement: "
                    f"{', '.join(lane.undetermined)}"
                )
            lines.append("")

        lines.append(
            "  A per-rule 'silent on required' is not a detector miss: only the "
            "combined"
        )
        lines.append(
            "  lane can miss, and that column says which rule would have caught "
            "it."
        )
        lines.append("")

        lines.append(
            "Scoring: requiring evidence is not counted as an error for "
            f"kind {', '.join(SEARCH_TOLERATED_KINDS)} (too vague to answer; "
            "the right reply is a clarifying question)."
        )
        lines.append("")
        lines.append("Categories (by kind), combined lane")
        for category in self.categories:
            accuracy = (
                f"{category.accuracy:.3f}" if category.accuracy is not None else "n/a"
            )
            verdict = (
                f"INCONCLUSIVE (fewer than {category.min_examples} examples)"
                if category.inconclusive
                else ""
            )
            lines.append(
                f"  {category.kind:<26} {category.judged:>3} judged  "
                f"{accuracy:>6}  {verdict}"
            )
        lines.append("")

        institutional = self.institutional
        incorrect = institutional["incorrect"]
        lines.append(
            f"Institutional questions: {institutional['judged']} judged, "
            f"{len(incorrect)} incorrect"
            + (f" ({', '.join(incorrect)})" if incorrect else "")
        )
        lines.append(
            "  A miss here is the dangerous direction (ADR-027 §4, dormant per "
            "ADR-035 §9)."
        )
        lines.append("")
        if self.model is None:
            lines.append(
                "Model decisions: none. Pass --model-decision to put the "
                "model's route beside"
            )
            lines.append(
                "  the detector verdict, in its own section. It calls the "
                "vendor and spends credits."
            )
        else:
            lines.extend(self.model.render_lines())
        return "\n".join(lines)


def _tally(code: str, judgements: Sequence[Judgement], lane: str) -> RuleTally:
    fired: list[str] = []
    over_fires: list[str] = []
    silent: list[str] = []
    for judgement in judgements:
        verdict = judgement.verdict(lane)
        if verdict is None:
            continue
        if verdict.fired(code):
            fired.append(judgement.question_id)
            if judgement.counts_as_over_search:
                over_fires.append(judgement.question_id)
        elif judgement.expects_evidence:
            silent.append(judgement.question_id)
    return RuleTally(
        code=code,
        fired=tuple(fired),
        over_fires=tuple(over_fires),
        silent_on_required=tuple(silent),
    )


def _lane_result(lane: str, judgements: Sequence[Judgement]) -> LaneResult:
    judged = [j for j in judgements if j.verdict(lane) is not None]
    return LaneResult(
        lane=lane,
        judged=tuple(j.question_id for j in judged),
        over_fires=tuple(
            j.question_id
            for j in judged
            if j.verdict(lane).evidence_required and j.counts_as_over_search
        ),
        misses=tuple(
            j.question_id
            for j in judged
            if not j.verdict(lane).evidence_required and j.expects_evidence
        ),
        undetermined=tuple(
            j.question_id for j in judged if j.verdict(lane).undetermined
        ),
        rules=tuple(_tally(code, judged, lane) for code in REASON_CODES),
    )


def _categories(
    judgements: Sequence[Judgement], min_examples: int
) -> tuple[CategoryResult, ...]:
    kinds: dict[str, list[Judgement]] = {}
    for judgement in judgements:
        kinds.setdefault(judgement.kind or "unspecified", []).append(judgement)
    return tuple(
        CategoryResult(
            kind=kind,
            judged=len(group),
            correct=sum(1 for j in group if j.correct(LANE_COMBINED)),
            min_examples=min_examples,
        )
        for kind, group in sorted(kinds.items())
    )


def judge(
    detector: EvidenceDetector, question: Question, *, record_scoped: bool = False
) -> Judgement:
    """The three verdicts for one annotated question.

    `record_scoped` is false for every curated question: the set holds no
    Conversation, and `scope_record` is structural rather than textual. The
    parameter exists so a Paper Chat case can be asserted directly.
    """
    raw = detector.detect_lane(
        question.question, source=LANE_RAW, record_scoped=record_scoped
    )
    resolved = (
        detector.detect_lane(
            question.resolved_question,
            source=LANE_RESOLVED,
            record_scoped=record_scoped,
        )
        if question.resolved_question
        else None
    )
    combined = detector.detect(
        question.question,
        resolved_question=question.resolved_question,
        record_scoped=record_scoped,
    )
    return Judgement(
        question_id=question.id,
        question=question.question,
        kind=question.kind,
        institutional=question.institutional,
        expects_evidence=_NEEDS_CORPUS[question.evidence_required],
        search_tolerated=question.kind in SEARCH_TOLERATED_KINDS,
        raw=raw,
        resolved=resolved,
        combined=combined,
        resolved_question=question.resolved_question,
    )


def run_curated(
    detector: EvidenceDetector,
    question_set: QuestionSet,
    *,
    min_examples: int = MIN_EXAMPLES,
    provenance: Optional[dict[str, Any]] = None,
    decider: Optional[ModelEvidenceDecision] = None,
) -> EvidenceReport:
    """Submit the annotated questions to the detector and score the result.

    With a `decider`, each is also put to the model, once, on the raw question
    and its Resolved form together. Curated questions carry no earlier turns,
    so no prior reader question is sent; `decide` has no way to be handed a
    Passage or an answer regardless.
    """
    questions = annotated(question_set)
    judgements = tuple(judge(detector, q) for q in questions)
    model = (
        ModelResult(
            judgements=judgements,
            decisions=tuple(
                decider.decide(q.question, resolved_question=q.resolved_question)
                for q in questions
            ),
        )
        if decider is not None and judgements
        else None
    )
    rule_set = detector.rule_set
    return EvidenceReport(
        question_set=question_set,
        judgements=judgements,
        lanes=tuple(_lane_result(lane, judgements) for lane in LANES),
        categories=_categories(judgements, min_examples),
        rule_set_digest=rule_set.digest,
        rule_set={
            "digest": rule_set.digest,
            "summary": rule_set.summary(),
            "term_counts": rule_set.term_counts,
            "definition": rule_set.as_dict(),
        },
        provenance=dict(provenance or {}),
        min_examples=min_examples,
        model=model,
    )
