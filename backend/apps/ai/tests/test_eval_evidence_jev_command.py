"""`eval_evidence --model-decision --decision-mode jev-noul` (IR-482).

Offline: the decision model is a `ScriptedDecisionModel`, so no vendor is
called. The curated-instrument properties still hold -- no `Conversation`,
`Turn` or shadow row, and nothing reaches the answer path -- and the run file
records the returned model version, the state digest and the request provenance,
including that retention terms are unverified.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import apps.ai.management.commands.eval_evidence as command
from apps.ai.evidence.jev_noul import STATE_FIELDS, jev_digest
from apps.ai.models import Conversation, Turn
from apps.ai.providers.decisions import NoulAnswer, ScriptedDecisionModel
from apps.ai.providers.openrouter_decisions import PINNED_MODEL
from apps.ai.tests.test_eval_evidence_model_command import direct, grounded, write_set

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

VERSION = "typesafe/jev-1.13-20260917"


class ByWord(ScriptedDecisionModel):
    def noul(self, state, **kwargs):
        self.calls.append({"state": state, **kwargs})
        p = 0.9 if "paper" in state["question"] else 0.1
        return NoulAnswer(probability=p, model=VERSION, input_tokens=100)


@pytest.fixture(autouse=True)
def institution_terms(settings):
    settings.AI_EVIDENCE_INSTITUTION_TERMS = ("CIT-U",)


@pytest.fixture
def questions(tmp_path):
    return write_set(
        tmp_path,
        grounded("q1", "what did the paper find?"),
        direct("q2", "what is a median?"),
    )


@pytest.fixture
def fake(monkeypatch):
    model = ByWord()
    monkeypatch.setattr(command, "_openrouter_decision_model", lambda: model)
    return model


def run(questions, *extra):
    call_command(
        "eval_evidence", "--questions", questions, "--model-decision",
        "--decision-mode", "jev-noul", *extra,
    )


class TheRunTests:
    def test_the_curve_and_the_provenance_are_recorded(self, fake, questions, tmp_path, capsys):
        out = tmp_path / "runs"
        run(questions, "--out", str(out))

        (written,) = out.glob("*-evidence-*.json")
        data = json.loads(written.read_text(encoding="utf-8"))
        prov = data["provenance"]
        model = data["model"]
        assert model["questions"] == 2 and model["fallbacks"] == 0
        assert model["models"] == [VERSION]
        assert model["operating_point"] is None
        assert len(model["threshold_curve"]["thresholds"]) == 19
        assert prov["decision_mode"] == "jev-noul"
        assert prov["prompt_digest"] == jev_digest(PINNED_MODEL)
        assert prov["model"] == PINNED_MODEL
        assert prov["workers"] == 1
        assert prov["request"]["endpoint"].endswith("/api/alpha/decisions")
        assert prov["request"]["state_fields"] == list(STATE_FIELDS)
        assert "Model decision" in capsys.readouterr().out

    def test_unverified_retention_terms_and_the_approval_scope_are_in_the_file(
        self, fake, questions, tmp_path
    ):
        out = tmp_path / "runs"
        run(questions, "--out", str(out))

        (written,) = out.glob("*-evidence-*.json")
        prov = json.loads(written.read_text(encoding="utf-8"))["provenance"]
        assert "UNVERIFIED" in prov["vendor_terms"]
        assert "retention" in prov["vendor_terms"].lower()
        assert "public proxy question set only" in prov["approval"]["scope"]
        assert prov["approval"]["approver"] == "JIVE"

    def test_one_call_per_question_and_no_passage_in_any_state(self, fake, questions):
        run(questions, "--no-write")

        assert len(fake.calls) == 2
        for call in fake.calls:
            assert set(call["state"]) <= set(STATE_FIELDS)

    def test_it_creates_no_conversation_and_no_turn(self, fake, questions):
        run(questions, "--no-write")
        assert (Conversation.objects.count(), Turn.objects.count()) == (0, 0)

    def test_it_never_builds_the_composition_root(self, fake, questions, monkeypatch):
        import apps.ai.composition as composition

        def boom(*args, **kwargs):
            raise AssertionError("the answer path's root was built")

        monkeypatch.setattr(composition, "composition_root", boom)
        run(questions, "--no-write")


class TheRefusalTests:
    def test_the_mode_needs_model_decision(self, questions):
        with pytest.raises(CommandError, match="needs --model-decision"):
            call_command(
                "eval_evidence", "--questions", questions,
                "--decision-mode", "jev-noul", "--no-write",
            )

    def test_a_set_that_is_not_the_public_proxy_tier_is_refused(self, fake, tmp_path):
        path = tmp_path / "private.json"
        path.write_text(
            json.dumps({
                "name": "private", "tier": "institutional",
                "questions": [grounded("q1", "what did the paper find?")],
            }),
            encoding="utf-8",
        )
        with pytest.raises(CommandError, match="public proxy"):
            run(str(path), "--no-write")
        assert fake.calls == []

    def test_a_set_that_does_not_declare_its_tier_is_refused(self, fake, tmp_path):
        path = tmp_path / "untiered.json"
        path.write_text(
            json.dumps({"name": "x", "questions": [grounded("q1", "what did the paper find?")]}),
            encoding="utf-8",
        )
        with pytest.raises(CommandError, match="declare"):
            run(str(path), "--no-write")
        assert fake.calls == []

    def test_a_run_over_five_percent_fallbacks_says_not_to_pool_it(
        self, monkeypatch, questions, capsys
    ):
        from apps.ai.providers.decisions import DecisionUnavailable

        down = ScriptedDecisionModel(DecisionUnavailable("x"), DecisionUnavailable("x"))
        monkeypatch.setattr(command, "_openrouter_decision_model", lambda: down)
        run(questions, "--no-write")
        assert "do not pool" in capsys.readouterr().out

    def test_a_clean_run_carries_no_pooling_warning(self, fake, questions, capsys):
        run(questions, "--no-write")
        assert "do not pool" not in capsys.readouterr().out

    def test_no_openrouter_key_is_refused_by_name(self, questions):
        with override_settings(
            LLM_BASE_URL="https://api.groq.com/openai/v1",
            LLM_API_KEY="groq-key",
            LLM_ANSWER_VENDOR="", LLM_RESOLVE_VENDOR="", LLM_SUMMARY_VENDOR="",
            LLM_SUMMARY_API_KEY="",
        ):
            with pytest.raises(CommandError, match="OpenRouter"):
                run(questions, "--no-write")

    def test_the_groq_key_is_never_sent_to_openrouter(self, monkeypatch):
        captured = []

        class Capture:
            def __init__(self, api_key, **kwargs):
                captured.append(api_key)

        monkeypatch.setattr(command, "OpenRouterDecisionsAdapter", Capture)
        with override_settings(
            LLM_BASE_URL="https://api.groq.com/openai/v1",
            LLM_API_KEY="groq-key",
            LLM_ANSWER_VENDOR="", LLM_RESOLVE_VENDOR="",
            LLM_SUMMARY_VENDOR="openrouter",
            LLM_SUMMARY_API_KEY="or-key",
            LLM_SUMMARY_MODEL="m",
        ):
            command._openrouter_decision_model()
        assert captured == ["or-key"]

    def test_the_default_run_is_unchanged_and_calls_no_decision_model(self, fake, questions):
        call_command("eval_evidence", "--questions", questions, "--no-write")
        assert fake.calls == []
