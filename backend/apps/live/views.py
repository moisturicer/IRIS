"""`GET /api/v1/live/`: the tab's hint stream (ADR-073)."""
from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import connection
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts import notice, sessions
from apps.accounts.authentication import IdleAwareJWTAuthentication, current, refuse_stale

from .channels import channels_for
from .stream import events, get_hub


class _Refused(Exception):
    def __init__(self, status, body):
        super().__init__(body)
        self.status, self.body = status, body


def _authenticate(request):
    """
    The stream's channels and its token's expiry, checked as every request is,
    recording nothing. The channels are read here, in sync code, because they
    need the account's role from the database (decision 3).
    """
    try:
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            raise _Refused(401, {"detail": "Sign in to receive live updates.", "code": "not_authenticated"})
        try:
            token = AccessToken(header[len("Bearer "):])
        except TokenError:
            raise _Refused(401, {"detail": "Token is invalid or expired.", "code": "token_not_valid"})
        try:
            user = IdleAwareJWTAuthentication().get_user(token)
            if not current(token, user):
                refuse_stale(token)
            sid = token.get("sid")
            if not sid:
                raise _Refused(401, {"detail": "Sign in again.", "code": "token_not_valid"})
            sessions.check_open(sid)
        except AuthenticationFailed as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
            raise _Refused(401, {key: str(value) for key, value in detail.items()})
        if notice.requires_answer(user):
            raise _Refused(403, {"detail": "Answer the data notice first.", "code": "notice_acceptance_required"})
        return channels_for(user), float(token["exp"])
    finally:
        # Nothing else is read while the stream is open (decision 2), so the
        # connection is let go now. Inside a transaction (a test's) it stays.
        if not connection.in_atomic_block:
            connection.close()


class LiveStreamView(View):
    """GET only; an async class view, so the route matrix can read its method."""

    http_method_names = ["get"]

    async def get(self, request):
        try:
            channels, expires_at = await sync_to_async(_authenticate)(request)
        except _Refused as refused:
            return JsonResponse(refused.body, status=refused.status)

        hub = get_hub()
        queue = hub.register(channels)

        async def body():
            try:
                async for line in events(queue, expires_at):
                    yield line
            finally:
                hub.unregister(channels, queue)

        response = StreamingHttpResponse(body(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store"
        response["X-Accel-Buffering"] = "no"  # nginx passes it through unbuffered
        return response


live_stream = LiveStreamView.as_view()
