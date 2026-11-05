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
from ai.runs.executor import Compacted, Executor, RunContext, Unavailable
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
        identity = self._identity(executor)
        pinned = {
            "executor": identity["executor"], "executor_version": identity["executor_version"],
            "protocol": runs_config.PROTOCOL, "schema": runs_config.SCHEMA,
        }
        if identity["agent"] is not None:
            pinned["agent"] = identity["agent"]
        profiles = getattr(executor, "profiles", None)
        if profiles:
            # The run keeps these bounds whichever worker answers it (IR-862).
            pinned["bounds"] = asdict(profiles[depth])
        return pinned

    @staticmethod
    def _identity(executor: Executor) -> dict:
        """The part of a pin that names who may answer the run."""
        pin = getattr(executor, "pin", None)
        return {"executor": executor.name, "executor_version": executor.version,
                "agent": pin.as_dict() if pin is not None else None}

    def _executor_for(self, pinned: dict | None) -> Executor | None:
        """The executor the run was pinned to, unchanged, or None."""
        pinned = pinned or {}
        executor = self.executors.get(pinned.get("executor"))
        # Never continue a run under another executor or AGENT pin (IR-727).
        if executor is None or self._identity(executor) != {
                "executor": pinned.get("executor"), "executor_version": pinned.get("executor_version"),
                "agent": pinned.get("agent")}:
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

    @property
    def can_compact(self) -> bool:
        """Whether a reader may ask to condense a Conversation (IR-754).

        Only an AGENT that new runs are pinned to and that has a compaction
        rule: the same mechanism and the same admission as automatic
        compaction, never a second summarizer.
        """
        return (getattr(self.executor, "compaction", None) is not None
                and callable(getattr(self.executor, "compact", None)))

    async def submit(self, grant, *, key, question, conversation_id, base_revision,
                     depth=runs_config.DEFAULT_DEPTH):
        """The run's projection, and whether this submission admitted it."""
        return await self._enqueue(grant, key=key, question=question, conversation_id=conversation_id,
                                   base_revision=base_revision, depth=depth, pinned=self.pinned(depth))

    async def submit_compaction(self, grant, *, key, conversation_id, base_revision):
        """The run that condenses the Conversation, and whether this request admitted it (IR-754).

        A run of its own: it has its own identity, deadline and allowance,
        asks nothing and writes no Turn. It is admitted only where an Ask
        would be -- no active run in the Conversation, the revision the reader
        saw -- so it never shares or extends an investigation's budget.
        """
        depth = "ordinary"
        return await self._enqueue(grant, key=key, question=None, conversation_id=conversation_id,
                                   base_revision=base_revision, depth=depth, compaction=True,
                                   pinned={**self.pinned(depth), "kind": runs_config.KIND_COMPACT})

    async def _enqueue(self, grant, *, key, question, conversation_id, base_revision, depth, pinned,
                       compaction=False):
        dispatch = self.cfg.dispatch
        row, created = await self.store.admit(
            grant, key=key, question=question, conversation_id=conversation_id,
            base_revision=base_revision, deadline_seconds=self.cfg.limits.deadline_for(depth),
            allowance=self.cfg.limits.allowance(), pinned=pinned, depth=depth,
            max_queued=dispatch.max_queued, max_active_per_reader=dispatch.max_active_per_reader,
            compaction=compaction,
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
            # A run pinned to anything else waits for a worker that serves it (IR-862).
            serves=[self._identity(e) for e in self.executors.values()],
        )
        if claim is None:
            return False
        await self.execute(claim)
        return True

    async def _save(self, claim: Claim, step: int, body: dict) -> bool:
        """Store a completed step under the claim's fence; False once it lost the run (IR-724)."""
        try:
            await self.store.save_checkpoint(claim.run_id, claim.fence, step, body,
                                             lease_seconds=self.cfg.limits.lease_seconds)
        except Fenced:
            return False
        return True

    async def _commit_handoff(self, claim: Claim, handoff) -> tuple:
        """Commit a compact handoff under the claim's fence (IR-734)."""
        return await self.store.commit_handoff(claim.run_id, claim.fence, handoff)

    def _context(self, claim: Claim, bounds) -> RunContext:
        return RunContext(
            allowance=claim.allowance, remaining_seconds=claim.remaining_seconds,
            depth=claim.depth, prior=claim.prior, state=claim.state or {},
            bounds=bounds, checkpoint=claim.checkpoint, spent=claim.spent or {},
            save=lambda step, body: self._save(claim, step, body),
            handoff=claim.handoff, compactions=claim.compactions, committed=claim.committed,
            commit_handoff=lambda handoff: self._commit_handoff(claim, handoff),
        )

    async def execute(self, claim: Claim) -> None:
        """The run's tools read under the reader's stored grant (IR-719)."""
        run_id = claim.run_id
        executor = self._executor_for(claim.pinned)
        if executor is None:
            # Claimed directly (`claim`), or its pin changed under it; never substituted.
            log.info("run %s unavailable: pin_changed", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            bounds = self._bounds_for(executor, claim.pinned)
        except ValueError:
            log.info("run %s unavailable: bounds_unpinned", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        compacting = (claim.pinned or {}).get("kind") == runs_config.KIND_COMPACT
        if compacting and not callable(getattr(executor, "compact", None)):
            log.info("run %s unavailable: cannot_compact", run_id)
            await self.store.fail(run_id, claim.fence, "unavailable")
            return
        try:
            tools = ResearchTools(self.store.dsn, claim.grant, run_id, claim.fence, claim.scope_record_id,
                                  embedding_provider=self.embedding_provider, embedding_ledger=self.embedding_ledger)
            # Every provider attempt inside is admitted against this run (IR-725).
            with admission.bound(admission.RunBinding(run_id, claim.fence)):
                if compacting:
                    result = await executor.compact(tools, self._context(claim, bounds))
                elif getattr(executor, "takes_context", False):
                    result = await executor.answer(claim.question, tools, context=self._context(claim, bounds))
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
            if isinstance(result, Compacted):
                await self.store.commit_compaction(run_id, claim.fence, result)
            else:
                await self.store.commit_final(run_id, claim.fence, result)
        except Fenced:
            return
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            # Rolled back whole; nothing of the answer was written.
            await self.store.fail(run_id, claim.fence, "commit_failed")
