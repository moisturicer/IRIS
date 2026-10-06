"""The curated instrument for the evidence detector (IR-464, ADR-035 §10).

**Two instruments, never conflated.** This one supplies every accuracy number,
over the annotated question set, against `evidence_required` and
`institutional`. Production-shaped shadowing (IR-466) supplies integration and
operational figures only and carries no ground truth, because nobody labelled
real reader questions.

It creates no `Conversation`, no `Turn` and no shadow row, and in this ticket
it calls no model: the report holds a `model` slot that stays empty until
IR-465 puts the model decision beside the detector verdict. **Detector results
and model decisions are separate sections, never one number.**

Three reporting rules, because each one stops a misreading:

- **A per-rule miss is not a detector miss.** `sourcing_demand` not firing on a
  question about a paper is the rule working. Only the combined OR verdict can
  miss.
- **Raw and Resolved are separate lanes.** An over-fire is attributable to the
  text it came from, and the Resolved lane covers only the questions carrying
  one.
- **A category with too few examples is inconclusive, not accurate.** With two
  questions in a category, one question is fifty points.

Pure: no Django, no database, no vendor. The command does the I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from apps.ai.evidence import REASON_CODES, SOURCE_RAW, SOURCE_RESOLVED, Verdict
from apps.ai.evidence.detector import EvidenceDetector

from .labels import Question, QuestionSet

#: Fewer labelled examples than this in a category and the category's numbers
#: are reported as inconclusive rather than as a measurement.
MIN_EXAMPLES = 5

LANE_RAW = SOURCE_RAW
LANE_RESOLVED = SOURCE_RESOLVED
LANE_COMBINED = "combined"
LANES = (LANE_RAW, LANE_RESOLVED, LANE_COMBINED)

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
        return verdict.evidence_required == self.expects_evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.question_id,
            "question": self.question,
            "kind": self.kind,
            "institutional": self.institutional,
            "expects_evidence": self.expects_evidence,
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
    #: Empty in IR-464: this command calls no model.
    model: Optional[dict[str, Any]] = None

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
            "question_set": self.question_set.as_dict(),
            "coverage": self.coverage,
            "rule_set_digest": self.rule_set_digest,
            "rule_set": self.rule_set,
            "detector": {
                "lanes": [lane.as_dict() for lane in self.lanes],
                "categories": [c.as_dict() for c in self.categories],
                "institutional": self.institutional,
            },
            "model": self.model,
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
        lines.append(
            "Model decisions: none. This command calls no model in IR-464; "
            "IR-465 adds one"
        )
        lines.append("  beside the detector verdict, in its own section.")
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
            if not judgement.expects_evidence:
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
            if j.verdict(lane).evidence_required and not j.expects_evidence
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
) -> EvidenceReport:
    """Submit the annotated questions to the detector and score the result."""
    judgements = tuple(judge(detector, q) for q in annotated(question_set))
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
        model=None,
    )
