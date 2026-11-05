"""Recheck a paid AGENT payload immediately before every physical attempt.

An explicit, expiring development approval may admit the exact revisions of
public proxy sources it names. Reader access is independently checked under
the run's grant and PostgreSQL row security. Institutional Records remain
closed until their canonical Contact-person disclosure rule is available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import asyncpg

from ai.agent.protocol import ModelTurn, ToolResult, User
from ai.research.tools import Source

from . import errors
from .errors import AdmissionDenied
from .scope import RunBinding

NO_TRAINING = "no-training"
PROXY_ORIGINS = frozenset({"imported_reference", "synthetic"})
CONTROL_KEYS = frozenset({"status", "reason", "coverage", "error", "revision"})
CONTROL_VALUES = frozenset({"ok", "no_match", "partial", "unavailable", "tool_limit",
                            "invalid_arguments", "unknown_tool", "unknown_handle",
                            "source_replaced", "unauthorized", "run_ended", "exceeds_context"})


@dataclass(frozen=True)
class ProxyApproval:
    """One development campaign's reviewed, public source revisions."""

    approval_id: str
    model: str
    endpoint: str
    account: str
    campaign: str
    expires_at: datetime
    sources: frozenset[Source]

    def permits(self, pin, account: str | None, campaign: str | None,
                sources: frozenset[Source]) -> bool:
        return (self.approval_id == "IR-889" and self.expires_at.tzinfo is not None
                and self.expires_at > datetime.now(timezone.utc)
                and pin.model == self.model and pin.endpoint == self.endpoint
                and account == self.account and campaign == self.campaign
                and bool(sources) and sources <= self.sources)

    @classmethod
    def from_json(cls, raw: str) -> ProxyApproval | None:
        """An unset or malformed operator manifest never opens the send gate."""
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if set(data) != {"approval_id", "model", "endpoint", "account", "campaign",
                             "expires_at", "sources"}:
                return None
            sources = frozenset(Source(**item) for item in data["sources"])
            if not sources or len(sources) > 40 or any(s.record_id < 1 or s.chunk_set_id < 1
                                                       or not s.extraction_hash
                                  for s in sources):
                return None
            return cls(data["approval_id"], data["model"], data["endpoint"],
                       data["account"], data["campaign"],
                       datetime.fromisoformat(data["expires_at"]), sources)
        except (TypeError, ValueError, KeyError):
            return None


def _control_only(entry: ToolResult) -> bool:
    """An empty dependency set is allowed only for a content-free control."""
    if not entry.control_only:
        return False
    try:
        body = json.loads(entry.content)
    except (TypeError, ValueError):
        return False
    if not isinstance(body, dict) or not body or set(body) - CONTROL_KEYS:
        return body == {"withheld": "exceeds_context", "coverage": "none"}
    for name in ("status", "reason", "error", "withheld"):
        if name in body and body[name] not in CONTROL_VALUES:
            return False
    if "coverage" in body:
        coverage = body["coverage"]
        if (not isinstance(coverage, dict) or set(coverage) - {"returned", "total", "truncated"}
                or any(type(value) not in (int, bool, type(None)) for value in coverage.values())):
            return False
    return "revision" not in body or (type(body["revision"]) is int and body["revision"] >= 0)


def _sources(entries: Iterable) -> frozenset[Source]:
    found: set[Source] = set()
    for entry in entries:
        if not isinstance(entry, (ToolResult, ModelTurn, User)):
            raise AdmissionDenied(errors.WITHHELD)
        if getattr(entry, "unverified_provenance", False):
            raise AdmissionDenied(errors.WITHHELD)
        dependencies = getattr(entry, "dependencies", frozenset())
        if isinstance(entry, ToolResult) and not dependencies and not _control_only(entry):
            raise AdmissionDenied(errors.WITHHELD)
        if not isinstance(dependencies, frozenset) or any(not isinstance(d, Source)
                                                           for d in dependencies):
            raise AdmissionDenied(errors.WITHHELD)
        found.update(dependencies)
    return frozenset(found)


class SendGuard:
    def __init__(self, dsn: str, proxy_approval: ProxyApproval | None = None,
                 *, stage: str = "production"):
        self.dsn = dsn
        self.proxy_approval = proxy_approval
        self.stage = stage

    async def check(self, binding: RunBinding, pin, dependencies: Iterable = (), *,
                    account: str | None = None, campaign: str | None = None) -> None:
        if pin.data_policy != NO_TRAINING:
            raise AdmissionDenied(errors.PROVIDER_REFUSED)
        sources = _sources(dependencies)
        # IR-827 has no account-specific OpenRouter evidence yet. The approved
        # proxy seam can be exercised through the recording provider only.
        if sources and pin.adapter != "recording":
            raise AdmissionDenied(errors.PROVIDER_REFUSED)
        if sources and (self.stage != "development" or self.proxy_approval is None
                        or not self.proxy_approval.permits(pin, account, campaign, sources)):
            raise AdmissionDenied(errors.WITHHELD)
        try:
            conn = await asyncpg.connect(self.dsn)
            try:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT r.state, r.fence, r.deadline_at <= now() AS overdue,
                                  coalesce(r.grant_expires_at > now(), false) AS granted,
                                  iris_authz.reader_status(r.reader_id) AS reader, r.reader_id,
                                  r.reader_grant, c.scope_record_id
                             FROM iris_ai.ask_run r
                             JOIN iris_ai.conversation c ON c.id = r.conversation_id
                            WHERE r.id = $1 AND c.deleted_at IS NULL FOR SHARE OF r, c""",
                        binding.run_id,
                    )
                    if row is None or row["state"] != "running" or row["fence"] != binding.fence:
                        raise AdmissionDenied(errors.RUN_CANCELLED)
                    if row["overdue"]:
                        raise AdmissionDenied(errors.DEADLINE)
                    if row["reader"] != "active" or not row["granted"]:
                        raise AdmissionDenied(errors.ACCESS_REVOKED)
                    if sources:
                        await self._check_sources(conn, row, sources)
            finally:
                await conn.close()
        except asyncpg.InsufficientPrivilegeError:
            raise AdmissionDenied(errors.ACCESS_REVOKED) from None
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            raise AdmissionDenied(errors.STORE_UNAVAILABLE) from None

    async def _check_sources(self, conn, run, sources: frozenset[Source]) -> None:
        grant = run["reader_grant"]
        if not grant:
            raise AdmissionDenied(errors.ACCESS_REVOKED)
        try:
            reader = await conn.fetchval(
                "SELECT (iris_authz.begin_research($1, 'reader_session')->>'sub')::bigint", grant)
        except asyncpg.PostgresError:
            raise AdmissionDenied(errors.ACCESS_REVOKED) from None
        if reader != run["reader_id"]:
            raise AdmissionDenied(errors.ACCESS_REVOKED)
        ids = sorted({source.record_id for source in sources})
        rows = await conn.fetch(
            """SELECT r.id, r.origin, r.is_ip, r.embargo_answered_at,
                      r.embargoed_until, r.embargo_released_at,
                      cs.id AS chunk_set_id, cs.extraction_hash
                 FROM public.records_record r
                 JOIN public.ai_chunkset cs ON cs.record_id = r.id AND cs.is_active
                WHERE r.id = ANY($1::bigint[])
                  AND ($2::bigint IS NULL OR r.id = $2)""",
            ids, run["scope_record_id"],
        )
        current = {row["id"]: row for row in rows}
        for source in sources:
            row = current.get(source.record_id)
            if (row is None or row["chunk_set_id"] != source.chunk_set_id
                    or row["extraction_hash"] != source.extraction_hash
                    or row["origin"] not in PROXY_ORIGINS or row["is_ip"] is not False
                    or row["embargo_answered_at"] is None
                    or (row["embargoed_until"] is not None
                        and row["embargo_released_at"] is None)):
                raise AdmissionDenied(errors.WITHHELD)
