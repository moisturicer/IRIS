"""The admission settings, read and checked (IR-545, ADR-041).

**Fail closed.** No limit has a default. With `AI_PROVIDER_ADMISSION=enforce`
and any limit unset, `read_limits()` raises `NotConfigured` and every paid
attempt is refused. A *malformed* value is different: it stops Django at
startup (`verify_admission_configuration`), because it is a typo rather than
a decision nobody has made yet.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Mapping, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

OFF = "off"
ENFORCE = "enforce"
MODES = (OFF, ENFORCE)

#: Every limit setting, in the order an operator would fill them in.
CAMPAIGN_SETTINGS = (
    "AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS",
    "AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS",
    "AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS",
    "AI_ADMISSION_CAMPAIGN_MAX_COST_USD",
    "AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES",
)
RUN_SETTINGS = (
    "AI_ADMISSION_RUN_MAX_ATTEMPTS",
    "AI_ADMISSION_RUN_MAX_INPUT_TOKENS",
    "AI_ADMISSION_RUN_MAX_OUTPUT_TOKENS",
    "AI_ADMISSION_RUN_MAX_COST_USD",
)
REQUIRED_SETTINGS = (
    "AI_ADMISSION_CAMPAIGN",
    *CAMPAIGN_SETTINGS,
    "AI_ADMISSION_RESERVE_FRACTION",
    *RUN_SETTINGS,
    "AI_ADMISSION_LANE_CONCURRENCY",
    "AI_ADMISSION_ACCOUNT_CONCURRENCY",
    "AI_ADMISSION_PRICES",
    "AI_ADMISSION_MAX_OUTPUT_TOKENS",
    "AI_ADMISSION_QUEUE_DEPTH",
    "AI_ADMISSION_QUEUE_PER_USER",
)


class NotConfigured(Exception):
    """At least one limit is unset. The message names them."""


@dataclass(frozen=True)
class Ceiling:
    """Totals one scope may be charged. ``active_ms`` is campaign-only."""

    attempts: int
    input_tokens: int
    output_tokens: int
    cost_micros: int
    active_ms: Optional[int] = None

    def scaled(self, fraction: float) -> "Ceiling":
        """The share of this ceiling spendable before the reserve, rounded down."""
        return Ceiling(
            attempts=math.floor(self.attempts * fraction),
            input_tokens=math.floor(self.input_tokens * fraction),
            output_tokens=math.floor(self.output_tokens * fraction),
            cost_micros=math.floor(self.cost_micros * fraction),
            active_ms=None if self.active_ms is None else math.floor(self.active_ms * fraction),
        )


@dataclass(frozen=True)
class Price:
    """US$ per million tokens -- numerically, micro-dollars per token."""

    input: float
    output: float


@dataclass(frozen=True)
class Limits:
    campaign_key: str
    campaign: Ceiling
    reserve_fraction: float
    reserve_released: bool
    run: Ceiling
    lanes: Mapping[str, int]
    account_concurrency: int
    prices: Mapping[str, Price]
    max_output_tokens: int
    queue_depth: int
    queue_per_user: int
    lease_grace_seconds: float

    @property
    def spendable(self) -> Ceiling:
        """The campaign less its protected reserve, unless that is released."""
        if self.reserve_released:
            return self.campaign
        return self.campaign.scaled(1 - self.reserve_fraction)


def mode() -> str:
    return str(getattr(settings, "AI_PROVIDER_ADMISSION", OFF)).strip().lower() or OFF


def enforcing() -> bool:
    return mode() == ENFORCE


def _raw(name: str) -> str:
    value = getattr(settings, name, "")
    return "" if value is None else str(value).strip()


def _positive(name: str, cast=int):
    raw = _raw(name)
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        raise ImproperlyConfigured(f"{name} must be a number, not {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ImproperlyConfigured(f"{name} must be positive, not {raw!r}")
    return value


def _mapping(name: str) -> dict:
    raw = _raw(name)
    try:
        value = json.loads(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a JSON object") from None
    if not isinstance(value, dict) or not value:
        raise ImproperlyConfigured(f"{name} must be a non-empty JSON object")
    return value


def _lanes() -> dict[str, int]:
    lanes = {}
    for lane, count in _mapping("AI_ADMISSION_LANE_CONCURRENCY").items():
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ImproperlyConfigured(
                f"AI_ADMISSION_LANE_CONCURRENCY[{lane!r}] must be a positive integer"
            )
        lanes[str(lane)] = count
    return lanes


def _prices() -> dict[str, Price]:
    prices = {}
    for model, entry in _mapping("AI_ADMISSION_PRICES").items():
        try:
            price = Price(input=float(entry["input"]), output=float(entry["output"]))
        except (KeyError, TypeError, ValueError):
            raise ImproperlyConfigured(
                f"AI_ADMISSION_PRICES[{model!r}] must be {{\"input\": n, \"output\": n}}"
            ) from None
        if not (math.isfinite(price.input) and math.isfinite(price.output)) or min(
            price.input, price.output
        ) < 0:
            raise ImproperlyConfigured(f"AI_ADMISSION_PRICES[{model!r}] must not be negative")
        prices[str(model)] = price
    return prices


def _micros(usd: float) -> int:
    return math.floor(usd * 1_000_000)


def read_limits() -> Limits:
    """Every limit, or `NotConfigured` naming the unset ones."""
    missing = [name for name in REQUIRED_SETTINGS if not _raw(name)]
    if missing:
        raise NotConfigured(", ".join(missing))
    fraction = _positive("AI_ADMISSION_RESERVE_FRACTION", float)
    if fraction >= 1:
        raise ImproperlyConfigured("AI_ADMISSION_RESERVE_FRACTION must be below 1")
    return Limits(
        campaign_key=_raw("AI_ADMISSION_CAMPAIGN"),
        campaign=Ceiling(
            attempts=_positive("AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS"),
            input_tokens=_positive("AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS"),
            output_tokens=_positive("AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS"),
            cost_micros=_micros(_positive("AI_ADMISSION_CAMPAIGN_MAX_COST_USD", float)),
            active_ms=math.floor(
                _positive("AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES", float) * 60_000
            ),
        ),
        reserve_fraction=fraction,
        reserve_released=bool(getattr(settings, "AI_ADMISSION_RESERVE_RELEASED", False)),
        run=Ceiling(
            attempts=_positive("AI_ADMISSION_RUN_MAX_ATTEMPTS"),
            input_tokens=_positive("AI_ADMISSION_RUN_MAX_INPUT_TOKENS"),
            output_tokens=_positive("AI_ADMISSION_RUN_MAX_OUTPUT_TOKENS"),
            cost_micros=_micros(_positive("AI_ADMISSION_RUN_MAX_COST_USD", float)),
        ),
        lanes=_lanes(),
        account_concurrency=_positive("AI_ADMISSION_ACCOUNT_CONCURRENCY"),
        prices=_prices(),
        max_output_tokens=_positive("AI_ADMISSION_MAX_OUTPUT_TOKENS"),
        queue_depth=_positive("AI_ADMISSION_QUEUE_DEPTH"),
        queue_per_user=_positive("AI_ADMISSION_QUEUE_PER_USER"),
        lease_grace_seconds=max(0.0, float(getattr(settings, "AI_ADMISSION_LEASE_GRACE_SECONDS", 15.0))),
    )


def output_cap() -> Optional[int]:
    """The per-call completion cap to send under enforcement, if it is set
    and well-formed; ``None`` otherwise, which admission then refuses."""
    if not enforcing() or not _raw("AI_ADMISSION_MAX_OUTPUT_TOKENS"):
        return None
    try:
        return _positive("AI_ADMISSION_MAX_OUTPUT_TOKENS")
    except ImproperlyConfigured:
        return None


def verify_admission_configuration() -> None:
    """Startup check, from `AiConfig.ready()`.

    Refuses an unknown mode, a malformed limit under `enforce`, and a queued
    Ask IRIS (`AI_DURABLE_ASK`) without enforcement: the pilot README §6 gates
    concurrent runs on shared quotas, and this is where that gate is held.
    Unset limits are *not* a startup error -- they refuse paid work instead.
    """
    if mode() not in MODES:
        raise ImproperlyConfigured(
            f"AI_PROVIDER_ADMISSION must be one of {', '.join(MODES)}, not {mode()!r}"
        )
    if getattr(settings, "AI_DURABLE_ASK", False) and not enforcing():
        raise ImproperlyConfigured(
            "AI_DURABLE_ASK needs AI_PROVIDER_ADMISSION=enforce: queued questions "
            "run concurrently, and their provider attempts must be admitted against "
            "shared limits (IR-545, ADR-041)."
        )
    if enforcing():
        try:
            read_limits()
        except NotConfigured:
            pass
