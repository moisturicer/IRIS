"""Tokens, counter identifiers and payload encryption (ADR-045 §3, §5, §6)."""

import base64
import hashlib
import hmac
import re
import secrets

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings

#: 32 random bytes, base64url without padding.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def digest(token: str) -> str:
    """What is stored and looked up. The raw token is never stored in clear."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def identifier(kind: str, value: str) -> str:
    """A keyed HMAC naming a recipient or address in the limit counters.

    Keyed so that a counter table read on its own does not reveal which
    addresses asked: a plain hash of an email is reversible by guessing.
    """
    key = settings.RECOVERY_COUNTER_HMAC_KEY.encode("utf-8")
    return hmac.new(key, f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(key.encode("ascii")) for key in settings.RECOVERY_MAIL_ENCRYPTION_KEY])


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
