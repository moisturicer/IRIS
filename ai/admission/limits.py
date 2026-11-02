"""The shared admission limits, read fail-closed (IR-725).

The same `AI_ADMISSION_*` names and meanings as Django's (IR-545), so both
runtimes spend one campaign. A run's own ceiling is its persisted AskRun
allowance, not `AI_ADMISSION_RUN_*`. Nothing here is a production value.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Mapping

REQUIRED = (
    "AI_ADMISSION_CAMPAIGN",
    "AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS",
    "AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS",
    "AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS",
    "AI_ADMISSION_CAMPAIGN_MAX_COST_USD",
    "AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES",
    "AI_ADMISSION_RESERVE_FRACTION",
    "AI_ADMISSION_LANE_CONCURRENCY",
    "AI_ADMISSION_ACCOUNT_CONCURRENCY",
    "AI_ADMISSION_PRICES",
    "AI_ADMISSION_MAX_OUTPUT_TOKENS",
)


class NotConfigured(Exception):
    """A limit is unset or malformed; the message names it."""


@dataclass(frozen=True)
class Ceiling:
    attempts: int
    input_tokens: int
    output_tokens: int
    cost_micros: int
    active_ms: int | None = None

    def scaled(self, fraction: float) -> "Ceiling":
        return Ceiling(*(None if v is None else math.floor(v * fraction) for v in (
            self.attempts, self.input_tokens, self.output_tokens, self.cost_micros, self.active_ms)))

    @classmethod
    def of_allowance(cls, allowance: Mapping) -> "Ceiling":
        """An AskRun's persisted allowance (IR-722)."""
        return cls(
            attempts=int(allowance["max_attempts"]),
            input_tokens=int(allowance["max_input_tokens"]),
            output_tokens=int(allowance["max_output_tokens"]),
            cost_micros=micros(float(allowance["max_cost_usd"])),
        )


@dataclass(frozen=True)
class Price:
    """US$ per million tokens, so micro-dollars per token."""

    input: float
    output: float


@dataclass(frozen=True)
class Limits:
    campaign_key: str
    campaign: Ceiling
    reserve_fraction: float
    reserve_released: bool
    lanes: Mapping[str, int]
    account_concurrency: int
    prices: Mapping[str, Price]
    max_output_tokens: int
    lease_grace_seconds: float

    @property
    def spendable(self) -> Ceiling:
        """The campaign less its protected reserve, unless that is released."""
        return self.campaign if self.reserve_released else self.campaign.scaled(1 - self.reserve_fraction)


def micros(usd: float) -> int:
    return math.floor(usd * 1_000_000)


def _raw(values, name) -> str:
    value = getattr(values, name, None)
    return "" if value is None else str(value).strip()


def _positive(values, name, cast=int):
    raw = _raw(values, name)
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        raise NotConfigured(f"{name} must be a number") from None
    if not math.isfinite(value) or value <= 0:
        raise NotConfigured(f"{name} must be positive")
    return value


def _mapping(values, name) -> dict:
    try:
        value = json.loads(_raw(values, name))
    except ValueError:
        raise NotConfigured(f"{name} must be a JSON object") from None
    if not isinstance(value, dict) or not value:
        raise NotConfigured(f"{name} must be a non-empty JSON object")
    return value


def _lanes(values) -> dict[str, int]:
    lanes = {}
    for lane, count in _mapping(values, "AI_ADMISSION_LANE_CONCURRENCY").items():
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise NotConfigured(f"AI_ADMISSION_LANE_CONCURRENCY[{lane!r}] must be a positive integer")
        lanes[str(lane)] = count
    return lanes


def _prices(values) -> dict[str, Price]:
    prices = {}
    for model, entry in _mapping(values, "AI_ADMISSION_PRICES").items():
        try:
            price = Price(input=float(entry["input"]), output=float(entry["output"]))
        except (KeyError, TypeError, ValueError):
            raise NotConfigured(f"AI_ADMISSION_PRICES[{model!r}] is malformed") from None
        if not (math.isfinite(price.input) and math.isfinite(price.output)) or min(
                price.input, price.output) < 0:
            raise NotConfigured(f"AI_ADMISSION_PRICES[{model!r}] must not be negative")
        prices[str(model)] = price
    return prices


def read(values) -> Limits:
    """Every limit, or `NotConfigured` naming the unset ones."""
    missing = [name for name in REQUIRED if not _raw(values, name)]
    if missing:
        raise NotConfigured(", ".join(missing))
    key = _raw(values, "AI_ADMISSION_CAMPAIGN")
    if len(key) > 64:
        raise NotConfigured("AI_ADMISSION_CAMPAIGN is at most 64 characters")
    fraction = _positive(values, "AI_ADMISSION_RESERVE_FRACTION", float)
    if fraction >= 1:
        raise NotConfigured("AI_ADMISSION_RESERVE_FRACTION must be below 1")
    grace = _raw(values, "AI_ADMISSION_LEASE_GRACE_SECONDS")
    try:
        grace_seconds = max(0.0, float(grace)) if grace else 15.0
    except ValueError:
        raise NotConfigured("AI_ADMISSION_LEASE_GRACE_SECONDS must be a number") from None
    if not math.isfinite(grace_seconds):
        raise NotConfigured("AI_ADMISSION_LEASE_GRACE_SECONDS must be finite")
    return Limits(
        campaign_key=key,
        campaign=Ceiling(
            attempts=_positive(values, "AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS"),
            input_tokens=_positive(values, "AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS"),
            output_tokens=_positive(values, "AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS"),
            cost_micros=micros(_positive(values, "AI_ADMISSION_CAMPAIGN_MAX_COST_USD", float)),
            active_ms=math.floor(_positive(values, "AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES", float) * 60_000),
        ),
        reserve_fraction=fraction,
        reserve_released=_raw(values, "AI_ADMISSION_RESERVE_RELEASED").lower() in ("1", "true", "yes"),
        lanes=_lanes(values),
        account_concurrency=_positive(values, "AI_ADMISSION_ACCOUNT_CONCURRENCY"),
        prices=_prices(values),
        max_output_tokens=_positive(values, "AI_ADMISSION_MAX_OUTPUT_TOKENS"),
        lease_grace_seconds=grace_seconds,
    )
