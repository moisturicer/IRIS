"""Reader-invisible shadow decisions on real traffic (IR-466, ADR-035 §4, §10).

In-request, `shadow_turn` writes a pending row and enqueues after commit; it
never raises. In the worker, `run_shadow_decision` claims the row, decides,
and writes fenced by the claim's token. A tool call is recorded, never run.
Logs carry Turn ids and codes only.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional, Sequence

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.ai.history import (
    history_token_budget,
    recent_window,
    token_margin,
)
from apps.ai.inference import InferenceTask, profile_for
from apps.ai.models import (
    MODEL_HISTORY_STATES,
    ShadowEvidenceDecision,
    ShadowEvidenceTally,
    Turn,
)
from apps.ai.models.shadow import COMPLETED, FAILED, PENDING, RUNNING, SKIPPED
from apps.ai.resilience.circuit import CircuitState
from apps.ai.resilience.llm import breaker_for
from apps.ai.resilience.rate_limit import Lane, RateLimited, bucket_for

from .config import active_rule_set, decision_enabled, detector, sample_rate
from .model_decision import (
    ROUTE_DIRECT,
    ROUTE_EVIDENCE,
    ModelEvidenceDecision,
    estimated_request_tokens,
    prompt_digest,
)

logger = logging.getLogger(__name__)

SHADOW_BREAKER_KEY = f"{InferenceTask.ANSWER.breaker_key}::shadow"

MANIFEST_VERSION = 1

#: Held back for the decision's output, then reconciled with real usage.
RESERVED_OUTPUT_TOKENS = 1024

# Outcomes. Every row not completed, and every tally, is missing coverage.
SKIP_MODEL_UNCONFIGURED = "model_unconfigured"
SKIP_ANSWER_BREAKER_OPEN = "answer_breaker_open"
SKIP_ANSWER_BREAKER_FAILURES = "answer_breaker_failures"
SKIP_BUDGET_SPENT = "shadow_budget_spent"
FAIL_RETRIES_EXHAUSTED = "retries_exhausted"

TALLY_TURN_DELETED = "turn_deleted"
TALLY_RECORD_FAILED = "record_failed"
TALLY_ENQUEUE_FAILED = "enqueue_failed"

EVENT_NOT_CLAIMED = "not_claimed"
EVENT_FENCED_OUT = "fenced_out"
EVENT_RECLAIMED = "reclaimed"
EVENT_DECIDED = "decided"


def _log(code: str, turn_id: Optional[int]) -> None:
    logger.info("evidence shadow %s turn=%s", code, turn_id)


def tally(code: str) -> None:
    """Count an event that has no row to be counted on."""
    row, _ = ShadowEvidenceTally.objects.get_or_create(code=code)
    ShadowEvidenceTally.objects.filter(pk=row.pk).update(count=F("count") + 1)


def _tally_quietly(code: str) -> None:
    try:
        tally(code)
    except Exception:
        pass


# -- the manifest ----------------------------------------------------------


def generation_parameters() -> dict:
    """What `build_profile_llm` sends for the `answer` task beyond messages."""
    profile = profile_for(InferenceTask.ANSWER)
    return {
        "vendor": profile.vendor.value,
        "model": profile.model,
        "fallback_models": list(profile.fallback_models),
        "temperature": float(settings.LLM_TEMPERATURE),
        "reasoning_effort": (
            (settings.LLM_REASONING_EFFORT or "") if profile.reasoning_visible else ""
        ),
    }


def _window_entry(turn) -> dict:
    return {
        "turn_id": turn.pk,
        "question_chars": len(turn.question or ""),
        "answer_chars": len(turn.answer or ""),
    }


def _configuration() -> dict:
    return {
        "history_token_budget": history_token_budget(),
        "history_token_margin": token_margin(),
        "eligibility_states": sorted(MODEL_HISTORY_STATES),
        "rule_set_digest": active_rule_set().digest,
        "prompt_digest": prompt_digest(),
        "generation": generation_parameters(),
    }


def build_manifest(history: Sequence, *, record_scoped: bool) -> dict:
    """The window this request used and the configuration in force.
    Lengths, never text."""
    return {
        "version": MANIFEST_VERSION,
        "window": [_window_entry(turn) for turn in history],
        "record_scoped": bool(record_scoped),
        **_configuration(),
    }


_MANIFEST_KEYS = frozenset(
    {
        "version",
        "window",
        "record_scoped",
        "history_token_budget",
        "history_token_margin",
        "eligibility_states",
        "rule_set_digest",
        "prompt_digest",
        "generation",
    }
)


def verify(turn, manifest: dict) -> None:
    if turn.pk is None or not Turn.objects.filter(pk=turn.pk).exists():
        raise ValueError("turn_not_stored")
    if set(manifest) != _MANIFEST_KEYS or manifest["version"] != MANIFEST_VERSION:
        raise ValueError("manifest_shape")
    if any(entry["turn_id"] >= turn.pk for entry in manifest["window"]):
        raise ValueError("manifest_window")


# -- in-request ------------------------------------------------------------


def should_shadow(rng: Callable[[], float] = random.random) -> bool:
    if not decision_enabled():
        return False
    rate = sample_rate()
    return rate > 0 and rng() < rate


def _answer_breaker_skip() -> Optional[str]:
    """Breakers are per process, so this is authoritative only where reader
    calls trip it: in the web request. The worker re-reads its own."""
    breaker = breaker_for(InferenceTask.ANSWER.breaker_key)
    if breaker.state is not CircuitState.CLOSED:
        return SKIP_ANSWER_BREAKER_OPEN
    if breaker.failures:
        return SKIP_ANSWER_BREAKER_FAILURES
    return None


def shadow_turn(
    turn,
    *,
    history: Sequence,
    record_scoped: bool,
    rng: Callable[[], float] = random.random,
):
    """Record a pending decision for ``turn``; enqueue it after commit.
    Returns the row or ``None``. Never raises."""
    try:
        if not should_shadow(rng):
            return None
        verdict = detector().detect(
            turn.question,
            resolved_question=turn.resolved_question or None,
            record_scoped=record_scoped,
        )
        manifest = build_manifest(history, record_scoped=record_scoped)
        verify(turn, manifest)
        skip = _answer_breaker_skip()
        terminal = (
            {"status": SKIPPED, "outcome": skip, "finished_at": timezone.now()}
            if skip
            else {}
        )
        with transaction.atomic():
            row = ShadowEvidenceDecision.objects.create(
                turn=turn, manifest=manifest, detector=verdict.as_dict(), **terminal
            )
    except Exception as exc:
        logger.warning(
            "evidence shadow %s turn=%s error=%s",
            TALLY_RECORD_FAILED,
            turn.pk,
            type(exc).__name__,
        )
        _tally_quietly(TALLY_RECORD_FAILED)
        return None

    if skip:
        _log(skip, turn.pk)
    else:
        transaction.on_commit(lambda: _enqueue(row.pk, turn.pk))
    return row


def _enqueue(shadow_id: int, turn_id: int) -> None:
    from apps.ai.tasks import decide_evidence_shadow

    try:
        # No publish retries: a down broker must not stall the reader.
        decide_evidence_shadow.apply_async((shadow_id,), retry=False)
    except Exception:
        _log(TALLY_ENQUEUE_FAILED, turn_id)
        _tally_quietly(TALLY_ENQUEUE_FAILED)


# -- claiming and fencing --------------------------------------------------


@dataclass(frozen=True)
class Claim:
    shadow_id: int
    turn_id: int
    token: uuid.UUID
    reclaimed: bool = False


def stale_after() -> timedelta:
    return timedelta(seconds=settings.AI_EVIDENCE_SHADOW_STALE_SECONDS)


def claim(shadow_id: int, *, now=None) -> Optional[Claim]:
    """Move a row to running under a fresh token, or return ``None``.

    One conditional ``UPDATE`` with its row count checked, so of two racing
    workers exactly one wins. A stale running row is reclaimed once.
    """
    now = now or timezone.now()
    token = uuid.uuid4()
    rows = ShadowEvidenceDecision.objects.filter(pk=shadow_id)

    if rows.filter(status=PENDING).update(
        status=RUNNING, claim_token=token, claimed_at=now, claims=F("claims") + 1
    ):
        reclaimed = False
    elif rows.filter(
        status=RUNNING, claimed_at__lt=now - stale_after(), reclaims=0
    ).update(
        claim_token=token,
        claimed_at=now,
        claims=F("claims") + 1,
        reclaims=F("reclaims") + 1,
    ):
        reclaimed = True
    else:
        return None

    turn_id = rows.values_list("turn_id", flat=True).first()
    return Claim(shadow_id=shadow_id, turn_id=turn_id, token=token, reclaimed=reclaimed)


def _fenced(held: Claim):
    return ShadowEvidenceDecision.objects.filter(
        pk=held.shadow_id, status=RUNNING, claim_token=held.token
    )


def release(held: Claim) -> bool:
    """Hand a claimed row back to pending, for a retry."""
    return bool(_fenced(held).update(status=PENDING, claim_token=None, claimed_at=None))


def finish(held: Claim, status: str, outcome: str = "", **fields) -> bool:
    """Write a terminal status, only while this claim still holds the row."""
    return bool(
        _fenced(held).update(
            status=status, outcome=outcome, finished_at=timezone.now(), **fields
        )
    )


def _finish_or_fenced(held: Claim, status: str, outcome: str = "", **fields) -> str:
    if finish(held, status, outcome, **fields):
        code = outcome or EVENT_DECIDED
    else:
        code = EVENT_FENCED_OUT
    _log(code, held.turn_id)
    return code


# -- the worker ------------------------------------------------------------


def parity(turn, manifest: dict) -> dict:
    """What differs between the request's manifest and the task's view of
    the same request. Ids, lengths, digests and settings -- never text."""
    window = recent_window(
        Turn.objects.filter(conversation_id=turn.conversation_id, pk__lt=turn.pk)
    )
    current = {**_configuration(), "window": [_window_entry(t) for t in window]}
    differences = {
        key: {"request": manifest.get(key), "task": value}
        for key, value in current.items()
        if manifest.get(key) != value
    }

    wanted = [entry["turn_id"] for entry in manifest.get("window", [])]
    present = set(Turn.objects.filter(pk__in=wanted).values_list("pk", flat=True))
    missing = [pk for pk in wanted if pk not in present]
    if missing:
        differences["window_turns_missing"] = {"request": wanted, "task": missing}
    return differences


def _prior_questions(manifest: dict) -> list[str]:
    """Prior reader questions from the manifest's window. No answer text
    (ADR-035 §8)."""
    wanted = [entry["turn_id"] for entry in manifest.get("window", [])]
    questions = dict(Turn.objects.filter(pk__in=wanted).values_list("pk", "question"))
    return [questions[pk] for pk in wanted if pk in questions]


def union_route(detector_verdict: dict, model_route: str) -> str:
    """ADR-035 §3: either half can require evidence; direct needs both."""
    if detector_verdict.get("evidence_required", True) or model_route != ROUTE_DIRECT:
        return ROUTE_EVIDENCE
    return ROUTE_DIRECT


def _shadow_bucket():
    return bucket_for(Lane.SHADOW)


def run_shadow_decision(
    shadow_id: int,
    *,
    final_attempt: bool = True,
    decider_factory: Optional[Callable[[], Optional[ModelEvidenceDecision]]] = None,
    bucket_factory: Callable = _shadow_bucket,
    now=None,
) -> str:
    """Decide one row and return the outcome code. An unexpected error
    releases the claim and re-raises, or on the final attempt fails the row."""
    if not ShadowEvidenceDecision.objects.filter(pk=shadow_id).exists():
        _log(TALLY_TURN_DELETED, None)
        tally(TALLY_TURN_DELETED)
        return TALLY_TURN_DELETED

    held = claim(shadow_id, now=now)
    if held is None:
        _log(EVENT_NOT_CLAIMED, None)
        return EVENT_NOT_CLAIMED
    if held.reclaimed:
        _log(EVENT_RECLAIMED, held.turn_id)

    try:
        return _decide(held, decider_factory, bucket_factory)
    except Exception as exc:
        logger.warning(
            "evidence shadow error turn=%s error=%s final=%s",
            held.turn_id,
            type(exc).__name__,
            final_attempt,
        )
        if final_attempt:
            return _finish_or_fenced(held, FAILED, FAIL_RETRIES_EXHAUSTED)
        release(held)
        raise


def _decide(held: Claim, decider_factory, bucket_factory) -> str:
    from apps.ai.composition import composition_root

    row = ShadowEvidenceDecision.objects.select_related("turn").get(pk=held.shadow_id)
    turn = row.turn

    decider = (decider_factory or composition_root().shadow_decider)()
    if decider is None:
        return _finish_or_fenced(held, SKIPPED, SKIP_MODEL_UNCONFIGURED)

    breaker_skip = _answer_breaker_skip()
    if breaker_skip:
        return _finish_or_fenced(held, SKIPPED, breaker_skip)

    differences = parity(turn, row.manifest)
    prior = _prior_questions(row.manifest)
    resolved = turn.resolved_question or None

    reserved = (
        estimated_request_tokens(
            turn.question, resolved_question=resolved, prior_reader_questions=prior
        )
        + RESERVED_OUTPUT_TOKENS
    )
    bucket = bucket_factory()
    try:
        window = bucket.spend(reserved)
    except RateLimited:
        return _finish_or_fenced(held, SKIPPED, SKIP_BUDGET_SPENT)

    try:
        decision = decider.decide(
            turn.question, resolved_question=resolved, prior_reader_questions=prior
        )
    except BaseException:
        # Nothing was reported as used; hand the reservation back.
        bucket.adjust(-reserved, window)
        raise
    if decision.input_tokens is not None or decision.output_tokens is not None:
        used = (decision.input_tokens or 0) + (decision.output_tokens or 0)
        bucket.adjust(used - reserved, window)

    code = _finish_or_fenced(
        held,
        COMPLETED,
        decision=decision.as_dict(),
        route=union_route(row.detector, decision.route),
        parity_matched=not differences,
        parity_differences=differences,
    )
    if code == EVENT_FENCED_OUT:
        # A model call was paid for and discarded.
        ShadowEvidenceDecision.objects.filter(pk=held.shadow_id).update(
            fenced_out_completions=F("fenced_out_completions") + 1
        )
    return code


# -- reporting -------------------------------------------------------------


def coverage() -> dict:
    """Operational figures only (ADR-035 §10); no accuracy."""
    rows = ShadowEvidenceDecision.objects.all()
    by_status = dict(rows.values_list("status").annotate(n=Count("pk")))
    by_outcome = dict(
        rows.exclude(outcome="").values_list("outcome").annotate(n=Count("pk"))
    )
    tallies = dict(ShadowEvidenceTally.objects.values_list("code", "count"))
    sums = rows.aggregate(
        reclaims=Sum("reclaims"), fenced_out=Sum("fenced_out_completions")
    )
    decided = by_status.get(COMPLETED, 0)
    recorded = sum(by_status.values())
    return {
        "recorded": recorded,
        "decided": decided,
        "missing": recorded - decided + sum(tallies.values()),
        "by_status": by_status,
        "by_outcome": by_outcome,
        "tallies": tallies,
        "reclaims": sums["reclaims"] or 0,
        "fenced_out_completions": sums["fenced_out"] or 0,
        "parity_mismatches": rows.filter(parity_matched=False).count(),
    }
