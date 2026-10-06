"""Reading the evidence decision's configuration, once, at startup (IR-464).

ADR-035 §5: the generic English rules are in code; institution and Area terms
are settings, because an institution name is deployment-specific under
ADR-005's instance-per-tenant posture.

**Read at startup, not per request** -- a deliberate divergence from IR-396's
read-per-request convention. That setting tunes recall; this one gates a
safeguard, and a per-request read would let a `.env` edit silently remove an
evidence requirement between two questions.

Django refuses to start when the institution-term list is empty and the
decision is enabled, so disabling the rule requires turning the feature off
rather than blanking a string. `on` is rejected as an invalid mode (ADR-035
§1): a mode the parser accepts is one somebody enters by accident.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .detector import EvidenceDetector
from .rules import RuleSet, build_rule_set

logger = logging.getLogger(__name__)

SETTING_MODE = "AI_EVIDENCE_DECISION"
SETTING_INSTITUTION_TERMS = "AI_EVIDENCE_INSTITUTION_TERMS"
SETTING_AREA_TERMS = "AI_EVIDENCE_AREA_TERMS"
SETTING_SAMPLE_RATE = "AI_EVIDENCE_SHADOW_SAMPLE_RATE"

MODE_OFF = "off"
MODE_SHADOW = "shadow"

#: The only accepted modes. Phase 0 records what it would have decided and
#: changes no answer a reader sees.
MODES = (MODE_OFF, MODE_SHADOW)

#: Named rather than merely absent, so the refusal can say why.
REJECTED_MODES = ("on",)

_cached: Optional[RuleSet] = None


def configured_mode() -> str:
    return str(getattr(settings, SETTING_MODE, MODE_OFF) or MODE_OFF).strip().lower()


def sample_rate() -> float:
    return float(getattr(settings, SETTING_SAMPLE_RATE, 0.0) or 0.0)


def decision_enabled() -> bool:
    """Whether this deployment records evidence decisions at all."""
    return configured_mode() in (MODE_SHADOW,)


def _terms(name: str) -> tuple[str, ...]:
    raw = getattr(settings, name, ()) or ()
    if isinstance(raw, str):
        raw = raw.split(",")
    return tuple(str(term).strip() for term in raw if str(term).strip())


def institution_terms() -> tuple[str, ...]:
    return _terms(SETTING_INSTITUTION_TERMS)


def area_terms() -> tuple[str, ...]:
    return _terms(SETTING_AREA_TERMS)


def evidence_configuration_problems() -> list[str]:
    """What is wrong with this deployment's evidence configuration."""
    problems: list[str] = []
    mode = configured_mode()
    if mode in REJECTED_MODES:
        problems.append(
            f"{SETTING_MODE}={mode!r} is rejected, not merely unimplemented: "
            f"Phase 0 records a decision and changes no answer a reader sees "
            f"(ADR-035 §1). Accepted: {', '.join(MODES)}"
        )
    elif mode not in MODES:
        problems.append(
            f"{SETTING_MODE}={mode!r} is not one of {', '.join(MODES)}"
        )

    try:
        rate_ok = 0.0 <= sample_rate() <= 1.0
    except (TypeError, ValueError):
        rate_ok = False
    if not rate_ok:
        problems.append(f"{SETTING_SAMPLE_RATE} is not a number between 0 and 1")

    if decision_enabled() and not institution_terms():
        problems.append(
            f"{SETTING_INSTITUTION_TERMS} is empty while {SETTING_MODE}="
            f"{mode}. The institution_term rule is a safeguard, so it is "
            f"turned off by setting {SETTING_MODE}={MODE_OFF}, not by "
            f"blanking the term list (ADR-035 §5)"
        )
    return problems


def verify_evidence_configuration() -> None:
    """Refuse to start rather than drop an evidence requirement silently."""
    problems = evidence_configuration_problems()
    if problems:
        raise ImproperlyConfigured(
            "Evidence decision configuration (IR-464):\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )


def load_rule_set() -> RuleSet:
    """Build the active rule set from settings and cache it.

    Called once from `AiConfig.ready()`. The resolved set is logged here and
    nowhere else, so a deployment's rule set is recoverable from its startup
    log by digest.
    """
    global _cached
    _cached = build_rule_set(
        institution_terms=institution_terms(), area_terms=area_terms()
    )
    logger.info(
        "Evidence detector rule set loaded (%s=%s): %s",
        SETTING_MODE,
        configured_mode(),
        _cached.summary(),
    )
    return _cached


def active_rule_set() -> RuleSet:
    """The rule set this process is using. Loaded on first use if startup has
    not run it -- a management command imports before `ready()` in some
    entry points, and a missing cache is not a reason to refuse."""
    return _cached if _cached is not None else load_rule_set()


def reset_rule_set() -> None:
    """Drop the cache so the next call re-reads settings. For tests, and for
    the test that proves a settings change does *not* reach a loaded set."""
    global _cached
    _cached = None


def detector() -> EvidenceDetector:
    return EvidenceDetector(active_rule_set())
