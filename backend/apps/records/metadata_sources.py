"""The author's field-source decisions and the stale-save refusal (IR-833).

IR-830 decision 16: Publish tracks each autofillable field's source apart
from its value, so a late extraction never overwrites what the author did and
a reopened draft does not mistake a system placeholder for the author's words.
``Record.metadata_sources`` stores one decision per field:

- ``placeholder`` -- the dialog wrote it (the title made from the file name).
- ``automatic`` -- filled in from the PDF; ``previous`` is what Undo restores.
- ``accepted`` -- the author chose a value the PDF offered.
- ``authored`` -- the author typed or cleared it.
- ``dismissed`` -- the author turned the PDF's value down.

``source_revision`` names the manuscript revision a decision was made
against, opaque to the server. Nothing here is a confidence value.
"""

from rest_framework import status
from rest_framework.exceptions import APIException

from .metadata_suggestions import ABSTRACT_LIMIT
from .metadata_suggestions import FIELDS as _SUGGESTED

FIELDS = frozenset(_SUGGESTED)
STATES = frozenset({"placeholder", "automatic", "accepted", "authored", "dismissed"})
_KEYS = frozenset({"state", "source_revision", "previous"})
# Undo restores at most an abstract's worth of text.
_PREVIOUS_LIMIT = ABSTRACT_LIMIT
_REVISION_LIMIT = 64


class StaleDraft(APIException):
    """A save made from an older view of the draft (``409 stale_edit``)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "stale_edit"

    def __init__(self, current: int):
        super().__init__()
        # Set after init, which would turn the revision into a string: the
        # client compares it as the number every other response carries.
        self.detail = {
            "detail": "This draft was changed somewhere else. Reload it to see the newer version.",
            "code": "stale_edit",
            "details_revision": current,
        }


def metadata_sources_problem(value) -> str | None:
    """What is wrong with these decisions, or ``None``."""
    if not isinstance(value, dict):
        return "Send an object of field decisions."
    for field, decision in value.items():
        if field not in FIELDS:
            return f"'{field}' is not a field Publish fills in."
        if not isinstance(decision, dict) or set(decision) - _KEYS:
            return f"The decision for '{field}' must hold only state, source_revision and previous."
        if decision.get("state") not in STATES:
            return f"The decision for '{field}' has no known state."
        revision = decision.get("source_revision")
        if revision is not None and (not isinstance(revision, str) or len(revision) > _REVISION_LIMIT):
            return f"The decision for '{field}' names no valid source revision."
        previous = decision.get("previous")
        if previous is not None and (not isinstance(previous, str) or len(previous) > _PREVIOUS_LIMIT):
            return f"The decision for '{field}' holds an invalid previous value."
    return None
