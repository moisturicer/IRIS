"""Synthetic independent indexing transport; reads test authority only from stdin."""

import asyncio
import json
import sys
from types import SimpleNamespace

from ai.admission.limits import read
from ai.ingestion.indexing import Bounds, process


class Recording:
    model = "voyage-context-4"
    dimensions = 1024
    data_policy = "no-training"
    account = "recording"
    calls = 0
    delay = 0

    async def embed(self, texts, *, input_type):
        self.calls += 1
        if self.delay and self.calls == 1:
            print("sending", flush=True)
            await asyncio.sleep(self.delay)
        return SimpleNamespace(vectors=[[1.0] + [0.0] * 1023 for _ in texts], input_tokens=10)


async def main():
    data = json.load(sys.stdin)
    provider = Recording()
    provider.delay = data.get("delay", 0)
    result = await process(
        data["dsn"],
        data["token"],
        pipeline="synthetic-v1",
        provider=provider,
        limits=read(SimpleNamespace(**data["limits"])),
        bounds=Bounds(60, 10, 10, 100000, 1),
    )
    print(json.dumps({"state": result, "calls": provider.calls}))


if __name__ == "__main__":
    asyncio.run(main())
