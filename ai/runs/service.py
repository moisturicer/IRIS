"""Submit and run one AI-owned AskRun (IR-722).

Admission, the executor and the final commit are three separate steps; no
transaction is open while the executor runs. Queue dispatch is IR-723: here
a newly admitted run is executed inline, once.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

from ai.runs import config as runs_config
from ai.runs.executor import Executor, Unavailable
from ai.runs.store import Fenced, RunStore

logger = logging.getLogger(__name__)


class RunService:
    def __init__(self, store: RunStore, cfg: runs_config.RunsConfig, executor: Executor):
        self.store = store
        self.cfg = cfg
        self.executor = executor
        self.worker = f"inline-{uuid.uuid4().hex[:12]}"

    def pinned(self) -> dict:
        pinned = {
            "executor": self.executor.name, "executor_version": self.executor.version,
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }
        pin = getattr(self.executor, "pin", None)
        if pin is not None:
            pinned["agent"] = pin.as_dict()
        return pinned

    async def submit(self, grant, *, key, question, conversation_id, base_revision):
        """The run's projection, and whether this submission admitted it."""
        row, created = await self.store.admit(
            grant, key=key, question=question, conversation_id=conversation_id,
            base_revision=base_revision, deadline_seconds=self.cfg.limits.deadline_seconds,
            allowance=self.cfg.limits.allowance(), pinned=self.pinned(),
        )
        if created:
            await self.execute(row["id"])
        return await self.store.status(grant, row["id"]), created

    async def execute(self, run_id) -> None:
        claim = await self.store.claim(
            run_id, worker=self.worker, lease_seconds=self.cfg.limits.lease_seconds,
            executor=self.executor.name, reserved_units=self.executor.reserved_units,
        )
        if claim is None:
            return
        if claim.pinned != self.pinned():
            # Never continue a run under another model or protocol (IR-727).
            logger.info("run %s unavailable: pin_changed", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            result = await self.executor.answer(claim.question)
        except Unavailable as refused:
            # Operators get the code; readers only see `unavailable`.
            logger.info("run %s unavailable: %s", run_id, refused.code)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        except Exception:
            await self.store.fail(run_id, claim.fence, "executor_failed")
            return
        try:
            await self.store.commit_final(run_id, claim.fence, result)
        except Fenced:
            return
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            # Rolled back whole; nothing of the answer was written.
            await self.store.fail(run_id, claim.fence, "commit_failed")
