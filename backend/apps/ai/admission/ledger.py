"""Reserve before sending, settle after (IR-545, ADR-041).

**Atomic across processes.** `admit` locks the campaign row ``FOR UPDATE`` on
the `admission` connection, then checks and writes in one transaction. Two
web processes, two Celery workers or two replicas reach the same row, so they
take turns; none can read "one attempt left" while another is spending it.
The connection is its own, so a reservation commits when `admit` returns even
if the caller is inside a transaction of its own.

**Worst case first.** A reservation holds, before anything is sent:

* the attempt itself;
* input tokens bounded from above -- no tokenizer emits more tokens than the
  text has UTF-8 bytes, so bytes plus a per-text overhead is safe for every
  model, whatever its tokenizer;
* the completion cap the request carries (an attempt with no cap is refused);
* the cost of those tokens at the *highest* price among the models that may
  answer it -- a vendor that resolves a fallback list itself may bill any of
  them;
* active time: the attempt's own timeout plus a grace period, which is also
  its lease.

**Settled to what the vendor reported.** Whatever the vendor did not report
stays charged at its reservation: unknown usage is conservative, never zero.
An attempt that failed before its request was sent is released.

**Leases.** An open reservation holds a concurrency slot until settled or
until its lease ends. A lease is never shorter than the attempt's own
timeout, so the slot cannot be handed on while the request may still be
talking to the vendor; a stream renews its lease as it reads, and a stream
whose renewal is refused stops. A reservation whose lease ran out unsettled
-- its worker died -- is marked abandoned at the next admission and keeps its
reserved charge.

**Store failure denies.** A database error while admitting refuses the
attempt. A database error while settling leaves the reservation open, so it
is later abandoned at its reserved, larger, charge.
"""

from __future__ import annotations

import hashlib
import logging
import math
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Iterator, Optional, Sequence

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections, transaction
from django.db.models import F, Sum
from django.db.models.functions import Coalesce

from apps.ai.models.admission import (
    ABANDONED,
    OPEN,
    RELEASED,
    SETTLED,
    ProviderCampaign,
    ProviderReservation,
)

from . import errors, scope
from .limits import Limits, NotConfigured, enforcing, read_limits

logger = logging.getLogger(__name__)

ALIAS = "admission"

#: Added per text to its byte count: role markers and message framing.
_PER_TEXT_OVERHEAD = 8


@dataclass(frozen=True)
class Request:
    """One physical attempt, described before it is sent."""

    operation: str
    #: The lane when no workload names one.
    default_lane: str
    account: str
    #: The model asked for, then every model the vendor may answer with.
    models: tuple[str, ...]
    input_tokens: int
    #: The completion cap sent with the request; ``None`` if it has none.
    output_tokens: Optional[int]
    timeout_seconds: float


def account_for(key: str) -> str:
    """A digest naming the vendor account a credential spends. Never the key
    itself. The key alone, not the endpoint: one key used through two
    endpoints (chat and decisions, or a base URL with and without a trailing
    slash) is one account, with one limit."""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:32]


def estimate_tokens(*texts: str) -> int:
    """An upper bound on the tokens in ``texts`` (see the module docstring)."""
    return sum(len(text.encode("utf-8")) + _PER_TEXT_OVERHEAD for text in texts)


def _worst_cost(limits: Limits, models: Sequence[str], input_tokens: int, output_tokens: int):
    prices = [limits.prices.get(model) for model in models]
    if not prices or any(price is None for price in prices):
        return None
    return math.ceil(
        input_tokens * max(p.input for p in prices) + output_tokens * max(p.output for p in prices)
    )


def _ms(delta: timedelta) -> int:
    return max(0, math.ceil(delta.total_seconds() * 1000))


def _db_now():
    """The database's clock, so every replica reads leases against one time."""
    with connections[ALIAS].cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        return cursor.fetchone()[0]


class _Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _deny(reason: str, lane: str = "") -> errors.AdmissionDenied:
    scope.note_denial(reason)
    logger.info("provider admission refused: %s (lane %s)", reason, lane or "-")
    return errors.AdmissionDenied(reason)


def _locked_campaign(key: str) -> ProviderCampaign:
    manager = ProviderCampaign.objects.using(ALIAS)
    campaign = manager.select_for_update().filter(key=key).first()
    if campaign is None:
        # Two processes may both find it missing; one insert wins, neither fails.
        manager.bulk_create([ProviderCampaign(key=key)], ignore_conflicts=True)
        campaign = manager.select_for_update().get(key=key)
    return campaign


def _charged(queryset) -> dict:
    return queryset.aggregate(
        attempts=Coalesce(Sum("charge_attempts"), 0),
        input_tokens=Coalesce(Sum("charge_input_tokens"), 0),
        output_tokens=Coalesce(Sum("charge_output_tokens"), 0),
        cost_micros=Coalesce(Sum("charge_cost_micros"), 0),
    )


def _over(charged: dict, ceiling, wanted: dict) -> bool:
    return any(
        charged[name] + wanted[name] > getattr(ceiling, name)
        for name in wanted
        if getattr(ceiling, name) is not None
    )


def admit(request: Request) -> "Ticket":
    """Reserve ``request``'s worst case, or raise `AdmissionDenied`."""
    lane = scope.lane_for(request.default_lane)
    run = scope.current_run()
    if run is not None and errors.RUN_CANCELLED not in run.denials and run.halted():
        raise _deny(errors.RUN_CANCELLED, lane)
    if run is not None:
        sticky = next((reason for reason in run.denials if reason in errors.STICKY), None)
        if sticky is not None:
            # The run already learned this cannot succeed: stop new work.
            raise errors.AdmissionDenied(sticky)
    try:
        limits = read_limits()
    except (NotConfigured, ImproperlyConfigured):
        raise _deny(errors.NOT_CONFIGURED, lane) from None
    if request.output_tokens is None:
        raise _deny(errors.UNBOUNDED_OUTPUT, lane)
    cost = _worst_cost(limits, request.models, request.input_tokens, request.output_tokens)
    if cost is None:
        raise _deny(errors.UNPRICED_MODEL, lane)
    lease = timedelta(seconds=max(0.0, request.timeout_seconds) + limits.lease_grace_seconds)
    wanted = {
        "attempts": 1,
        "input_tokens": request.input_tokens,
        "output_tokens": request.output_tokens,
        "cost_micros": cost,
    }
    try:
        with transaction.atomic(using=ALIAS):
            pk, campaign_id = _reserve(limits, request, lane, run, wanted, lease)
    except _Refused as refused:
        raise _deny(refused.reason, lane) from None
    except DatabaseError:
        logger.exception("provider admission store unavailable")
        raise _deny(errors.STORE_UNAVAILABLE, lane) from None
    return Ticket(pk, campaign_id, limits, request, lease)


def _reserve(limits, request, lane, run, wanted, lease) -> tuple[int, int]:
    campaign = _locked_campaign(limits.campaign_key)
    now = _db_now()
    reservations = ProviderReservation.objects.using(ALIAS).filter(campaign=campaign)
    reservations.filter(state=OPEN, lease_expires_at__lt=now).update(state=ABANDONED)

    lane_limit = limits.lanes.get(lane)
    if lane_limit is None:
        raise _Refused(errors.LANE_NOT_CONFIGURED)
    in_flight = reservations.filter(state=OPEN)
    if in_flight.filter(lane=lane).count() >= lane_limit:
        raise _Refused(errors.LANE_BUSY)
    if in_flight.filter(account=request.account).count() >= limits.account_concurrency:
        raise _Refused(errors.ACCOUNT_BUSY)

    active_ms = _ms(lease)
    charged = {
        "attempts": campaign.charged_attempts,
        "input_tokens": campaign.charged_input_tokens,
        "output_tokens": campaign.charged_output_tokens,
        "cost_micros": campaign.charged_cost_micros,
        "active_ms": campaign.charged_active_ms,
    }
    if _over(charged, limits.spendable, {**wanted, "active_ms": active_ms}):
        raise _Refused(errors.CAMPAIGN_EXHAUSTED)
    if run is not None and _over(
        _charged(reservations.filter(run_key=run.key)), run.ceiling or limits.run, wanted,
    ):
        raise _Refused(errors.RUN_BUDGET_EXHAUSTED)

    reservation = ProviderReservation.objects.using(ALIAS).create(
        campaign=campaign,
        lane=lane,
        account=request.account,
        operation=request.operation,
        model=request.models[0][:128],
        run_key="" if run is None else run.key[:64],
        work_key=(scope.current_work_item() or ("" if run is None else run.key))[:64],
        created_at=now,
        lease_expires_at=now + lease,
        reserved_input_tokens=wanted["input_tokens"],
        reserved_output_tokens=wanted["output_tokens"],
        reserved_cost_micros=wanted["cost_micros"],
        reserved_active_ms=active_ms,
        charge_input_tokens=wanted["input_tokens"],
        charge_output_tokens=wanted["output_tokens"],
        charge_cost_micros=wanted["cost_micros"],
        charge_active_ms=active_ms,
    )
    ProviderCampaign.objects.using(ALIAS).filter(pk=campaign.pk).update(
        charged_attempts=F("charged_attempts") + 1,
        charged_input_tokens=F("charged_input_tokens") + wanted["input_tokens"],
        charged_output_tokens=F("charged_output_tokens") + wanted["output_tokens"],
        charged_cost_micros=F("charged_cost_micros") + wanted["cost_micros"],
        charged_active_ms=F("charged_active_ms") + active_ms,
    )
    return reservation.pk, campaign.pk


class Ticket:
    """One admitted attempt: renew its lease while it runs, settle it once."""

    def __init__(
        self, pk: int, campaign_id: int, limits: Limits, request: Request, lease: timedelta
    ) -> None:
        self.pk = pk
        self._campaign_id = campaign_id
        self._limits = limits
        self._request = request
        self._lease = lease
        self._settled = False

    @property
    def lease_seconds(self) -> float:
        return self._lease.total_seconds()

    @property
    def grace_seconds(self) -> float:
        return self._limits.lease_grace_seconds

    def _lock(self) -> ProviderReservation:
        """The campaign row, then this reservation: the order `admit` takes
        them in. Taking them the other way round deadlocks against it."""
        ProviderCampaign.objects.using(ALIAS).select_for_update().get(pk=self._campaign_id)
        return ProviderReservation.objects.using(ALIAS).select_for_update().get(pk=self.pk)

    def renew(self) -> None:
        """Extend the lease from now, or raise `AdmissionLost` when it already
        ran out -- someone else may hold the slot, so the attempt must stop."""
        try:
            with transaction.atomic(using=ALIAS):
                reservation = self._lock()
                now = _db_now()
                if reservation.state != OPEN or reservation.lease_expires_at < now:
                    raise _Refused(errors.LEASE_LOST)
                expires = now + self._lease
                extra = _ms(expires - reservation.lease_expires_at)
                ProviderReservation.objects.using(ALIAS).filter(pk=self.pk).update(
                    lease_expires_at=expires,
                    reserved_active_ms=F("reserved_active_ms") + extra,
                    charge_active_ms=F("charge_active_ms") + extra,
                )
                ProviderCampaign.objects.using(ALIAS).filter(pk=reservation.campaign_id).update(
                    charged_active_ms=F("charged_active_ms") + extra,
                )
        except _Refused:
            scope.note_denial(errors.LEASE_LOST)
            raise errors.AdmissionLost() from None
        except DatabaseError:
            # Without a renewal the lease runs out under a live stream.
            logger.exception("provider admission store unavailable on renewal")
            scope.note_denial(errors.STORE_UNAVAILABLE)
            raise errors.AdmissionDenied(errors.STORE_UNAVAILABLE) from None

    def settle(self, usage: scope.AttemptUsage) -> None:
        """Replace the reservation with what is known. Idempotent."""
        if self._settled:
            return
        self._settled = True
        try:
            with transaction.atomic(using=ALIAS):
                self._settle(usage)
        except DatabaseError:
            logger.exception(
                "provider admission could not settle reservation %s; it stays charged "
                "at its reservation and is abandoned when its lease ends", self.pk,
            )

    def _settle(self, usage: scope.AttemptUsage) -> None:
        reservation = self._lock()
        if reservation.state in (SETTLED, RELEASED):
            return
        now = _db_now()
        if not usage.sent:
            charge = {"attempts": 0, "input_tokens": 0, "output_tokens": 0, "cost_micros": 0,
                      "active_ms": 0}
            state = RELEASED
        else:
            input_tokens = (
                reservation.reserved_input_tokens if usage.input_tokens is None else usage.input_tokens
            )
            output_tokens = (
                reservation.reserved_output_tokens if usage.output_tokens is None else usage.output_tokens
            )
            models = (usage.model,) if usage.model in self._limits.prices else self._request.models
            cost = _worst_cost(self._limits, models, input_tokens, output_tokens)
            if usage.cost_usd is not None and usage.reported:
                cost = math.ceil(usage.cost_usd * 1_000_000)
            charge = {
                "attempts": 1,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_micros": reservation.reserved_cost_micros if cost is None else cost,
                "active_ms": _ms(now - reservation.created_at),
            }
            state = SETTLED
        deltas = {
            "attempts": charge["attempts"] - reservation.charge_attempts,
            "input_tokens": charge["input_tokens"] - reservation.charge_input_tokens,
            "output_tokens": charge["output_tokens"] - reservation.charge_output_tokens,
            "cost_micros": charge["cost_micros"] - reservation.charge_cost_micros,
            "active_ms": charge["active_ms"] - reservation.charge_active_ms,
        }
        ProviderReservation.objects.using(ALIAS).filter(pk=self.pk).update(
            state=state,
            settled_at=now,
            sent=usage.sent,
            usage_reported=usage.sent and usage.reported,
            charge_attempts=charge["attempts"],
            charge_input_tokens=charge["input_tokens"],
            charge_output_tokens=charge["output_tokens"],
            charge_cost_micros=charge["cost_micros"],
            charge_active_ms=charge["active_ms"],
        )
        ProviderCampaign.objects.using(ALIAS).filter(pk=reservation.campaign_id).update(
            charged_attempts=F("charged_attempts") + deltas["attempts"],
            charged_input_tokens=F("charged_input_tokens") + deltas["input_tokens"],
            charged_output_tokens=F("charged_output_tokens") + deltas["output_tokens"],
            charged_cost_micros=F("charged_cost_micros") + deltas["cost_micros"],
            charged_active_ms=F("charged_active_ms") + deltas["active_ms"],
        )


@contextmanager
def provider_attempt(describe: Callable[[], Request]) -> Iterator[Optional[Ticket]]:
    """Admit one physical attempt around the block that makes it, then settle.

    ``describe`` builds the `Request`; it is not called with admission off, so
    the default path pays nothing for it. The block calls `scope.mark_sent`
    just before sending and `scope.report_usage` with what came back.
    """
    if not enforcing():
        yield None
        return
    ticket = admit(describe())
    usage = scope.AttemptUsage()
    try:
        with scope.attempt_usage(usage):
            yield ticket
    finally:
        ticket.settle(usage)
