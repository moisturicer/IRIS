"""An independent AGENT research worker process for IR-862's tests.

`python -m ai.tests.agent_worker <dsn> <spec.json>`

Built by `ai.runs.worker.build` from the spec's settings, as the real worker
is, with the recording provider standing in for the configured vendor. Each
response is an answer text, or "hang" for an attempt that never answers.
Serves until no run is in flight and none has ended for `idle_seconds`,
then prints how many runs it ran.
"""

import asyncio
import json
import sys
import time
from types import SimpleNamespace

from ai.infrastructure.recording_adapter import HANG, RecordingAgentProvider
from ai.runs.worker import Worker, build


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


def reply(text):
    if text == "hang":
        return HANG
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


async def main(dsn, raw):
    spec = json.loads(raw)
    values = {**spec["values"], "RUNS_DATABASE_URL": dsn}
    vendor = Vendor(values, [reply(text) for text in spec["responses"]], spec.get("delay", 0.0))
    service = build(SimpleNamespace(**values), agent_provider=vendor)
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
