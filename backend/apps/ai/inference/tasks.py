"""The closed set of Inference tasks (IR-378, ADR-021 §Amendment).

Four names, defined here and nowhere else. A caller asks for a task rather
than for "the LLM", and an unrecognised name raises instead of falling
through to a default -- ADR-021's no-silent-fall-through rule, which the
amendment says matters more now that configuration is per task.

``task`` alone is avoided in shared code because Celery owns that word.
"""

from __future__ import annotations

from enum import Enum
from typing import Union


class InferenceTask(Enum):
    """What a model is being asked to do.

    ``DESCRIBE_FIGURE`` is declared and unused: its implementation is a
    separate spec (it reverses ADR-025's no-image-leaves-the-deployment
    clause and needs two new ports), and reserving the name here keeps the
    set closed rather than growing it later by surprise.
    """

    ANSWER = "answer"
    RESOLVE = "resolve"
    SUMMARY = "summary"
    DESCRIBE_FIGURE = "describe_figure"

    @property
    def settings_prefix(self) -> str:
        """The settings namespace for this task, e.g. ``LLM_ANSWER``."""
        return f"LLM_{self.name}"

    @property
    def breaker_key(self) -> str:
        """This task's key into the circuit breaker registry (IR-386).

        A task's own namespace, distinct from `LLMProviderConfig.key`'s
        `base_url::model` -- two tasks pointed at the same vendor and model
        would otherwise share a breaker, so one task's rate limiting could
        stop an unrelated task from answering.
        """
        return f"inference-task::{self.value}"


class UnknownInferenceTask(ValueError):
    """A name that is not one of the four."""


def inference_task(name: Union[InferenceTask, str]) -> InferenceTask:
    """Coerce a task name to its ``InferenceTask``, or raise."""
    if isinstance(name, InferenceTask):
        return name
    try:
        return InferenceTask(name)
    except ValueError as exc:
        known = ", ".join(task.value for task in InferenceTask)
        raise UnknownInferenceTask(
            f"{name!r} is not an Inference task. The set is closed: {known}."
        ) from exc
