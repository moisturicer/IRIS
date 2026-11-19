"""
Test helpers for the refresh cookie (ADR-072).

The refresh token is only ever in the `iris_refresh` cookie, never a response
body, and refresh and logout read it from there with `X-IRIS-Auth: 1`. These
helpers do what the browser does, so tests keep holding several sign-ins'
tokens at once, as they did when the token came in the body.
"""
from django.conf import settings
from rest_framework.test import APIClient

REFRESH_URL = "/api/v1/auth/token/refresh/"
LOGOUT_URL = "/api/v1/auth/logout/"
FIRST_PARTY = {"HTTP_X_IRIS_AUTH": "1"}


def refresh_from(response) -> str:
    """The refresh token a login or refresh response set in its cookie."""
    return response.cookies[settings.REFRESH_COOKIE_NAME].value


def tokens_of(response) -> dict:
    """A login or refresh response's body, with its cookie's refresh token as ``refresh``."""
    return {**response.json(), "refresh": refresh_from(response)}


def with_refresh_cookie(client: APIClient, refresh: str | None) -> APIClient:
    if refresh is None:
        client.cookies.pop(settings.REFRESH_COOKIE_NAME, None)
    else:
        client.cookies[settings.REFRESH_COOKIE_NAME] = refresh
    return client


def post_refresh(refresh: str | None, client: APIClient | None = None, **headers):
    """`POST /auth/token/refresh/` presenting ``refresh`` as the browser would."""
    client = with_refresh_cookie(client or APIClient(), refresh)
    return client.post(REFRESH_URL, format="json", **FIRST_PARTY, **headers)


def post_logout(refresh: str | None, access: str, client: APIClient | None = None):
    client = with_refresh_cookie(client or APIClient(), refresh)
    return client.post(LOGOUT_URL, format="json", HTTP_AUTHORIZATION=f"Bearer {access}", **FIRST_PARTY)
