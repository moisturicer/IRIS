"""
JWT authentication and refresh that honour the inactivity rule (IR-166) and
the credential version (ADR-045 §4, IR-642).

`apps.accounts.sessions` holds the inactivity rule; these two are where every
request and every refresh pass through it. Both also compare the token's `cv`
claim with the account's `credential_version`, so a password reset or change
refuses every token minted before it, from the very next request.
"""

from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from . import sessions
from .models import User


class CredentialsChanged(AuthenticationFailed):
    """401 with ``code: credentials_changed``: sign in again.

    Raised for a token minted before the account's password last changed, and
    for one minted before ADR-045 at all -- no ``cv`` or no ``sid`` -- which
    is the deliberate cost of the rollout: every such holder signs in again.
    """
    default_detail = "Your sign-in is no longer valid. Sign in again."
    default_code = "credentials_changed"

    def __init__(self):
        super().__init__({"detail": self.default_detail, "code": self.default_code})


def current(token, user) -> bool:
    return token.get("sid") is not None and token.get("cv") == user.credential_version


class IdleAwareJWTAuthentication(JWTAuthentication):
    """simplejwt's authentication, refusing a session idle past the limit or
    a token from before the account's last password change."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        if not current(token, user):
            raise CredentialsChanged()
        sessions.touch(token["sid"], request)
        return user, token


class IdleAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh only a live, current session, and count the refresh as its activity.

    A refresh token without a ``sid`` was issued before IR-166, and one without
    a ``cv`` before ADR-045; both are refused, so their browsers sign in again.
    """

    def validate(self, attrs):
        try:
            token = UntypedToken(attrs["refresh"])
        except TokenError:
            return super().validate(attrs)
        if token.get(api_settings.TOKEN_TYPE_CLAIM) != RefreshToken.token_type:
            return super().validate(attrs)
        sid = token.get("sid")
        if not sid:
            raise InvalidToken("This sign-in predates session tracking. Sign in again.")
        # Reset and refresh both lock the account before issuing credentials.
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=token.get("user_id")).first()
            if user is None or not current(token, user):
                raise CredentialsChanged()
            sessions.refuse_if_ended(sid)
            data = super().validate(attrs)
            sessions.touch(sid, self.context["request"])
            return data

