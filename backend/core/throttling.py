"""
Soft rate limits (IR-999): each budget counts over two windows.

The per-minute burst is the one a person can reach, by clicking fast or
opening many tabs, and its refusal clears in under a minute. The daily
backstop, in the scope without `_burst`, sits far above heavy real use, so
only a script waits hours. One long window alone made ordinary testing
wait about twenty hours once a day's budget was spent.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AnonBurstThrottle(AnonRateThrottle):
    scope = "anon_burst"


class UserBurstThrottle(UserRateThrottle):
    scope = "user_burst"
