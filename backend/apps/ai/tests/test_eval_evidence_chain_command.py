"""`eval_evidence --chain` (IR-486).

Offline: stored runs are small hand-written result files and live deciders are
fakes patched over `Command._decider`, so no vendor account is needed. The
curated-instrument properties still hold -- no `Conversation`, `Turn` or shadow
row -- and the file is a `chain` file, never an `evidence` one, so
`report_evidence_pilot` cannot pick it up by its glob.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

import apps.ai.management.commands.eval_evidence as command
from apps.ai.evidence.model_decision import (
    REASON_ANSWERED_DIRECTLY,
    REASON_SEARCH_REQUESTED,
    ROUTE_DIRECT,
    ROUTE_EVIDENCE,
    ModelDecision,
)
from apps.ai.models import Conversation, Turn
from apps.ai.tests.test_eval_evidence_model_command import direct, grounded, write_set

pytestmark = pytest.mark.django_required


@pytest.fixture(autouse=True)
def institution_terms(settings):
    settings.AI_EVIDENCE_INSTITUTION_TERMS = ("CIT-U",)


@pytest.fixture
def questions(tmp_path):
    return write_set(
        tmp_path,
        grounded("q1", "what did the paper find?"),
        grounded("q2", "how does attention work in transformers"),
        direct("q3", "what is a median?"),
    )


def row(qid, expects, p=None, search=None, *, tolerated=False, cost=None):
    searches = (p >= 0.5) if p is not None else search
    return {
        "id": qid,
        "expects_evidence": expects,
        "search_tolerated": tolerated,
        "detector": False,
        "route": "evidence" if searches else "direct",
        "reason": REASON_SEARCH_REQUESTED if searches else REASON_ANSWERED_DIRECTLY,
        "anomalies": [],
        "latency_ms": 100,
        "input_tokens": 10,
        "output_tokens": None,
        "answer_present": False,
        "answer_chars": 0,
        "model": "m",
        **({"probability": p} if p is not None else {}),
        **({"cost_usd": cost} if cost is not None else {}),
    }


def result_file(tmp_path, name, rows):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"model": {"per_question": rows}}), encoding="utf-8")
    return str(path)


@pytest.fixture
def stored(tmp_path):
    jev = result_file(
        tmp_path,
        "jev",
        [row("q1", True, 0.9), row("q2", True, 0.05, cost=0.001), row("q3", False, 0.02)],
    )
    label = result_file(
        tmp_path,
        "label",
        [row("q1", True, search=True), row("q2", True, search=True), row("q3", False, search=False)],
    )
    return jev, label


CUTOFFS = ("--search-cutoff", "0.5", "--direct-cutoff", "0.2")


def chain(questions, *extra):
    call_command("eval_evidence", "--questions", questions, "--chain", *extra)


def written(out):
    (path,) = out.glob("*.json")
    return path, json.loads(path.read_text(encoding="utf-8"))


class TheStoredReplayTests:
    def test_replays_stored_runs_into_a_chain_file(self, questions, stored, tmp_path, capsys):
        jev, label = stored
        out = tmp_path / "runs"
        chain(questions, "--from-run", f"jev={jev}", "--from-run", f"label={label}", *CUTOFFS, "--out", str(out))

        path, data = written(out)
        assert "-chain-" in path.name and "-evidence-" not in path.name
        assert data["instrument"] == "curated-chain"
        assert data["operating_point"] is None
        assert data["bands"] == {"search_cutoff": 0.5, "direct_cutoff": 0.2}
        arms = {a["arm"]: a for a in data["arms"]}
        # the label rescues q2, the question Jev scored low
        assert arms["detector+jev"]["missed_searches"]["stable"] == ["q2"]
        assert arms["detector+jev+llm"]["missed_searches"]["stable"] == []
        assert arms["detector+jev+llm"]["rescue"]["per_replicate"][0]["rescued_by_llm"] == ["q2"]
        assert data["provenance"]["stored_runs"][0]["sha256"] != "unknown"
        assert data["provenance"]["cost_usd"] == 0.001
        assert "MISSED SEARCHES FIRST" in capsys.readouterr().out

    def test_arms_without_their_decider_are_named_as_skipped(self, questions, stored, tmp_path):
        jev, _ = stored
        out = tmp_path / "runs"
        chain(questions, "--from-run", f"jev={jev}", *CUTOFFS, "--out", str(out))
        _, data = written(out)
        assert "detector+jev+llm" in data["skipped_arms"]
        assert "jev_failure_llm_alone" in data["skipped_arms"]

    def test_the_detector_input_ablation_is_always_recorded(self, questions, stored, tmp_path):
        jev, _ = stored
        out = tmp_path / "runs"
        chain(questions, "--from-run", f"jev={jev}", *CUTOFFS, "--out", str(out), "--resolver-label", "small")
        _, data = written(out)
        assert data["ablations"]["resolver_label"] == "small"
        assert data["ablations"]["detector_input"]["raw_only"]

    def test_a_stored_run_from_another_set_is_refused(self, questions, tmp_path):
        other = result_file(tmp_path, "other", [row("x1", True, 0.9)])
        with pytest.raises(CommandError, match="answers 1 questions"):
            chain(questions, "--from-run", f"jev={other}", *CUTOFFS, "--no-write")

    def test_both_cutoffs_are_required(self, questions, stored):
        jev, _ = stored
        with pytest.raises(CommandError, match="no operating point"):
            chain(questions, "--from-run", f"jev={jev}", "--search-cutoff", "0.5", "--no-write")

    def test_inverted_cutoffs_are_refused(self, questions, stored):
        jev, _ = stored
        with pytest.raises(CommandError, match="must not exceed"):
            chain(questions, "--from-run", f"jev={jev}", "--search-cutoff", "0.2", "--direct-cutoff", "0.5", "--no-write")

    def test_no_runs_at_all_is_refused(self, questions):
        with pytest.raises(CommandError, match="needs decider runs"):
            chain(questions, *CUTOFFS, "--no-write")

    def test_a_malformed_from_run_is_refused(self, questions):
        with pytest.raises(CommandError, match="DECIDER=PATH"):
            chain(questions, "--from-run", "nonsense", *CUTOFFS, "--no-write")

    def test_a_run_file_without_model_decisions_is_refused(self, questions, tmp_path):
        bare = tmp_path / "bare.json"
        bare.write_text(json.dumps({"model": None}), encoding="utf-8")
        with pytest.raises(CommandError, match="no model decisions"):
            chain(questions, "--from-run", f"label={bare}", *CUTOFFS, "--no-write")

    @pytest.mark.db_required
    @pytest.mark.django_db
    def test_it_creates_no_conversation_turn_or_shadow_row(self, questions, stored, tmp_path):
        jev, label = stored
        chain(questions, "--from-run", f"jev={jev}", "--from-run", f"label={label}", *CUTOFFS, "--out", str(tmp_path / "r"))
        assert Conversation.objects.count() == 0 and Turn.objects.count() == 0


class Fake:
    def __init__(self, searches, probability=None):
        self.searches, self.probability = searches, probability
        self.seen = []

    def decide(self, question, *, resolved_question=None, prior_reader_questions=()):
        self.seen.append(resolved_question)
        s = self.searches(question)
        return ModelDecision(
            route=ROUTE_EVIDENCE if s else ROUTE_DIRECT,
            reason=REASON_SEARCH_REQUESTED if s else REASON_ANSWERED_DIRECTLY,
            latency_ms=5,
            model="fake",
            probability=(0.9 if s else 0.05) if self.probability else None,
            cost_usd=0.0005 if self.probability else None,
        )


@pytest.fixture
def fakes(monkeypatch):
    built = {}

    def decider(self, mode="tools", max_tokens=0):
        built[mode] = Fake(lambda q: "median" not in q, probability=(mode == "jev-noul"))
        return built[mode]

    monkeypatch.setattr(command.Command, "_decider", decider)
    return built


class TheLiveTests:
    def test_collects_the_requested_replicates_and_scores_them(self, fakes, questions, tmp_path):
        out = tmp_path / "runs"
        chain(questions, "--live", "jev,label", "--repeats", "3", *CUTOFFS, "--out", str(out))
        _, data = written(out)
        chain_arm = next(a for a in data["arms"] if a["arm"] == "detector+jev+llm")
        assert chain_arm["replicates"] == 3
        assert data["provenance"]["live_deciders"] == {"jev": "jev-noul", "label": "route-label"}
        assert len(fakes["jev-noul"].seen) == 9

    def test_ablating_the_resolved_question_withholds_it(self, fakes, tmp_path):
        qs = write_set(
            tmp_path,
            {**grounded("q1", "and the second one?"), "resolved_question": "what did the paper find second?"},
            direct("q2", "what is a median?"),
        )
        out = tmp_path / "runs"
        chain(qs, "--live", "label", "--ablate-resolved", *CUTOFFS, "--out", str(out))
        _, data = written(out)
        seen = fakes["route-label"].seen
        assert "what did the paper find second?" in seen and None in seen
        assert data["ablations"]["decider_input"]["raw_only"]

    def test_ablation_needs_a_live_run(self, questions, stored):
        jev, _ = stored
        with pytest.raises(CommandError, match="needs --live"):
            chain(questions, "--from-run", f"jev={jev}", "--ablate-resolved", *CUTOFFS, "--no-write")

    def test_live_jev_is_refused_off_the_proxy_tier(self, fakes, tmp_path):
        path = tmp_path / "private.json"
        path.write_text(
            json.dumps({"name": "p", "tier": "real", "questions": [grounded("q1", "what did the paper find?")]}),
            encoding="utf-8",
        )
        with pytest.raises(CommandError, match="public proxy question set only"):
            chain(str(path), "--live", "jev", *CUTOFFS, "--no-write")

    def test_an_unknown_live_decider_is_refused(self, questions):
        with pytest.raises(CommandError, match="--live names"):
            chain(questions, "--live", "gpt", *CUTOFFS, "--no-write")
