"""Short-lived JWTs for approved record downloads (FR-M6-01 extension)."""
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

DOWNLOAD_TOKEN_LIFETIME = timedelta(hours=24)
TOKEN_TYPE = "download"


def make_download_token(*, download_request_id: int, record_id: int, user_id: int) -> str:
    now = timezone.now()
    payload = {
        "typ": TOKEN_TYPE,
        "drid": download_request_id,
        "rid": record_id,
        "uid": user_id,
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_download_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    if payload.get("typ") != TOKEN_TYPE:
        raise jwt.InvalidTokenError("Invalid token type.")
    return payload
