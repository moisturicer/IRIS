"""The five rules, one reason code each (IR-464, ADR-035 §5).

Pure: no Django, no database, no model, no vendor.
"""

import pytest

from apps.ai.evidence.rules import (
    AGGREGATE_SHAPE,
    DOCUMENT_REFERENCE,
    INSTITUTION_TERM,
    REASON_CODES,
    SCOPE_RECORD,
    SOURCING_DEMAND,
    build_rule_set,
    normalize,
)

TERMS = ("CIT-U", "Cebu Institute of Technology", "IRIS")
AREAS = ("College of Computer Studies",)


def rule_set():
    return build_rule_set(institution_terms=TERMS, area_terms=AREAS)


def fired(question):
    normalized = normalize(question)
    return {rule.code for rule in rule_set().rules if rule.matches(normalized)}


def test_there_are_exactly_five_reason_codes_one_per_rule():
    assert REASON_CODES == (
        SCOPE_RECORD,
        INSTITUTION_TERM,
        DOCUMENT_REFERENCE,
        SOURCING_DEMAND,
        AGGREGATE_SHAPE,
    )
    # Four lexical rules; `scope_record` is structural and carries no terms.
    assert {rule.code for rule in rule_set().rules} == set(REASON_CODES) - {
        SCOPE_RECORD
    }


@pytest.mark.parametrize(
    "question, code",
    [
        ("what research has CIT-U published on tilapia?", INSTITUTION_TERM),
        ("who in the College of Computer Studies works on this?", INSTITUTION_TERM),
        ("what does IRIS hold about water quality?", INSTITUTION_TERM),
        ("what did the paper conclude?", DOCUMENT_REFERENCE),
        ("which authors worked on pond sampling?", DOCUMENT_REFERENCE),
        ("summarise the thesis on aquaculture", DOCUMENT_REFERENCE),
        ("what is the evidence for that claim?", SOURCING_DEMAND),
        ("give me the source for that number", SOURCING_DEMAND),
        ("answer with citations", SOURCING_DEMAND),
        ("what are the research gaps in aquaculture here?", AGGREGATE_SHAPE),
        ("how many studies cover water quality?", AGGREGATE_SHAPE),
        ("which papers mention tilapia?", AGGREGATE_SHAPE),
        ("what are the trends over the last five years?", AGGREGATE_SHAPE),
    ],
)
def test_each_lexical_rule_raises_its_own_code(question, code):
    assert code in fired(question)


@pytest.mark.parametrize(
    "question",
    [
        "what is the colour of the sky?",
        "what is the difference between a mean and a median?",
        "what does it mean for an optimization problem to be convex?",
        "how does it compare?",
    ],
)
def test_a_general_question_raises_nothing(question):
    assert fired(question) == set()


@pytest.mark.parametrize("spelling", ["CIT-U", "cit u", "CIT  U", "cit-u", "CIT–U"])
def test_an_institution_term_folds_across_spellings(spelling):
    assert INSTITUTION_TERM in fired(f"what has {spelling} published on ponds?")


def test_a_term_is_matched_as_a_phrase_not_as_a_substring():
    # "paper" is a term; "paperwork" is not that term.
    assert DOCUMENT_REFERENCE not in fired("how much paperwork does this need?")


def test_there_is_no_restricted_evidence_rule():
    """ADR-035 §5: restricted material is protected by the visibility
    predicate and the disclosure gate, never by a word list."""
    every_term = {
        term for rule in rule_set().rules for term in rule.terms
    }
    for forbidden in ("confidential", "restricted", "embargo", "embargoed", "secret"):
        assert forbidden not in every_term


def test_the_digest_covers_the_complete_active_rule_set():
    baseline = rule_set().digest
    assert baseline == rule_set().digest
    assert build_rule_set(institution_terms=TERMS).digest != baseline
    assert (
        build_rule_set(institution_terms=(*TERMS, "Another University")).digest
        != baseline
    )


def test_the_digest_does_not_move_when_a_term_is_merely_reordered():
    assert (
        build_rule_set(institution_terms=tuple(reversed(TERMS)), area_terms=AREAS).digest
        == rule_set().digest
    )


def test_the_digest_names_the_generic_rules_too():
    """A results file must change when a generic English term changes, not
    only when a deployment's institution list does."""
    definition = rule_set().as_dict()
    codes = {rule["code"] for rule in definition["rules"]}
    assert codes == set(REASON_CODES)
    assert any(
        rule["code"] == DOCUMENT_REFERENCE and "paper" in rule["terms"]
        for rule in definition["rules"]
    )
