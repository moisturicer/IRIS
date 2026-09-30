"""Where a run's commit comes from (IR-394).

A results file is only reproducible if it says which code produced it. The
command runs inside a container that has no git, so an environment variable
the caller sets from the host has to win, and "unknown" has to remain the
honest answer when nothing can say.
"""

import pytest

from apps.ai.management.commands import eval_retrieval
from apps.ai.management.commands.eval_retrieval import _git_commit


class _Done:
    def __init__(self, out):
        self.stdout = out


def test_the_environment_variable_wins_over_git(monkeypatch):
    monkeypatch.setenv("IRIS_GIT_COMMIT", "abc1234-dirty")
    monkeypatch.setattr(
        eval_retrieval.subprocess, "run",
        lambda *a, **k: pytest.fail("git must not be asked when the caller said"),
    )

    assert _git_commit() == "abc1234-dirty"


def test_a_blank_variable_falls_back_to_git(monkeypatch):
    monkeypatch.setenv("IRIS_GIT_COMMIT", "   ")
    monkeypatch.setattr(eval_retrieval.subprocess, "run", lambda *a, **k: _Done("def5678\n"))

    assert _git_commit() == "def5678"


def test_git_is_asked_to_mark_an_uncommitted_tree(monkeypatch):
    """`--dirty`: a run made from a modified tree must not read as the commit."""
    monkeypatch.delenv("IRIS_GIT_COMMIT", raising=False)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Done("def5678-dirty\n")

    monkeypatch.setattr(eval_retrieval.subprocess, "run", fake_run)

    assert _git_commit() == "def5678-dirty"
    assert "--dirty" in seen["cmd"]


def test_no_git_and_no_variable_is_unknown_not_a_guess(monkeypatch):
    monkeypatch.delenv("IRIS_GIT_COMMIT", raising=False)

    def no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(eval_retrieval.subprocess, "run", no_git)

    assert _git_commit() == "unknown"


def test_a_git_failure_is_unknown(monkeypatch):
    monkeypatch.delenv("IRIS_GIT_COMMIT", raising=False)
    monkeypatch.setattr(eval_retrieval.subprocess, "run", lambda *a, **k: _Done(""))

    assert _git_commit() == "unknown"
