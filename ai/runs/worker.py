"""The research worker process (IR-723, ADR-049 §2, §12).

`python -m ai.runs.worker` with the gateway's RUNS_* settings. Runs
`RUNS_WORKER_CONCURRENCY` slots; each claims from PostgreSQL, and waits for
a wakeup or `RUNS_POLL_SECONDS` when nothing can run. It serves research
runs only: ingestion runs on its own workers and never takes these slots.
Each slot holds at most one database connection at a time.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from ai.runs.service import RunService

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, service: RunService):
        self.service = service
        self.dispatch = service.cfg.dispatch

    async def _slot(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                if await self.service.run_next():
                    continue
            except Exception:
                log.exception("run dispatch failed")
            try:
                await self.service.notifier.wait(self.dispatch.poll_seconds)
            except Exception:
                log.warning("wakeup wait failed", exc_info=True)
                await asyncio.sleep(self.dispatch.poll_seconds)

    async def serve(self, stop: asyncio.Event) -> None:
        await asyncio.gather(*(self._slot(stop) for _ in range(self.dispatch.worker_concurrency)))


def build(settings, *, agent_provider=None) -> RunService:
    """New runs are pinned to `RUNS_EXECUTOR`; every claimed run is answered
    by the executor its own pin names (IR-862). An AGENT worker still serves
    deterministic runs, so both coexist during the cutover.

    `agent_provider` replaces the configured vendor adapter, for tests only.
    """
    from ai.runs import agent_profile
    from ai.runs import config as runs_config
    from ai.runs.dispatch import notifier_for
    from ai.runs.executor import DeterministicExecutor
    from ai.runs.store import RunStore

    cfg = runs_config.read(settings)
    profile = agent_profile.selected(settings)
    deterministic = DeterministicExecutor()
    if profile is None:
        pinned_to, also = deterministic, ()
    else:
        pinned_to = agent_profile.executor(profile, cfg.database_url, provider=agent_provider)
        also = (deterministic,)
    return RunService(RunStore(cfg.database_url), cfg, pinned_to, notifier_for(cfg.redis_url),
                      serves=also, **search_providers(settings, cfg.database_url, profile))


def search_providers(settings, dsn: str, profile) -> dict:
    """Search-by-meaning providers, only when configured (IR-886).

    Without the AGENT profile there is no admission ledger to charge, and
    without a Voyage key no query embedding: search then answers by keyword
    and says so. Reranking is off unless RUNS_RERANK_MODEL names a model.
    """
    key = str(getattr(settings, "VOYAGE_API_KEY", "") or "").strip()
    if profile is None or not key:
        return {}
    from ai.admission.ledger import Ledger
    from ai.ingestion.embeddings import VoyageContextEmbeddings
    from ai.research.rerank import VoyageReranker

    rerank_model = str(getattr(settings, "RUNS_RERANK_MODEL", "") or "").strip()
    return {
        "embedding_provider": VoyageContextEmbeddings(
            key, model="voyage-context-4", dimensions=1024),
        "embedding_ledger": Ledger(dsn, profile.limits),
        "reranker": VoyageReranker(key, model=rerank_model) if rerank_model else None,
    }


async def _main() -> None:
    from ai.infrastructure.settings import settings

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await Worker(build(settings)).serve(stop)


def main() -> None:
    from ai.runs.config import RunsUnavailable

    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(_main())
    except RunsUnavailable as refused:
        raise SystemExit(f"runs are not configured: {refused}") from None


if __name__ == "__main__":
    main()
