"""Terms read at startup, and the modes Django refuses (IR-464, ADR-035 §1/§5).

These touch `django.conf.settings` but no database.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.ai.evidence import config as evidence_config
from apps.ai.evidence.rules import INSTITUTION_TERM


@pytest.fixture(autouse=True)
def fresh_cache():
    evidence_config.reset_rule_set()
    yield
    evidence_config.reset_rule_set()


# -- the modes -------------------------------------------------------------


@override_settings(AI_EVIDENCE_DECISION="on")
def test_on_is_rejected_as_an_invalid_mode():
    """ADR-035 §1: `on` is rejected, not merely unimplemented. A mode a parser
    accepts is one somebody enters by accident."""
    with pytest.raises(ImproperlyConfigured, match="rejected"):
        evidence_config.verify_evidence_configuration()


@override_settings(AI_EVIDENCE_DECISION="enabled")
def test_an_unknown_mode_is_refused():
    with pytest.raises(ImproperlyConfigured, match="AI_EVIDENCE_DECISION"):
        evidence_config.verify_evidence_configuration()


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_the_two_accepted_modes_start(mode):
    with override_settings(
        AI_EVIDENCE_DECISION=mode, AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",)
    ):
        evidence_config.verify_evidence_configuration()
        assert evidence_config.configured_mode() == mode


def test_the_default_mode_is_off_and_nothing_is_enabled():
    assert evidence_config.configured_mode() == "off"
    assert evidence_config.decision_enabled() is False


# -- the institution-term guard --------------------------------------------


@override_settings(AI_EVIDENCE_DECISION="shadow", AI_EVIDENCE_INSTITUTION_TERMS=())
def test_django_refuses_to_start_with_no_institution_terms_while_enabled():
    """The rule is a safeguard, so it is turned off by turning the feature
    off, never by blanking the term list (ADR-035 §5)."""
    with pytest.raises(ImproperlyConfigured, match="AI_EVIDENCE_INSTITUTION_TERMS"):
        evidence_config.verify_evidence_configuration()


@override_settings(AI_EVIDENCE_DECISION="off", AI_EVIDENCE_INSTITUTION_TERMS=())
def test_an_empty_term_list_is_fine_while_the_decision_is_off():
    evidence_config.verify_evidence_configuration()


@override_settings(AI_EVIDENCE_DECISION="shadow", AI_EVIDENCE_INSTITUTION_TERMS="  ,  ")
def test_a_whitespace_only_term_list_counts_as_empty():
    with pytest.raises(ImproperlyConfigured, match="AI_EVIDENCE_INSTITUTION_TERMS"):
        evidence_config.verify_evidence_configuration()


# -- read at startup, not per request --------------------------------------


@override_settings(
    AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",), AI_EVIDENCE_AREA_TERMS=("Nursing",)
)
def test_the_terms_are_read_into_the_rule_set():
    rule_set = evidence_config.load_rule_set()
    terms = rule_set.rule(INSTITUTION_TERM).terms
    assert "cit u" in terms
    assert "nursing" in terms


def test_a_loaded_rule_set_does_not_change_when_a_setting_does():
    """The point of reading at startup: a `.env` edit must not be able to
    remove an evidence requirement between two questions (ADR-035 §5)."""
    with override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",)):
        loaded = evidence_config.load_rule_set()

    with override_settings(AI_EVIDENCE_INSTITUTION_TERMS=()):
        assert evidence_config.active_rule_set() is loaded
        assert "cit u" in evidence_config.active_rule_set().rule(INSTITUTION_TERM).terms

        reloaded = evidence_config.load_rule_set()
        assert reloaded.rule(INSTITUTION_TERM).terms == ()


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_rule_set_is_logged_once_with_its_digest(monkeypatch):
    """A deployment's rule set is recoverable from its startup log by digest,
    and logged in one place so it cannot be logged per request."""
    lines = []
    monkeypatch.setattr(
        evidence_config.logger,
        "info",
        lambda message, *args: lines.append(message % args),
    )
    rule_set = evidence_config.load_rule_set()
    assert len(lines) == 1
    assert "rule set loaded" in lines[0]
    assert rule_set.digest[:12] in lines[0]


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_detector_is_built_from_the_active_rule_set():
    assert (
        evidence_config.detector().rule_set is evidence_config.active_rule_set()
    )
