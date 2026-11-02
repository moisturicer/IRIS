"""
What a locked sign-in is told (IR-555).

There are two server locks, and they end differently:

* **django-axes** refuses a user and IP after `AXES_FAILURE_LIMIT` failures
  and admits them again once enough of those failures are older than
  `AXES_COOLOFF_TIME`. Its reply is `too_many_attempts` with `unlock_at`.
* **The manual lock** (`User.is_locked`, set by RDCO) never lifts on its own.
  `LoginView` answers it with `locked_by_admin` and no `unlock_at`.

The client stopped inventing a duration for either: it counts down only to a
time the server gave it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_cool_off, get_failure_limit
from django.conf import settings
from django.http import JsonResponse

TOO_MANY_ATTEMPTS = "too_many_attempts"
LOCKED_BY_ADMIN = "locked_by_admin"


def unlock_at(request, credentials: Optional[dict]) -> Optional[datetime]:
    """
    When axes will next admit this user and IP, from axes' own records.

    Axes counts the failures on attempts whose latest failure is within the
    cool-off, summed per lockout group, and refuses while any group's sum
    reaches the limit. Attempts drop out of that window newest-last, so a
    group stays locked until the attempt that first takes its newest-first
    running sum to the limit has aged out: that attempt's time plus the
    cool-off. With one attempt row, the usual case, that is simply the latest
    failure plus the cool-off -- not "now plus the cool-off", because a refused
    attempt during the lock is itself recorded and moves the time.

    `None` when the handler keeps no attempt rows to read or no cool-off is
    configured (a lock that never lifts on its own).
    """
    cool_off = get_cool_off(request)
    handler = AxesProxyHandler.get_implementation()
    if cool_off is None or not hasattr(handler, "get_user_attempts"):
        return None

    limit = get_failure_limit(request, credentials)
    ends = []
    for attempts in handler.get_user_attempts(request, credentials):
        running = 0
        for attempt in attempts.order_by("-attempt_time"):
            running += attempt.failures_since_start
            if running >= limit:
                ends.append(attempt.attempt_time + cool_off)
                break
    return max(ends, default=None)


def lockout_response(request, original_response=None, credentials=None) -> JsonResponse:
    """
    `AXES_LOCKOUT_CALLABLE`: a JSON 429 saying which lock this is and when it lifts.

    Under ASGI, which production runs, axes' middleware takes its async path
    and calls this with two arguments, `(request, credentials)`, so the
    credentials arrive as `original_response` and `credentials` is `None`. The
    handler also leaves them on the request, which is where they are read from
    then: without them axes finds no attempts and the time would be lost.
    """
    credentials = credentials or getattr(request, "axes_credentials", None)
    ends = unlock_at(request, credentials)
    return JsonResponse(
        {
            "detail": "Account locked: too many failed sign-in attempts.",
            "code": TOO_MANY_ATTEMPTS,
            "unlock_at": ends.isoformat() if ends else None,
        },
        status=settings.AXES_HTTP_RESPONSE_CODE,
    )
