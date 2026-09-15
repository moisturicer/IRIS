"""A token budget shared across replicas (IR-132).

**Why Redis and not a counter.** The reference implementation ADR-015 borrows
from holds its counters in process memory. That is correct with one process and
wrong with four: each replica enforces the limit locally and the vendor account
sees four times the intended rate. The state has to live where every replica
can see it.

**Why two lanes.** A bulk backfill and an interactive question draw on the same
account, and the one a person is waiting on must not lose. Separate budgets are
the bulkhead; the query lane gets the larger share.

The bucket is a fixed window rather than a leaky bucket: a window keyed by
wall-clock division needs one atomic increment and an expiry, where a leaky
bucket needs a read-modify-write that is only safe under a Lua script. For
protecting a vendor quota, the extra smoothness is not worth the extra moving
part.
"""

from __future__ import annotations

import enum
import math
import time
from typing import Callable, Optional, Protocol


class Lane(enum.Enum):
    """Which budget a call draws on."""

    QUERY = "query"
    INGESTION = "ingestion"


#: How the account's budget is divided. The query lane is prioritised because a
#: person is waiting on it; ingestion is a backfill that can take longer.
_LANE_SHARE = {Lane.QUERY: 0.7, Lane.INGESTION: 0.3}


class RateLimited(RuntimeError):
    """The lane's budget for this window is spent.

    Raised rather than blocking: a caller holding a request open while it waits
    for a quota is the connection-pool exhaustion the circuit breaker next door
    exists to prevent.
    """


class _Store(Protocol):
    """The two operations this needs. Narrow on purpose -- it is what lets the
    tests substitute a dict and still exercise the shared-state property."""

    def incrby(self, key: str, amount: int) -> int: ...
    def expire(self, key: str, seconds: int) -> bool: ...


def lane_budget(lane: Lane, total: int) -> int:
    """This lane's share of the account budget."""
    return int(math.floor(total * _LANE_SHARE[lane]))


class TokenBucket:
    def __init__(
        self,
        store: _Store,
        lane: Lane,
        budget: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._lane = lane
        self._budget = budget
        self._window = window_seconds
        self._clock = clock

    def _key(self) -> str:
        """One key per lane per window.

        The window is part of the key rather than a stored timestamp, so
        expiry is Redis's job and there is no read-modify-write to race on.
        """
        window = int(self._clock() // self._window)
        return f"iris:ratelimit:{self._lane.value}:{window}"

    def spend(self, tokens: int) -> None:
        """Consume ``tokens`` from this lane, or raise.

        The increment is atomic, which is what makes this correct across
        replicas. When the spend would breach the budget it is **given back**
        before raising -- otherwise a caller already over the limit keeps
        burning the window it is locked out of and never recovers within it.
        """
        key = self._key()
        spent = self._store.incrby(key, tokens)
        # Refresh the expiry on every write: a key that outlived its window
        # would carry spend into the next one.
        self._store.expire(key, self._window * 2)

        if spent > self._budget:
            self._store.incrby(key, -tokens)
            raise RateLimited(
                f"{self._lane.value} lane has spent its budget of {self._budget} "
                f"for this {self._window}s window"
            )


def bucket_for(lane: Lane, store: Optional[_Store] = None) -> TokenBucket:
    """The configured bucket for a lane.

    Uses a **raw Redis client**, not Django's cache API: the correctness of
    this depends on an atomic increment, and `django.core.cache` exposes
    `incr` only for keys that already exist and offers no way to set an expiry
    in the same breath. Reaching for the client directly is honest about what
    is needed rather than building a shim that hides a race.
    """
    from django.conf import settings

    if store is None:
        import redis

        store = redis.Redis.from_url(
            getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )

    total = getattr(settings, "AI_RATE_LIMIT_TOKENS_PER_MINUTE", 1_000_000)
    return TokenBucket(store, lane, budget=lane_budget(lane, total), window_seconds=60)
