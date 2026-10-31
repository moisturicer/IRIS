"""
Inactivity expiry (IR-166, NFR-S2): a session ends after 30 minutes in which
the *user* did nothing, however long it has been open.

Why not the token lifetimes: the access token's 30 minutes was never an
inactivity rule, because the client refreshes it silently. A session lasted
the refresh token's 7 days whether anyone was at the keyboard or not. And a
request is not activity either: an open tab polls.

So the client reports, and the server decides. Every request from the
interface carries ``X-IRIS-Idle-Seconds``, the seconds since the last real
interaction (pointer, key, touch). The moment of activity that request
attests to is ``now - idle``. A session's ``last_activity_at`` is the latest
such moment from any of its requests, so a poll from an untouched tab
extends nothing, while a second tab the user *is* using keeps the session
alive. A request with no header -- a script, the AI stream's bare ``fetch`` --
counts as activity when it arrives.

A session is idle when more than the timeout has passed since that stored
moment, judged before the request in hand is applied (see `touch`). A page
that sends no requests while the user reads it would otherwise look idle, so
the interface sends a heartbeat every few minutes while there is input to
report.

The client can lie about its own idleness. That is acceptable: the rule
protects an unattended screen from a passer-by, not the server from the user.

Once a session is found idle it is ended for good; fresh activity does not
revive it. The refresh token's 7-day lifetime remains the absolute limit.

An ended session records why (IR-645), and its refusal says so: a user who
signed out in another tab is not told they were away too long. A session
ended before the reason was recorded has none, and reads as idle -- the
message it had before.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.enums import SessionEndReason

from .models import UserSession

#: The header the interface sends; see frontend/src/lib/activity.ts.
IDLE_HEADER = "HTTP_X_IRIS_IDLE_SECONDS"

#: A session's activity is written at most this often. Every request reads it;
#: writing it on each one would put an UPDATE on every poll. The cost is that a
#: session can end up to this much *early*, never late.
WRITE_EVERY = timedelta(seconds=60)


def now():
    """The clock, a seam so tests can move it without moving token expiry."""
    return timezone.now()


def idle_timeout() -> timedelta:
    return timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)


class SessionEnded(AuthenticationFailed):
    """401 naming why the session ended, so the interface can say so.

    An `AuthenticationFailed`, not a bare `APIException`: DRF keeps a 401 only
    for those (with a ``WWW-Authenticate`` header) and turns anything else
    raised during authentication into a 403.
    """

    def __init__(self, reason=None):
        code, detail = _REFUSALS.get(reason) or _idle_refusal()
        super().__init__({"detail": detail, "code": code})


def _idle_refusal():
    minutes = settings.SESSION_IDLE_TIMEOUT_MINUTES
    return "session_idle", f"You were signed out after {minutes} minutes of inactivity."


#: The 401 ``code`` and message for each reason. Idle, null and an unknown
#: session fall through to `_idle_refusal`, so the wire format they had before
#: IR-645 is unchanged.
_REFUSALS = {
    SessionEndReason.LOGOUT: ("session_ended", "This session was signed out."),
    SessionEndReason.LOCKED: ("account_locked", "You were signed out because your account was locked."),
    SessionEndReason.PASSWORD_CHANGED: (
        "session_ended_password_changed",
        "You were signed out because your password was changed.",
    ),
    SessionEndReason.REVOKED: ("session_ended_revoked", "An administrator ended this session."),
}


def start_session(user) -> RefreshToken:
    """Open a session and return its refresh token, carrying the session id."""
    at = now()
    session = UserSession.objects.create(user=user, created_at=at, last_activity_at=at)
    refresh = RefreshToken.for_user(user)
    refresh["sid"] = str(session.id)
    # for_user stores the token before we add sid. Keep its stored payload in
    # sync so end_all_sessions can identify the device it must spare.
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(token=str(refresh))
    return refresh


def end_session(sid, reason: SessionEndReason) -> None:
    """End session ``sid`` for ``reason``. The first ending stands."""
    UserSession.objects.filter(id=sid, ended_at__isnull=True).update(ended_at=now(), ended_reason=reason)


def require_eligible_account(user) -> None:
    """The same account-state rule for requests and refresh, including no sid."""
    if not user.is_active or user.is_locked:
        raise SessionEnded(SessionEndReason.LOCKED)


@transaction.atomic
def end_all_sessions(user, reason: SessionEndReason, *, except_sid=None) -> None:
    """End open sessions, preserving their first reason and optionally one device.

    Older stored refresh payloads lack sid even though the issued token has it.
    When sparing a device these cannot safely be blacklisted: their presented
    sid still goes through the ended-session rule on every request and refresh.
    Without an exception (account lock), every outstanding token is blacklisted.
    """
    open_sessions = UserSession.objects.filter(user=user, ended_at__isnull=True)
    if except_sid:
        open_sessions = open_sessions.exclude(id=except_sid)
    open_sessions.update(ended_at=now(), ended_reason=reason)
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    for token in tokens.iterator():
        if except_sid:
            # These are our own stored payloads; ignore expiry while reading
            # their session identity. Authentication verifies the issued JWT.
            sid = UntypedToken(token.token, verify=False).get("sid")
            if sid is None or str(sid) == str(except_sid):
                continue
        BlacklistedToken.objects.get_or_create(token=token)


@transaction.atomic
def revoke_token(token: OutstandingToken) -> None:
    """End the session a stored refresh token belongs to, and blacklist it (IR-657).

    Blacklisting alone leaves the access token working until it expires. A stored
    payload with no sid predates that being kept, and only the blacklisting applies.
    """
    sid = UntypedToken(token.token, verify=False).get("sid")
    if sid:
        end_session(sid, SessionEndReason.REVOKED)
    BlacklistedToken.objects.get_or_create(token=token)


def refuse_if_ended(sid) -> None:
    """Raise `SessionEnded` when session ``sid`` is ended or unknown; write nothing.

    Refresh asks this before validating the token: a logout blacklists the
    refresh token too, and that refusal alone would not say the session ended.
    """
    session = UserSession.objects.filter(id=sid).only("ended_at", "ended_reason").first()
    if session is None:
        raise SessionEnded()
    if session.ended_at is not None:
        raise SessionEnded(session.ended_reason)


def idle_seconds(request) -> int:
    """Seconds since the user's last interaction, as the client reports it.

    Missing or malformed means the request is itself the interaction. Negative
    is clamped to zero, so a client cannot vouch for activity in the future.
    """
    try:
        return max(0, int(request.META.get(IDLE_HEADER, 0)))
    except (TypeError, ValueError):
        return 0


def touch(sid, request) -> None:
    """Record this request's activity on session ``sid``, or refuse it as idle.

    Raises `SessionEnded` when the session is ended, unknown, or was idle past
    the timeout *before* this request arrived. The judgement uses the stored
    activity only: a user who walks away for 31 minutes and then clicks has
    still been away for 31 minutes, and their click must not excuse it. The
    interface's heartbeat (frontend/src/lib/activity.ts) is what keeps the
    stored figure current while someone works on a page that sends nothing.
    """
    at = now()
    session = UserSession.objects.filter(id=sid).only("last_activity_at", "ended_at", "ended_reason").first()
    if session is None:
        raise SessionEnded()
    if session.ended_at is not None:
        raise SessionEnded(session.ended_reason)

    if at - session.last_activity_at > idle_timeout():
        end_session(sid, SessionEndReason.IDLE)
        raise SessionEnded(SessionEndReason.IDLE)

    activity = at - timedelta(seconds=idle_seconds(request))

    if activity - session.last_activity_at >= WRITE_EVERY:
        # Monotonic under concurrency: a slower request carrying an older
        # moment cannot move the clock back.
        UserSession.objects.filter(id=sid, last_activity_at__lt=activity).update(last_activity_at=activity)
