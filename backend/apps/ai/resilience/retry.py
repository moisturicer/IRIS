"""Bounded retry with backoff (IR-132).

A slow or flaky vendor should cost a few extra seconds, not an unbounded wait
and not a thundering herd. ``sleep`` is injected so the tests assert the
*schedule* rather than living through it.

Deliberately does **not** retry everything. A refusal the vendor will repeat --
a bad key, a malformed request, a rate limit -- is not made better by asking
again, and retrying a rate limit specifically makes the outage worse.
"""

from __future__ import annotations

import time
from typing import Callable, Sequence, Type, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    operation: Callable[[], T],
    attempts: int = 3,
    base_delay: float = 0.5,
    retry_on: Sequence[Type[BaseException]] = (Exception,),
    give_up_on: Sequence[Type[BaseException]] = (),
    give_up_on_kind: Sequence[object] = (),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``operation``, retrying transient failures with doubling delays.

    ``give_up_on`` wins over ``retry_on``, so a caller can say "retry network
    errors, but never a rate limit" without having to enumerate every network
    error. The last failure is re-raised rather than wrapped: the caller's
    circuit breaker needs to see the real exception to count it.

    ``give_up_on_kind`` is the same idea read a different way (IR-320): the
    vendor boundary raises one exception type for many failures
    (``LLMUnavailable``, ``VoyageError``), so a bad key and a dropped
    connection cannot be told apart by ``give_up_on``'s exception-type list --
    only by the ``.kind`` the boundary already attached. This module stays
    generic and does not import that vocabulary; a caller passes the members
    it wants to give up on (typically from ``apps.ai.providers.errors
    .ErrorKind``), and an exception with no ``.kind`` attribute -- anything
    not raised by a classified adapter boundary -- never matches, so passing
    this for a plain exception type is a no-op. Checked alongside
    ``give_up_on``, with the same "wins over retry" precedence.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be at least 1, got {attempts}")

    delay = base_delay
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except give_up_on:
            raise
        except retry_on as exc:
            if give_up_on_kind and getattr(exc, "kind", None) in give_up_on_kind:
                raise
            if attempt == attempts:
                raise
            sleep(delay)
            delay *= 2
    raise AssertionError("unreachable: the loop either returns or raises")
