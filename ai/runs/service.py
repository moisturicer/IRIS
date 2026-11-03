"""Submit and run one AI-owned AskRun (IR-722, IR-723).

Admission commits a queued run, then wakes workers; a worker claims and
runs it. Disconnecting changes nothing: only Stop ends a run early. No
transaction is open while the executor runs.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict

import asyncpg

from ai.admission import scope as admission
from ai.agent.budget import Bounds
from ai.research.tools import ResearchTools
from ai.runs import config as runs_config
from ai.runs.dispatch import Notifier, PollingNotifier
from ai.runs.executor import Executor, RunContext, Unavailable
from ai.runs.store import Claim, Fenced, RunStore

log = logging.getLogger(__name__)


class RunService:
    def __init__(self, store: RunStore, cfg: runs_config.RunsConfig, executor: Executor,
                 notifier: Notifier | None = None, *, serves=(), embedding_provider=None,
                 embedding_ledger=None):
        self.embedding_provider = embedding_provider
        self.embedding_ledger = embedding_ledger
        self.store = store
        self.cfg = cfg
        #: What new runs are pinned to.
        self.executor = executor
        #: Every executor this worker answers runs with, by name (IR-862).
        self.executors = {e.name: e for e in (*serves, executor)}
        self.notifier = notifier or PollingNotifier()
        self.worker = f"worker-{uuid.uuid4().hex[:12]}"

    def pinned(self, depth: str = "ordinary", executor: Executor | None = None) -> dict:
        """What fixes a run's interpretation, persisted at admission."""
        executor = executor or self.executor
        pinned = {
            "executor": executor.name, "executor_version": executor.version,
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }
        pin = getattr(executor, "pin", None)
        if pin is not None:
            pinned["agent"] = pin.as_dict()
        profiles = getattr(executor, "profiles", None)
        if profiles:
            # The run keeps these bounds whichever worker answers it (IR-862).
            pinned["bounds"] = asdict(profiles[depth])
        return pinned

    def _executor_for(self, pinned: dict | None) -> Executor | None:
        """The executor the run was pinned to, unchanged, or None."""
        pinned = pinned or {}
        executor = self.executors.get(pinned.get("executor"))
        if executor is None or pinned.get("executor_version") != executor.version:
            return None
        pin = getattr(executor, "pin", None)
        # Never continue a run under another AGENT pin (IR-727).
        if pinned.get("agent") != (pin.as_dict() if pin is not None else None):
            return None
        return executor

    @staticmethod
    def _bounds_for(executor: Executor, pinned: dict | None) -> Bounds | None:
        """A researching run's bounds as admitted; ValueError when unusable.

        A run without them is refused rather than given this worker's, which
        could be wider (IR-862).
        """
        if not getattr(executor, "profiles", None):
            return None
        stored = (pinned or {}).get("bounds")
        if not isinstance(stored, dict):
            raise ValueError("bounds")
        try:
            return Bounds(**stored)
        except TypeError:
            raise ValueError("bounds") from None

    async def submit(self, grant, *, key, question, conversation_id, base_revision,
                     depth="ordinary"):
        """The run's projection, and whether this submission admitted it."""
        dispatch = self.cfg.dispatch
        row, created = await self.store.admit(
            grant, key=key, question=question, conversation_id=conversation_id,
            base_revision=base_revision, deadline_seconds=self.cfg.limits.deadline_for(depth),
            allowance=self.cfg.limits.allowance(), pinned=self.pinned(depth), depth=depth,
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
            executor=None, reserved_units={n: e.reserved_units for n, e in self.executors.items()},
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
        executor = self._executor_for(claim.pinned)
        if executor is None:
            # Not served here under its pin; never substituted (IR-727, IR-862).
            log.info("run %s unavailable: pin_changed", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            bounds = self._bounds_for(executor, claim.pinned)
        except ValueError:
            log.info("run %s unavailable: bounds_unpinned", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            tools = ResearchTools(self.store.dsn, claim.grant, run_id, claim.fence, claim.scope_record_id,
                                  embedding_provider=self.embedding_provider, embedding_ledger=self.embedding_ledger)
            # Every provider attempt inside is admitted against this run (IR-725).
            with admission.bound(admission.RunBinding(run_id, claim.fence)):
                if getattr(executor, "takes_context", False):
                    result = await executor.answer(claim.question, tools, context=RunContext(
                        allowance=claim.allowance, remaining_seconds=claim.remaining_seconds,
                        depth=claim.depth, prior=claim.prior, state=claim.state or {},
                        bounds=bounds,
                    ))
                else:
                    result = await executor.answer(claim.question, tools)
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
