"""The shared token bucket (IR-132).

Tested against a fake Redis that implements the two operations the bucket
actually uses. That is deliberate rather than lazy: the property under test is
that the *state lives outside the process*, and a fake store shared between two
bucket instances demonstrates that far more directly than one real Redis and
one process ever could.
"""

import pytest

from apps.ai.resilience.rate_limit import (
    Lane,
    RateLimited,
    TokenBucket,
    lane_budget,
)


class FakeRedis:
    """The two calls `TokenBucket` makes, and a shared dict behind them."""

    def __init__(self):
        self.store = {}
        self.expiries = {}

    def incrby(self, key, amount):
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    def expire(self, key, seconds):
        self.expiries[key] = seconds
        return True


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class BucketTests:
    def test_spending_within_the_budget_is_allowed(self):
        bucket = TokenBucket(FakeRedis(), Lane.QUERY, budget=100, window_seconds=60)
        bucket.spend(40)
        bucket.spend(40)  # no raise

    def test_exceeding_the_budget_raises(self):
        bucket = TokenBucket(FakeRedis(), Lane.QUERY, budget=100, window_seconds=60)
        bucket.spend(90)
        with pytest.raises(RateLimited):
            bucket.spend(20)

    def test_the_window_expires_and_the_budget_returns(self):
        clock = _Clock()
        redis = FakeRedis()
        bucket = TokenBucket(
            redis, Lane.QUERY, budget=100, window_seconds=60, clock=clock
        )
        bucket.spend(100)
        with pytest.raises(RateLimited):
            bucket.spend(1)

        clock.advance(61)
        bucket.spend(100)  # a new window, a fresh budget

    def test_a_refused_spend_does_not_consume_the_budget(self):
        """Otherwise a caller that is over the limit keeps burning the window
        it is already locked out of, and never recovers within it."""
        redis = FakeRedis()
        bucket = TokenBucket(redis, Lane.QUERY, budget=100, window_seconds=60)
        bucket.spend(95)
        with pytest.raises(RateLimited):
            bucket.spend(50)

        bucket.spend(5)  # the remaining 5 are still there


class SharedAcrossReplicasTests:
    """The reason this is Redis and not a counter.

    The reference implementation ADR-015 borrows from holds counters in process
    memory, which is correct with one process and wrong with four: the account
    sees four times the intended rate.
    """

    def test_two_instances_sharing_a_store_share_one_budget(self):
        redis = FakeRedis()
        replica_one = TokenBucket(redis, Lane.QUERY, budget=100, window_seconds=60)
        replica_two = TokenBucket(redis, Lane.QUERY, budget=100, window_seconds=60)

        replica_one.spend(60)
        with pytest.raises(RateLimited):
            replica_two.spend(60)

    def test_a_process_local_counter_would_have_allowed_it(self):
        """Stated as a test so the property is not merely asserted in a
        comment: two buckets with *separate* stores do not see each other,
        which is exactly the bug."""
        one = TokenBucket(FakeRedis(), Lane.QUERY, budget=100, window_seconds=60)
        two = TokenBucket(FakeRedis(), Lane.QUERY, budget=100, window_seconds=60)

        one.spend(60)
        two.spend(60)  # no raise -- 120 spent against a budget of 100


class LaneTests:
    """A bulkhead: a bulk backfill must not starve someone waiting on an
    answer."""

    def test_the_lanes_hold_separate_budgets(self):
        redis = FakeRedis()
        ingestion = TokenBucket(redis, Lane.INGESTION, budget=100, window_seconds=60)
        query = TokenBucket(redis, Lane.QUERY, budget=100, window_seconds=60)

        ingestion.spend(100)
        query.spend(100)  # unaffected by the backfill next door

    def test_exhausting_ingestion_does_not_refuse_a_query(self):
        redis = FakeRedis()
        ingestion = TokenBucket(redis, Lane.INGESTION, budget=10, window_seconds=60)
        query = TokenBucket(redis, Lane.QUERY, budget=10, window_seconds=60)

        with pytest.raises(RateLimited):
            ingestion.spend(50)
        query.spend(10)

    def test_the_query_lane_is_given_the_larger_share(self):
        """ADR-015's priority rule, expressed as configuration rather than
        left to whoever sets the environment variables."""
        assert lane_budget(Lane.QUERY, total=1000) > lane_budget(Lane.INGESTION, total=1000)

    def test_the_lane_budgets_do_not_exceed_the_account_budget(self):
        total = 1000
        assert lane_budget(Lane.QUERY, total) + lane_budget(Lane.INGESTION, total) <= total
