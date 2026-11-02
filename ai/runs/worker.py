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


def build(settings) -> RunService:
    from ai.runs import config as runs_config
    from ai.runs.dispatch import notifier_for
    from ai.runs.executor import DeterministicExecutor
    from ai.runs.store import RunStore

    cfg = runs_config.read(settings)
    return RunService(RunStore(cfg.database_url), cfg, DeterministicExecutor(),
                      notifier_for(cfg.redis_url))


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
    except RunsUnavailable:
        raise SystemExit("runs are not configured; every RUNS_* limit is required") from None


if __name__ == "__main__":
    main()
