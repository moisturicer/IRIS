"""`describe_figure` is reserved, and nothing calls it (IR-378).

Declared so the task set is closed rather than grown later by surprise; its
implementation is a separate spec that first has to reverse ADR-025's
"no image ever leaves the deployment" clause. A file scan rather than a
Django test, like `test_one_retrieval_stack.py` -- what is being asserted is
that no module reaches for it.
"""

import pathlib

from testing.source_files import python_sources

APPS = pathlib.Path(__file__).resolve().parents[3]
INFERENCE = APPS / "ai" / "inference"


def _python_files():
    return [
        path
        for path in python_sources(APPS)
        if INFERENCE not in path.parents
    ]


def test_nothing_outside_the_inference_package_asks_for_describe_figure():
    callers = [
        str(path.relative_to(APPS))
        for path in _python_files()
        if "describe_figure" in path.read_text(encoding="utf-8").lower()
    ]
    assert callers == [], (
        f"{callers} reach for the reserved `describe_figure` task. It is "
        f"declared and unused until its own spec lands (it needs a figure "
        f"describer port, a crop port, and an ADR superseding ADR-025)."
    )
