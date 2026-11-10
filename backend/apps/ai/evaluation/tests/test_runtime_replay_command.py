"""IR-740: `eval_replay_conversations --runtime-url` writes a runtime run in IR-606's file.

The runtime's reader edge is a scripted seam, so this proves the command's wiring,
manifest and labels. It makes no network call and spends nothing.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.conversations import lock_record, split_digests

from .test_conversations import conv, make_set
from .test_runtime_replay import Seam


def inputs(tmp_path, cases=None):
    data = make_set(cases or [conv("d1", split="development"), conv("h1", split="held_out",
                                                                      topic="other",
                                                                      papers=("Q",))])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    return set_path, lock_path, data


@pytest.fixture
def served(monkeypatch):
    seam = Seam()
    seen = {}

    def build(url, token):
        seen.update(url=url, token=token)
        return seam

    monkeypatch.setattr(
        "apps.ai.management.commands.eval_replay_conversations.runtime_seam", build)
    monkeypatch.setenv("IRIS_EVAL_TOKEN", "jwt-secret-value")
    return seen


def call(tmp_path, *extra, **kw):
    set_path, lock_path, data = inputs(tmp_path)
    out = tmp_path / "runs"
    call_command("eval_replay_conversations", *extra, set=str(set_path), lock=str(lock_path),
                 out=str(out), **kw)
    return data, [json.loads(p.read_text()) for p in out.iterdir()]


def test_a_runtime_smoke_writes_a_runtime_run_labelled_contract_evidence(tmp_path, served):
    data, [run] = call(tmp_path, case=["d1"], smoke=True, runtime_url="https://edge.example",
                       cache="cold")
    assert served == {"url": "https://edge.example", "token": "jwt-secret-value"}
    assert run["arm"] == "runtime" and run["providers"] == "fake"
    manifest = run["manifest"]
    assert manifest["engine_version"] == "ai-runtime-1" and manifest["controller_version"] is None
    assert manifest["protocol_version"] == "runs-reader-1"
    assert manifest["identity"] == {"engine": "ai-runtime-1", "transport": "runs-reader-1",
                                    "schema": "runtime-rows-1"}
    assert manifest["model_ids"] == {"agent": "scripted"}
    assert manifest["runtime"] == {"depth": "deep", "declared_by": "operator", "edge": "reader-edge"}
    assert manifest["set_digests"] == split_digests(data)
    assert manifest["cache_state"] == "cold" and manifest["attempted_physical_calls"] == 0
    assert run["evidence"]["kind"] == "contract" and run["evidence"]["human_reviewed"] is False
    assert run["conversations"][0]["turns"][0]["saved_turn"] is not None
    assert "jwt-secret-value" not in json.dumps(run)


def test_the_runtime_arm_needs_its_url(tmp_path, served):
    with pytest.raises(CommandError, match="--runtime-url"):
        call(tmp_path, case=["d1"], smoke=True, arm="runtime")


def test_held_out_cases_and_real_providers_are_still_gated_before_any_request(tmp_path, served):
    with pytest.raises(CommandError, match="development case"):
        call(tmp_path, case=["h1"], smoke=True, runtime_url="https://x")
    with pytest.raises(CommandError, match="approval ID"):
        call(tmp_path, case=["d1"], providers="real", runtime_url="https://x")
    assert served == {}
