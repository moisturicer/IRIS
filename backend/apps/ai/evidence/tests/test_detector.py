"""The OR rule, the fail-safe, and what the detector cannot do (IR-464).

ADR-035 §5. Pure: no Django, no database, no model, no vendor.
"""

import pytest

from apps.ai.evidence.detector import (
    SOURCE_RAW,
    SOURCE_RESOLVED,
    SOURCE_SCOPE,
    EvidenceDetector,
    Verdict,
)
from apps.ai.evidence.rules import (
    DOCUMENT_REFERENCE,
    INSTITUTION_TERM,
    SCOPE_RECORD,
    SOURCING_DEMAND,
    build_rule_set,
)


@pytest.fixture
def detector():
    return EvidenceDetector(
        build_rule_set(
            institution_terms=("CIT-U", "IRIS"),
            area_terms=("College of Computer Studies",),
        )
    )


# -- the OR rule -----------------------------------------------------------


def test_a_rewrite_that_drops_a_sourcing_demand_still_yields_a_requirement(detector):
    verdict = detector.detect(
        "what is the evidence for that, with sources?",
        resolved_question="how does photosynthesis work?",
    )
    assert verdict.evidence_required
    assert SOURCING_DEMAND in verdict.codes
    assert verdict.codes_from(SOURCE_RAW) == (SOURCING_DEMAND,)
    assert verdict.codes_from(SOURCE_RESOLVED) == ()


def test_a_rewrite_that_drops_an_institution_name_still_yields_a_requirement(detector):
    verdict = detector.detect(
        "what has CIT-U found about pond sampling?",
        resolved_question="what is known about pond sampling?",
    )
    assert verdict.evidence_required
    assert verdict.codes_from(SOURCE_RAW) == (INSTITUTION_TERM,)
    assert verdict.codes_from(SOURCE_RESOLVED) == ()


def test_a_rewrite_that_introduces_a_requirement_also_yields_one(detector):
    """The OR runs both ways: the Resolved question is the lane that catches a
    follow-up whose raw text carries no repository vocabulary at all."""
    verdict = detector.detect(
        "what exactly did they say about that?",
        resolved_question="what did the authors say about Pareto fronts?",
    )
    assert verdict.evidence_required
    assert verdict.codes_from(SOURCE_RAW) == ()
    assert verdict.codes_from(SOURCE_RESOLVED) == (DOCUMENT_REFERENCE,)


def test_neither_text_firing_yields_no_requirement(detector):
    verdict = detector.detect(
        "what is the difference between a mean and a median?",
        resolved_question="what is the difference between a mean and a median?",
    )
    assert verdict.evidence_required is False
    assert verdict.codes == ()
    assert verdict.undetermined is False


# -- the structural rule ---------------------------------------------------


def test_a_record_scoped_conversation_always_yields_scope_record(detector):
    verdict = detector.detect("what is the colour of the sky?", record_scoped=True)
    assert verdict.evidence_required
    assert verdict.codes == (SCOPE_RECORD,)
    assert verdict.hits[0].source == SOURCE_SCOPE


def test_scope_record_survives_an_unreadable_question(detector):
    verdict = detector.detect("", record_scoped=True)
    assert verdict.evidence_required
    assert SCOPE_RECORD in verdict.codes
    assert verdict.undetermined is False


# -- the fail-safe ---------------------------------------------------------


@pytest.mark.parametrize("text", [None, "", "   ", "\n", "?", "...", "???"])
def test_an_unreadable_question_fails_safe_to_a_requirement(detector, text):
    verdict = detector.detect(text)
    assert verdict.evidence_required
    assert verdict.undetermined
    assert verdict.codes == ()


def test_an_unreadable_raw_question_with_a_readable_rewrite_is_not_undetermined(
    detector,
):
    verdict = detector.detect("", resolved_question="what did the paper find?")
    assert verdict.evidence_required
    assert verdict.undetermined is False
    assert verdict.codes_from(SOURCE_RESOLVED) == (DOCUMENT_REFERENCE,)


# -- what the detector cannot do -------------------------------------------


def test_the_detector_cannot_express_a_refusal():
    """A high-recall rule may add retrieval; it may never drive a refusal
    (ADR-035 §5). There is no field on a `Verdict` a consumer could read as
    one -- the outcomes are 'evidence required' and 'no requirement
    detected', and the second is not a claim that nothing exists."""
    fields = set(Verdict.__dataclass_fields__)
    assert fields == {"evidence_required", "hits", "rule_set_digest", "undetermined"}
    for name in fields:
        assert "refus" not in name and "decline" not in name


def test_the_verdict_records_the_rule_set_it_was_produced_under(detector):
    verdict = detector.detect("what did the paper find?")
    assert verdict.rule_set_digest == detector.rule_set.digest


def test_a_lane_reads_one_text_only(detector):
    raw = detector.detect_lane("what did the paper find?", source=SOURCE_RAW)
    assert raw.codes_from(SOURCE_RAW) == (DOCUMENT_REFERENCE,)
    assert raw.codes_from(SOURCE_RESOLVED) == ()

    resolved = detector.detect_lane(
        "what did the paper find?", source=SOURCE_RESOLVED
    )
    assert resolved.codes_from(SOURCE_RESOLVED) == (DOCUMENT_REFERENCE,)
    assert resolved.codes_from(SOURCE_RAW) == ()


def test_a_lane_name_outside_the_two_is_refused(detector):
    with pytest.raises(ValueError, match="lane"):
        detector.detect_lane("anything", source=SOURCE_SCOPE)


def test_a_verdict_serializes_its_codes_and_its_hits(detector):
    data = detector.detect(
        "what has CIT-U published, with sources?", record_scoped=True
    ).as_dict()
    assert data["evidence_required"] is True
    assert data["codes"][0] == SCOPE_RECORD
    assert {hit["source"] for hit in data["hits"]} == {SOURCE_SCOPE, SOURCE_RAW}
