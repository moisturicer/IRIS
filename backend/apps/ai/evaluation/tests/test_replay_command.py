"""IR-606: a separate, free development smoke launch writes a scoreable run."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.conversations import lock_record

from .test_conversations import conv, make_set


def _inputs(tmp_path):
    data = make_set([conv("d1", split="development")])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    return set_path, lock_path


def test_held_out_case_is_rejected_before_network(tmp_path, monkeypatch):
    data = make_set([conv("h1", split="held_out")])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    with pytest.raises(CommandError, match="development case"):
        call_command("eval_replay_conversations", set=str(set_path), lock=str(lock_path),
                     case=["h1"], smoke=True, runtime_url="https://runtime.invalid")
