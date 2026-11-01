"""Worker wakeups (IR-723, ADR-049 §3).

A wakeup is a hint, never proof of work: workers claim from PostgreSQL and
scan anyway every poll interval, so a lost, duplicated or early wakeup only
changes when a committed run starts.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

WAKEUP_KEY = "iris_ai:runs:wakeup"
#: Wakeups kept at most; more say nothing a scan would not.
WAKEUP_BACKLOG = 64


class Notifier(Protocol):
    async def notify(self) -> None: ...

    async def wait(self, timeout: float) -> None: ...


class PollingNotifier:
    """No transport: workers find work by scanning alone."""

    async def notify(self) -> None:
        return None

    async def wait(self, timeout: float) -> None:
        await asyncio.sleep(timeout)


class RedisNotifier:
    def __init__(self, url: str):
        import redis.asyncio as redis

        self.client = redis.from_url(url)

    async def notify(self) -> None:
        async with self.client.pipeline(transaction=False) as pipe:
            await pipe.lpush(WAKEUP_KEY, 1).ltrim(WAKEUP_KEY, 0, WAKEUP_BACKLOG - 1).execute()

    async def wait(self, timeout: float) -> None:
        await self.client.blpop([WAKEUP_KEY], timeout=timeout)

    async def close(self) -> None:
        await self.client.aclose()


def notifier_for(url: str) -> Notifier:
    return RedisNotifier(url) if url else PollingNotifier()
