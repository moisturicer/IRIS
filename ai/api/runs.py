"""Reader routes for AI-owned runs (IR-722, IR-723).

Every route needs the service secret (main.py) and a Django-issued
`reader_session` grant in X-IRIS-Reader-Grant, verified inside PostgreSQL.
A foreign run or Conversation is the same 404 as a missing one.

A submission is queued and answered by a worker; the reader polls status
to follow it, and a disconnect never cancels it.
"""

from __future__ import annotations

import functools
import re
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ai.runs import anchor
from ai.runs import config as runs_config
from ai.runs.service import RunService
from ai.runs.store import TITLE_MAX, Busy, Conflict, NotFound, Unauthorized
from ai.runs import public, stream

router = APIRouter()

GRANT_HEADER = "X-IRIS-Reader-Grant"


class RenameRequest(BaseModel):
    #: None or blank restores the first-question title (IR-1160).
    title: str | None = Field(default=None, max_length=1000)


class SubmitRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    #: The Conversation revision the question was asked against.
    base_revision: int | None = Field(default=None, ge=0)
    #: The larger configured profile unless the reader chooses "ordinary" (ADR-049 §16 as amended).
    depth: Literal["ordinary", "deep"] = runs_config.DEFAULT_DEPTH
    #: Paper Chat only: `{record_id, manuscript_revision, page, quote}`, the passage the question is
    #: about (IR-581). Shape is checked by `anchor.parse`, so every malformed one is `invalid_selection`.
    selection: dict | None = None


@functools.cache
def get_run_service() -> RunService:
    from ai.infrastructure.settings import settings
    from ai.runs.worker import build

    return build(settings)


def _service():
    try:
        return get_run_service()
    except runs_config.RunsUnavailable:
        return None


def _unavailable():
    return JSONResponse({"status": "unavailable"}, status_code=503)


async def _call(service, action, protocol=None):
    if protocol not in (None, public.PROTOCOL):
        return JSONResponse({"status": "unsupported_protocol"}, status_code=406)
    if service is None:
        return _unavailable()
    if protocol and service.executor.name != "agent":
        # A deterministic echo is an operator test, never a reader research answer.
        return _unavailable()
    try:
        return await action(service)
    except Unauthorized:
        return JSONResponse({"status": "unauthorized"}, status_code=401)
    except NotFound:
        return JSONResponse({"status": "not_found"}, status_code=404)
    except Conflict as conflict:
        if protocol:
            return JSONResponse({"status": "conflict"}, status_code=409)
        return JSONResponse({"status": conflict.code, **conflict.detail}, status_code=409)
    except Busy as busy:
        return JSONResponse({"status": "busy", **({} if protocol else {"reason": busy.reason})}, status_code=503)
    except anchor.Refused as refused:
        # The reader is told why, in both protocols: there is something they can do about each.
        return JSONResponse({"status": refused.code}, status_code=422)


def _meter(s) -> dict:
    """What the context meter draws beside the reported tokens: the answer's reserve and the compaction threshold."""
    reserves = getattr(s.executor, "reserves", None)
    rule = getattr(s.executor, "compaction", None)
    return {"reserved_tokens": (reserves.output_tokens + reserves.reasoning_tokens) if reserves else None,
            "compacts_at_tokens": rule.threshold_tokens if rule else None}


def _cursor(raw: str | None):
    """The (updated_at, id) a page ended at; ValueError if `raw` is not one."""
    if raw is None:
        return None
    stamp, _, ident = raw.partition("|")
    when = datetime.fromisoformat(stamp)
    if when.tzinfo is None:
        raise ValueError(raw)
    return when, uuid.UUID(ident)


@router.get("/conversations")
async def list_conversations(
    q: str | None = Query(default=None, max_length=200),
    before: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    """The reader's Conversations for the history list, one page at a time. Reader protocol only."""
    if protocol is None:
        return JSONResponse({"status": "unsupported_protocol"}, status_code=406)
    try:
        cursor = _cursor(before)
    except ValueError:
        return JSONResponse({"status": "invalid_cursor"}, status_code=422)

    async def act(s: RunService):
        items = await s.store.list_conversations(
            grant, q=(q or "").strip() or None, before=cursor, limit=limit + 1)
        page = items[:limit]
        more = len(items) > limit
        return JSONResponse({"protocol": public.PROTOCOL, "conversations": page,
                             "next": f"{page[-1]['updated_at']}|{page[-1]['id']}" if more else None})

    return await _call(service, act, protocol)


@router.post("/runs")
async def submit_run(
    body: SubmitRequest,
    idempotency_key: str = Header(min_length=8, max_length=128),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    try:
        selection = anchor.parse(body.selection) if body.selection is not None else None
    except ValueError:
        return JSONResponse({"status": "invalid_selection"}, status_code=422)

    async def act(s: RunService):
        run, created = await s.submit(
            grant, key=idempotency_key, question=body.question,
            conversation_id=body.conversation_id, base_revision=body.base_revision,
            depth=body.depth, selection=selection,
        )
        if protocol:
            run = await s.store.status(grant, run["id"], reader_projection=True)
        return JSONResponse(public.run(run, **_meter(s)) if protocol else run,
                            status_code=201 if created else 200)

    return await _call(service, act, protocol)


@router.get("/runs/{run_id}")
async def run_status(
    run_id: uuid.UUID,
    #: The journal position a reconnecting reader has already seen (IR-726); reader protocol only.
    after: int | None = Query(default=None, ge=0),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    if after is not None and not protocol:
        return JSONResponse({"status": "unsupported_protocol"}, status_code=406)

    async def act(s: RunService):
        snapshot = await s.store.status(grant, run_id, reader_projection=bool(protocol))
        return JSONResponse(public.run(snapshot, **_meter(s), after=after)
                            if protocol else snapshot)

    return await _call(service, act, protocol)


@router.get("/runs/{run_id}/draft")
async def stream_draft(
    run_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    """The answer as it is being written, as server-sent events, from its first piece.

    Each event is `{"t": "reset"}` (a new attempt replaces the text so far),
    `{"t": "text", "d": "..."}` or `{"t": "end"}`. Unchecked: the committed
    Turn is the answer. Reader protocol only; 204 when drafts are not published.
    """
    if protocol is None:
        return JSONResponse({"status": "unsupported_protocol"}, status_code=406)

    async def act(s: RunService):
        await s.store.status(grant, run_id)  # owned by this reader, or NotFound / Unauthorized
        if s.drafts is None:
            return Response(status_code=204)

        async def events():
            last = "0"
            idle = 0.0
            while True:
                try:
                    found = await s.drafts.xread({stream.key(run_id): last}, block=2000, count=200)
                except (TimeoutError, OSError):
                    found = []
                if not found:
                    idle += 2
                    # Nothing for a while: end once the run has, and keep the connection alive meanwhile.
                    run = await s.store.status(grant, run_id)
                    if run["state"] not in ("queued", "running") or idle > 900:
                        yield "data: {\"t\": \"end\"}\n\n"
                        return
                    yield ": keep-alive\n\n"
                    continue
                idle = 0.0
                for _key, entries in found:
                    for entry_id, fields in entries:
                        last = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                        raw = fields.get(b"e") or fields.get("e")
                        text = raw.decode() if isinstance(raw, bytes) else raw
                        yield f"data: {text}\n\n"
                        if '"t": "end"' in text:
                            return

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return await _call(service, act, protocol)


@router.post("/runs/{run_id}/retry")
async def retry_run(
    run_id: uuid.UUID,
    idempotency_key: str = Header(min_length=8, max_length=128),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    """Ask again, explicitly (IR-726): a new run linked to one that ended without an answer.

    201 with the new run, 200 for the same request again or a retry already
    started, 409 when the run is not retryable or its Conversation moved on.
    The first run's allowance and charges are untouched.
    """
    async def act(s: RunService):
        run, created = await s.retry(grant, run_id, key=idempotency_key)
        if protocol:
            run = await s.store.status(grant, run["id"], reader_projection=True)
        return JSONResponse(public.run(run, **_meter(s)) if protocol else run,
                            status_code=201 if created else 200)

    return await _call(service, act, protocol)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    async def act(s: RunService):
        snapshot = await s.store.cancel(grant, run_id, reader_projection=bool(protocol))
        return JSONResponse(public.run(snapshot, **_meter(s)) if protocol else snapshot)

    return await _call(service, act, protocol)


@router.get("/conversations/{conversation_id}")
async def reopen_conversation(
    conversation_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    async def act(s: RunService):
        snapshot = await s.store.reopen(grant, conversation_id, include_runs=bool(protocol))
        return JSONResponse(public.conversation(snapshot, **_meter(s)) if protocol else snapshot)

    return await _call(service, act, protocol)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: RenameRequest,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    if body.title is not None and len(body.title.strip()) > TITLE_MAX:
        return JSONResponse({"status": "title_too_long", "max_length": TITLE_MAX}, status_code=422)

    async def act(s: RunService):
        title = await s.store.rename(grant, conversation_id, body.title)
        return JSONResponse({"protocol": public.PROTOCOL, "id": str(conversation_id), "title": title})

    return await _call(service, act)


def _filename(title: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:80].strip("-")
    return f"{stem or 'conversation'}.md"


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    """The reader's Markdown download (IR-1167): the reopen view, rendered."""
    async def act(s: RunService):
        view = public.conversation(await s.store.reopen(grant, conversation_id, include_runs=True))
        return Response(public.markdown(view), media_type="text/markdown; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{_filename(view["title"])}"',
        })

    return await _call(service, act)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    async def act(s: RunService):
        await s.store.delete_conversation(grant, conversation_id)
        return Response(status_code=204)

    return await _call(service, act)
