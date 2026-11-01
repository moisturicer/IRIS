"""Research-grant settings, read and checked (IR-717, ADR-049 §6).

Off by default. When `AI_RESEARCH_GRANTS` is on, every key setting is
required and Django refuses to start without it.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Mapping

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

KID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
MIN_SECRET_BYTES = 32
#: The verifier in PostgreSQL enforces the same ceiling.
MAX_TTL_SECONDS = 900
MIN_TTL_SECONDS = 30


class GrantsUnavailable(Exception):
    """Grants are off or misconfigured; callers answer `unavailable`."""


@dataclass(frozen=True)
class GrantConfig:
    keys: Mapping[str, bytes]
    active_kid: str
    audience: str
    deployment: str
    ttl_seconds: int

    @property
    def active_secret(self) -> bytes:
        return self.keys[self.active_kid]


def enabled() -> bool:
    return bool(getattr(settings, "AI_RESEARCH_GRANTS", False))


def _decode(secret: str) -> bytes:
    padded = secret + "=" * (-len(secret) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def problems() -> list[str]:
    found: list[str] = []
    keys: dict[str, bytes] = {}
    for entry in str(getattr(settings, "AI_RESEARCH_GRANT_KEYS", "") or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        kid, sep, secret = entry.partition(":")
        if not sep or not KID.match(kid):
            found.append("AI_RESEARCH_GRANT_KEYS entries must be kid:base64url-secret")
            continue
        try:
            raw = _decode(secret.strip())
        except (binascii.Error, ValueError):
            found.append(f"AI_RESEARCH_GRANT_KEYS key {kid} is not base64url")
            continue
        if len(raw) < MIN_SECRET_BYTES:
            found.append(f"AI_RESEARCH_GRANT_KEYS key {kid} must be at least {MIN_SECRET_BYTES} bytes")
        if kid in keys:
            found.append(f"AI_RESEARCH_GRANT_KEYS names {kid} twice")
        keys[kid] = raw
    if not keys:
        found.append("AI_RESEARCH_GRANT_KEYS is required")
    active = str(getattr(settings, "AI_RESEARCH_GRANT_ACTIVE_KEY", "") or "").strip()
    if not active:
        found.append("AI_RESEARCH_GRANT_ACTIVE_KEY is required")
    elif active not in keys:
        found.append("AI_RESEARCH_GRANT_ACTIVE_KEY must name a key in AI_RESEARCH_GRANT_KEYS")
    for name in ("AI_RESEARCH_GRANT_AUDIENCE", "AI_RESEARCH_GRANT_DEPLOYMENT"):
        if not str(getattr(settings, name, "") or "").strip():
            found.append(f"{name} is required")
    ttl = getattr(settings, "AI_RESEARCH_GRANT_TTL_SECONDS", None)
    if not isinstance(ttl, int) or not MIN_TTL_SECONDS <= ttl <= MAX_TTL_SECONDS:
        found.append(
            f"AI_RESEARCH_GRANT_TTL_SECONDS must be {MIN_TTL_SECONDS}-{MAX_TTL_SECONDS}"
        )
    return found


def read() -> GrantConfig:
    if not enabled() or problems():
        raise GrantsUnavailable
    keys = {}
    for entry in settings.AI_RESEARCH_GRANT_KEYS.split(","):
        if entry.strip():
            kid, _, secret = entry.strip().partition(":")
            keys[kid] = _decode(secret.strip())
    return GrantConfig(
        keys=keys,
        active_kid=settings.AI_RESEARCH_GRANT_ACTIVE_KEY.strip(),
        audience=settings.AI_RESEARCH_GRANT_AUDIENCE.strip(),
        deployment=settings.AI_RESEARCH_GRANT_DEPLOYMENT.strip(),
        ttl_seconds=settings.AI_RESEARCH_GRANT_TTL_SECONDS,
    )


def verify_grant_configuration() -> None:
    """Startup check, from `AiConfig.ready()`."""
    if enabled():
        found = problems()
        if found:
            raise ImproperlyConfigured("; ".join(found) + " (IR-717; see backend/.env.example)")
