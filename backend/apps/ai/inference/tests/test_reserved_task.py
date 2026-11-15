"""The vision tasks are reached only through the composition root (IR-378,
IR-852, IR-1102).

ADR-056 §10 gives `describe_figure` its one caller, `figure_describer()`, and
ADR-067's amendment gives `transcribe_formula` its one, `formula_transcriber()`.
A file scan rather than a Django test, like `test_one_retrieval_stack.py`: what
is asserted is that no other module reaches for either.
"""

import pathlib
import re

import pytest

from testing.source_files import python_sources

APPS = pathlib.Path(__file__).resolve().parents[3]
INFERENCE = APPS / "ai" / "inference"
CALLERS = {"ai/composition.py"}


def _python_files():
    return [
        path
        for path in python_sources(APPS)
        if INFERENCE not in path.parents
    ]


@pytest.mark.parametrize("task, seam", [
    ("describe_figure", "figure_describer"),
    ("transcribe_formula", "formula_transcriber"),
])
def test_only_the_composition_root_asks_for_a_vision_task(task, seam):
    pattern = re.compile(rf"\b{task}\b")
    callers = {
        path.relative_to(APPS).as_posix()
        for path in _python_files()
        if pattern.search(path.read_text(encoding="utf-8").lower())
        and "tests" not in path.relative_to(APPS).parts
    }
    assert callers == CALLERS, (
        f"{sorted(callers - CALLERS)} reach for `{task}` directly; "
        f"go through CompositionRoot.{seam}()."
    )
