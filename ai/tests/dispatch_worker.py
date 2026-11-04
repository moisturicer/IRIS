"""An independent research worker process for IR-723's dispatch tests.

`python -m ai.tests.dispatch_worker <dsn> <config.json>`

Serves with `ai.runs.worker.Worker` until no run is in flight and none has
ended for `idle_seconds`, then prints how many runs it ran. Its executor sleeps `deep_seconds` for a
question starting "deep:" and `ordinary_seconds` otherwise.
"""

import asyncio
import json
import sys
import time

from ai.runs import config as runs_config
from ai.runs.dispatch import notifier_for
from ai.runs.executor import Result
from ai.runs.service import RunService
from ai.runs.store import RunStore
from ai.runs.worker import Worker


class SleepingExecutor:
    # A slowed deterministic executor: runs are answered by the executor their
    # pin names (IR-862), and these runs are pinned to the deterministic one.
    name = "deterministic"
    version = "1"
    reserved_units = 1

    def __init__(self, ordinary_seconds, deep_seconds):
        self.seconds = {"ordinary": ordinary_seconds, "deep": deep_seconds}

    async def answer(self, question, tools):
        await asyncio.sleep(self.seconds["deep" if question.startswith("deep:") else "ordinary"])
        return Result(answer=f"Slept on: {question}")


async def main(dsn, raw):
    spec = json.loads(raw)
    cfg = runs_config.RunsConfig(
        database_url=dsn, executor="deterministic",
        limits=runs_config.RunLimits(**spec["limits"]),
        dispatch=runs_config.Dispatch(**spec["dispatch"]),
        redis_url=spec.get("redis_url", ""),
    )
    service = RunService(RunStore(dsn), cfg,
                         SleepingExecutor(spec["ordinary_seconds"], spec["deep_seconds"]),
                         notifier_for(cfg.redis_url))
    ran = 0
    in_flight = 0
    last = time.monotonic()
    execute = service.execute

    async def counted(claim):
        nonlocal ran, in_flight, last
        in_flight += 1
        try:
            await execute(claim)
        finally:
            in_flight -= 1
            ran += 1
            last = time.monotonic()

    service.execute = counted
    stop = asyncio.Event()

    async def watch():
        while in_flight or time.monotonic() - last < spec["idle_seconds"]:
            await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(Worker(service).serve(stop), watch())
    return ran


if __name__ == "__main__":
    print(asyncio.run(main(sys.argv[1], sys.argv[2])))
