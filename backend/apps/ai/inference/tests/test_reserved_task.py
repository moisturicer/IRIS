"""`describe_figure` is reached only through the composition root (IR-378, IR-852).

ADR-056 §10 gives the task its one caller, `figure_describer()`, used by
`figure_descriptions.py`. A file scan rather than a Django test, like
`test_one_retrieval_stack.py`: what is asserted is that no other module
reaches for it.
"""

import pathlib
import re

from testing.source_files import python_sources

APPS = pathlib.Path(__file__).resolve().parents[3]
INFERENCE = APPS / "ai" / "inference"
CALLERS = {"ai/composition.py"}
TASK = re.compile(r"\bdescribe_figure\b")


def _python_files():
    return [
        path
        for path in python_sources(APPS)
        if INFERENCE not in path.parents
    ]


def test_only_the_composition_root_asks_for_describe_figure():
    callers = {
        path.relative_to(APPS).as_posix()
        for path in _python_files()
        if TASK.search(path.read_text(encoding="utf-8").lower())
        and "tests" not in path.relative_to(APPS).parts
    }
    assert callers == CALLERS, (
        f"{sorted(callers - CALLERS)} reach for `describe_figure` directly; "
        f"go through CompositionRoot.figure_describer() (IR-852)."
    )
