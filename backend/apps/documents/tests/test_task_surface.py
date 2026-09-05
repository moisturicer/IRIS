"""What ``apps.documents.tasks`` no longer contains (IR-107).

A guard, not a unit test. The prototype extractor chain it names was three
undeclared libraries behind a loop that swallowed every ``ImportError`` —
which is why it appeared to work on a developer machine and raised on a clean
install. Naming the deleted symbols here makes a revert loud.

Needs Django loaded (the module imports Celery and Django utilities) but no
database.
"""

import pytest

from apps.documents import tasks

pytestmark = [pytest.mark.django_required]


@pytest.mark.parametrize(
    "name",
    [
        "_run_extraction_chain",
        "_extract_with_opendataloader",
        "_extract_with_pymupdf",
        "_extract_with_tesseract",
        "_EXTRACTORS",
    ],
)
def test_the_prototype_extractor_chain_is_gone(name):
    assert not hasattr(tasks, name), f"{name} is back in apps.documents.tasks"


def test_extraction_goes_through_the_structured_extractor_port():
    """The one seam. If this stops being where the extractor comes from, the
    task's tests are exercising something the worker does not run."""
    from apps.ai.extraction import StructuredExtractor

    assert isinstance(tasks._build_extractor(), StructuredExtractor)
