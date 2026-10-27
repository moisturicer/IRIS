"""SSE that streams under ASGI too (IR-504).

Django buffers a sync stream to the end under ASGI. Here the generator runs
in one call on the request's own thread, so its DB connection and context
variables stay together, and each chunk reaches the loop as it is made.
"""

from __future__ import annotations

import asyncio
import threading

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

_END = object()


class EventStreamResponse(StreamingHttpResponse):
    def __init__(self, events, **kwargs):
        kwargs.setdefault("content_type", "text/event-stream")
        super().__init__(events, **kwargs)
        self._source = events
        self["Cache-Control"] = "no-cache"
        # nginx buffers a proxied response by default -- see `nginx.conf`.
        self["X-Accel-Buffering"] = "no"

    async def __aiter__(self):
        loop = asyncio.get_running_loop()
        chunks: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        content = self.streaming_content

        def put(item):
            try:
                loop.call_soon_threadsafe(chunks.put_nowait, item)
            except RuntimeError:  # the loop closed after the reader left
                stop.set()

        def pump():
            try:
                for chunk in content:
                    put(chunk)
                    if stop.is_set():
                        break
            except Exception as exc:  # raised again on the event loop
                put(exc)
            finally:
                # Closed on its own thread, so an interrupted answer is recorded.
                try:
                    close = getattr(self._source, "close", None)
                    if close is not None:
                        close()
                finally:
                    put(_END)

        # Held so the task outlives a disconnect until the run reaches a step.
        self._pump = asyncio.ensure_future(sync_to_async(pump, thread_sensitive=True)())
        try:
            while True:
                item = await chunks.get()
                if item is _END:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stop.set()
