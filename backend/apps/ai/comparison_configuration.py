"""Opt-in comparison controls; spending ceilings must be explicitly configured."""
import math

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.ai.admission.limits import Ceiling, NotConfigured, enforcing


def verify_comparison_configuration():
    if settings.AI_COMPARISON_MAX_RECORDS < 2:
        raise ImproperlyConfigured("AI_COMPARISON_MAX_RECORDS must be at least 2")
    if settings.AI_COMPARISON_DEADLINE_SECONDS <= 0:
        raise ImproperlyConfigured("AI_COMPARISON_DEADLINE_SECONDS must be positive")
    if settings.AI_COMPARISON_ENABLED and not (
        settings.AI_DURABLE_ASK and settings.AI_PAPER_BRIEFS_ENABLED
        and settings.AI_RESEARCH_LANE != "off" and enforcing()
    ):
        raise ImproperlyConfigured(
            "AI_COMPARISON_ENABLED needs durable Ask, paper briefs, research routing "
            "and enforced provider admission"
        )


def comparison_ceiling():
    values = {}
    for field, name, cast in (
        ("attempts", "AI_COMPARISON_MAX_ATTEMPTS", int),
        ("input_tokens", "AI_COMPARISON_MAX_INPUT_TOKENS", int),
        ("output_tokens", "AI_COMPARISON_MAX_OUTPUT_TOKENS", int),
        ("cost_micros", "AI_COMPARISON_MAX_COST_USD", float),
    ):
        raw = getattr(settings, name, "")
        if raw in (None, ""):
            raise NotConfigured(name)
        try:
            value = cast(raw)
        except (ValueError, TypeError):
            raise ImproperlyConfigured(f"{name} must be positive") from None
        if not math.isfinite(value) or value <= 0:
            raise ImproperlyConfigured(f"{name} must be positive")
        values[field] = math.floor(value * 1_000_000) if field == "cost_micros" else value
    return Ceiling(**values)
