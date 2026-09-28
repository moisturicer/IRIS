"""Refusing to start on a misconfigured Inference task (IR-379).

Per-task configuration multiplies the number of things that can be mistyped,
which is why ADR-021 §Amendment makes its no-silent-fall-through rule *more*
important rather than less. Two mistakes take the deployment down here:

* an **unknown task name** -- `LLM_ANWSER_MODEL` configures nothing, and
  without this check reads as a feature that was never switched on;
* a **configured task with no key** -- which would otherwise surface days
  later as a failed answer on a reader's question.

One thing is deliberately not a mistake: a task **nobody configured** is off.
That is how a developer with a single Groq key runs IRIS with no OpenRouter
account.

**Configured means an operator set a model, in the environment.** Not "a model
resolved from somewhere": `answer` inherits the flat `LLM_MODEL`, which *ships
with a default*, so a Profile carrying a model does not mean anybody chose one
-- and refusing on the shipped default would make a vendor account a
precondition for running IRIS at all, including its test suite. Setting
`LLM_MODEL` **does** count, inherited or not, so the long-standing flat
configuration is checked like any other.

Split like ``config.settings.validation``: the rules are pure functions over
values they are handed, and the caller raises. That is the only way a fail-fast
path gets verified without booting Django once per broken environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from django.core.exceptions import ImproperlyConfigured

from .profiles import (
    UnknownVendor,
    api_key_variables,
    model_variables,
    profile_for,
)
from .tasks import InferenceTask

#: The per-task suffixes a Profile reads. A variable shaped
#: ``LLM_<SEGMENT>_<SUFFIX>`` is claiming to configure a task called SEGMENT.
PROFILE_SUFFIXES = (
    "VENDOR",
    "BASE_URL",
    "API_KEY",
    "MODEL",
    "FALLBACK_MODELS",
    "REASONING",
)

#: Segments that are not task names. `LLM_FALLBACK_MODEL` predates per-task
#: configuration and still configures IR-321's cross-vendor entry, so reading
#: it as a task named `fallback` would refuse a correctly configured
#: deployment.
RESERVED_SEGMENTS = frozenset({"FALLBACK"})

#: Segments that *were* reserved and are not any more, and what replaced them.
#: A refusal here is the point: IR-383 moved resolution onto the `resolve`
#: Profile, so a leftover `LLM_RESOLUTION_MODEL` now configures nothing -- and
#: the value it most likely still holds is the withdrawn model that made
#: every follow-up fail. Silently ignoring it would reproduce that bug.
RENAMED_SEGMENTS = {"RESOLUTION": "LLM_RESOLVE_MODEL"}

_PREFIX = "LLM_"


@dataclass(frozen=True)
class TaskKeyState:
    """One task's key situation, as the pure rule needs to see it.

    ``model_variable`` is the variable that configures the task, or empty when
    nobody configured it -- carried rather than a bare flag so the refusal can
    name the variable that turned the task on as well as the one that is
    missing. For `answer` it may be the inherited flat ``LLM_MODEL``.
    """

    task: InferenceTask
    model_variable: str
    api_key: str
    key_variables: tuple[str, ...]

    @property
    def configured(self) -> bool:
        return bool(self.model_variable)


def _task_segment(name: str) -> Optional[str]:
    """The task a variable name claims to configure, or ``None``.

    Longest suffix first, so ``LLM_ANSWER_FALLBACK_MODELS`` is read as
    `answer`'s fallback list rather than as a task called ANSWER_FALLBACK.
    """
    if not name.startswith(_PREFIX):
        return None
    rest = name[len(_PREFIX) :]
    for suffix in sorted(PROFILE_SUFFIXES, key=len, reverse=True):
        if rest.endswith(f"_{suffix}"):
            segment = rest[: -len(suffix) - 1]
            return segment or None
    return None


def unknown_task_problems(names: Iterable[str]) -> tuple[str, ...]:
    """What is wrong with these variable names, by task name.

    One problem per mistyped segment rather than per variable: a typo repeated
    across a task's four variables is one mistake.
    """
    offenders: dict[str, str] = {}

    for name in names:
        segment = _task_segment(name)
        if segment is None or segment in RESERVED_SEGMENTS:
            continue
        if segment.lower() in {task.value for task in InferenceTask}:
            continue
        offenders.setdefault(segment, name)

    return tuple(
        _unknown_task_problem(segment, name)
        for segment, name in sorted(offenders.items())
    )


def _unknown_task_problem(segment: str, name: str) -> str:
    known = ", ".join(task.value for task in InferenceTask)
    replacement = RENAMED_SEGMENTS.get(segment)
    if replacement:
        # Naming the replacement rather than the whole set: this variable was
        # correct configuration until a named ticket moved it, so the operator
        # needs a rename, not a lesson about the task set.
        return (
            f"{name} no longer configures anything: question resolution moved "
            f"onto the `resolve` Inference task in IR-383. Move its value to "
            f"{replacement} and remove {name}. Leaving it set is how a "
            f"withdrawn model survives a redeploy and fails every follow-up."
        )
    return (
        f"{name} configures {segment.lower()!r}, which is not an Inference "
        f"task. The set is closed and lives in code: {known}. Fix the name or "
        f"remove the variable -- it currently configures nothing, so the "
        f"feature it looks like it enables is off."
    )


def missing_key_problems(states: Iterable[TaskKeyState]) -> tuple[str, ...]:
    """Which configured tasks cannot reach their vendor.

    Every problem, never the first: a deployment that fixes one variable per
    restart is a bad afternoon.
    """
    problems = []
    for state in states:
        if not state.configured or state.api_key.strip():
            continue
        where = " or ".join(state.key_variables)
        problems.append(
            f"The {state.task.value!r} Inference task is configured "
            f"({state.model_variable} is set) but has no vendor key. Set "
            f"{where}, or unset {state.model_variable} to leave the task off. "
            f"A task with no key is a deployment mistake, not an off switch: "
            f"every question routed to it would fail."
        )
    return tuple(problems)


def inference_configuration_problems(
    *, names: Iterable[str], keys: Iterable[TaskKeyState]
) -> tuple[str, ...]:
    """Everything wrong with this Inference configuration."""
    return unknown_task_problems(names) + missing_key_problems(keys)


def configured_environment() -> Mapping[str, str]:
    """Where a task name can be mistyped: the process environment and ``.env``.

    Both, because either can carry the typo and neither sees the other's. A
    mistyped name never becomes a Django setting -- nothing reads it -- so
    scanning ``settings`` would find nothing to complain about.
    """
    environment = dict(os.environ)
    for name, value in _dotenv_values().items():
        environment.setdefault(name, value)
    return environment


def _dotenv_values() -> Mapping[str, str]:
    """``backend/.env`` as python-decouple already parsed it, or nothing.

    Reached through the loaded repository rather than by re-reading the file:
    one parser, and no second opinion about quoting or comments.
    """
    try:
        from decouple import config

        return dict(config.config.repository.data)
    except (ImportError, AttributeError, TypeError):
        # A repository that is not a parsed file, or none loaded yet. Narrow
        # on purpose: swallowing everything here would turn a real fault into
        # silently reduced coverage, which is the failure this module exists
        # to prevent.
        return {}


def task_key_states(environment: Mapping[str, str]) -> tuple[TaskKeyState, ...]:
    """Each task's key situation, resolved through its Profile."""
    return tuple(
        TaskKeyState(
            task=task,
            model_variable=_model_variable_set_in(environment, task),
            api_key=profile_for(task).api_key,
            key_variables=api_key_variables(task),
        )
        for task in InferenceTask
    )


def _model_variable_set_in(
    environment: Mapping[str, str], task: InferenceTask
) -> str:
    """Which variable configured ``task``, in the environment, or empty.

    The environment rather than the resolved Profile, because `answer`
    inherits ``LLM_MODEL`` and that setting *ships with a default*: a Profile
    with a model does not mean an operator chose one, and refusing to start on
    the shipped default would make a vendor account a precondition for running
    IRIS at all -- including its test suite.
    """
    for variable in model_variables(task):
        if environment.get(variable, "").strip():
            return variable
    return ""


def verify_inference_configuration() -> None:
    """Refuse to start rather than fail on a reader's question.

    The same posture the rest of IRIS takes toward a missing secret: taking
    the deployment down is louder than serving requests that cannot work.
    """
    environment = configured_environment()
    try:
        keys = task_key_states(environment)
    except UnknownVendor as exc:
        # A vendor outside the sanctioned pair is the same class of typo, and
        # it would otherwise wait for the first call to that task.
        raise ImproperlyConfigured(str(exc)) from exc

    problems = inference_configuration_problems(
        names=environment.keys(), keys=keys
    )
    if problems:
        raise ImproperlyConfigured(
            "Inference configuration (IR-379):\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )
