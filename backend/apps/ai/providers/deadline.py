"""A run's wall-clock deadline, read by every model call (IR-511, ADR-038 §5).

A run sets it once; each vendor call then gets `min(its timeout, time left)`
without the narrow `generate(system, user)` port growing a parameter.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, Optional, Tuple

Clock = Callable[[], float]

_deadline: ContextVar[Optional[Tuple[float, Clock]]] = ContextVar(
    "model_call_deadline", default=None
)


@contextmanager
def model_call_deadline(
    seconds: float, *, clock: Clock = time.monotonic
) -> Iterator[None]:
    """Bound every model call inside this block to `seconds` from now.

    A nested deadline can shorten the outer one, never extend it. `clock`
    is for tests.
    """
    current = _deadline.get()
    if current is not None:
        clock = current[1]
    at = clock() + seconds
    if current is not None:
        at = min(at, current[0])
    token = _deadline.set((at, clock))
    try:
        yield
    finally:
        _deadline.reset(token)


def time_left() -> Optional[float]:
    """Seconds until the run's deadline, or `None` outside a run."""
    current = _deadline.get()
    if current is None:
        return None
    at, clock = current
    return at - clock()


def bounded(timeout_seconds: float) -> float:
    """`timeout_seconds`, capped by the time left in the run."""
    left = time_left()
    return timeout_seconds if left is None else min(timeout_seconds, left)
