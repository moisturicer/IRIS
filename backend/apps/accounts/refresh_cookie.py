"""
The refresh token's cookie (ADR-072).

The refresh token never appears in a response body or in the browser's own
storage. It travels in one `HttpOnly` cookie that page scripts can't read,
scoped to the auth endpoints, with `SameSite=Strict`, so a browser doesn't send
it with a request another site starts.

Refresh and logout read the cookie, so they also refuse a request that isn't
from the app itself (decision 5): its `Origin`, when sent, must be one of
`CORS_ALLOWED_ORIGINS` or the request's own host, and it must carry
`X-IRIS-Auth: 1`, which a cross-origin page can't add without a preflight that
CORS refuses.
"""
from django.conf import settings
from rest_framework.exceptions import PermissionDenied

#: The custom header refresh and logout require (ADR-072 decision 5).
FIRST_PARTY_HEADER = "HTTP_X_IRIS_AUTH"


class NotFirstParty(PermissionDenied):
    default_detail = "This request must come from IRIS itself."
    default_code = "not_first_party"


def require_first_party(request) -> None:
    """Refuse a cookie-reading request another site could have started."""
    if request.META.get(FIRST_PARTY_HEADER) != "1":
        raise NotFirstParty()
    origin = request.META.get("HTTP_ORIGIN")
    if origin is None:
        # Browsers send Origin on every cross-origin POST, so its absence means
        # a same-origin request from an older browser, or a non-browser client.
        return
    allowed = set(settings.CORS_ALLOWED_ORIGINS)
    allowed.add(f"{request.scheme}://{request.get_host()}")
    if origin not in allowed:
        raise NotFirstParty()


def read(request) -> str | None:
    return request.COOKIES.get(settings.REFRESH_COOKIE_NAME) or None


def set_cookie(response, refresh, session) -> None:
    """Put ``refresh`` in the cookie.

    A remembered session's cookie lasts until the session's fixed end and
    survives a browser restart. Any other session's has no `Max-Age`, so it
    ends with the browser session, and the idle rule ends the session itself.
    """
    max_age = None
    if session is not None and session.expires_at is not None:
        from .sessions import now  # One clock with the session rules
        max_age = max(int((session.expires_at - now()).total_seconds()), 0)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=max_age,
        path=settings.REFRESH_COOKIE_PATH,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )


def clear_cookie(response) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        samesite="Strict",
    )
