"""
Publishing a hint (ADR-073 decisions 1 and 3).

A hint names what changed, never the change: `{"topics": [...]}`. It is
published after the transaction commits, so a page that refetches on it reads
the new state. Redis being down never fails the act that published: the error
is logged and the page catches up on focus or reconnect (decision 6).

`LIVE_ENABLED` turns publishing off (the test settings do, as CI has no Redis);
a test that wants to see hints swaps in a recorder with `use_publisher`.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Callable, Iterable

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

Sender = Callable[[str, str], None]
_client = None
_override: Sender | None = None


def _redis_send(channel: str, payload: str) -> None:
    global _client
    if _client is None:
        import redis
        _client = redis.Redis.from_url(
            settings.LIVE_REDIS_URL, socket_connect_timeout=1, socket_timeout=1,
        )
    _client.publish(channel, payload)


def _send(channel: str, topics: list[str]) -> None:
    payload = json.dumps({"topics": topics}, separators=(",", ":"))
    try:
        (_override or _redis_send)(channel, payload)
    except Exception:  # never fail the act; pages catch up on focus
        logger.warning("live: could not publish to %s", channel, exc_info=True)


def enabled() -> bool:
    """Whether a hint would be sent at all: on, or a test recording them."""
    return settings.LIVE_ENABLED or _override is not None


def publish(channels: Iterable[str], topics: Iterable[str]) -> None:
    """Send `topics` to `channels` once the current transaction commits."""
    channels = sorted(set(channels))
    topics = sorted(set(topics))
    if not channels or not topics:
        return
    if not enabled():
        return

    def send_all():
        for channel in channels:
            _send(channel, topics)

    transaction.on_commit(send_all)


@contextmanager
def use_publisher(sender: Sender):
    """Route every publish to `sender(channel, payload)` for the duration (tests)."""
    global _override
    previous, _override = _override, sender
    try:
        yield
    finally:
        _override = previous
