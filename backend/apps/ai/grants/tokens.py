"""The grant wire format: `irg1.<kid>.<b64url claims>.<b64url HMAC-SHA256>`.

Django signs; PostgreSQL verifies (`iris_authz.verify_research_grant`).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

PREFIX = "irg1"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign(claims: dict, kid: str, secret: bytes) -> str:
    body = b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{PREFIX}.{kid}.{body}"
    tag = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(tag)}"
