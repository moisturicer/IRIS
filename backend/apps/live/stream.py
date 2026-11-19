"""
The live stream (ADR-073 decisions 2, 4, 5 and 7).

One `GET /api/v1/live/` per tab, answered as `text/event-stream`. Fully async:
after authenticating once it holds no thread and no database connection, only
a bounded queue fed by this process's single Redis subscription (`Hub`).

The stream ends when the access token it was opened with expires, when its
queue overflows, or when the reader leaves. The browser reconnects, refreshing
its token first when it must, and refetches what it shows (decision 6).
"""
from __future__ import annotations

import asyncio
import logging
import time
import weakref
from collections import defaultdict
from contextlib import contextmanager

from django.conf import settings

from .channels import PREFIX

logger = logging.getLogger(__name__)

PING_SECONDS = 25      # under nginx's 60 s proxy_read_timeout (decision 7)
QUEUE_MAX = 50         # hints a slow reader may fall behind before it is closed


class StreamQueue(asyncio.Queue):
    """A stream's hints; `overflowed` once it fell too far behind to keep."""

    def __init__(self):
        super().__init__(maxsize=QUEUE_MAX)
        self.overflowed = False


class Hub:
    """
    One Redis subscription per process, fanned out to its open streams (decision 4).

    `listen=False` builds a hub that only fans out what `dispatch` is given, so
    tests need no Redis.
    """

    def __init__(self, url: str | None = None, *, listen: bool = True):
        self._url = url
        self._listen = listen
        self._subs: dict[str, set[StreamQueue]] = defaultdict(set)
        self._task: asyncio.Task | None = None

    @property
    def stream_count(self) -> int:
        return len({q for qs in self._subs.values() for q in qs})

    def register(self, channels: list[str]) -> StreamQueue:
        queue = StreamQueue()
        for channel in channels:
            self._subs[channel].add(queue)
        if self._listen and (self._task is None or self._task.done()):
            self._task = asyncio.get_running_loop().create_task(self._run())
        return queue

    def unregister(self, channels: list[str], queue: StreamQueue) -> None:
        for channel in channels:
            queue_set = self._subs.get(channel)
            if queue_set is not None:
                queue_set.discard(queue)
                if not queue_set:
                    del self._subs[channel]

    def dispatch(self, channel: str, data: str) -> None:
        for queue in list(self._subs.get(channel, ())):
            if queue.overflowed:
                continue
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                queue.overflowed = True

    async def _run(self) -> None:
        import redis.asyncio as aioredis

        backoff = 1
        while self._subs:
            client = pubsub = None
            try:
                client = aioredis.from_url(self._url)
                pubsub = client.pubsub()
                await pubsub.psubscribe(f"{PREFIX}*")
                backoff = 1
                async for message in pubsub.listen():
                    if message.get("type") == "pmessage":
                        channel, data = message["channel"], message["data"]
                        self.dispatch(
                            channel.decode() if isinstance(channel, bytes) else channel,
                            data.decode() if isinstance(data, bytes) else data,
                        )
                    if not self._subs:
                        break
            except asyncio.CancelledError:
                raise
            except Exception:
                # Redis down: streams stay open and quiet; pages refetch on focus.
                logger.warning("live: subscription lost, retrying in %ss", backoff, exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            finally:
                for closer in (pubsub, client):
                    if closer is not None:
                        try:
                            await closer.aclose()
                        except Exception:
                            pass


_hubs: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Hub]" = weakref.WeakKeyDictionary()
_override: Hub | None = None


def get_hub() -> Hub:
    """This event loop's hub: one per server process under uvicorn."""
    if _override is not None:
        return _override
    loop = asyncio.get_running_loop()
    hub = _hubs.get(loop)
    if hub is None:
        hub = _hubs[loop] = Hub(settings.LIVE_REDIS_URL)
    return hub


@contextmanager
def use_hub(hub: Hub):
    global _override
    previous, _override = _override, hub
    try:
        yield hub
    finally:
        _override = previous


async def events(queue: StreamQueue, expires_at: float, *, ping: float = PING_SECONDS, clock=time.time):
    """The stream's lines: a hint per message, a ping when quiet, until it must end."""
    yield ": connected\n\n"
    while True:
        remaining = expires_at - clock()
        if remaining <= 0 or queue.overflowed:
            return
        try:
            data = await asyncio.wait_for(queue.get(), timeout=min(ping, remaining))
        except asyncio.TimeoutError:
            yield ": ping\n\n"
            continue
        yield f"data: {data}\n\n"
