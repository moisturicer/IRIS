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
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

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


class SessionIdle(AuthenticationFailed):
    """401 with ``code: session_idle``, so the interface can say why.

    An `AuthenticationFailed`, not a bare `APIException`: DRF keeps a 401 only
    for those (with a ``WWW-Authenticate`` header) and turns anything else
    raised during authentication into a 403.
    """
    default_detail = "You were signed out after a period of inactivity."
    default_code = "session_idle"

    def __init__(self):
        minutes = settings.SESSION_IDLE_TIMEOUT_MINUTES
        super().__init__({
            "detail": f"You were signed out after {minutes} minutes of inactivity.",
            "code": self.default_code,
        })


def start_session(user) -> RefreshToken:
    """Open a session and return its refresh token, carrying the session id."""
    at = now()
    session = UserSession.objects.create(user=user, created_at=at, last_activity_at=at)
    refresh = RefreshToken.for_user(user)
    refresh["sid"] = str(session.id)
    # ADR-045 §4: copied into every access token and through every rotation,
    # so a password change refuses all of them at once.
    refresh["cv"] = user.credential_version
    return refresh


def end_session(sid) -> None:
    UserSession.objects.filter(id=sid, ended_at__isnull=True).update(ended_at=now())


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

    Raises `SessionIdle` when the session is ended, unknown, or was idle past
    the timeout *before* this request arrived. The judgement uses the stored
    activity only: a user who walks away for 31 minutes and then clicks has
    still been away for 31 minutes, and their click must not excuse it. The
    interface's heartbeat (frontend/src/lib/activity.ts) is what keeps the
    stored figure current while someone works on a page that sends nothing.
    """
    at = now()
    session = UserSession.objects.filter(id=sid).only("last_activity_at", "ended_at").first()
    if session is None or session.ended_at is not None:
        raise SessionIdle()

    if at - session.last_activity_at > idle_timeout():
        end_session(sid)
        raise SessionIdle()

    activity = at - timedelta(seconds=idle_seconds(request))

    if activity - session.last_activity_at >= WRITE_EVERY:
        # Monotonic under concurrency: a slower request carrying an older
        # moment cannot move the clock back.
        UserSession.objects.filter(id=sid, last_activity_at__lt=activity).update(last_activity_at=activity)
