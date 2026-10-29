"""
JWT authentication and refresh that honour the inactivity rule (IR-166).

`apps.accounts.sessions` holds the rule; these two are where every request
and every refresh pass through it.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from . import sessions


class IdleAwareJWTAuthentication(JWTAuthentication):
    """simplejwt's authentication, refusing a session idle past the limit.

    An access token with no ``sid`` -- minted by `AccessToken.for_user` in a
    test or a script, never by sign-in -- is accepted: its own 30-minute
    lifetime already bounds it. Refresh is where such a token stops (below).
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        sid = token.get("sid")
        if sid:
            sessions.touch(sid, request)
        return user, token


class IdleAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh only a live session, and count the refresh as its activity.

    A refresh token without a ``sid`` was issued before IR-166 and is refused,
    so every browser signed in before the deploy signs in again within the
    access token's 30 minutes rather than the refresh token's 7 days.
    """

    def validate(self, attrs):
        try:
            sid = RefreshToken(attrs["refresh"]).get("sid")
        except TokenError:
            # Malformed or expired: the parent's validation says so.
            return super().validate(attrs)
        if not sid:
            raise InvalidToken("This sign-in predates session tracking. Sign in again.")
        # Validated first, so a rotated or blacklisted token records no activity.
        data = super().validate(attrs)
        sessions.touch(sid, self.context["request"])
        return data
