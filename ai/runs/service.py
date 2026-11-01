"""Submit and run one AI-owned AskRun (IR-722).

Admission, the executor and the final commit are three separate steps; no
transaction is open while the executor runs. Queue dispatch is IR-723: here
a newly admitted run is executed inline, once.
"""

from __future__ import annotations

import uuid

import asyncpg

from ai.research.tools import ResearchTools
from ai.runs import config as runs_config
from ai.runs.executor import Executor
from ai.runs.store import Fenced, RunStore


class RunService:
    def __init__(self, store: RunStore, cfg: runs_config.RunsConfig, executor: Executor):
        self.store = store
        self.cfg = cfg
        self.executor = executor
        self.worker = f"inline-{uuid.uuid4().hex[:12]}"

    def pinned(self) -> dict:
        return {
            "executor": self.executor.name, "executor_version": self.executor.version,
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }

    async def submit(self, grant, *, key, question, conversation_id, base_revision):
        """The run's projection, and whether this submission admitted it."""
        row, created = await self.store.admit(
            grant, key=key, question=question, conversation_id=conversation_id,
            base_revision=base_revision, deadline_seconds=self.cfg.limits.deadline_seconds,
            allowance=self.cfg.limits.allowance(), pinned=self.pinned(),
        )
        if created:
            await self.execute(row["id"], grant)
        return await self.store.status(grant, row["id"]), created

    async def execute(self, run_id, grant) -> None:
        """The run's tools read under the reader's `grant` (IR-719)."""
        claim = await self.store.claim(
            run_id, worker=self.worker, lease_seconds=self.cfg.limits.lease_seconds,
            executor=self.executor.name, reserved_units=self.executor.reserved_units,
        )
        if claim is None:
            return
        try:
            tools = ResearchTools(self.store.dsn, grant, run_id, claim.fence, claim.scope_record_id)
            result = await self.executor.answer(claim.question, tools)
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
