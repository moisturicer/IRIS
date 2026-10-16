"""IR-598: the eval_conversations command end to end. No database, no vendor."""

import json

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from .test_conversation_scoring import review, run
from apps.ai.evaluation.conversations import FAMILIES, split_digests

from .test_conversations import conv, make_set


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("eval_conversations reached the network")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def _write(path, value):
    path.write_text(json.dumps(value))
    return str(path)


def test_validate_writes_then_checks_a_lock(tmp_path):
    data = make_set([conv("a"), conv("b", "A02", "held_out", "t2", ("Q",))])
    path = _write(tmp_path / "s.json", data)
    lock = str(tmp_path / "lock.json")
    call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                 write_lock=lock)
    call_command("eval_conversations", set=path, validate=True, min_conversations=1, lock=lock)
    data["conversations"][1]["topic"] = "moved"
    path = _write(tmp_path / "s.json", data)
    with pytest.raises(CommandError, match="validation failed"):
        call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                     lock=lock)


def test_validate_fails_below_the_readiness_count(tmp_path):
    path = _write(tmp_path / "s.json", make_set([conv("a")]))
    with pytest.raises(CommandError):
        call_command("eval_conversations", set=path, validate=True)


def _locked(tmp_path, data):
    path = _write(tmp_path / "s.json", data)
    lock = str(tmp_path / "lock.json")
    call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                 write_lock=lock)
    return path, lock, split_digests(data)


def test_score_writes_a_run_file_and_blocks_on_a_breach(tmp_path):
    data = make_set([conv(f"c{i}", FAMILIES[0]) for i in range(3)])
    path, lock, digests = _locked(tmp_path, data)
    manifest = {"set_digests": digests}
    cur = _write(tmp_path / "cur.json", run("current", manifest=manifest))
    ctl = _write(tmp_path / "ctl.json", run("controller", manifest=manifest))
    reviews = [review("c0"), review("c1", arm="controller", access_breach=True)]
    rev = _write(tmp_path / "r.json", reviews)
    out = tmp_path / "out"
    call_command("eval_conversations", set=path, score=True, reviews=rev, out=str(out),
                 runs=[f"current={cur}", f"controller={ctl}"], min_examples=1, lock=lock,
                 allow_draft=True)
    (written,) = out.iterdir()
    report = json.loads(written.read_text())
    assert report["enablement_blocked"] is True
    assert report["blocked_arms"] == ["controller"]
    assert "current" in report["arms"]


def test_score_refuses_unequal_conditions(tmp_path):
    path, lock, digests = _locked(tmp_path, make_set([conv("c0")]))
    manifest = {"set_digests": digests}
    cur = _write(tmp_path / "cur.json", run("current", manifest=manifest))
    ctl = _write(tmp_path / "ctl.json",
                 run("controller", manifest={**manifest, "data_policy": "other"}))
    rev = _write(tmp_path / "r.json", [review("c0")])
    with pytest.raises(CommandError, match="data_policy"):
        call_command("eval_conversations", set=path, score=True, reviews=rev, lock=lock,
                     allow_draft=True, runs=[f"current={cur}", f"controller={ctl}"],
                     out=str(tmp_path / "o"))
