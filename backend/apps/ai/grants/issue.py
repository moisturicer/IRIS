"""Django issues research grants (IR-717, ADR-049 §6-7).

Purposes, never interchangeable:
- `record_read`: the reader only.
- `reader_run`: an owned AskRun, its Conversation and Record scope.
- `ingestion`: one IngestionJob and revision; no reader.

Claims carry identity and binding; access is read live on verification.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from enum import Enum

from apps.ai.grants import config, tokens

RECORD_READ = "record_read"
READER_RUN = "reader_run"
INGESTION = "ingestion"
PURPOSES = (RECORD_READ, READER_RUN, INGESTION)


class Refusal(str, Enum):
    """Why a grant was refused. Public-safe."""

    NOT_FOUND = "not_found"
    ENDED = "ended"
    UNAUTHORIZED = "unauthorized"


class GrantRefused(Exception):
    """Not issuable for this reader and binding."""

    def __init__(self, code: Refusal):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Grant:
    token: str
    claims: dict

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.claims["exp"], tz=dt_timezone.utc)


def _claims(cfg, purpose: str, *, now: int, exp: int, **binding) -> dict:
    return {
        "v": 1, "kid": cfg.active_kid, "aud": cfg.audience, "dep": cfg.deployment,
        "pur": purpose, "iat": now, "exp": exp, "jti": uuid.uuid4().hex,
        "sub": None, "gen": None, "run": None, "cnv": None, "rec": None,
        "job": None, "rev": None, **binding,
    }


def _sign(cfg, claims) -> Grant:
    return Grant(tokens.sign(claims, cfg.active_kid, cfg.active_secret), claims)


def _require_reader(user) -> None:
    if not getattr(user, "is_authenticated", False) or not user.is_active or user.is_locked:
        raise GrantRefused(Refusal.NOT_FOUND)


def record_read_grant(user) -> Grant:
    cfg = config.read()
    _require_reader(user)
    now = int(time.time())
    return _sign(cfg, _claims(
        cfg, RECORD_READ, now=now, exp=now + cfg.ttl_seconds,
        sub=user.pk, gen=user.credential_version,
    ))


def reader_grant(user, run) -> Grant:
    """For an existing run owned by `user`; never outlives its deadline."""
    from apps.ai.models import AskRun

    cfg = config.read()
    _require_reader(user)
    run = (AskRun.objects.select_related("conversation")
           .filter(pk=run.pk, user_id=user.pk, conversation__user_id=user.pk).first())
    if run is None:
        raise GrantRefused(Refusal.NOT_FOUND)
    now = int(time.time())
    deadline = int(run.deadline_at.timestamp())
    if run.is_terminal or deadline <= now:
        raise GrantRefused(Refusal.ENDED)
    return _sign(cfg, _claims(
        cfg, READER_RUN, now=now, exp=min(now + cfg.ttl_seconds, deadline),
        sub=user.pk, gen=user.credential_version, run=str(run.pk),
        cnv=run.conversation_id, rec=run.conversation.record_id,
    ))


def ingestion_grant(job) -> Grant:
    cfg = config.read()
    now = int(time.time())
    return _sign(cfg, _claims(
        cfg, INGESTION, now=now, exp=now + cfg.ttl_seconds,
        job=job.pk, rec=job.record_id, rev=job.extraction_hash,
    ))


def renew_reader_grant(user, run, token: str, *, using: str = "default") -> Grant:
    """A fresh grant for the same binding, rechecked against current facts."""
    from apps.ai.grants import database

    claims = database.verify(token, READER_RUN, using=using)
    if claims is None or claims.get("sub") != user.pk or claims.get("run") != str(run.pk):
        raise GrantRefused(Refusal.UNAUTHORIZED)
    return reader_grant(user, run)
