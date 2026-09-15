"""A circuit breaker for the vendor calls (IR-132).

ADR-008's degraded mode only helps if something notices the vendor is down.
Without a breaker, every request waits for its own timeout and each one holds a
connection while it does -- one failing dependency consumes the pool and takes
the whole application with it.

The clock is injected, so every transition is testable without sleeping. A
resilience component whose tests take real seconds is one whose tests get
skipped, and this is precisely the code nobody exercises by hand.

Composed *around* a port rather than written into an adapter (see
``apps/ai/providers/voyage.py``): an adapter that breaks its own circuit cannot
be tested for the failure it hides, and the fake would have to grow the same
machinery to stay a substitute.
"""

from __future__ import annotations

import enum
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(RuntimeError):
    """The dependency is presumed down; the call was refused without being made.

    Distinct from whatever the dependency itself raises, so a caller can tell
    "we did not try" from "we tried and it failed" -- only the first should
    degrade silently.
    """


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_after_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_after = reset_after_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open = False
        # One breaker instance may be shared by threads under gunicorn; the
        # state is a handful of ints and a float, so a lock is cheap and the
        # alternative is a torn count that never quite reaches the threshold.
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state_unlocked()

    def _state_unlocked(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._half_open:
            return CircuitState.HALF_OPEN
        if self._clock() - self._opened_at >= self._reset_after:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def call(self, operation: Callable[[], T]) -> T:
        """Run ``operation``, or refuse if the circuit is open.

        The call happens outside the lock: holding it across a network request
        would serialise every caller behind the slowest one, which is the
        problem this class exists to prevent.
        """
        with self._lock:
            state = self._state_unlocked()
            if state is CircuitState.OPEN:
                raise CircuitOpen(
                    f"circuit open after {self._failures} consecutive failures; "
                    f"retrying in "
                    f"{self._reset_after - (self._clock() - self._opened_at):.0f}s"
                )
            trial = state is CircuitState.HALF_OPEN
            self._half_open = trial

        try:
            result = operation()
        except Exception:
            with self._lock:
                if trial:
                    # A failed trial reopens immediately. Giving a dependency
                    # that is still down another N attempts would make the
                    # window meaningless.
                    self._opened_at = self._clock()
                    self._half_open = False
                else:
                    self._failures += 1
                    if self._failures >= self._failure_threshold:
                        self._opened_at = self._clock()
                        self._half_open = False
            raise

        with self._lock:
            # A success resets the count rather than decrementing it: two
            # failures an hour apart are not an outage, and a decrementing
            # counter trips on them eventually.
            self._failures = 0
            self._opened_at = None
            self._half_open = False
        return result
