"""Reader routes for AI-owned runs (IR-722).

Every route needs the service secret (main.py) and a Django-issued
`reader_session` grant in X-IRIS-Reader-Grant, verified inside PostgreSQL.
A foreign run or Conversation is the same 404 as a missing one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ai.runs import config as runs_config
from ai.runs.executor import DeterministicExecutor
from ai.runs.service import RunService
from ai.runs.store import Conflict, NotFound, RunStore, Unauthorized

router = APIRouter()

GRANT_HEADER = "X-IRIS-Reader-Grant"


class SubmitRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    #: The Conversation revision the question was asked against.
    base_revision: int | None = Field(default=None, ge=0)


def get_run_service() -> RunService:
    from ai.infrastructure.settings import settings

    cfg = runs_config.read(settings)
    return RunService(RunStore(cfg.database_url), cfg, DeterministicExecutor())


def _service():
    try:
        return get_run_service()
    except runs_config.RunsUnavailable:
        return None


def _unavailable():
    return JSONResponse({"status": "unavailable"}, status_code=503)


async def _call(service, action):
    if service is None:
        return _unavailable()
    try:
        return await action(service)
    except Unauthorized:
        return JSONResponse({"status": "unauthorized"}, status_code=401)
    except NotFound:
        return JSONResponse({"status": "not_found"}, status_code=404)
    except Conflict as conflict:
        return JSONResponse({"status": conflict.code, **conflict.detail}, status_code=409)


@router.post("/runs")
async def submit_run(
    body: SubmitRequest,
    idempotency_key: str = Header(min_length=8, max_length=128),
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    async def act(s: RunService):
        run, created = await s.submit(
            grant, key=idempotency_key, question=body.question,
            conversation_id=body.conversation_id, base_revision=body.base_revision,
        )
        return JSONResponse(run, status_code=201 if created else 200)

    return await _call(service, act)


@router.get("/runs/{run_id}")
async def run_status(
    run_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    async def act(s: RunService):
        return JSONResponse(await s.store.status(grant, run_id))

    return await _call(service, act)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    async def act(s: RunService):
        return JSONResponse(await s.store.cancel(grant, run_id))

    return await _call(service, act)


@router.get("/conversations/{conversation_id}")
async def reopen_conversation(
    conversation_id: uuid.UUID,
    grant: str | None = Header(default=None, alias=GRANT_HEADER),
    service: RunService | None = Depends(_service),
):
    async def act(s: RunService):
        return JSONResponse(await s.store.reopen(grant, conversation_id))

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
