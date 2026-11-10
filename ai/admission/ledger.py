"""Reserve before sending, settle after, in Django's ledger (IR-725).

`apps.ai.admission.ledger`'s semantics over asyncpg: same campaign lock,
worst-case reservation, settlement and abandoned leases. Differences: the
run's ceiling is its AskRun allowance summed over every fence and campaign,
and a run no longer running under the caller's fence, or past its deadline,
admits nothing. Writes and settles only ``owner = 'ai'`` rows.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

import asyncpg

from . import errors
from .errors import AdmissionDenied
from .limits import Ceiling, Limits, NotConfigured
from .limits import read as read_limits
from .scope import RunBinding

log = logging.getLogger(__name__)

APP_NAME = "iris-ai-admission"
OWNER = "ai"
_PER_TEXT_OVERHEAD = 8
_STORE_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)
_CHARGE = ("attempts", "input_tokens", "output_tokens", "cost_micros")


def estimate_tokens(*texts: str) -> int:
    """An upper bound on the tokens in ``texts``: no tokenizer emits more
    tokens than UTF-8 bytes."""
    return sum(len(text.encode("utf-8")) + _PER_TEXT_OVERHEAD for text in texts)


@dataclass(frozen=True)
class Request:
    """One physical attempt, described before it is sent. No content."""

    operation: str
    purpose: str
    purpose_version: str
    lane: str
    account: str
    models: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    #: The provider's own timeout; ``None`` leaves what remains of the deadline.
    timeout_seconds: Optional[float] = None


@dataclass
class Usage:
    sent: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: Optional[str] = None
    #: Of `input_tokens`, served from the provider's prompt cache. Recorded, never discounted (IR-953).
    cached_input_tokens: Optional[int] = None

    @property
    def reported(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None


def _worst_cost(limits: Limits, models: Sequence[str], input_tokens: int, output_tokens: int):
    prices = [limits.prices.get(model) for model in models]
    if not prices or any(price is None for price in prices):
        return None
    return math.ceil(input_tokens * max(p.input for p in prices)
                     + output_tokens * max(p.output for p in prices))


def _ms(delta: timedelta) -> int:
    return max(0, math.ceil(delta.total_seconds() * 1000))


def _over(charged: dict, ceiling: Ceiling, wanted: dict) -> bool:
    return any(charged[name] + wanted[name] > getattr(ceiling, name)
               for name in wanted if getattr(ceiling, name) is not None)


class _Refused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Ledger:
    def __init__(self, dsn: str, limits: Optional[Limits]):
        """``limits`` of ``None`` refuses every attempt as `not_configured`."""
        self.dsn = dsn
        self.limits = limits

    @classmethod
    def from_settings(cls, dsn: str, values) -> "Ledger":
        try:
            return cls(dsn, read_limits(values))
        except NotConfigured as missing:
            log.warning("provider admission not configured: %s", missing)
            return cls(dsn, None)

    async def _connect(self):
        conn = await asyncpg.connect(self.dsn, server_settings={"application_name": APP_NAME})
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        return conn

    async def admit(self, request: Request, binding: Optional[RunBinding]) -> "Ticket":
        """Reserve ``request``'s worst case, or raise `AdmissionDenied`."""
        if binding is None:
            raise AdmissionDenied(errors.NOT_BOUND)
        limits = self.limits
        if limits is None:
            raise AdmissionDenied(errors.NOT_CONFIGURED)
        cost = _worst_cost(limits, request.models, request.input_tokens, request.output_tokens)
        if cost is None:
            raise AdmissionDenied(errors.UNPRICED_MODEL)
        wanted = {"attempts": 1, "input_tokens": request.input_tokens,
                  "output_tokens": request.output_tokens, "cost_micros": cost}
        try:
            conn = await self._connect()
            try:
                async with conn.transaction():
                    pk, campaign_id, timeout = await self._reserve(conn, limits, request, binding, wanted)
            finally:
                await conn.close()
        except _Refused as refused:
            log.info("provider admission refused: %s (run %s)", refused.reason, binding.run_id)
            raise AdmissionDenied(refused.reason) from None
        except _STORE_ERRORS:
            log.exception("provider admission store unavailable")
            raise AdmissionDenied(errors.STORE_UNAVAILABLE) from None
        return Ticket(self, pk, campaign_id, request, timeout)

    async def _reserve(self, conn, limits: Limits, request: Request, binding: RunBinding, wanted):
        campaign = await self._locked_campaign(conn, limits.campaign_key)
        now = await conn.fetchval("SELECT clock_timestamp()")
        await conn.execute(
            """UPDATE public.ai_providerreservation SET state = 'abandoned'
                WHERE campaign_id = $1 AND state = 'open' AND lease_expires_at < $2""",
            campaign["id"], now,
        )
        run = await self._work(conn, binding)
        if run is None or run["state"] != "running" or run["fence"] != binding.fence:
            raise _Refused(errors.RUN_CANCELLED)
        timeout = (run["deadline_at"] - now).total_seconds()
        if timeout <= 0:
            raise _Refused(errors.DEADLINE)
        if request.timeout_seconds is not None:
            timeout = min(timeout, request.timeout_seconds)

        account = request.account[:32]
        lane_limit = limits.lanes.get(request.lane)
        if lane_limit is None:
            raise _Refused(errors.LANE_NOT_CONFIGURED)
        in_lane, in_account = await conn.fetchrow(
            """SELECT count(*) FILTER (WHERE lane = $2), count(*) FILTER (WHERE account = $3)
                 FROM public.ai_providerreservation WHERE campaign_id = $1 AND state = 'open'""",
            campaign["id"], request.lane, account,
        )
        if in_lane >= lane_limit:
            raise _Refused(errors.LANE_BUSY)
        if in_account >= limits.account_concurrency:
            raise _Refused(errors.ACCOUNT_BUSY)

        lease = timedelta(seconds=timeout + limits.lease_grace_seconds)
        active_ms = _ms(lease)
        charged = {name: campaign[f"charged_{name}"] for name in (*_CHARGE, "active_ms")}
        if _over(charged, limits.spendable, {**wanted, "active_ms": active_ms}):
            raise _Refused(errors.CAMPAIGN_EXHAUSTED)
        run_charged = dict(await conn.fetchrow(
            """SELECT coalesce(sum(charge_attempts), 0) AS attempts,
                      coalesce(sum(charge_input_tokens), 0) AS input_tokens,
                      coalesce(sum(charge_output_tokens), 0) AS output_tokens,
                      coalesce(sum(charge_cost_micros), 0) AS cost_micros
                 FROM public.ai_providerreservation WHERE run_key = $1""",
            binding.key,
        ))
        try:
            ceiling = Ceiling.of_allowance(run["allowance"])
        except (KeyError, TypeError, ValueError):
            raise _Refused(errors.NOT_CONFIGURED) from None
        # Every campaign counts: rotating the campaign never renews a run.
        if _over(run_charged, ceiling, wanted):
            raise _Refused(errors.RUN_BUDGET_EXHAUSTED)

        pk = await conn.fetchval(
            """INSERT INTO public.ai_providerreservation
                   (campaign_id, lane, account, operation, model, run_key, work_key, state,
                    created_at, lease_expires_at, sent, usage_reported,
                    reserved_input_tokens, reserved_output_tokens, reserved_cost_micros,
                    reserved_active_ms, charge_input_tokens, charge_output_tokens,
                    charge_cost_micros, charge_active_ms, charge_attempts,
                    owner, purpose, purpose_version)
               VALUES ($1, $2, $3, $4, $5, $6, $6, 'open', $7, $8, false, false,
                       $9, $10, $11, $12, $9, $10, $11, $12, 1, $13, $14, $15)
               RETURNING id""",
            campaign["id"], request.lane, account, request.operation[:16],
            request.models[0][:128], binding.key, now, now + lease,
            wanted["input_tokens"], wanted["output_tokens"], wanted["cost_micros"], active_ms,
            OWNER, request.purpose[:32], request.purpose_version[:64],
        )
        await conn.execute(
            """UPDATE public.ai_providercampaign
                  SET charged_attempts = charged_attempts + 1,
                      charged_input_tokens = charged_input_tokens + $2,
                      charged_output_tokens = charged_output_tokens + $3,
                      charged_cost_micros = charged_cost_micros + $4,
                      charged_active_ms = charged_active_ms + $5
                WHERE id = $1""",
            campaign["id"], wanted["input_tokens"], wanted["output_tokens"],
            wanted["cost_micros"], active_ms,
        )
        return pk, campaign["id"], timeout

    async def _work(self, conn, binding):
        return await conn.fetchrow(
            "SELECT state, fence, allowance, deadline_at FROM iris_ai.ask_run WHERE id = $1",
            binding.run_id,
        )

    @staticmethod
    async def _locked_campaign(conn, key: str):
        select = "SELECT * FROM public.ai_providercampaign WHERE key = $1 FOR UPDATE"
        campaign = await conn.fetchrow(select, key)
        if campaign is None:
            # Two processes may both find it missing; one insert wins, neither fails.
            await conn.execute(
                """INSERT INTO public.ai_providercampaign
                       (key, created_at, charged_attempts, charged_input_tokens,
                        charged_output_tokens, charged_cost_micros, charged_active_ms)
                   VALUES ($1, now(), 0, 0, 0, 0, 0) ON CONFLICT (key) DO NOTHING""",
                key,
            )
            campaign = await conn.fetchrow(select, key)
        return campaign


class Ticket:
    """One admitted attempt: send within `timeout_seconds`, settle once."""

    def __init__(self, ledger: Ledger, pk: int, campaign_id: int, request: Request, timeout: float):
        self._ledger = ledger
        self.pk = pk
        self._campaign_id = campaign_id
        self._request = request
        #: What remains of the run's deadline; the attempt may not outlive it.
        self.timeout_seconds = timeout
        self._settled = False

    async def settle(self, usage: Usage) -> None:
        """Replace the reservation with what is known. Idempotent."""
        if self._settled:
            return
        self._settled = True
        try:
            conn = await self._ledger._connect()
            try:
                async with conn.transaction():
                    await self._settle(conn, usage)
            finally:
                await conn.close()
        except _STORE_ERRORS:
            log.exception("could not settle reservation %s; it stays charged at its reservation", self.pk)

    async def _settle(self, conn, usage: Usage) -> None:
        limits = self._ledger.limits
        # Campaign, then reservation: the order `admit` takes them in.
        await conn.execute("SELECT 1 FROM public.ai_providercampaign WHERE id = $1 FOR UPDATE",
                           self._campaign_id)
        reservation = await conn.fetchrow(
            """SELECT * FROM public.ai_providerreservation
                WHERE id = $1 AND owner = $2 FOR UPDATE""", self.pk, OWNER,
        )
        if reservation is None or reservation["state"] in ("settled", "released"):
            return
        now = await conn.fetchval("SELECT clock_timestamp()")
        if not usage.sent:
            charge = dict.fromkeys((*_CHARGE, "active_ms"), 0)
            state = "released"
        else:
            input_tokens = (reservation["reserved_input_tokens"] if usage.input_tokens is None
                            else usage.input_tokens)
            output_tokens = (reservation["reserved_output_tokens"] if usage.output_tokens is None
                             else usage.output_tokens)
            models = (usage.model,) if usage.model in limits.prices else self._request.models
            cost = _worst_cost(limits, models, input_tokens, output_tokens)
            charge = {
                "attempts": 1, "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_micros": reservation["reserved_cost_micros"] if cost is None else cost,
                "active_ms": _ms(now - reservation["created_at"]),
            }
            state = "settled"
        delta = {name: charge[name] - reservation[f"charge_{name}"] for name in charge}
        await conn.execute(
            """UPDATE public.ai_providerreservation
                  SET state = $2, settled_at = $3, sent = $4, usage_reported = $5,
                      charge_attempts = $6, charge_input_tokens = $7, charge_output_tokens = $8,
                      charge_cost_micros = $9, charge_active_ms = $10, cached_input_tokens = $11
                WHERE id = $1""",
            self.pk, state, now, usage.sent, usage.sent and usage.reported,
            charge["attempts"], charge["input_tokens"], charge["output_tokens"],
            charge["cost_micros"], charge["active_ms"], usage.cached_input_tokens if usage.sent else None,
        )
        await conn.execute(
            """UPDATE public.ai_providercampaign
                  SET charged_attempts = charged_attempts + $2,
                      charged_input_tokens = charged_input_tokens + $3,
                      charged_output_tokens = charged_output_tokens + $4,
                      charged_cost_micros = charged_cost_micros + $5,
                      charged_active_ms = charged_active_ms + $6
                WHERE id = $1""",
            self._campaign_id, delta["attempts"], delta["input_tokens"], delta["output_tokens"],
            delta["cost_micros"], delta["active_ms"],
        )
