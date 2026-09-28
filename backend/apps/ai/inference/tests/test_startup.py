"""A misconfigured Inference task fails at startup, not on a question (IR-379).

Two shapes of mistake, and one non-mistake. A typo in a task name and a
configured task with no key both take the deployment down; a task nobody
configured is simply off, which is what lets this suite run on a machine with
no vendor account at all.

The rules are asserted as pure functions over crafted inputs -- the only way a
fail-fast path gets verified without booting Django once per broken
environment. One test does boot it, in a subprocess, to prove the check runs
at startup rather than on first use.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from apps.ai.inference import InferenceTask
from apps.ai.inference.startup import (
    TaskKeyState,
    configured_environment,
    inference_configuration_problems,
    missing_key_problems,
    unknown_task_problems,
)

BACKEND = Path(__file__).resolve().parents[4]


def _state(task, *, configured, api_key="", key_variables=("LLM_X_API_KEY",)):
    return TaskKeyState(
        task=task,
        model_variable=f"{task.settings_prefix}_MODEL" if configured else "",
        api_key=api_key,
        key_variables=key_variables,
    )


class UnknownTaskNameTests:
    def test_a_mistyped_task_name_is_a_problem(self):
        problems = unknown_task_problems(["LLM_ANWSER_MODEL"])

        assert len(problems) == 1
        # The offending value and the variable carrying it, so the typo is
        # fixable from the failure alone.
        assert "ANWSER" in problems[0]
        assert "LLM_ANWSER_MODEL" in problems[0]

    def test_the_message_lists_the_valid_tasks(self):
        (problem,) = unknown_task_problems(["LLM_ANWSER_MODEL"])

        for task in InferenceTask:
            assert task.value in problem

    def test_every_real_task_name_is_accepted(self):
        names = [
            f"{task.settings_prefix}_{suffix}"
            for task in InferenceTask
            for suffix in ("VENDOR", "BASE_URL", "API_KEY", "MODEL",
                           "FALLBACK_MODELS", "REASONING")
        ]

        assert unknown_task_problems(names) == ()

    def test_the_flat_and_legacy_llm_variables_are_not_task_names(self):
        """These predate per-task configuration and still configure real
        things: reading `LLM_FALLBACK_MODEL` as a task named `fallback` would
        refuse to start a deployment that is correctly configured."""
        assert unknown_task_problems([
            "LLM_BASE_URL",
            "LLM_API_KEY",
            "LLM_MODEL",
            "LLM_TEMPERATURE",
            "LLM_REASONING_EFFORT",
            "LLM_FALLBACK_BASE_URL",
            "LLM_FALLBACK_API_KEY",
            "LLM_FALLBACK_MODEL",
            "LLM_RESOLUTION_MODEL",
        ]) == ()

    def test_a_variable_outside_the_llm_namespace_is_ignored(self):
        assert unknown_task_problems(["VOYAGE_API_KEY", "DEBUG"]) == ()

    def test_one_typo_across_several_variables_is_reported_once(self):
        problems = unknown_task_problems(
            ["LLM_ANWSER_MODEL", "LLM_ANWSER_API_KEY", "LLM_ANWSER_VENDOR"]
        )

        assert len(problems) == 1


class MissingKeyTests:
    def test_a_configured_task_with_no_key_is_a_problem(self):
        (problem,) = missing_key_problems([
            _state(
                InferenceTask.SUMMARY,
                configured=True,
                key_variables=("LLM_SUMMARY_API_KEY",),
            )
        ])

        # Both the task and the variable, per the acceptance criterion.
        assert "summary" in problem
        assert "LLM_SUMMARY_API_KEY" in problem

    def test_an_unconfigured_task_is_off_rather_than_a_problem(self):
        assert missing_key_problems([
            _state(InferenceTask.DESCRIBE_FIGURE, configured=False)
        ]) == ()

    def test_a_configured_task_with_a_key_is_no_problem(self):
        assert missing_key_problems([
            _state(InferenceTask.SUMMARY, configured=True, api_key="sk-live")
        ]) == ()

    def test_a_blank_key_is_an_absent_key(self):
        """An unset shell variable interpolated into an env file yields
        ``KEY=``, which is as unconfigured as an absent line."""
        assert missing_key_problems([
            _state(InferenceTask.SUMMARY, configured=True, api_key="   ")
        ])

    def test_every_inherited_variable_is_named(self):
        (problem,) = missing_key_problems([
            _state(
                InferenceTask.ANSWER,
                configured=True,
                key_variables=("LLM_ANSWER_API_KEY", "LLM_API_KEY"),
            )
        ])

        assert "LLM_ANSWER_API_KEY" in problem
        assert "LLM_API_KEY" in problem

    def test_all_problems_are_reported_not_only_the_first(self):
        """A deployment that fixes one variable per restart is a bad
        afternoon."""
        problems = missing_key_problems([
            _state(InferenceTask.SUMMARY, configured=True),
            _state(InferenceTask.RESOLVE, configured=True),
        ])

        assert len(problems) == 2


class BothRulesTogetherTests:
    def test_a_clean_configuration_has_no_problems(self):
        assert inference_configuration_problems(names=[], keys=[]) == ()

    def test_both_kinds_of_mistake_surface_in_one_refusal(self):
        problems = inference_configuration_problems(
            names=["LLM_ANWSER_MODEL"],
            keys=[_state(InferenceTask.SUMMARY, configured=True)],
        )

        assert len(problems) == 2


class WhereATypoLivesTests:
    """A mistyped name never becomes a Django setting -- nothing reads it --
    so the scan has to look at the environment it was typed into."""

    pytestmark = pytest.mark.django_required

    def test_a_process_environment_variable_is_seen(self, monkeypatch):
        monkeypatch.setenv("LLM_ANWSER_MODEL", "some-model")

        assert "LLM_ANWSER_MODEL" in configured_environment()

    def test_a_dotenv_variable_is_seen(self, monkeypatch):
        """Reached through the repository python-decouple already parsed, so
        there is no second opinion about quoting or comments."""
        from decouple import config

        repository = config.config.repository
        monkeypatch.setitem(repository.data, "LLM_ANWSER_MODEL", "some-model")

        assert "LLM_ANWSER_MODEL" in configured_environment()


class StartupTests:
    """The check runs when Django starts, not when a reader asks something."""

    pytestmark = pytest.mark.django_required

    def _check(self, **overrides):
        environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.development"}
        environment.update(overrides)
        return subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=BACKEND,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_manage_py_check_refuses_a_configured_task_with_no_key(self):
        """CI catches it without booting a server."""
        result = self._check(LLM_SUMMARY_MODEL="some-model", LLM_SUMMARY_API_KEY="")

        assert result.returncode != 0
        assert "LLM_SUMMARY_API_KEY" in result.stderr + result.stdout

    def test_manage_py_check_refuses_an_unknown_task_name(self):
        result = self._check(LLM_ANWSER_MODEL="some-model")

        assert result.returncode != 0
        assert "ANWSER" in result.stderr + result.stdout

    def test_manage_py_check_passes_with_no_vendor_keys_at_all(self):
        """Running IRIS must not become conditional on having an account.

        Nothing configured, which is what a fresh checkout looks like: the
        shipped `LLM_MODEL` default is not a model anybody chose, so it does
        not make `answer` a configured task.
        """
        result = self._check(LLM_API_KEY="", LLM_ANSWER_API_KEY="", LLM_MODEL="")

        assert result.returncode == 0, result.stderr

    def test_manage_py_check_refuses_the_flat_settings_without_a_key(self):
        """`answer` inherits the flat keys, so a model set there is a
        configured task like any other -- this is the shape a long-standing
        deployment actually has, and it was the reported failure: a reader's
        question, not a deploy, discovering the missing key."""
        result = self._check(LLM_MODEL="some-model", LLM_API_KEY="")

        assert result.returncode != 0
        output = result.stderr + result.stdout
        assert "answer" in output
        # The variable that turned the task on, and both that could supply a
        # key: for `answer` the inherited flat one is a real answer.
        assert "LLM_MODEL is set" in output
        assert "LLM_API_KEY" in output
