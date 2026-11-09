"""The deterministic half of the evidence decision (IR-464, ADR-035 §5).

Five rules over question text emitting five reason codes, run on the raw and
Resolved questions and combined by OR. Nothing in a live path consumes it:
IR-957 retired the shadow pilot (IR-466) with Django's answer path. The
curated instrument that measures it lives in `apps.ai.evaluation.evidence`.
"""

from .config import (
    SETTING_AREA_TERMS,
    SETTING_INSTITUTION_TERMS,
    active_rule_set,
    area_terms,
    detector,
    institution_terms,
    load_rule_set,
    reset_rule_set,
)
from .detector import (
    SOURCE_RAW,
    SOURCE_RESOLVED,
    SOURCE_SCOPE,
    EvidenceDetector,
    RuleHit,
    Verdict,
)
from .rules import (
    AGGREGATE_SHAPE,
    DOCUMENT_REFERENCE,
    INSTITUTION_TERM,
    REASON_CODES,
    SCOPE_RECORD,
    SOURCING_DEMAND,
    LexicalRule,
    RuleSet,
    build_rule_set,
    normalize,
)

__all__ = [
    "AGGREGATE_SHAPE",
    "DOCUMENT_REFERENCE",
    "EvidenceDetector",
    "INSTITUTION_TERM",
    "LexicalRule",
    "REASON_CODES",
    "RuleHit",
    "RuleSet",
    "SCOPE_RECORD",
    "SETTING_AREA_TERMS",
    "SETTING_INSTITUTION_TERMS",
    "SOURCE_RAW",
    "SOURCE_RESOLVED",
    "SOURCE_SCOPE",
    "SOURCING_DEMAND",
    "Verdict",
    "active_rule_set",
    "area_terms",
    "build_rule_set",
    "detector",
    "institution_terms",
    "load_rule_set",
    "normalize",
    "reset_rule_set",
]
