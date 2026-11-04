"""An independent AGENT research worker process for IR-862's and IR-724's tests.

`python -m ai.tests.agent_worker <dsn> <spec.json>`

Built by `ai.runs.worker.build` from the spec's settings, as the real worker
is, with the recording provider standing in for the configured vendor. Each
response is an answer text, a raw chat-completions response, or "hang" for
an attempt that never answers. Serves until no run is in flight and none has
ended for `idle_seconds`, then prints how many runs it ran.

`spec["die"]` (IR-724) kills the process outright, with no cleanup, at one
point of a step: `{"at": "response" | "tool" | "before_checkpoint" |
"after_checkpoint", "after": n}`, the n-th time it is reached. It exits
`KILLED`.

`spec["admitted"] = false` builds it with `unadmitted` instead: IR-725's
guard withholds every request carrying a tool result from a paid provider,
so only an unadmitted worker can continue past a completed step.
"""

import asyncio
import json
import os
import sys
import time
from types import SimpleNamespace

from ai.agent.tools import Investigation
from ai.infrastructure.recording_adapter import HANG, RecordingAgentProvider
from ai.runs.service import RunService
from ai.runs.store import RunStore
from ai.runs.worker import Worker, build

KILLED = 9


class Vendor(RecordingAgentProvider):
    """Accepts the pin the profile builds for the configured adapter."""

    adapter = "openai-compatible"

    def __init__(self, values, responses, delay):
        model = values["RUNS_AGENT_MODEL"]
        capacities = json.loads(values["AGENT_LLM_CAPACITIES"])
        from ai.agent.context import Capacity

        super().__init__(responses=responses, endpoint=values["AGENT_LLM_ENDPOINT"].rstrip("/"),
                         models=(model,), capabilities=("tools",),
                         capacities={model: Capacity(**capacities[model])})
        self.delay = delay

    async def converse(self, request):
        turn = await super().converse(request)
        await asyncio.sleep(self.delay)
        return turn


def unadmitted(settings, provider) -> RunService:
    """As `build`, but the AGENT executor sends to the recording provider with no admission."""
    from ai.agent.executor import AgentExecutor
    from ai.runs import agent_profile
    from ai.runs import config as runs_config
    from ai.runs.dispatch import notifier_for
    from ai.runs.executor import DeterministicExecutor

    cfg = runs_config.read(settings)
    profile = agent_profile.selected(settings)
    executor = AgentExecutor(provider, profile.pin, profile.reserves, profiles=profile.bounds,
                             price=profile.limits.prices[profile.pin.model])
    return RunService(RunStore(cfg.database_url), cfg, executor, notifier_for(cfg.redis_url),
                      serves=(DeterministicExecutor(),))


def reply(text):
    if isinstance(text, dict):
        return text
    if text == "hang":
        return HANG
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


def arm(die, vendor) -> None:
    """Exit at once, as a killed process does, the `after`-th time `at` is reached."""
    reached = 0

    def tick():
        nonlocal reached
        reached += 1
        if reached >= die.get("after", 1):
            sys.stdout.flush()
            os._exit(KILLED)

    def after(owner, name):
        original = getattr(owner, name)

        async def wrapped(*args, **kw):
            result = await original(*args, **kw)
            tick()
            return result

        setattr(owner, name, wrapped)

    at = die["at"]
    if at == "response":
        # The vendor answered; nothing was settled, run or saved after it.
        after(vendor, "converse")
    elif at == "tool":
        after(Investigation, "execute")
    elif at == "after_checkpoint":
        after(RunStore, "save_checkpoint")
    elif at == "before_checkpoint":
        original = RunStore.save_checkpoint

        async def before(*args, **kw):
            tick()
            return await original(*args, **kw)

        RunStore.save_checkpoint = before
    else:
        raise ValueError(at)


async def main(dsn, raw):
    spec = json.loads(raw)
    values = {**spec["values"], "RUNS_DATABASE_URL": dsn}
    vendor = Vendor(values, [reply(text) for text in spec["responses"]], spec.get("delay", 0.0))
    if spec.get("die"):
        arm(spec["die"], vendor)
    settings = SimpleNamespace(**values)
    if spec.get("admitted", True):
        service = build(settings, agent_provider=vendor)
    else:
        service = unadmitted(settings, vendor)
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
