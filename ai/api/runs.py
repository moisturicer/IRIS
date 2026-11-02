"""Reader routes for AI-owned runs (IR-722, IR-723).

Every route needs the service secret (main.py) and a Django-issued
`reader_session` grant in X-IRIS-Reader-Grant, verified inside PostgreSQL.
A foreign run or Conversation is the same 404 as a missing one.

A submission is queued and answered by a worker; the reader polls status
to follow it, and a disconnect never cancels it.
"""

from __future__ import annotations

import functools
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ai.runs import config as runs_config
from ai.runs.service import RunService
from ai.runs.store import Busy, Conflict, NotFound, Unauthorized
from ai.runs import public

router = APIRouter()

GRANT_HEADER = "X-IRIS-Reader-Grant"


class SubmitRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    #: The Conversation revision the question was asked against.
    base_revision: int | None = Field(default=None, ge=0)
    #: "deep" asks for the larger configured profile (ADR-049 §16).
    depth: Literal["ordinary", "deep"] = "ordinary"


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


@router.post("/runs")
async def submit_run(
    body: SubmitRequest,
    idempotency_key: str = Header(min_length=8, max_length=128),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    async def act(s: RunService):
        run, created = await s.submit(
            grant, key=idempotency_key, question=body.question,
            conversation_id=body.conversation_id, base_revision=body.base_revision,
            depth=body.depth,
        )
        if protocol:
            run = await s.store.status(grant, run["id"], reader_projection=True)
        return JSONResponse(public.run(run) if protocol else run, status_code=201 if created else 200)

    return await _call(service, act, protocol)


@router.get("/runs/{run_id}")
async def run_status(
    run_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
    protocol: str | None = Header(default=None, alias="X-IRIS-Protocol"),
):
    async def act(s: RunService):
        snapshot = await s.store.status(grant, run_id, reader_projection=bool(protocol))
        return JSONResponse(public.run(snapshot) if protocol else snapshot)

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
        return JSONResponse(public.run(snapshot) if protocol else snapshot)

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
        return JSONResponse(public.conversation(snapshot) if protocol else snapshot)

    return await _call(service, act, protocol)


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
