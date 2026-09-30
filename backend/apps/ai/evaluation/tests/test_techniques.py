"""The switches a run can move, and what it records about them (IR-394).

IR-394's criterion is that the harness "accepts a configuration switching each
technique on or off independently, and records it". Two properties carry the
weight here:

- A run file says what every ADR-033 §5 technique was set to, including the
  ones whose setting does not exist yet. A run whose configuration is implicit
  cannot be reproduced.
- Asking for a technique that is not implemented yet is **refused**, not
  silently ignored. A run that claims to measure fusion while fusion does not
  exist would produce a number indistinguishable from the baseline and a
  results file asserting otherwise.

No database and no vendor: this is the registry and the override mechanism.
"""

import pytest
from django.test import override_settings

from apps.ai.evaluation import techniques
from apps.ai.evaluation.report import RunConfig
from apps.ai.evaluation.techniques import (
    TECHNIQUES,
    Technique,
    TechniqueError,
    parse_override,
    render_registry,
    resolve,
    technique,
)

# The six ADR-033 §5 names the fusion, cut-off and selection tickets land.
ADR_033_TECHNIQUES = {
    "fusion",
    "keyword_retrieval",
    "relevance_cut_off",
    "per_paper_cap",
    "neighbour_joining",
    "token_budget",
}


# -- the registry -------------------------------------------------------------


def test_every_adr_033_technique_is_in_the_registry():
    assert {t.name for t in TECHNIQUES} == ADR_033_TECHNIQUES


def test_names_and_settings_are_each_unique():
    assert len({t.name for t in TECHNIQUES}) == len(TECHNIQUES)
    assert len({t.setting for t in TECHNIQUES}) == len(TECHNIQUES)


def test_every_technique_names_the_ticket_that_lands_it():
    assert all(t.ticket and t.setting.startswith("AI_") for t in TECHNIQUES)


def test_an_unknown_name_is_refused_and_the_known_ones_are_named():
    with pytest.raises(TechniqueError) as exc:
        technique("hybrid")

    assert "fusion" in str(exc.value)


def test_the_registry_renders_for_an_operator_choosing_a_run():
    rendered = render_registry()

    assert "fusion" in rendered
    assert "AI_RETRIEVAL_FUSION_ENABLED" in rendered


# -- what a run records ------------------------------------------------------


def test_a_technique_whose_setting_does_not_exist_yet_is_recorded_as_such():
    fusion = resolve()["fusion"]

    assert fusion["implemented"] is False
    assert fusion["value"] is None
    assert fusion["setting"] == "AI_RETRIEVAL_FUSION_ENABLED"


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=True)
def test_a_technique_whose_setting_exists_is_recorded_at_its_value():
    fusion = resolve()["fusion"]

    assert fusion["implemented"] is True
    assert fusion["value"] is True
    assert fusion["overridden"] is False


def test_resolve_records_all_six_techniques_whatever_the_run_asked_for():
    assert set(resolve()) == ADR_033_TECHNIQUES


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=False)
def test_an_override_is_recorded_as_an_override():
    fusion = resolve([("fusion", True)])["fusion"]

    assert fusion["value"] is True
    assert fusion["overridden"] is True


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=False)
def test_the_results_file_spells_a_switch_the_way_the_cli_does():
    assert resolve([("fusion", True)]).changes == ("fusion=on",)
    assert resolve([("fusion", True)]).moved == ("fusion",)
    assert resolve().changes == ()


# -- overrides ---------------------------------------------------------------


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=False)
def test_a_boolean_override_reads_on_and_off():
    assert parse_override("fusion=on") == ("fusion", True)
    assert parse_override("fusion=off") == ("fusion", False)


@override_settings(AI_MAX_PASSAGES_PER_RECORD=0, AI_RELEVANCE_MIN_SCORE=0.0)
def test_a_numeric_override_keeps_its_type():
    assert parse_override("per_paper_cap=3") == ("per_paper_cap", 3)
    assert parse_override("relevance_cut_off=0.35") == ("relevance_cut_off", 0.35)


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=False)
def test_a_value_the_technique_cannot_take_is_refused():
    with pytest.raises(TechniqueError):
        parse_override("fusion=0.5")


def test_an_override_with_no_value_is_refused():
    with pytest.raises(TechniqueError):
        parse_override("fusion")


def test_overriding_a_technique_that_does_not_exist_yet_is_refused():
    """The whole point: a run must not report a technique it never applied."""
    with pytest.raises(TechniqueError) as exc:
        parse_override("fusion=on")

    assert "IR-395" in str(exc.value)


# -- applying them -----------------------------------------------------------


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=False)
def test_an_applied_override_is_what_the_stack_reads():
    from django.conf import settings

    resolved = resolve([("fusion", True)])
    with resolved.applied():
        assert settings.AI_RETRIEVAL_FUSION_ENABLED is True
    assert settings.AI_RETRIEVAL_FUSION_ENABLED is False


def test_applying_a_baseline_changes_no_setting():
    from django.conf import settings

    with resolve().applied():
        assert not hasattr(settings, "AI_RETRIEVAL_FUSION_ENABLED")


# -- a run under an override -------------------------------------------------


class _Root:
    """A root that reports what the setting said when retrieval was built."""

    def __init__(self, seen):
        self._seen = seen

    def retriever(self):
        from django.conf import settings

        self._seen.append(settings.AI_CHUNK_MAX_TOKENS)
        return self

    def retrieve(self, question, user, limit):
        from apps.ai.retrieval.ports import RetrievalResult

        return RetrievalResult(passages=(), degraded=False, mode="vector")

    def source_selection(self, max_sources):
        return self

    def apply(self, passages):
        return list(passages)

    def embedder(self):
        return self

    def reranker(self):
        return self

    def without_reranking(self):
        return self


def test_a_run_applies_the_override_before_retrieval_is_built(monkeypatch):
    """A recorded override that the stack never saw would be a false record."""
    monkeypatch.setattr(
        techniques,
        "TECHNIQUES",
        (
            Technique(
                name="chunk_ceiling",
                setting="AI_CHUNK_MAX_TOKENS",
                kind="int",
                adr="none -- a stand-in for a technique that exists",
                ticket="IR-287",
                note="only here to prove an override reaches the stack",
            ),
        ),
    )
    from apps.ai.evaluation import harness
    from apps.ai.evaluation.labels import parse_question_set

    question_set = parse_question_set(
        {
            "name": "inline",
            "questions": [
                {
                    "id": "q1",
                    "question": "does the override reach retrieval?",
                    "expected": [{"record": "anything", "quote": "a quote long enough to pass"}],
                }
            ],
        }
    )
    seen = []
    config = RunConfig(techniques=resolve([("chunk_ceiling", 123)]))

    harness.run(_Root(seen), question_set, config, user=object())

    assert seen == [123]


@override_settings(AI_RETRIEVAL_FUSION_ENABLED=True)
def test_the_configuration_label_names_the_switch_that_moved():
    config = RunConfig(techniques=resolve([("fusion", False)]))

    assert "fusion=off" in config.label
