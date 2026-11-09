"""The answer as the model writes it, relayed to the reader token by token.

The worker publishes each text piece of a model attempt to a Redis stream per
run; the gateway replays it to the reader over server-sent events. A draft is
unchecked: the committed Turn replaces it, and may differ when the answer
checks repair it. Passage handles become the same [1], [2] numbers the final
answer uses. Without Redis nothing is published and the reader waits for the
Turn, as before.
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
#: Phases whose text may be the answer; a compaction's summary is never shown.
SHOWN_PHASES = ("gather", "final", "repair")

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
        self.shown = True

    async def _add(self, event: dict) -> None:
        try:
            await self.client.xadd(key(self.run_id), {"e": json.dumps(event)}, maxlen=MAX_EVENTS, approximate=True)
            await self.client.expire(key(self.run_id), TTL_SECONDS)
        except Exception:  # A lost piece costs the live view, never the answer.
            log.debug("draft publish failed for run %s", self.run_id, exc_info=True)

    async def attempt(self, phase: str) -> None:
        """A new model attempt starts: its text replaces the previous attempt's."""
        self.shown = phase in SHOWN_PHASES
        self.numbering, self.held = {}, ""
        if self.shown:
            await self._add({"t": "reset", "phase": phase})

    def _number(self, match: re.Match) -> str:
        handle = match.group(1)
        if handle not in self.numbering:
            self.numbering[handle] = len(self.numbering) + 1
        return f"[{self.numbering[handle]}]"

    async def text(self, piece: str) -> None:
        if not self.shown or not piece:
            return
        text = self.held + piece
        partial = PARTIAL.search(text)
        self.held = partial.group(0) if partial else ""
        visible = HANDLE.sub(self._number, text[: len(text) - len(self.held)])
        if visible:
            await self._add({"t": "text", "d": visible})

    async def end(self) -> None:
        if self.shown and self.held:
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
