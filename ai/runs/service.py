"""Submit and run one AI-owned AskRun (IR-722, IR-723).

Admission commits a queued run, then wakes workers; a worker claims and
runs it. Disconnecting changes nothing: only Stop ends a run early. No
transaction is open while the executor runs.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

from ai.research.tools import ResearchTools
from ai.runs import config as runs_config
from ai.runs.dispatch import Notifier, PollingNotifier
from ai.runs.executor import Executor
from ai.runs.store import Claim, Fenced, RunStore

log = logging.getLogger(__name__)


class RunService:
    def __init__(self, store: RunStore, cfg: runs_config.RunsConfig, executor: Executor,
                 notifier: Notifier | None = None):
        self.store = store
        self.cfg = cfg
        self.executor = executor
        self.notifier = notifier or PollingNotifier()
        self.worker = f"worker-{uuid.uuid4().hex[:12]}"

    def pinned(self) -> dict:
        return {
            "executor": self.executor.name, "executor_version": self.executor.version,
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }

    async def submit(self, grant, *, key, question, conversation_id, base_revision,
                     depth="ordinary"):
        """The run's projection, and whether this submission admitted it."""
        dispatch = self.cfg.dispatch
        row, created = await self.store.admit(
            grant, key=key, question=question, conversation_id=conversation_id,
            base_revision=base_revision, deadline_seconds=self.cfg.limits.deadline_for(depth),
            allowance=self.cfg.limits.allowance(), pinned=self.pinned(), depth=depth,
            max_queued=dispatch.max_queued, max_active_per_reader=dispatch.max_active_per_reader,
        )
        if created:
            try:
                await self.notifier.notify()
            except Exception:
                # Committed already; a worker's scan finds it.
                log.warning("run wakeup not sent", exc_info=True)
        return await self.store.status(grant, row["id"]), created

    async def run_next(self) -> bool:
        """Claim and run one run; False when none can run now."""
        claim = await self.store.claim_next(
            worker=self.worker, lease_seconds=self.cfg.limits.lease_seconds,
            executor=self.executor.name, reserved_units=self.executor.reserved_units,
            deep_concurrency=self.cfg.dispatch.deep_concurrency,
            max_running_per_reader=self.cfg.dispatch.max_running_per_reader,
        )
        if claim is None:
            return False
        await self.execute(claim)
        return True

    async def execute(self, claim: Claim) -> None:
        """The run's tools read under the reader's stored grant (IR-719)."""
        run_id = claim.run_id
        try:
            tools = ResearchTools(self.store.dsn, claim.grant, run_id, claim.fence, claim.scope_record_id)
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
