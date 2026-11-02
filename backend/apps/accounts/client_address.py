"""
Which address a request really came from (IR-656).

Behind nginx, `REMOTE_ADDR` is nginx. Each proxy appends the address it heard
from to `X-Forwarded-For`, so with N trusted proxies in front of Django the
client is the Nth entry from the right. Everything further left was sent by the
client and can say anything, so it is never read.

The direct peer is the fallback when the header cannot be trusted: too few
entries, or a trusted position holding something that is no address. Requests
then share that peer's lock, which is the safe way to be wrong.
"""
from __future__ import annotations

from ipaddress import ip_address

from django.conf import settings


def client_address(request) -> str | None:
    peer = request.META.get("REMOTE_ADDR")
    count = settings.TRUSTED_PROXY_COUNT
    if count < 1:
        return peer

    forwarded = [
        entry.strip() for entry in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    ]
    if len(forwarded) < count:
        return peer
    candidate = forwarded[-count]
    try:
        ip_address(candidate)
    except ValueError:
        return peer
    return candidate
