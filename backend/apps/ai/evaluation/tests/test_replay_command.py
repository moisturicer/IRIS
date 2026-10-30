"""IR-606: a separate, free development smoke launch writes a scoreable run."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.ai.evaluation.conversations import lock_record, split_digests

from .test_conversations import conv, make_set
from apps.ai.tests.corpus import make_user


def _inputs(tmp_path):
    data = make_set([conv("d1", split="development")])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    return set_path, lock_path


@pytest.mark.db_required
@pytest.mark.django_db
def test_smoke_records_cost_and_public_evidence(tmp_path, monkeypatch, settings):
    set_path, lock_path = _inputs(tmp_path)
    user = make_user("ir606-command@cit.edu")
    monkeypatch.setenv("IRIS_EVAL_TOKEN", str(RefreshToken.for_user(user).access_token))
    monkeypatch.setattr("apps.ai.controller.versions.NEW_RUN_ENGINE", "controller-v1")
    settings.AI_DURABLE_ASK = False
    settings.AI_RESEARCH_LANE = "off"
    out = tmp_path / "runs"
    call_command("eval_replay_conversations", set=str(set_path), lock=str(lock_path),
                 case=["d1"], smoke=True,
                 out=str(out))
    (path,) = out.iterdir()
    run = json.loads(path.read_text())
    assert run["providers"] == "fake"
    assert run["conversations"][0]["cost"] == 0
    assert run["conversations"][0]["turns"][0]["usage_status"] == "missing"
    assert run["manifest"]["set_digests"] == split_digests(json.loads(set_path.read_text()))
    assert run["manifest"]["attempted_physical_calls"] == 0
    assert run["conversations"][0]["turns"][0]["saved_turn"] is not None


def test_held_out_case_is_rejected_before_network(tmp_path, monkeypatch):
    data = make_set([conv("h1", split="held_out")])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    with pytest.raises(CommandError, match="development case"):
        call_command("eval_replay_conversations", set=str(set_path), lock=str(lock_path),
                     case=["h1"], smoke=True)
