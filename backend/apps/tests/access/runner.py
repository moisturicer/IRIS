"""
Fire one table cell and record what came back (IR-615).

Every request runs inside a savepoint that is rolled back, so the owner's
`DELETE` of the record, RDCO's approval of a delete request or an office's
clearance does not change the world for the next cell. The cache is cleared
before each one too: DRF's throttles count in it, and the anonymous rate
(100/day) is far below the number of requests the matrix makes.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.cache import cache
from django.db import transaction
from django.urls import resolve, reverse

from .cells import Call, Observed, Ref, Response, resolve as resolve_value
from .routes import Route, view_class
from .world import MISSING_PK, World

#: Stands in for the response when the view raised instead of answering.
RAISED = 599


def _send(client, route: Route, method: str, call: Call, world: World, user, missing: str | None):
    def lookup(ref: Ref):
        return MISSING_PK if ref.name == missing else world.value(ref.name, ref.attr)

    kwargs = resolve_value(call.kwargs, lookup, world.download_token)
    url = reverse(route.name, kwargs=kwargs)
    match = resolve(url)
    if view_class(match.func) is not view_class(route.view):
        raise AssertionError(
            f"reverse({route.name!r}) reached {match.view_name}, not {route}: "
            "the table cannot fire this route by name"
        )
    query = resolve_value(call.query, lookup, world.download_token)
    if query:
        url = f"{url}?{urlencode(query)}"
    data = resolve_value(call.data, lookup, world.download_token) if call.data is not None else None

    client.force_authenticate(user)
    cache.clear()
    try:
        with transaction.atomic():
            sender = getattr(client, method.lower())
            response = sender(url, data, format=call.format) if data is not None else sender(url)
            # Never `response.close()` here: it sends `request_finished`, whose
            # `close_old_connections` the test client only holds off inside
            # its own request, and the test's connection closes mid-run. The
            # client closes a response itself, and a streamed one when the
            # stream is drained.
            body = (
                b"".join(response.streaming_content) if response.streaming else response.content
            )
            transaction.set_rollback(True)
    except Exception as exc:  # the view raised: a fault, reported as one
        return Response(RAISED, f"{type(exc).__name__}: {exc}".encode())
    finally:
        client.force_authenticate(None)
        world.restore_files()
    return Response(response.status_code, body)


def observe(client, route: Route, method: str, call: Call, world: World, role: str,
            waiver: str = "") -> Observed:
    user = world.users[role]
    missing_ids = [v.name for v in call.kwargs.values() if isinstance(v, Ref)]
    return Observed(
        response=_send(client, route, method, call, world, user, None),
        missing=tuple(_send(client, route, method, call, world, user, m) for m in missing_ids),
        can_see=all(world.can_see(role, name) for name in call.object_refs),
        waiver=waiver,
    )
