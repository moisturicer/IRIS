"""
Scheduled erasure of old personal data (ADR-051 decision 19, IR-794).

One daily beat task calls `run_retention`. Each kind of data registers itself
here with a `RetentionType`, so a later type (comment text, comment reports,
per-account view records) is one registration beside its own model and needs no
new job.

The period for each type is a `SystemSetting` of whole days, set by the System
Admin alone (IR-667) once the data protection officer approves it. **A blank
period erases nothing, and no default period exists in this module or anywhere
in code.** A value that is not a positive whole number is treated like a blank
one, because guessing what was meant could erase data nobody approved erasing.

`AuditEvent` rows are never touched: they are insert-only at the database
(IR-166), and no type may register them. The run's own event carries counts per
type and nothing about a person.

Safe to repeat and to interrupt: an eraser blanks only what is still set, so a
second run finds nothing, and the whole run is one transaction, so an
interrupted one erases nothing and the next run does it again.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from django.db import transaction
from django.utils import timezone

from .models import AuditEvent
from .services import create_audit_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionType:
    """
    One kind of personal data with a retention period.

    `key` names the type in the audit event's counts. `setting_key` is the
    `SystemSetting` holding its period in days. `erase(cutoff)` removes or blanks
    everything of this type older than `cutoff` and returns how many rows it
    changed; it must change nothing it has already changed.
    """

    key: str
    setting_key: str
    erase: Callable[[datetime], int]


_REGISTRY: dict[str, RetentionType] = {}


def register(retention_type: RetentionType) -> None:
    """Register a type. Registering the same type again is a no-op; a clash is a bug."""
    existing = _REGISTRY.get(retention_type.key)
    if existing is not None and existing != retention_type:
        raise ValueError(f"Retention type {retention_type.key!r} is already registered.")
    if any(t.setting_key == retention_type.setting_key and t.key != retention_type.key
           for t in _REGISTRY.values()):
        raise ValueError(f"Setting {retention_type.setting_key!r} already holds another type's period.")
    _REGISTRY[retention_type.key] = retention_type


def registered_types() -> list[RetentionType]:
    return sorted(_REGISTRY.values(), key=lambda t: t.key)


def setting_keys() -> set[str]:
    return {t.setting_key for t in _REGISTRY.values()}


def parse_period(value: str | None) -> int | None:
    """Whole days from a setting's text, or None when it is blank or not a positive whole number."""
    text = (value or "").strip()
    if not text:
        return None
    if not (text.isascii() and text.isdigit()):
        return None
    days = int(text)
    return days if days > 0 else None


def period_error(value: str) -> str | None:
    """Why `value` is not a valid period, or None. Blank is valid: it means nothing is erased."""
    if not value.strip():
        return None
    if parse_period(value) is None:
        return "Enter a whole number of days, or leave it blank to erase nothing."
    return None


def run_retention(now: datetime | None = None) -> dict[str, int]:
    """
    Erase what is past its period, for every registered type, and write one audit event.

    Returns the counts per type. `now` exists so a test can freeze the clock.
    """
    from apps.accounts.models import SystemSetting

    now = now or timezone.now()
    periods = dict(
        SystemSetting.objects.filter(key__in=setting_keys()).values_list("key", "value")
    )
    counts: dict[str, int] = {}
    with transaction.atomic():
        for retention_type in registered_types():
            raw = periods.get(retention_type.setting_key)
            days = parse_period(raw)
            if days is None:
                if (raw or "").strip():
                    logger.warning(
                        "Retention period %s is not a positive whole number of days; "
                        "erasing nothing of type %s.", retention_type.setting_key, retention_type.key,
                    )
                counts[retention_type.key] = 0
                continue
            counts[retention_type.key] = retention_type.erase(now - timedelta(days=days))
        create_audit_event(
            AuditEvent.RETENTION_CLEANUP_RUN, None, metadata={"counts": counts},
        )
    return counts
