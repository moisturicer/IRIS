"""The shadow lane and the breaker reads IR-466's capacity isolation needs.

Shadow spends only against its own strictly-bounded lane, and adding that lane
changes nothing on the reader path: the query and ingestion shares are what
they were, and no reader request touches a bucket at all (IR-468 owns that).
"""

import pytest
from django.test import override_settings

from apps.ai.resilience.circuit import CircuitBreaker
from apps.ai.resilience.rate_limit import (
    Lane,
    RateLimited,
    TokenBucket,
    bucket_for,
    lane_budget,
)

from .test_rate_limit import FakeRedis


def test_the_reader_lanes_keep_their_shares():
    assert lane_budget(Lane.QUERY, 1_000_000) == 700_000
    assert lane_budget(Lane.INGESTION, 1_000_000) == 300_000


@override_settings(
    AI_EVIDENCE_SHADOW_TOKENS_PER_MINUTE=5_000,
    AI_RATE_LIMIT_TOKENS_PER_MINUTE=1_000_000,
)
def test_the_shadow_lane_has_its_own_budget_not_a_share_of_the_account():
    store = FakeRedis()
    bucket = bucket_for(Lane.SHADOW, store=store)

    bucket.spend(5_000)
    with pytest.raises(RateLimited):
        bucket.spend(1)

    assert all(":shadow:" in key for key in store.store)


@override_settings(AI_EVIDENCE_SHADOW_TOKENS_PER_MINUTE=5_000)
def test_spending_shadow_leaves_the_query_lane_untouched():
    store = FakeRedis()
    bucket_for(Lane.SHADOW, store=store).spend(4_000)

    bucket_for(Lane.QUERY, store=store).spend(1)
    assert {key.split(":")[2] for key in store.store} == {"shadow", "query"}


def test_adjust_reconciles_a_reservation_with_what_was_actually_spent():
    store = FakeRedis()
    bucket = TokenBucket(store, Lane.SHADOW, budget=1_000, window_seconds=60, clock=lambda: 60.0)

    key = bucket.spend(600)
    bucket.adjust(-250, key)
    bucket.adjust(50, key)

    assert store.store == {"iris:ratelimit:shadow:1": 400}


def test_adjust_reconciles_into_the_window_the_reservation_came_from():
    store = FakeRedis()
    clock = {"now": 119.0}
    bucket = TokenBucket(
        store, Lane.SHADOW, budget=1_000, window_seconds=60, clock=lambda: clock["now"]
    )

    key = bucket.spend(600)
    clock["now"] = 121.0
    bucket.adjust(-500, key)

    assert store.store == {"iris:ratelimit:shadow:1": 100}


def test_adjust_records_a_real_overspend_rather_than_refusing_it():
    """The tokens were already paid for; the next spend is what is refused."""
    store = FakeRedis()
    bucket = TokenBucket(store, Lane.SHADOW, budget=100, window_seconds=60, clock=lambda: 60.0)

    key = bucket.spend(90)
    bucket.adjust(40, key)

    assert store.store["iris:ratelimit:shadow:1"] == 130
    with pytest.raises(RateLimited):
        bucket.spend(1)


def test_a_breaker_reports_its_consecutive_failures():
    breaker = CircuitBreaker(failure_threshold=5)

    def fail():
        raise ValueError("down")

    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(fail)
    assert breaker.failures == 2

    breaker.call(lambda: None)
    assert breaker.failures == 0
