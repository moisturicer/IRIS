"""Submit and run one AI-owned AskRun (IR-722, IR-723).

Admission commits a queued run, then wakes workers; a worker claims and
runs it. Disconnecting changes nothing: only Stop ends a run early. No
transaction is open while the executor runs.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

from ai.admission import scope as admission
from ai.research.tools import ResearchTools
from ai.runs import config as runs_config
from ai.runs.dispatch import Notifier, PollingNotifier
from ai.runs.executor import Executor, RunContext, Unavailable
from ai.runs.store import Claim, Fenced, RunStore

log = logging.getLogger(__name__)


class RunService:
    def __init__(self, store: RunStore, cfg: runs_config.RunsConfig, executor: Executor,
                 notifier: Notifier | None = None, *, embedding_provider=None, embedding_ledger=None):
        self.embedding_provider = embedding_provider
        self.embedding_ledger = embedding_ledger
        self.store = store
        self.cfg = cfg
        self.executor = executor
        self.notifier = notifier or PollingNotifier()
        self.worker = f"worker-{uuid.uuid4().hex[:12]}"

    def pinned(self) -> dict:
        pinned = {
            "executor": self.executor.name, "executor_version": self.executor.version,
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }
        pin = getattr(self.executor, "pin", None)
        if pin is not None:
            pinned["agent"] = pin.as_dict()
        return pinned

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
        if (claim.pinned or {}).get("agent") != self.pinned().get("agent"):
            # Never continue a run under another AGENT pin (IR-727).
            log.info("run %s unavailable: pin_changed", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            tools = ResearchTools(self.store.dsn, claim.grant, run_id, claim.fence, claim.scope_record_id,
                                  embedding_provider=self.embedding_provider, embedding_ledger=self.embedding_ledger)
            # Every provider attempt inside is admitted against this run (IR-725).
            with admission.bound(admission.RunBinding(run_id, claim.fence)):
                if getattr(self.executor, "takes_context", False):
                    result = await self.executor.answer(claim.question, tools, context=RunContext(
                        allowance=claim.allowance, remaining_seconds=claim.remaining_seconds,
                        depth=claim.depth, prior=claim.prior, state=claim.state or {},
                    ))
                else:
                    result = await self.executor.answer(claim.question, tools)
        except Unavailable as refused:
            # Operators get the code; readers only see `unavailable`.
            log.info("run %s unavailable: %s", run_id, refused.code)
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
