"""Shared sliding-window limits for the recovery endpoints (ADR-045 §5).

A counter is the `RecoveryAttempt` rows under one `RecoveryBucket` key. Every
check locks its bucket row before reading the attempts under it, and a
request checks its buckets one at a time in a fixed order, so two workers
deciding at once serialise rather than both seeing room for one more -- the defect of
DRF's per-process throttling this replaces. Postgres rather than Redis: the
admission and the intent it admits commit in one transaction, and the suite
proves the property against the real database CI runs.

An attempt exactly ``window`` seconds old has left the window. A refused
attempt is not counted, so the Retry-After a client is told is the truth.
"""

import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction

from apps.accounts.models import RecoveryAttempt, RecoveryBucket

from . import clock, crypto


@dataclass(frozen=True)
class Window:
    limit: int
    seconds: int


class Throttled(Exception):
    def __init__(self, retry_after: int):
        super().__init__(retry_after)
        self.retry_after = retry_after


def request_windows():
    return (Window(settings.RECOVERY_REQUEST_IP_10M, 600), Window(settings.RECOVERY_REQUEST_IP_DAY, 86400))


def confirm_windows():
    return (Window(settings.RECOVERY_CONFIRM_IP_10M, 600),)


def recipient_windows():
    """Per normalized address, across every purpose. The cooldown is a
    window too: one issuance per ``RECOVERY_COOLDOWN_SECONDS``."""
    return (
        Window(settings.RECOVERY_RECIPIENT_HOUR, 3600),
        Window(settings.RECOVERY_RECIPIENT_DAY, 86400),
        Window(1, settings.RECOVERY_COOLDOWN_SECONDS),
    )


def _locked(key: str) -> RecoveryBucket:
    """The bucket row for ``key``, created if missing and locked.

    The dispatcher may purge an idle bucket between the insert and the lock;
    inserting again is then correct, because nothing was counted on it.
    """
    while True:
        RecoveryBucket.objects.bulk_create([RecoveryBucket(key=key)], ignore_conflicts=True)
        bucket = RecoveryBucket.objects.select_for_update().filter(key=key).first()
        if bucket is not None:
            return bucket


def admit(key: str, windows, at) -> int | None:
    """Count one attempt on ``key``, or return the seconds until it would fit.

    Must run inside a transaction: the bucket lock is held until it commits.
    """
    bucket = _locked(key)
    longest = max(window.seconds for window in windows)
    recent = list(
        RecoveryAttempt.objects.filter(bucket=bucket, at__gt=at - timedelta(seconds=longest))
        .order_by("-at").values_list("at", flat=True)[: max(w.limit for w in windows)]
    )
    waits = []
    for window in windows:
        inside = [t for t in recent if t > at - timedelta(seconds=window.seconds)]
        if len(inside) >= window.limit:
            leaves = inside[window.limit - 1] + timedelta(seconds=window.seconds)
            waits.append(max(1, math.ceil((leaves - at).total_seconds())))
    if waits:
        return max(waits)
    RecoveryAttempt.objects.create(bucket=bucket, at=at)
    return None


def admit_address(action: str, ip: str, windows) -> None:
    """Count one request from ``ip`` against ``action``'s limits, in its own
    transaction so the attempt stays counted whatever the request does next.
    Raises `Throttled`."""
    at = clock.now()
    with transaction.atomic():
        wait = admit(f"ip:{action}:{crypto.identifier('ip', ip)}", windows, at)
    if wait is not None:
        raise Throttled(wait)


def client_ip(request) -> str:
    """The connecting address, or the proxy's report of it when the
    connection is from a configured proxy. Walks X-Forwarded-For from the
    right, skipping trusted proxies, so a client cannot prepend its own."""
    remote = request.META.get("REMOTE_ADDR", "")
    trusted = set(settings.RECOVERY_TRUSTED_PROXIES)
    if remote not in trusted:
        return remote
    hops = [h.strip() for h in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if h.strip()]
    for hop in reversed(hops):
        if hop not in trusted:
            return hop
    return remote
