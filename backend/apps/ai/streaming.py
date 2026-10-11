"""Server-Sent Events that stream under ASGI as well as WSGI (IR-504).

Django serves a synchronous `StreamingHttpResponse` under ASGI by reading
the whole generator into a list first, so every progress event would reach
the reader only once the answer was finished. A research run takes up to
90 s, which made that buffering visible.

`EventStreamResponse` keeps the plain synchronous iterator for WSGI and the
test client, and under ASGI runs the generator in one call on the request's
own thread, handing each chunk to the event loop as it is produced. One call
keeps the generator's database connection and context variables (the run
deadline among them) in one place, as WSGI does.
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
        self._events = events
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
            except BaseException as exc:  # handed to the event loop to raise
                put(exc)
            finally:
                # The reader left: close here, on the generator's own thread,
                # so an interrupted answer is still recorded (IR-328).
                close = getattr(self._events, "close", None)
                if close is not None:
                    close()
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
