"""Scoring the proposed evidence-decision chain offline (IR-486, ADR-035).

The chain (IR-484): hard rules and the detector short-circuit to a search; Jev
scores what is left; a high or uncertain score searches; a low score is put to
an LLM route label, and only both agreeing permits a direct answer; a Jev
failure leaves the LLM to decide alone. This module replays that chain over
decider runs that already exist (stored run files) or that the command just
collected, and scores every arm on the same facts.

**Nothing here chooses an operating point.** Bands are two parameters the
caller passes in; the report draws the curve and sets none.

Pure: no database, no file I/O, and no vendor of its own. Deciders are
handed in, so a deterministic fake exercises every arm.

Reporting rules, each stopping a misreading:

- **Missed searches come first.** A direct answer to a question that needed the
  corpus is the expensive error; an extra search is a cost.
- **Ambiguous questions are reported apart.** A search on one is tolerated, so
  it is neither a miss nor an over-search.
- **A replicate over 5% fallbacks is reported alone** and left out of every
  pooled figure (stable and flaky misses, mean rates).
- **A simulated Jev failure is not a measured one.** The forced-failure arm
  says so, and its fallback rate is not the vendor's.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from apps.ai.evidence.model_decision import (
    REASON_PROVIDER_FAILURE,
    REASON_RATE_LIMITED,
    REASON_TIMEOUT,
    ModelDecision,
)
from apps.ai.evidence.rules import SCOPE_RECORD

from .evidence import SEARCH_TOLERATED_KINDS, THRESHOLDS, Judgement

#: A replicate with more fallbacks than this is reported alone, never pooled.
FALLBACK_POOLING_LIMIT = 0.05

DECIDER_JEV = "jev"
DECIDER_LABEL = "label"
DECIDER_TOOL = "tool"
DECIDERS = (DECIDER_JEV, DECIDER_LABEL, DECIDER_TOOL)

#: Detector reason codes that are structural, not lexical. Only
#: `scope_record` is one (ADR-035 §5).
STRUCTURAL_CODES = (SCOPE_RECORD,)

SEARCH = "search"
DIRECT = "direct"

# Chain reason codes. Each route carries exactly one, so a report can count
# why a question went where it did.
R_STRUCTURAL = "structural_rule"
R_DETECTOR = "detector_rule"
R_DETECTOR_SILENT = "detector_silent"
#: A model, not the detector, permitted the direct answer (no confirmer).
R_MODEL_PERMIT = "model_permit_direct"
R_JEV_SEARCH = "jev_search"
R_FIRST_SEARCH = "first_decider_search"
R_JEV_UNCERTAIN = "jev_uncertain"
R_LLM_SEARCH = "llm_search"
R_LLM_FAILED = "llm_failed"
R_BOTH_PERMIT = "both_permit_direct"
R_FIRST_FAILED = "first_failed"
R_JEV_FAILED_LLM_SEARCH = "jev_failed_llm_search"
R_JEV_FAILED_LLM_FAILED = "jev_failed_llm_failed"
#: The owner-decided single-opinion path (IR-484): its own code so every such
#: direct answer is countable and cappable.
R_LLM_ALONE_DIRECT = "llm_alone_after_jev_failure"
R_NO_SIGNAL = "signal_missing"

#: Vendor failures counted separately from a malformed reply.
FAILURE_REASONS = (REASON_TIMEOUT, REASON_RATE_LIMITED, REASON_PROVIDER_FAILURE)

CALIBRATION_BINS = tuple(round(0.1 * i, 1) for i in range(11))


class ChainError(ValueError):
    """An input that cannot be scored as what it claims to be."""


@dataclass(frozen=True)
class Bands:
    """Two cutoffs on Jev's probability. Below `direct_cutoff` is a direct
    candidate; from `search_cutoff` up is a search; between is **uncertain**
    and also searches. Equal cutoffs leave the uncertain band empty."""

    search_cutoff: float
    direct_cutoff: float

    def __post_init__(self) -> None:
        for name in ("search_cutoff", "direct_cutoff"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ChainError(f"{name} must be between 0 and 1, not {value}")
        if self.direct_cutoff > self.search_cutoff:
            raise ChainError(
                "direct_cutoff must not exceed search_cutoff "
                f"({self.direct_cutoff} > {self.search_cutoff})"
            )

    @classmethod
    def single(cls, cutoff: float) -> "Bands":
        return cls(search_cutoff=cutoff, direct_cutoff=cutoff)

    def as_dict(self) -> dict[str, float]:
        return {
            "search_cutoff": self.search_cutoff,
            "direct_cutoff": self.direct_cutoff,
        }


@dataclass(frozen=True)
class Facts:
    """What an arm needs to know about a question, apart from any decider."""

    question_id: str
    kind: Optional[str]
    expects_evidence: bool
    search_tolerated: bool
    detector_fires: bool
    structural_fires: bool = False

    @property
    def counts_as_over_search(self) -> bool:
        return not self.expects_evidence and not self.search_tolerated


def facts_from_judgement(judgement: Judgement, *, lane: str = "combined") -> Facts:
    """`lane` is the detector input ablation: raw question only, or raw and
    Resolved together."""
    verdict = judgement.verdict(lane)
    if verdict is None:
        verdict = judgement.combined
    return Facts(
        question_id=judgement.question_id,
        kind=judgement.kind,
        expects_evidence=judgement.expects_evidence,
        search_tolerated=judgement.search_tolerated,
        detector_fires=verdict.evidence_required,
        structural_fires=any(code in STRUCTURAL_CODES for code in verdict.codes),
    )


def facts_from_run_rows(rows: Sequence[Mapping[str, Any]]) -> list[Facts]:
    """Facts from a stored run's `per_question` rows. A stored row records the
    combined detector verdict but not which code fired, so none is structural
    (curated questions carry no Conversation, hence no record scope)."""
    return [
        Facts(
            question_id=row["id"],
            kind=None,
            expects_evidence=bool(row["expects_evidence"]),
            search_tolerated=bool(row.get("search_tolerated", False)),
            detector_fires=bool(row.get("detector", False)),
        )
        for row in rows
    ]


# -- decider runs -----------------------------------------------------------


@dataclass(frozen=True)
class DeciderRun:
    """One decider, one pass over the questions."""

    decider: str
    decisions: Mapping[str, ModelDecision]
    source: str = "live"
    prompt_digest: Optional[str] = None
    input_variant: str = "as_recorded"

    @property
    def n(self) -> int:
        return len(self.decisions)

    @property
    def fallbacks(self) -> int:
        return sum(1 for d in self.decisions.values() if not d.decided)

    @property
    def fallback_rate(self) -> Optional[float]:
        return self.fallbacks / self.n if self.n else None

    @property
    def reported_alone(self) -> bool:
        rate = self.fallback_rate
        return rate is not None and rate > FALLBACK_POOLING_LIMIT

    @property
    def models(self) -> list[str]:
        return sorted({d.model for d in self.decisions.values() if d.model})


def decision_from_row(row: Mapping[str, Any]) -> ModelDecision:
    """A `ModelDecision` from a stored `per_question` row."""
    return ModelDecision(
        route=row["route"],
        reason=row["reason"],
        anomalies=tuple(row.get("anomalies") or ()),
        latency_ms=int(row.get("latency_ms") or 0),
        input_tokens=row.get("input_tokens"),
        output_tokens=row.get("output_tokens"),
        answer_present=bool(row.get("answer_present")),
        answer_chars=int(row.get("answer_chars") or 0),
        model=row.get("model") or "",
        probability=row.get("probability"),
        cost_usd=row.get("cost_usd"),
    )


def run_from_result_file(
    decider: str, data: Mapping[str, Any], source: str
) -> DeciderRun:
    """A `DeciderRun` from an `eval_evidence --model-decision` result file."""
    if decider not in DECIDERS:
        raise ChainError(f"decider must be one of {DECIDERS}, not {decider!r}")
    model = data.get("model") if isinstance(data, Mapping) else None
    if not model or "per_question" not in model:
        raise ChainError(f"{source} holds no model decisions (run it with --model-decision)")
    if decider == DECIDER_JEV and not any(
        row.get("probability") is not None for row in model["per_question"]
    ):
        raise ChainError(f"{source} has no probabilities, so it is not a jev-noul run")
    return DeciderRun(
        decider=decider,
        decisions={row["id"]: decision_from_row(row) for row in model["per_question"]},
        source=source,
        prompt_digest=(data.get("provenance") or {}).get("prompt_digest"),
    )


# -- the policy -------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """One question's route under one arm, and what it took to get there."""

    question_id: str
    route: str
    reason: str
    first_called: bool = False
    second_called: bool = False
    latency_ms: int = 0
    cost_usd: float = 0.0
    calls_without_cost: int = 0
    llm_alone: bool = False


def _spend(*decisions: Optional[ModelDecision]) -> tuple[int, float, int]:
    latency, cost, uncosted = 0, 0.0, 0
    for decision in decisions:
        if decision is None:
            continue
        latency += decision.latency_ms
        if decision.cost_usd is None:
            uncosted += 1
        else:
            cost += decision.cost_usd
    return latency, cost, uncosted


def _outcome(facts, route, reason, first=None, second=None, *, alone=False) -> Outcome:
    latency, cost, uncosted = _spend(first, second)
    return Outcome(
        question_id=facts.question_id,
        route=route,
        reason=reason,
        first_called=first is not None,
        second_called=second is not None,
        latency_ms=latency,
        cost_usd=cost,
        calls_without_cost=uncosted,
        llm_alone=alone,
    )


def _first_searches(first: ModelDecision, bands: Bands) -> tuple[bool, str]:
    """Whether the first decider sends the question to a search, and why. A
    probability uses the bands; a plain route uses the route."""
    if first.probability is None:
        return first.evidence_required, R_FIRST_SEARCH
    if first.probability >= bands.search_cutoff:
        return True, R_JEV_SEARCH
    if first.probability >= bands.direct_cutoff:
        return True, R_JEV_UNCERTAIN
    return False, R_BOTH_PERMIT


def chain(
    facts: Facts,
    first: Optional[ModelDecision],
    second: Optional[ModelDecision],
    bands: Bands,
    *,
    force_first_failure: bool = False,
    alone_on_first_failure: bool = True,
) -> Outcome:
    """The two-stage chain for one question.

    `first` is Jev (or, in the no-new-vendor control, the route label) and
    `second` is the LLM confirmer. The detector and structural rules decide
    before either is consulted, and **a model can only ever move a question
    toward a search**: no branch below turns a rule's search into a direct
    answer.
    """
    if facts.structural_fires:
        return _outcome(facts, SEARCH, R_STRUCTURAL)
    if facts.detector_fires:
        return _outcome(facts, SEARCH, R_DETECTOR)

    first_failed = force_first_failure or first is None or not first.decided
    if first_failed:
        if not alone_on_first_failure:
            return _outcome(facts, SEARCH, R_FIRST_FAILED, first)
        if second is None or not second.decided:
            return _outcome(facts, SEARCH, R_JEV_FAILED_LLM_FAILED, first, second)
        if second.evidence_required:
            return _outcome(facts, SEARCH, R_JEV_FAILED_LLM_SEARCH, first, second)
        return _outcome(facts, DIRECT, R_LLM_ALONE_DIRECT, first, second, alone=True)

    searches, reason = _first_searches(first, bands)
    if searches:
        return _outcome(facts, SEARCH, reason, first)
    if second is None or not second.decided:
        return _outcome(facts, SEARCH, R_LLM_FAILED, first, second)
    if second.evidence_required:
        return _outcome(facts, SEARCH, R_LLM_SEARCH, first, second)
    return _outcome(facts, DIRECT, R_BOTH_PERMIT, first, second)


def _union(facts: Facts, decision: Optional[ModelDecision]) -> Outcome:
    """Detector OR one decider. A missing or failed decision searches."""
    if facts.structural_fires:
        return _outcome(facts, SEARCH, R_STRUCTURAL)
    if facts.detector_fires:
        return _outcome(facts, SEARCH, R_DETECTOR)
    if decision is None:
        return _outcome(facts, SEARCH, R_NO_SIGNAL)
    if decision.evidence_required:
        return _outcome(facts, SEARCH, R_LLM_SEARCH, decision)
    return _outcome(facts, DIRECT, R_MODEL_PERMIT, decision)


def _detector_only(facts: Facts) -> Outcome:
    if facts.structural_fires:
        return _outcome(facts, SEARCH, R_STRUCTURAL)
    if facts.detector_fires:
        return _outcome(facts, SEARCH, R_DETECTOR)
    return _outcome(facts, DIRECT, R_DETECTOR_SILENT)


def _jev_only(facts: Facts, first: Optional[ModelDecision], bands: Bands) -> Outcome:
    """Detector, then Jev's score alone: no confirmer, so Jev's permit is the
    whole decision. A failed Jev searches."""
    early = _detector_only(facts)
    if early.route == SEARCH:
        return early
    if first is None or not first.decided or first.probability is None:
        return _outcome(facts, SEARCH, R_FIRST_FAILED, first)
    searches, reason = _first_searches(first, bands)
    if searches:
        return _outcome(facts, SEARCH, reason, first)
    return _outcome(facts, DIRECT, R_MODEL_PERMIT, first)


# -- arms -------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    name: str
    description: str
    needs: tuple[str, ...]
    uses_bands: bool = False
    simulated_jev_failure: bool = False


ARM_STRUCTURAL = Arm("structural_only", "structural rules alone", ())
ARM_DETECTOR = Arm("detector", "structural rules and the keyword detector", ())
ARM_LABEL = Arm(
    "detector+label", "detector, then the Groq route label", (DECIDER_LABEL,)
)
ARM_TOOL = Arm(
    "detector+tool_call", "detector, then the tool-call decider", (DECIDER_TOOL,)
)
ARM_JEV = Arm(
    "detector+jev",
    "detector, then Jev at the bands; uncertain searches",
    (DECIDER_JEV,),
    uses_bands=True,
)
ARM_CHAIN = Arm(
    "detector+jev+llm",
    "detector, Jev, then the route label confirms every direct candidate",
    (DECIDER_JEV, DECIDER_LABEL),
    uses_bands=True,
)
ARM_JEV_FAILURE = Arm(
    "jev_failure_llm_alone",
    "Jev forced to fail on every question: the route label decides alone",
    (DECIDER_LABEL,),
    uses_bands=True,
    simulated_jev_failure=True,
)
ARM_CONTROL = Arm(
    "label+llm_confirm_no_jev",
    "no-new-vendor control: the route label, confirmed by the tool-call decider",
    (DECIDER_LABEL, DECIDER_TOOL),
)
ARMS = (
    ARM_STRUCTURAL,
    ARM_DETECTOR,
    ARM_LABEL,
    ARM_TOOL,
    ARM_JEV,
    ARM_CHAIN,
    ARM_JEV_FAILURE,
    ARM_CONTROL,
)
ARMS_BY_NAME = {arm.name: arm for arm in ARMS}


def available_arms(runs: Mapping[str, Sequence[DeciderRun]]) -> list[Arm]:
    return [a for a in ARMS if all(runs.get(d) for d in a.needs)]


def replicates_for(arm: Arm, runs: Mapping[str, Sequence[DeciderRun]]) -> int:
    return min((len(runs[d]) for d in arm.needs), default=1)


def route_arm(
    arm: Arm,
    facts: Sequence[Facts],
    runs: Mapping[str, Sequence[DeciderRun]],
    bands: Bands,
    replicate: int,
) -> list[Outcome]:
    """Every question's outcome under one arm, in one replicate."""

    def get(decider: str, qid: str) -> Optional[ModelDecision]:
        decider_runs = runs.get(decider) or ()
        return decider_runs[replicate].decisions.get(qid) if decider_runs else None

    outcomes: list[Outcome] = []
    for f in facts:
        if arm is ARM_STRUCTURAL:
            outcome = _outcome(
                f,
                SEARCH if f.structural_fires else DIRECT,
                R_STRUCTURAL if f.structural_fires else R_DETECTOR_SILENT,
            )
        elif arm is ARM_DETECTOR:
            outcome = _detector_only(f)
        elif arm in (ARM_LABEL, ARM_TOOL):
            outcome = _union(f, get(arm.needs[0], f.question_id))
        elif arm is ARM_JEV:
            outcome = _jev_only(f, get(DECIDER_JEV, f.question_id), bands)
        elif arm is ARM_CHAIN:
            first = get(DECIDER_JEV, f.question_id)
            outcome = chain(f, first, get(DECIDER_LABEL, f.question_id), bands)
        elif arm is ARM_JEV_FAILURE:
            outcome = chain(
                f,
                None,
                get(DECIDER_LABEL, f.question_id),
                bands,
                force_first_failure=True,
            )
        elif arm is ARM_CONTROL:
            outcome = chain(
                f,
                get(DECIDER_LABEL, f.question_id),
                get(DECIDER_TOOL, f.question_id),
                bands,
                alone_on_first_failure=False,
            )
        else:  # pragma: no cover - ARMS is closed
            raise ChainError(f"unknown arm {arm.name}")
        outcomes.append(outcome)
    return outcomes


# -- scoring ----------------------------------------------------------------


def _percentile(values: Sequence[int], fraction: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)), 1) - 1]


def _by_kind(ids: Sequence[str], kinds: Mapping[str, str]) -> dict[str, int]:
    counts = Counter(kinds.get(i, "unspecified") for i in ids)
    return dict(sorted(counts.items()))


@dataclass(frozen=True)
class ReplicateScore:
    """One arm in one replicate. `missed` leads: it is the expensive error."""

    replicate: int
    judged: int
    missed: tuple[str, ...]
    over_searches: tuple[str, ...]
    ambiguous_searched: tuple[str, ...]
    ambiguous_judged: int
    reasons: Mapping[str, int]
    llm_alone_direct: tuple[str, ...]
    llm_alone_needed_corpus: tuple[str, ...]
    direct_answers: int
    first_calls: int
    second_calls: int
    latencies_ms: tuple[int, ...]
    cost_usd: float
    calls_without_cost: int
    pooled: bool = True
    missed_by_kind: Mapping[str, int] = field(default_factory=dict)
    over_by_kind: Mapping[str, int] = field(default_factory=dict)

    @property
    def correct(self) -> int:
        return self.judged - len(self.missed) - len(self.over_searches)

    def as_dict(self) -> dict[str, Any]:
        n = self.judged or 1
        calls = len(self.latencies_ms) or 1
        return {
            "replicate": self.replicate,
            "pooled": self.pooled,
            "judged": self.judged,
            "missed_searches": list(self.missed),
            "missed_by_kind": dict(self.missed_by_kind),
            "over_searches": list(self.over_searches),
            "over_by_kind": dict(self.over_by_kind),
            "ambiguous": {
                "judged": self.ambiguous_judged,
                "searched": list(self.ambiguous_searched),
            },
            "correct": self.correct,
            "direct_answers": self.direct_answers,
            "reasons": dict(sorted(self.reasons.items())),
            "llm_alone": {
                "direct_answers": list(self.llm_alone_direct),
                "needed_corpus": list(self.llm_alone_needed_corpus),
            },
            "calls": {"first": self.first_calls, "second": self.second_calls},
            "latency_ms": {
                "mean": round(sum(self.latencies_ms) / calls) if self.latencies_ms else None,
                "p95": _percentile(self.latencies_ms, 0.95),
            },
            "cost_usd": {
                "total": round(self.cost_usd, 6),
                "per_decision": round(self.cost_usd / n, 6),
                "calls_without_reported_cost": self.calls_without_cost,
            },
        }


def score_replicate(
    outcomes: Sequence[Outcome],
    facts: Sequence[Facts],
    *,
    replicate: int,
    pooled: bool = True,
) -> ReplicateScore:
    by_id = {f.question_id: f for f in facts}
    kinds = {f.question_id: f.kind or "unspecified" for f in facts}
    missed, over, amb_searched, amb_judged = [], [], [], 0
    alone_direct, alone_needed = [], []
    for outcome in outcomes:
        f = by_id[outcome.question_id]
        searched = outcome.route == SEARCH
        if f.search_tolerated and not f.expects_evidence:
            amb_judged += 1
            if searched:
                amb_searched.append(f.question_id)
        elif f.expects_evidence and not searched:
            missed.append(f.question_id)
        elif f.counts_as_over_search and searched:
            over.append(f.question_id)
        if outcome.llm_alone and not searched:
            alone_direct.append(f.question_id)
            if f.expects_evidence:
                alone_needed.append(f.question_id)
    return ReplicateScore(
        replicate=replicate,
        judged=len(outcomes),
        missed=tuple(missed),
        over_searches=tuple(over),
        ambiguous_searched=tuple(amb_searched),
        ambiguous_judged=amb_judged,
        reasons=Counter(o.reason for o in outcomes),
        llm_alone_direct=tuple(alone_direct),
        llm_alone_needed_corpus=tuple(alone_needed),
        direct_answers=sum(1 for o in outcomes if o.route == DIRECT),
        first_calls=sum(1 for o in outcomes if o.first_called),
        second_calls=sum(1 for o in outcomes if o.second_called),
        latencies_ms=tuple(o.latency_ms for o in outcomes if o.first_called or o.second_called),
        cost_usd=sum(o.cost_usd for o in outcomes),
        calls_without_cost=sum(o.calls_without_cost for o in outcomes),
        pooled=pooled,
        missed_by_kind=_by_kind(missed, kinds),
        over_by_kind=_by_kind(over, kinds),
    )


@dataclass(frozen=True)
class ArmResult:
    arm: Arm
    bands: Optional[Bands]
    replicates: tuple[ReplicateScore, ...]
    #: Rescue figures for the two-stage arms: did the second decider search
    #: the questions the first would have let through?
    rescue: Optional[Mapping[str, Any]] = None

    @property
    def pooled(self) -> tuple[ReplicateScore, ...]:
        return tuple(r for r in self.replicates if r.pooled)

    @property
    def reported_alone(self) -> tuple[int, ...]:
        return tuple(r.replicate for r in self.replicates if not r.pooled)

    def _stability(self, attribute: str) -> dict[str, list[str]]:
        pooled = self.pooled
        if not pooled:
            return {"stable": [], "flaky": []}
        counts = Counter(i for r in pooled for i in getattr(r, attribute))
        stable = sorted(i for i, c in counts.items() if c == len(pooled))
        flaky = sorted(i for i, c in counts.items() if c < len(pooled))
        return {"stable": stable, "flaky": flaky}

    def summary(self) -> dict[str, Any]:
        """The figures an ablation compares, without the per-replicate rows."""
        pooled = self.pooled
        n = len(pooled) or 1
        return {
            "arm": self.arm.name,
            "pooled_replicates": len(pooled),
            "mean_missed": round(sum(len(r.missed) for r in pooled) / n, 2) if pooled else None,
            "mean_over_searches": (
                round(sum(len(r.over_searches) for r in pooled) / n, 2) if pooled else None
            ),
            "stable_missed": self._stability("missed")["stable"],
            "flaky_missed": self._stability("missed")["flaky"],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm.name,
            "description": self.arm.description,
            "needs": list(self.arm.needs),
            "simulated_jev_failure": self.arm.simulated_jev_failure,
            "bands": self.bands.as_dict() if self.bands else None,
            "replicates": len(self.replicates),
            "pooled_replicates": len(self.pooled),
            "reported_alone": list(self.reported_alone),
            "missed_searches": self._stability("missed"),
            "over_searches": self._stability("over_searches"),
            "rescue": self.rescue,
            "per_replicate": [r.as_dict() for r in self.replicates],
        }


def _rescue(
    facts: Sequence[Facts],
    runs: Mapping[str, Sequence[DeciderRun]],
    bands: Bands,
    replicate: int,
) -> dict[str, Any]:
    """For the questions that needed the corpus and Jev would have let
    through (a direct candidate), whether the LLM confirmer searched them, and
    which ones both let through."""
    jev, llm = runs[DECIDER_JEV][replicate], runs[DECIDER_LABEL][replicate]
    through, rescued, shared = [], [], []
    for f in facts:
        if not f.expects_evidence or f.detector_fires or f.structural_fires:
            continue
        d = jev.decisions.get(f.question_id)
        if d is None or not d.decided or d.probability is None:
            continue
        if d.probability >= bands.direct_cutoff:
            continue
        through.append(f.question_id)
        label = llm.decisions.get(f.question_id)
        if label is None or not label.decided or label.evidence_required:
            rescued.append(f.question_id)
        else:
            shared.append(f.question_id)
    return {
        "replicate": replicate,
        "jev_misses_before_confirmation": through,
        "rescued_by_llm": rescued,
        "missed_by_both": shared,
    }


def evaluate_arm(
    arm: Arm,
    facts: Sequence[Facts],
    runs: Mapping[str, Sequence[DeciderRun]],
    bands: Optional[Bands],
) -> ArmResult:
    bands = bands or Bands.single(0.5)
    replicates = replicates_for(arm, runs)
    scores = []
    for r in range(replicates):
        outcomes = route_arm(arm, facts, runs, bands, r)
        # A forced Jev failure is simulated, so only the real deciders gate pooling.
        gating = [d for d in arm.needs if not (arm.simulated_jev_failure and d == DECIDER_JEV)]
        pooled = not any(runs[d][r].reported_alone for d in gating)
        scores.append(score_replicate(outcomes, facts, replicate=r, pooled=pooled))
    rescue = None
    if arm is ARM_CHAIN:
        rescue = {"per_replicate": [_rescue(facts, runs, bands, r) for r in range(replicates)]}
    return ArmResult(
        arm=arm,
        bands=bands if arm.uses_bands else None,
        replicates=tuple(scores),
        rescue=rescue,
    )


def jev_curve(
    arm: Arm,
    facts: Sequence[Facts],
    runs: Mapping[str, Sequence[DeciderRun]],
    thresholds: Sequence[float] = THRESHOLDS,
) -> list[dict[str, Any]]:
    """Missed searches and over-searches at every single cutoff. The uncertain
    band is empty on a curve; no point is chosen."""
    rows = []
    for t in thresholds:
        result = evaluate_arm(arm, facts, runs, Bands.single(t))
        rows.append(
            {
                "threshold": t,
                "per_replicate": [
                    {
                        "replicate": r.replicate,
                        "pooled": r.pooled,
                        "missed": len(r.missed),
                        "over_searches": len(r.over_searches),
                        "direct_answers": r.direct_answers,
                    }
                    for r in result.replicates
                ],
            }
        )
    return rows


# -- calibration, health ----------------------------------------------------


def calibration(facts: Sequence[Facts], run: DeciderRun) -> dict[str, Any]:
    """Reliability curve and Brier score of Jev's probability against what the
    question needed. Ambiguous questions have no ground truth and are left
    out; so are calls that returned no probability."""
    by_id = {f.question_id: f for f in facts}
    points = []
    for qid, d in run.decisions.items():
        f = by_id.get(qid)
        if f is None or d.probability is None:
            continue
        if f.search_tolerated and not f.expects_evidence:
            continue
        points.append((d.probability, 1.0 if f.expects_evidence else 0.0))
    bins = []
    edges = CALIBRATION_BINS
    for lo, hi in zip(edges, edges[1:]):
        last = hi == edges[-1]
        members = [(p, y) for p, y in points if lo <= p < hi or (last and p == hi)]
        bins.append(
            {
                "from": lo,
                "to": hi,
                "n": len(members),
                "mean_probability": (
                    round(sum(p for p, _ in members) / len(members), 4) if members else None
                ),
                "fraction_needing_corpus": (
                    round(sum(y for _, y in members) / len(members), 4) if members else None
                ),
            }
        )
    return {
        "n": len(points),
        "ambiguous_excluded": True,
        "brier": (
            round(sum((p - y) ** 2 for p, y in points) / len(points), 4) if points else None
        ),
        "reliability": bins,
    }


def decider_health(run: DeciderRun) -> dict[str, Any]:
    n = run.n
    reasons = Counter(d.reason for d in run.decisions.values())

    def rate(count: int) -> Optional[float]:
        return round(count / n, 4) if n else None

    latencies = [d.latency_ms for d in run.decisions.values()]
    costs = [d.cost_usd for d in run.decisions.values()]
    known = [c for c in costs if c is not None]
    return {
        "decider": run.decider,
        "source": run.source,
        "input_variant": run.input_variant,
        "models": run.models,
        "prompt_digest": run.prompt_digest,
        "n": n,
        "fallbacks": run.fallbacks,
        "fallback_rate": rate(run.fallbacks),
        "failure_rate": rate(sum(reasons[c] for c in FAILURE_REASONS)),
        "timeout_rate": rate(reasons[REASON_TIMEOUT]),
        "rate_limit_rate": rate(reasons[REASON_RATE_LIMITED]),
        "malformed_rate": rate(
            run.fallbacks - sum(reasons[c] for c in FAILURE_REASONS)
        ),
        "reported_alone": run.reported_alone,
        "latency_ms": {
            "mean": round(sum(latencies) / n) if n else None,
            "p95": _percentile(latencies, 0.95),
        },
        "cost_usd": {
            "total": round(sum(known), 6),
            "per_decision": round(sum(known) / len(known), 6) if known else None,
            "calls_without_reported_cost": len(costs) - len(known),
        },
        "tokens": {
            "input": sum(d.input_tokens or 0 for d in run.decisions.values()),
            "output": sum(d.output_tokens or 0 for d in run.decisions.values()),
        },
    }


# -- proposal 12 §4, re-scored ----------------------------------------------

BAND_EDGES = ((0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.5), (0.5, 0.8), (0.8, 1.0001))
RESCUE_CUTOFFS = (0.2, 0.3, 0.5)


def mean_probabilities(jev_runs: Sequence[DeciderRun]) -> dict[str, float]:
    """Mean probability per question over runs. A question that any run failed
    to score has no mean and is left out rather than averaged over fewer."""
    if not jev_runs:
        return {}
    out = {}
    for qid in jev_runs[0].decisions:
        values = [r.decisions[qid].probability for r in jev_runs if qid in r.decisions]
        if len(values) == len(jev_runs) and all(v is not None for v in values):
            out[qid] = sum(values) / len(values)
    return out


def _category(f: Facts) -> str:
    if f.expects_evidence:
        return "needs_corpus"
    return "ambiguous" if f.search_tolerated else "does_not_need_corpus"


def band_table(
    facts: Sequence[Facts], jev_runs: Sequence[DeciderRun]
) -> list[dict[str, Any]]:
    """Where the questions sit by mean Jev probability (proposal 12 §4.1)."""
    means = mean_probabilities(jev_runs)
    rows = []
    for lo, hi in BAND_EDGES:
        counts = Counter(
            _category(f) for f in facts if f.question_id in means and lo <= means[f.question_id] < hi
        )
        rows.append(
            {
                "from": lo,
                "to": min(hi, 1.0),
                "needs_corpus": counts["needs_corpus"],
                "does_not_need_corpus": counts["does_not_need_corpus"],
                "ambiguous": counts["ambiguous"],
            }
        )
    return rows


def majority_searches(runs: Sequence[DeciderRun], qid: str) -> bool:
    """The majority route over runs; a tie searches, as a doubt always does."""
    votes = [r.decisions[qid].evidence_required for r in runs if qid in r.decisions]
    return bool(votes) and sum(votes) * 2 >= len(votes)


def rescue_table(
    facts: Sequence[Facts],
    jev_runs: Sequence[DeciderRun],
    label_runs: Sequence[DeciderRun],
    tool_runs: Sequence[DeciderRun],
    cutoffs: Sequence[float] = RESCUE_CUTOFFS,
) -> list[dict[str, Any]]:
    """Would a second model rescue Jev's misses (proposal 12 §4.2)? Majority
    route over the runs, for the evidence-required questions whose mean Jev
    probability sat below the cutoff."""
    means = mean_probabilities(jev_runs)
    rows = []
    for cutoff in cutoffs:
        misses = [
            f
            for f in facts
            if f.expects_evidence and f.question_id in means and means[f.question_id] < cutoff
        ]
        label = [f for f in misses if majority_searches(label_runs, f.question_id)]
        tool = [f for f in misses if majority_searches(tool_runs, f.question_id)]
        detector = [f for f in misses if f.detector_fires]
        caught = {f.question_id for f in label + tool + detector}
        rows.append(
            {
                "cutoff": cutoff,
                "jev_misses": len(misses),
                "label_rescues": len(label),
                "tool_rescues": len(tool),
                "detector_rescues": len(detector),
                "missed_by_all": len(misses) - len(caught),
                "missed_by_all_ids": sorted(
                    f.question_id for f in misses if f.question_id not in caught
                ),
            }
        )
    return rows


# -- the report -------------------------------------------------------------


@dataclass(frozen=True)
class ChainReport:
    """What a chained run produced. A value that serializes; no I/O here."""

    question_set: Mapping[str, Any]
    facts: tuple[Facts, ...]
    bands: Bands
    arms: tuple[ArmResult, ...]
    curves: Mapping[str, list[dict[str, Any]]]
    deciders: tuple[dict[str, Any], ...]
    calibration: tuple[dict[str, Any], ...]
    proposal_rescore: Optional[Mapping[str, Any]]
    ablations: Mapping[str, Any]
    provenance: Mapping[str, Any]
    skipped_arms: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "instrument": "curated-chain",
            "scoring": {
                "search_tolerated_kinds": list(SEARCH_TOLERATED_KINDS),
                "fallback_pooling_limit": FALLBACK_POOLING_LIMIT,
                "tie_rule": "a tie between runs searches",
            },
            "question_set": dict(self.question_set),
            "bands": self.bands.as_dict(),
            "operating_point": None,
            "arms": [a.as_dict() for a in self.arms],
            "skipped_arms": list(self.skipped_arms),
            "curves": dict(self.curves),
            "deciders": list(self.deciders),
            "calibration": list(self.calibration),
            "proposal_12_rescore": self.proposal_rescore,
            "ablations": dict(self.ablations),
            "provenance": dict(self.provenance),
        }

    def render(self) -> str:
        lines = [
            f"Chained decision evaluation: {self.question_set.get('name', '?')} "
            f"({len(self.facts)} judged questions)",
            f"Bands: search >= {self.bands.search_cutoff}, direct < "
            f"{self.bands.direct_cutoff}; between them is uncertain and searches. "
            "No operating point is chosen.",
            "",
            "Arms - MISSED SEARCHES FIRST (a direct answer where the corpus was needed)",
            f"  {'arm':<28} {'reps':>4} {'missed':>7} {'stable':>7} {'flaky':>6} "
            f"{'over':>5} {'amb.srch':>8} {'direct':>6} {'ms':>6} {'$/dec':>9}",
            "  " + "-" * 92,
        ]
        for result in self.arms:
            pooled = result.pooled
            n = len(pooled) or 1
            missed = sum(len(r.missed) for r in pooled) / n
            over = sum(len(r.over_searches) for r in pooled) / n
            amb = sum(len(r.ambiguous_searched) for r in pooled) / n
            direct = sum(r.direct_answers for r in pooled) / n
            lat = [x for r in pooled for x in r.latencies_ms]
            decisions = sum(r.judged for r in pooled)
            uncosted = sum(r.calls_without_cost for r in pooled)
            cost = (
                f"{sum(r.cost_usd for r in pooled) / decisions:.5f}"
                if pooled and decisions and not uncosted
                else "n/r"
            )
            stability = result._stability("missed")
            lines.append(
                f"  {result.arm.name:<28} {len(pooled):>4} {missed:>7.1f} "
                f"{len(stability['stable']):>7} {len(stability['flaky']):>6} "
                f"{over:>5.1f} {amb:>8.1f} {direct:>6.1f} "
                f"{round(sum(lat) / len(lat)) if lat else 0:>6} {cost:>9}"
            )
            if result.reported_alone:
                lines.append(
                    f"    replicate(s) {list(result.reported_alone)} exceeded "
                    f"{FALLBACK_POOLING_LIMIT:.0%} fallbacks: reported alone, not pooled."
                )
            if stability["stable"]:
                shown = stability["stable"][:8]
                more = len(stability["stable"]) - len(shown)
                lines.append(
                    f"    stable misses: {', '.join(shown)}"
                    + (f" and {more} more (all in the results file)" if more else "")
                )
        lines.append(
            "  (means over pooled replicates; ambiguous searches are tolerated; "
            "$/dec n/r = a call in the arm reported no cost)"
        )
        for result in self.arms:
            if result.arm.simulated_jev_failure:
                lines.append(
                    f"  {result.arm.name}: Jev failure is SIMULATED; its rate here is "
                    "not the vendor's."
                )
                for r in result.pooled:
                    lines.append(
                        f"    replicate {r.replicate}: {len(r.llm_alone_direct)} LLM-alone "
                        f"direct answers, {len(r.llm_alone_needed_corpus)} needed the corpus"
                    )
        if self.skipped_arms:
            lines.append(f"  skipped (no decider run supplied): {', '.join(self.skipped_arms)}")
        lines += ["", "Deciders"]
        for d in self.deciders:
            lines.append(
                f"  {d['decider']:<6} {d['source']:<28} n={d['n']} fallback "
                f"{d['fallback_rate']} (timeout {d['timeout_rate']}, rate-limit "
                f"{d['rate_limit_rate']}, malformed {d['malformed_rate']}) "
                f"mean {d['latency_ms']['mean']} ms"
                + ("  REPORTED ALONE" if d["reported_alone"] else "")
            )
        for c in self.calibration:
            lines.append(f"  Jev calibration: Brier {c['brier']} over {c['n']} questions")
        if self.proposal_rescore:
            lines += ["", "Proposal 12 §4, re-scored from the supplied runs"]
            for row in self.proposal_rescore["band_table"]:
                lines.append(
                    f"  p {row['from']:.1f}-{row['to']:.1f}: needs {row['needs_corpus']}, "
                    f"not {row['does_not_need_corpus']}, ambiguous {row['ambiguous']}"
                )
            for row in self.proposal_rescore.get("rescue_table") or []:
                lines.append(
                    f"  cutoff {row['cutoff']}: Jev misses {row['jev_misses']}, label "
                    f"rescues {row['label_rescues']}, tool {row['tool_rescues']}, "
                    f"detector {row['detector_rescues']}, missed by all {row['missed_by_all']}"
                )
        return "\n".join(lines)


def validate_runs(
    facts: Sequence[Facts], runs: Mapping[str, Sequence[DeciderRun]]
) -> None:
    """Every run must answer exactly the questions being scored: a stored run
    from a different set would otherwise be scored on the overlap and read as
    a result."""
    wanted = {f.question_id for f in facts}
    for decider_runs in runs.values():
        for run in decider_runs:
            got = set(run.decisions)
            if got != wanted:
                raise ChainError(
                    f"{run.source} ({run.decider}) answers {len(got)} questions "
                    f"but the set has {len(wanted)}; missing "
                    f"{sorted(wanted - got)[:5]}, extra {sorted(got - wanted)[:5]}"
                )


def build_report(
    *,
    question_set: Mapping[str, Any],
    facts: Sequence[Facts],
    runs: Mapping[str, Sequence[DeciderRun]],
    bands: Bands,
    ablations: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
) -> ChainReport:
    """Score every arm the supplied runs can support."""
    validate_runs(facts, runs)
    arms = available_arms(runs)
    skipped = tuple(a.name for a in ARMS if a not in arms)
    results = tuple(evaluate_arm(a, facts, runs, bands) for a in arms)

    curves: dict[str, list[dict[str, Any]]] = {}
    for arm in (ARM_JEV, ARM_CHAIN):
        if arm in arms:
            curves[arm.name] = jev_curve(arm, facts, runs)

    deciders = tuple(
        decider_health(run) for name in DECIDERS for run in runs.get(name, ())
    )
    calibrations = tuple(
        {**calibration(facts, run), "source": run.source} for run in runs.get(DECIDER_JEV, ())
    )
    rescore = None
    clean = {
        name: [r for r in rs if not r.reported_alone] for name, rs in runs.items()
    }
    if clean.get(DECIDER_JEV):
        rescore = {
            "band_table": band_table(facts, clean[DECIDER_JEV]),
            "rescue_table": (
                rescue_table(
                    facts, clean[DECIDER_JEV], clean[DECIDER_LABEL], clean[DECIDER_TOOL]
                )
                if clean.get(DECIDER_LABEL) and clean.get(DECIDER_TOOL)
                else None
            ),
            "runs_left_out": sorted(
                r.source for rs in runs.values() for r in rs if r.reported_alone
            ),
            "note": (
                "Bands and rescue read off the same questions as the runs; they "
                "show a shape, not cutoffs."
            ),
        }
    return ChainReport(
        question_set=question_set,
        facts=tuple(facts),
        bands=bands,
        arms=results,
        curves=curves,
        deciders=deciders,
        calibration=calibrations,
        proposal_rescore=rescore,
        ablations=dict(ablations or {}),
        provenance=dict(provenance or {}),
        skipped_arms=skipped,
    )


# -- collecting fresh runs ---------------------------------------------------


def collect_run(
    decider_name: str,
    decider: Any,
    questions: Sequence[Any],
    *,
    use_resolved: bool = True,
    source: str = "live",
    prompt_digest: Optional[str] = None,
) -> DeciderRun:
    """One pass of a decider over the annotated questions.

    `use_resolved=False` is the raw-question-only ablation: the Resolved
    question is simply not sent. Curated questions carry no earlier turns.
    """
    decisions = {
        q.id: decider.decide(
            q.question, resolved_question=q.resolved_question if use_resolved else None
        )
        for q in questions
    }
    return DeciderRun(
        decider=decider_name,
        decisions=decisions,
        source=source,
        prompt_digest=prompt_digest,
        input_variant="raw_and_resolved" if use_resolved else "raw_only",
    )
