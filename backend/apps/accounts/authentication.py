"""
JWT authentication and refresh enforcing account eligibility and session rules.

`apps.accounts.sessions` holds the rule; these two are where every request
and every refresh pass through it.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from . import sessions


class IdleAwareJWTAuthentication(JWTAuthentication):
    """simplejwt's authentication, refusing a session idle past the limit.

    An access token with no ``sid`` -- minted by `AccessToken.for_user` in a
    test or a script, never by sign-in -- is accepted only for an active,
    unlocked account. Its 30-minute lifetime bounds it; refresh refuses it.
    """

    def get_user(self, validated_token):
        # Check account state here, before simplejwt can answer inactive with
        # a different code. Tracked sessions are our revocation mechanism.
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken("Token contained no recognizable user identification") from exc
        try:
            user = self.user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist as exc:
            raise AuthenticationFailed("User not found", code="user_not_found") from exc
        sessions.require_eligible_account(user)
        return user

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
            # Signature and expiry checked, the blacklist not: `RefreshToken()`
            # would refuse a logged-out token here, before its session could
            # say why (IR-645). The parent's validation still checks both.
            token = UntypedToken(attrs["refresh"])
        except TokenError:
            # Malformed or expired: the parent's validation says so.
            return super().validate(attrs)
        if token.get(api_settings.TOKEN_TYPE_CLAIM) != RefreshToken.token_type:
            return super().validate(attrs)
        # Reuse the request rule before blacklist/session checks so an account
        # deactivated or locked outside the API is refused immediately too.
        IdleAwareJWTAuthentication().get_user(token)
        sid = token.get("sid")
        if not sid:
            raise InvalidToken("This sign-in predates session tracking. Sign in again.")
        # An ended session is refused by its reason before the token is judged:
        # logout blacklists the refresh token too, and "token not valid" would
        # not say the session ended (IR-645).
        sessions.refuse_if_ended(sid)
        # Validated next, so a rotated or blacklisted token records no activity.
        data = super().validate(attrs)
        sessions.touch(sid, self.context["request"])
        return data
