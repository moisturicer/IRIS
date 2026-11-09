"""The answer as the model writes it, relayed to the reader token by token.

The worker publishes the answer's text to a Redis stream per run; the gateway
replays it to the reader over server-sent events. Only the answer is shown:
the closing attempt streams as it is written, and a research turn's text is
held until that turn is known to be the answer, so a preamble before a tool
call is never shown. Passage handles become the same [1], [2] numbers the
committed Turn uses. Without Redis nothing is published and the reader waits
for the Turn, as before.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from contextvars import ContextVar
from typing import Optional

log = logging.getLogger(__name__)

#: How long a finished draft stays replayable.
TTL_SECONDS = 3600
MAX_EVENTS = 20_000
#: A passage handle as the agent cites it, complete.
HANDLE = re.compile(r"\[(P[0-9a-f]{20})\]")
#: The longest prefix of a handle still being written: held back until it completes.
PARTIAL = re.compile(r"\[(P[0-9a-f]{0,20})?$")
#: The closing attempt is the answer from its first word; a research turn's text is
#: held until the turn ends without calling a tool. Nothing else is ever shown.
LIVE_PHASES = ("final",)
HELD_PHASES = ("gather",)

_sink: ContextVar[Optional["DraftSink"]] = ContextVar("iris_draft_sink", default=None)


def key(run_id) -> str:
    return f"iris:draft:{run_id}"


class DraftSink:
    """One run's draft: numbered like the final answer, published as it arrives."""

    def __init__(self, client, run_id):
        self.client = client
        self.run_id = str(run_id)
        self.numbering: dict[str, int] = {}
        self.held = ""
        #: "live" publishes as it arrives, "hold" keeps it for `settle`, "off" drops it.
        self.mode = "off"
        self.kept: list[str] = []

    async def _add(self, event: dict) -> None:
        try:
            await self.client.xadd(key(self.run_id), {"e": json.dumps(event)}, maxlen=MAX_EVENTS, approximate=True)
            await self.client.expire(key(self.run_id), TTL_SECONDS)
        except Exception:  # A lost piece costs the live view, never the answer.
            log.debug("draft publish failed for run %s", self.run_id, exc_info=True)

    async def attempt(self, phase: str, *, live: bool = True) -> None:
        """A new model attempt starts. With `live` off nothing of it is ever published."""
        self.mode = "off" if not live else "live" if phase in LIVE_PHASES else "hold" if phase in HELD_PHASES else "off"
        self.numbering, self.held, self.kept = {}, "", []

    def _number(self, match: re.Match) -> str:
        handle = match.group(1)
        if handle not in self.numbering:
            self.numbering[handle] = len(self.numbering) + 1
        return f"[{self.numbering[handle]}]"

    async def text(self, piece: str) -> None:
        if not piece:
            return
        if self.mode == "hold":
            self.kept.append(piece)
        elif self.mode == "live":
            await self._publish(piece)

    async def _publish(self, piece: str) -> None:
        text = self.held + piece
        partial = PARTIAL.search(text)
        self.held = partial.group(0) if partial else ""
        visible = HANDLE.sub(self._number, text[: len(text) - len(self.held)])
        if visible:
            await self._add({"t": "text", "d": visible})

    async def settle(self, answer: bool) -> None:
        """The attempt ended. A held research turn that was the answer is published now; otherwise it is dropped."""
        kept, self.kept = self.kept, []
        if self.mode == "hold" and answer:
            for piece in kept:
                await self._publish(piece)
        self.mode = "off"

    async def final(self, text: str) -> None:
        """The committed answer, shown whole when checks decided its text; the page types it out."""
        self.numbering, self.held, self.kept, self.mode = {}, "", [], "off"
        if text:
            await self._add({"t": "text", "d": text})

    async def end(self) -> None:
        if self.held:
            await self._add({"t": "text", "d": HANDLE.sub(self._number, self.held)})
        self.held = ""
        await self._add({"t": "end"})


def active() -> Optional[DraftSink]:
    return _sink.get()


@contextlib.contextmanager
def bound(sink: Optional[DraftSink]):
    token = _sink.set(sink)
    try:
        yield sink
    finally:
        _sink.reset(token)


def client_for(url: str):
    """A Redis client, or None when wakeups are off: then nothing streams."""
    if not url:
        return None
    import redis.asyncio as redis

    # No socket timeout: a reader blocks on the stream for seconds at a time.
    return redis.from_url(url, socket_timeout=None, socket_connect_timeout=5)
