"""On-demand claims, whole-paper workers and version/access fences (IR-556)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.ai.admission import scope
from apps.ai.admission.errors import AdmissionDenied
from apps.ai.admission.ledger import estimate_tokens
from apps.ai.admission.limits import enforcing
from apps.ai.answers.service import model_that_answered
from apps.ai.composition import composition_root
from apps.ai.inference import InferenceTask, profile_for
from apps.ai.inference.providers import BRIEF_OUTPUT_TOKENS
from apps.ai.models import ChunkSet, PaperBrief, ProviderReservation
from apps.ai.overview.assembly import whole_paper
from apps.records.models import Record

from .reading import PROMPT_VERSION, SYSTEM, combine, prompt, reading_sections, verify_fields

logger = logging.getLogger(__name__)


def _profile_hash(profile):
    # Credentials are deliberately excluded from this persisted fingerprint.
    values = (
        profile.vendor.value, profile.base_url, profile.models,
        profile.data_policy.value, profile.provider_only,
        profile.model_provider_pins, profile.model_context_windows,
    )
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _window(profile):
    windows = dict(profile.model_context_windows)
    if not profile.model or profile.model not in windows:
        raise ValueError("context_window_unknown")
    return windows[profile.model]


def _unavailable(reason):
    return {"state": "unavailable", "brief": None, "reason": reason}


def _authorized(record_id, user_id):
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return None
    record = Record.objects.visible_to(user).filter(pk=record_id).first()
    if record is None or not composition_root().vendor_permits()(record):
        return None
    return record


def _wire(stored):
    return {
        "id": stored.pk, "record_id": stored.record_id, "chunk_set_id": stored.chunk_set_id,
        "content_hash": stored.content_hash, "prompt_version": stored.prompt_version,
        "fields": stored.fields, "model": stored.model_id,
        "models_used": stored.models_used, "usage": stored.usage,
        "section_count": len(stored.section_briefs),
        "generated_at": stored.updated_at,
    }


def brief_for(record, *, user, retry=False, dispatch=True):
    """First comparison use queues one reading; later uses reuse its version.

    The caller passes the current reader, even if it already checked access.
    This is also the public service seam IR-549's comparison may call.
    """
    if not getattr(settings, "AI_PAPER_BRIEFS_ENABLED", False):
        return _unavailable("not_enabled")
    if _authorized(record.pk, user.pk) is None:
        return _unavailable("disclosure_or_access")
    profile = profile_for(InferenceTask.BRIEF)
    try:
        _window(profile)
    except ValueError as exc:
        return _unavailable(str(exc))

    with transaction.atomic():
        Record.objects.select_for_update().get(pk=record.pk)
        if _authorized(record.pk, user.pk) is None:
            return _unavailable("disclosure_or_access")
        chunk_set = ChunkSet.objects.filter(record=record, is_active=True).first()
        if chunk_set is None:
            return {"state": "not_indexed", "brief": None}
        fingerprint = _profile_hash(profile)
        stored = PaperBrief.objects.filter(
            record=record, content_hash=chunk_set.content_hash,
            prompt_version=PROMPT_VERSION, profile_hash=fingerprint,
        ).first()
        if stored is not None and stored.chunk_set_id == chunk_set.pk:
            if stored.state == "ready":
                return {"state": "ready", "brief": _wire(stored), "cached": True}
            if stored.state == "generating":
                result = {"state": "generating", "brief": None}
                if not dispatch:
                    result.update(brief_id=stored.pk, claim=str(stored.claim),
                                  started=stored.started_at is not None)
                return result
            if not retry:
                return _unavailable(stored.reason)
        if not enforcing():
            return _unavailable("admission_required")
        if stored is None:
            stored = PaperBrief(
                record=record, content_hash=chunk_set.content_hash,
                prompt_version=PROMPT_VERSION, profile_hash=fingerprint,
            )
        stored.chunk_set = chunk_set
        stored.requested_by = user
        stored.claim = uuid.uuid4()
        stored.state = "generating"
        stored.reason = ""
        stored.started_at = None
        stored.fields = {}
        stored.section_briefs = []
        stored.models_used = []
        stored.model_id = ""
        stored.usage = {}
        stored.save()
        brief_id, claim = stored.pk, str(stored.claim)
        if dispatch:
            transaction.on_commit(lambda: _enqueue(brief_id, claim))
    result = {"state": "generating", "brief": None}
    if not dispatch:
        result.update(brief_id=brief_id, claim=claim, started=False)
    return result


def cached_brief(record, *, user):
    """The ready brief for the active version and profile; never a new reading.

    A research tool reuses briefs only (IR-591), so it queues no paid work.
    """
    if not getattr(settings, "AI_PAPER_BRIEFS_ENABLED", False):
        return _unavailable("not_enabled")
    if _authorized(record.pk, user.pk) is None:
        return _unavailable("disclosure_or_access")
    chunk_set = ChunkSet.objects.filter(record=record, is_active=True).first()
    if chunk_set is None:
        return {"state": "not_indexed", "brief": None}
    stored = PaperBrief.objects.filter(
        record=record, chunk_set=chunk_set, content_hash=chunk_set.content_hash,
        prompt_version=PROMPT_VERSION, state="ready",
        profile_hash=_profile_hash(profile_for(InferenceTask.BRIEF)),
    ).first()
    if stored is None:
        return _unavailable("not_generated")
    return {"state": "ready", "brief": _wire(stored), "cached": True}


def _enqueue(brief_id, claim):
    from apps.ai.tasks import generate_paper_brief

    try:
        generate_paper_brief.delay(brief_id, claim)
    except Exception:
        logger.exception("could not queue paper brief %s", brief_id)
        PaperBrief.objects.filter(pk=brief_id, claim=claim, state="generating").update(
            state="unavailable", reason="queue_unavailable", updated_at=timezone.now(),
        )


def _current(stored, profile):
    return (
        getattr(settings, "AI_PAPER_BRIEFS_ENABLED", False)
        and enforcing()
        and stored.prompt_version == PROMPT_VERSION
        and stored.profile_hash == _profile_hash(profile)
        and ChunkSet.objects.filter(
            pk=stored.chunk_set_id, record_id=stored.record_id,
            is_active=True, content_hash=stored.content_hash,
        ).exists()
        and _authorized(stored.record_id, stored.requested_by_id) is not None
    )


def _usage(run_key):
    rows = ProviderReservation.objects.using("admission").filter(
        Q(work_key=run_key) | Q(work_key="", run_key=run_key),
    )
    totals = rows.aggregate(input_tokens=Sum("charge_input_tokens"), output_tokens=Sum("charge_output_tokens"))
    # Deterministic unmetered fakes have no reservations; missing usage is unknown.
    if not rows.exists():
        return {"input_tokens": None, "output_tokens": None, "complete": False}
    return {**totals, "complete": not rows.filter(usage_reported=False, charge_attempts=1).exists()}


def _send_check(stored, prompt_tokens, model):
    profile = profile_for(InferenceTask.BRIEF)
    if not _current(stored, profile):
        raise AdmissionDenied("stale_or_forbidden")
    window = dict(profile.model_context_windows).get(model or profile.model)
    if window is None or prompt_tokens + BRIEF_OUTPUT_TOKENS > window:
        raise AdmissionDenied("context_window_unknown_or_insufficient")


def generate_brief(brief_id, claim):
    """Only one worker starts a claim, even on duplicate Celery delivery."""
    claimed = PaperBrief.objects.filter(pk=brief_id, claim=claim, state="generating")
    if not claimed.filter(started_at__isnull=True).update(started_at=timezone.now()):
        return
    stored = claimed.select_related("chunk_set", "record").first()
    if stored is None:
        return
    run_key = f"brief:{brief_id}"
    sections, models = [], []
    reason = "generation_unavailable"
    try:
        profile = profile_for(InferenceTask.BRIEF)
        if not _current(stored, profile):
            reason = "stale_or_forbidden"
            return
        sources = whole_paper(stored.chunk_set)
        if not sources:
            reason = "not_indexed"
            return
        stored_text = dict(stored.chunk_set.chunks.values_list("pk", "text"))
        batches = reading_sections(stored.record.title, sources, _window(profile), BRIEF_OUTPUT_TOKENS)
        llm = composition_root().llm_for(InferenceTask.BRIEF)
        with scope.run(scope.new_run(run_key)), scope.work_item(run_key), scope.workload("research"):
            for batch in batches:
                # Access, disclosure, version and profile are rechecked before every send.
                if not _current(stored, profile_for(InferenceTask.BRIEF)):
                    reason = "stale_or_forbidden"
                    return
                user_prompt = prompt(stored.record.title, batch)
                prompt_tokens = estimate_tokens(SYSTEM, user_prompt)
                with scope.before_send(lambda model: _send_check(stored, prompt_tokens, model)), scope.observe_usage() as reports:
                    reply = llm.generate(SYSTEM, user_prompt)
                sections.append(verify_fields(reply, batch, stored_text))
                response_model = reports[-1].model if reports else None
                models.append(response_model or model_that_answered(llm) or profile.model)
        fields = combine(sections)
        # Serialize the final version check with claims and re-chunking's parent lock.
        with transaction.atomic():
            Record.objects.select_for_update().get(pk=stored.record_id)
            if not _current(stored, profile_for(InferenceTask.BRIEF)):
                reason = "stale_or_forbidden"
                return
            claimed.update(
                state="ready", fields=fields, section_briefs=sections,
                model_id=models[-1], models_used=list(dict.fromkeys(models)),
                usage=_usage(run_key), reason="", updated_at=timezone.now(),
            )
    except (ValueError, json.JSONDecodeError):
        reason = "invalid_brief"
        logger.warning("invalid paper brief %s", brief_id)
    except Exception:
        # Never retry an unresolved paid attempt automatically after a worker failure.
        logger.exception("paper brief generation failed for %s", brief_id)
    finally:
        # A store outage must not leave a completed worker's claim generating.
        try:
            usage = _usage(run_key)
        except Exception:
            usage = {"input_tokens": None, "output_tokens": None, "complete": False}
        claimed.update(state="unavailable", reason=reason, usage=usage, updated_at=timezone.now())
