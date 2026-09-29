"""One way to reach a model, and it stays that way (IR-388).

`CompositionRoot.llm()` was the untasked, single-provider accessor every
caller used before Inference tasks existed. IR-378 expanded every caller onto
`llm_for(task)` one at a time, keeping `llm()` working meanwhile; this is the
contract half, and it deletes the accessor rather than deprecating it --
`llm_for(task)` is the only way in from here.

The cross-vendor machinery `llm()` used to reach (`cross_vendor_fallback_config`,
`LLM_FALLBACK_*`) was already deleted by IR-385, with its own regression guard
in `apps/ai/inference/tests/test_fallback.py::
TheCrossVendorPathIsDeletedNotDisabledTests` -- not repeated here.

The way this regresses is a caller reaching for the familiar bare accessor
because it is what an older commit or an old habit remembers.
"""

from __future__ import annotations

import pytest

from apps.ai.composition import CompositionRoot

pytestmark = pytest.mark.django_required


def test_the_untasked_accessor_is_gone():
    assert not hasattr(CompositionRoot, "llm"), (
        "CompositionRoot.llm() came back. Every caller reaches a model "
        "through llm_for(task) -- a bare accessor is the untasked path "
        "IR-388 removed, and the one every earlier Inference-task ticket "
        "left in place only so callers could migrate off it gradually."
    )
