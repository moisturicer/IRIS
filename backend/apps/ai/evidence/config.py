"""The evidence detector's configuration (IR-464).

ADR-035 §5: the generic English rules are in code; institution and Area terms
are settings, because an institution name is deployment-specific under
ADR-005's instance-per-tenant posture. Since IR-957 retired the shadow pilot,
the detector is an offline instrument only (`manage.py eval_evidence`), so the
rule set is built on first use rather than gated at startup.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings

from .detector import EvidenceDetector
from .rules import RuleSet, build_rule_set

logger = logging.getLogger(__name__)

SETTING_INSTITUTION_TERMS = "AI_EVIDENCE_INSTITUTION_TERMS"
SETTING_AREA_TERMS = "AI_EVIDENCE_AREA_TERMS"

_cached: Optional[RuleSet] = None


def _terms(name: str) -> tuple[str, ...]:
    raw = getattr(settings, name, ()) or ()
    if isinstance(raw, str):
        raw = raw.split(",")
    return tuple(str(term).strip() for term in raw if str(term).strip())


def institution_terms() -> tuple[str, ...]:
    return _terms(SETTING_INSTITUTION_TERMS)


def area_terms() -> tuple[str, ...]:
    return _terms(SETTING_AREA_TERMS)


def load_rule_set() -> RuleSet:
    """Build the active rule set from settings and cache it.

    The resolved set is logged here and nowhere else, so the rule set a run
    used is recoverable from its log by digest.
    """
    global _cached
    _cached = build_rule_set(
        institution_terms=institution_terms(), area_terms=area_terms()
    )
    logger.info(
        "Evidence detector rule set loaded: %s", _cached.summary(),
    )
    return _cached


def active_rule_set() -> RuleSet:
    """The rule set this process is using, built on first use."""
    return _cached if _cached is not None else load_rule_set()


def reset_rule_set() -> None:
    """Drop the cache so the next call re-reads settings. For tests, and for
    the test that proves a settings change does *not* reach a loaded set."""
    global _cached
    _cached = None


def detector() -> EvidenceDetector:
    return EvidenceDetector(active_rule_set())
