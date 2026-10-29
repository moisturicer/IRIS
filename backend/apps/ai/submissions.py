"""Request identity shared by JSON, SSE and queued sends (IR-561).

Claims commit before resolution or generation. A retry either replays its
Turn, follows its existing queued run, or gets 409 with Retry-After while
the first request is pending. It never starts another vendor call.
"""
import hashlib
import json
from dataclasses import replace
from uuid import UUID

from rest_framework.response import Response

from apps.ai.models import ChatSubmission


def claim(data, prepared, *, max_sources):
    raw = data.get("request_id")
    if raw is None:
        return None, True, None  # Older clients remain compatible.
    try:
        identity = UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None, False, Response({"detail": "request_id must be a UUID."}, status=400)
    if prepared.conversation is None:
        return None, False, Response({"detail": "request_id requires a Conversation."}, status=400)
    payload = {
        "question": prepared.question, "top_k": max_sources,
        "widen": bool(data.get("widen")), "route_override": prepared.route_override,
        "route_override_turn_id": prepared.override_turn_id,
        "comparison_record_ids": list(prepared.comparison_record_ids),
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    submission, created = ChatSubmission.objects.get_or_create(
        conversation=prepared.conversation, request_id=identity,
        defaults={"fingerprint": fingerprint},
    )
    if submission.fingerprint != fingerprint:
        return None, False, Response({"detail": "request_id already identifies a different question or options."}, status=409)
    return submission, created, None


def pending(submission):
    interrupted = submission.finished or (submission.run_id is not None and submission.run.is_terminal)
    return Response({
        "detail": ("This request ended without a saved answer. Send a new question to try again."
                   if interrupted else "IRIS is still answering this request. Retry with the same request_id."),
        "status": "interrupted" if interrupted else "pending",
    }, status=409, headers={"Retry-After": "1"})


def finish(submission):
    if submission is not None:
        ChatSubmission.objects.filter(pk=submission.pk).update(finished=True)


def bind(prepared, submission):
    return replace(prepared, submission_id=submission.pk) if submission is not None else prepared


def replay(submission, user, *, public):
    from apps.ai import public as public_protocol
    from apps.ai.conversations import turn_for_reader
    from apps.ai.presentation import record_card
    from apps.records.models import Record

    body = turn_for_reader(submission.turn, user, public=public)
    records = Record.objects.visible_to(user).filter(
        pk__in=[ref["id"] for ref in submission.source_refs],
    ).select_related("classification").prefetch_related("authors").in_bulk()
    body.update(turn_id=submission.turn_id, conversation_id=submission.conversation_id,
                mode=body.get("state", body.get("mode")), sources=[
                    record_card(records[ref["id"]], ref["score"])
                    for ref in submission.source_refs if ref["id"] in records
                ])
    # Datetimes in transcript shapes are rendered by DRF; SSE uses json.dumps.
    body.pop("created_at", None)
    return public_protocol.project_done(body) if public else body
