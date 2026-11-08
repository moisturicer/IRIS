"""Recheck a paid AGENT payload immediately before every physical attempt.

An explicit, expiring development approval may admit the exact revisions of
public proxy sources it names. Reader access is independently checked under
the run's grant and PostgreSQL row security. Institutional Records remain
closed until their canonical Contact-person disclosure rule is available.
"""

from __future__ import annotations

import hashlib
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
CONTROL_KEYS = frozenset({"status", "reason", "coverage", "error", "revision", "search"})
CONTROL_VALUES = frozenset({"ok", "no_match", "partial", "unavailable", "tool_limit",
                            "invalid_arguments", "unknown_tool", "unknown_handle",
                            "source_replaced", "unauthorized", "run_ended", "exceeds_context",
                            "invalid_argument", "unknown_filter_value", "ambiguous_filter_value"})
#: How a combined search ran (IR-886): fixed names and outcomes, never content.
SEARCH_SIGNALS = frozenset({"keyword", "semantic", "rerank"})
SEARCH_VALUES = frozenset({"ok", "off", "unavailable", "provider_gated", "provider_failed",
                           "embedding_space_changed", "withheld"})
OPENROUTER = "https://openrouter.ai/api/v1"
LUNA_FLOOR = "openai/gpt-6-luna:floor"


def routing_digest(routing) -> str:
    return hashlib.sha256(json.dumps(routing, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _routed_policy(pin, routing, price) -> bool:
    if (pin.adapter != "openai-compatible" or pin.endpoint != OPENROUTER
            or pin.model != LUNA_FLOOR or not isinstance(routing, dict)
            or price is None or not hasattr(price, "input") or not hasattr(price, "output")):
        return False
    if set(routing) != {"only", "allow_fallbacks", "data_collection", "zdr",
                        "max_price", "require_parameters"}:
        return False
    only, cap = routing["only"], routing["max_price"]
    return (isinstance(only, list) and bool(only) and len(only) <= 4
            and all(isinstance(tag, str) and tag.strip() == tag != "" for tag in only)
            and len(set(only)) == len(only)
            and routing["allow_fallbacks"] is False and routing["data_collection"] == "deny"
            and routing["zdr"] is True and routing["require_parameters"] is True
            and isinstance(cap, dict) and set(cap) == {"prompt", "completion"}
            and all(type(v) in (int, float) and 0 < v < 100 for v in cap.values())
            and price.input >= cap["prompt"] and price.output >= cap["completion"])


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
    vendor_evidence: str = ""
    routing_digest: str = ""

    def permits(self, pin, account: str | None, campaign: str | None,
                sources: frozenset[Source], routing=None, price=None) -> bool:
        base = (self.approval_id == "IR-889" and self.expires_at.tzinfo is not None
                and self.expires_at > datetime.now(timezone.utc)
                and pin.model == self.model and pin.endpoint == self.endpoint
                and account == self.account and campaign == self.campaign
                and sources <= self.sources)
        if pin.adapter == "recording":
            return base
        return (base and self.vendor_evidence.startswith("https://")
                and len(self.routing_digest) == 64 and _routed_policy(pin, routing, price)
                and self.routing_digest == routing_digest(routing))

    @classmethod
    def from_json(cls, raw: str) -> ProxyApproval | None:
        """An unset or malformed operator manifest never opens the send gate."""
        if not raw:
            return None
        try:
            data = json.loads(raw)
            basic = {"approval_id", "model", "endpoint", "account", "campaign", "expires_at", "sources"}
            if set(data) not in (basic, basic | {"vendor_evidence", "routing_digest"}):
                return None
            if any(not isinstance(data[key], str) or not data[key] for key in
                   ("approval_id", "model", "endpoint", "account", "campaign", "expires_at")):
                return None
            if (not isinstance(data.get("vendor_evidence", ""), str)
                    or not isinstance(data.get("routing_digest", ""), str)):
                return None
            sources = frozenset(Source(**item) for item in data["sources"])
            if not sources or len(sources) > 40 or any(s.record_id < 1 or s.chunk_set_id < 1
                                                       or not s.extraction_hash
                                  for s in sources):
                return None
            return cls(data["approval_id"], data["model"], data["endpoint"],
                       data["account"], data["campaign"],
                       datetime.fromisoformat(data["expires_at"]), sources,
                       data.get("vendor_evidence", ""), data.get("routing_digest", ""))
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
    if "search" in body:
        search = body["search"]
        if (not isinstance(search, dict) or set(search) - SEARCH_SIGNALS
                or any(value not in SEARCH_VALUES for value in search.values())):
            return False
    if "coverage" in body:
        coverage = body["coverage"]
        if (not isinstance(coverage, dict) or set(coverage) - {"returned", "total", "truncated"}
                or any(type(value) not in (int, bool, type(None)) for value in coverage.values())):
            return False
    return "revision" not in body or (type(body["revision"]) is int and body["revision"] >= 0)


#: Longest name or title a metadata result may carry.
METADATA_TEXT = 1000
COUNT_KEYS = frozenset({"kind", "total", "filters", "group_by", "groups", "ungrouped", "scope",
                        "relative_to"})
LIST_KEYS = frozenset({"kind", "total", "filters", "truncated", "relative_to", "papers"})
PAPER_KEYS = frozenset({"paper", "title", "year"})
SCOPES = frozenset({"readable_records", "paper_chat"})


def _text(value) -> bool:
    return isinstance(value, str) and len(value) <= METADATA_TEXT


def _number(value) -> bool:
    return type(value) is int and value >= 0


def _filters(value) -> bool:
    return isinstance(value, dict) and all(
        _text(k) and (_text(v) or type(v) in (int, bool)) for k, v in value.items())


def _counted(body) -> bool:
    if not isinstance(body, dict) or set(body) != COUNT_KEYS or body["kind"] != "exact_count":
        return False
    groups = body["groups"]
    return (_number(body["total"]) and _number(body["ungrouped"]) and _filters(body["filters"])
            and (body["group_by"] is None or _text(body["group_by"])) and body["scope"] in SCOPES
            and _text(body["relative_to"]) and isinstance(groups, list)
            and all(isinstance(g, dict) and set(g) == {"value", "count"} and _number(g["count"])
                    and (_text(g["value"]) or type(g["value"]) is int) for g in groups))


def _listed(body) -> bool:
    if not isinstance(body, dict) or set(body) != LIST_KEYS or body["kind"] != "record_list":
        return False
    papers = body["papers"]
    return (_number(body["total"]) and _filters(body["filters"]) and type(body["truncated"]) is bool
            and _text(body["relative_to"]) and isinstance(papers, list)
            and all(isinstance(p, dict) and set(p) == PAPER_KEYS and _text(p["paper"]) and _text(p["title"])
                    and (p["year"] is None or type(p["year"]) is int) for p in papers))


def _metadata_only(entry: ToolResult) -> bool:
    """An exact count or a title list, by exact shape: Record metadata, never Record text (IR-994)."""
    if not entry.metadata_only:
        return False
    try:
        body = json.loads(entry.content)
    except (TypeError, ValueError):
        return False
    if not isinstance(body, dict) or body.get("status") not in CONTROL_VALUES:
        return False
    if "reason" in body and body["reason"] not in CONTROL_VALUES:
        return False
    rest = set(body) - {"status", "reason"}
    return (rest == {"count"} and _counted(body["count"])) or (rest == {"list"} and _listed(body["list"]))


def _sources(entries: Iterable) -> frozenset[Source]:
    found: set[Source] = set()
    for entry in entries:
        if not isinstance(entry, (ToolResult, ModelTurn, User)):
            raise AdmissionDenied(errors.WITHHELD)
        if getattr(entry, "unverified_provenance", False):
            raise AdmissionDenied(errors.WITHHELD)
        dependencies = getattr(entry, "dependencies", frozenset())
        if (isinstance(entry, ToolResult) and not dependencies and not _control_only(entry)
                and not _metadata_only(entry)):
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

    def _pilot(self, pin) -> bool:
        return (getattr(pin, "adapter", None) == "openai-compatible"
                and getattr(pin, "endpoint", None) == OPENROUTER)

    def _approved(self, pin, sources, account, campaign, routing, price) -> bool:
        return (self.stage == "development" and self.proxy_approval is not None
                and self.proxy_approval.permits(pin, account, campaign, sources, routing, price))

    async def check(self, binding: RunBinding, pin, dependencies: Iterable = (), *,
                    account: str | None = None, campaign: str | None = None,
                    routing=None, price=None) -> None:
        if pin.data_policy != NO_TRAINING:
            raise AdmissionDenied(errors.PROVIDER_REFUSED)
        sources = _sources(dependencies)
        if (sources or self._pilot(pin)) and not self._approved(pin, sources, account, campaign,
                                                                routing, price):
            raise AdmissionDenied(errors.WITHHELD)
        if (await self._run_checked(binding, sources)) != sources:
            raise AdmissionDenied(errors.WITHHELD)

    async def eligible(self, binding: RunBinding, pin, sources: frozenset[Source], *,
                       account: str | None = None, campaign: str | None = None,
                       routing=None, price=None) -> frozenset[Source]:
        """The subset of `sources` a send could carry now; the rest is left out, not refused.

        Run-level failures (fence, deadline, revoked reader) still raise.
        """
        if not sources or pin.data_policy != NO_TRAINING:
            return frozenset()
        approved = frozenset(s for s in sources
                             if self._approved(pin, frozenset({s}), account, campaign, routing, price))
        if not approved:
            return approved
        return await self._run_checked(binding, approved)

    async def _run_checked(self, binding: RunBinding, sources: frozenset[Source]) -> frozenset[Source]:
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
                    return await self._current(conn, row, sources) if sources else frozenset()
            finally:
                await conn.close()
        except asyncpg.InsufficientPrivilegeError:
            raise AdmissionDenied(errors.ACCESS_REVOKED) from None
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            raise AdmissionDenied(errors.STORE_UNAVAILABLE) from None

    async def _current(self, conn, run, sources: frozenset[Source]) -> frozenset[Source]:
        """The sources still readable by the run's reader at their exact revision."""
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
            """SELECT r.id, r.origin, r.is_ip, r.is_embargoed, r.embargo_released_at,
                      cs.id AS chunk_set_id, cs.extraction_hash
                 FROM public.records_record r
                 JOIN public.ai_chunkset cs ON cs.record_id = r.id AND cs.is_active
                WHERE r.id = ANY($1::bigint[])
                  AND ($2::bigint IS NULL OR r.id = $2)""",
            ids, run["scope_record_id"],
        )
        current = {row["id"]: row for row in rows}

        def ok(source):
            row = current.get(source.record_id)
            return (row is not None and row["chunk_set_id"] == source.chunk_set_id
                    and row["extraction_hash"] == source.extraction_hash
                    and row["origin"] in PROXY_ORIGINS and row["is_ip"] is False
                    and row["is_embargoed"] is False and row["embargo_released_at"] is not None)

        return frozenset(s for s in sources if ok(s))
