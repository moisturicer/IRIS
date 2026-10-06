"""The deterministic half of the evidence decision (IR-464, ADR-035 §5).

Five rules over question text emitting five reason codes, run on the raw and
Resolved questions and combined by OR. The shadow pilot (`shadow.py`, IR-466)
records a verdict per sampled chat Turn and routes nothing; production routing
is out of scope for ADR-035 (§11). The curated instrument that measures this
lives in `apps.ai.evaluation.evidence`.
"""

from .config import (
    MODES,
    MODE_OFF,
    MODE_SHADOW,
    REJECTED_MODES,
    SETTING_AREA_TERMS,
    SETTING_INSTITUTION_TERMS,
    SETTING_MODE,
    active_rule_set,
    area_terms,
    configured_mode,
    decision_enabled,
    detector,
    institution_terms,
    evidence_configuration_problems,
    load_rule_set,
    reset_rule_set,
    verify_evidence_configuration,
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
    "MODES",
    "MODE_OFF",
    "MODE_SHADOW",
    "REASON_CODES",
    "REJECTED_MODES",
    "RuleHit",
    "RuleSet",
    "SCOPE_RECORD",
    "SETTING_AREA_TERMS",
    "SETTING_INSTITUTION_TERMS",
    "SETTING_MODE",
    "SOURCE_RAW",
    "SOURCE_RESOLVED",
    "SOURCE_SCOPE",
    "SOURCING_DEMAND",
    "Verdict",
    "active_rule_set",
    "area_terms",
    "build_rule_set",
    "configured_mode",
    "decision_enabled",
    "detector",
    "evidence_configuration_problems",
    "institution_terms",
    "load_rule_set",
    "normalize",
    "reset_rule_set",
    "verify_evidence_configuration",
]
