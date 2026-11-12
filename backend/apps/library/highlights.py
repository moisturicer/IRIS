"""
A reader's highlights, apart from the HTTP layer (IR-583, ADR-065).

Two questions live here so the views stay thin:

* is what the client sent a well-formed passage (`clean`), and
* what does a stored highlight say to this reader now (`entry`): current, or
  stale because the Manuscript they are served is no longer the one it was made
  on. Nothing here ever changes a stored highlight's identity.
"""

import uuid

from rest_framework.exceptions import ValidationError

from apps.records.models import RecordVersion
from apps.records.versions import served_manuscript_identity

from .models import MAX_HIGHLIGHT_CONTEXT, MAX_HIGHLIGHT_QUOTE, MAX_HIGHLIGHT_REGIONS

CURRENT = "current"
STALE = "stale"


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def clean(data) -> dict:
    """A highlight's fields from a POST body, or a 400. A refused write stores nothing."""
    data = data if isinstance(data, dict) else {}
    errors = {}

    revision = data.get("manuscript_revision")
    try:
        revision = uuid.UUID(revision) if isinstance(revision, str) else None
    except ValueError:
        revision = None
    if revision is None:
        errors["manuscript_revision"] = ["Send the Manuscript revision the paper was opened at."]

    page = data.get("page")
    if not _is_int(page) or page < 1:
        errors["page"] = ["Say which page the passage is on."]

    quote = data.get("quote")
    quote = quote.strip() if isinstance(quote, str) else ""
    if not quote:
        errors["quote"] = ["Select the passage to highlight."]
    elif len(quote) > MAX_HIGHLIGHT_QUOTE:
        errors["quote"] = [f"A highlight holds at most {MAX_HIGHLIGHT_QUOTE:,} characters."]

    context = {}
    for key in ("prefix", "suffix"):
        text = data.get(key, "")
        if not isinstance(text, str) or len(text) > MAX_HIGHLIGHT_CONTEXT:
            errors[key] = [f"The text around a passage is at most {MAX_HIGHLIGHT_CONTEXT} characters."]
        else:
            context[key] = text

    regions = _regions(data.get("regions", []), errors)

    if errors:
        raise ValidationError(errors)
    return {
        "manuscript_revision": revision, "page": page, "quote": quote,
        "prefix": context["prefix"], "suffix": context["suffix"], "regions": regions,
    }


def _regions(value, errors) -> list:
    """ADR-031's page-fraction rectangles, `{page, left, top, right, bottom}`, each 0-1."""
    if not isinstance(value, list) or len(value) > MAX_HIGHLIGHT_REGIONS:
        errors["regions"] = [f"A highlight has at most {MAX_HIGHLIGHT_REGIONS} regions."]
        return []
    regions = []
    for region in value:
        try:
            page = region["page"]
            box = [float(region[k]) for k in ("left", "top", "right", "bottom")]
        except (TypeError, KeyError, ValueError):
            errors["regions"] = ["Each region names its page and its left, top, right and bottom."]
            return []
        left, top, right, bottom = box
        if (not _is_int(page) or page < 1 or not all(0.0 <= v <= 1.0 for v in box)
                or left >= right or top >= bottom):
            errors["regions"] = ["A region is a rectangle on its page, measured in fractions of it."]
            return []
        regions.append({"page": page, "left": left, "top": top, "right": right, "bottom": bottom})
    return regions


def state_for(highlight, identity) -> str:
    """`current` only while the reader is served exactly the bytes it was made on."""
    revision, sha256 = identity
    same = revision == highlight.manuscript_revision and sha256 == highlight.manuscript_sha256
    return CURRENT if same else STALE


def context_for(record, user) -> tuple:
    """What a list of one Record's highlights needs, asked once: the identity `user`
    is served, and `{revision: Version number}` for the Record's Versions."""
    return served_manuscript_identity(record, user), version_numbers(record)


def entry(highlight, context) -> dict:
    """
    What a reader who may read the Record is told about `highlight`, given
    `context_for(record, user)`. `open_version` is the Version that still holds a
    stale highlight's bytes, which the reader may or may not be allowed to open
    (the interface decides from what it may see).
    """
    identity, versions = context
    state = state_for(highlight, identity)
    return {
        "id": highlight.pk,
        "record_id": highlight.record_id,
        "available": True,
        "state": state,
        "page": highlight.page,
        "quote": highlight.quote,
        "prefix": highlight.prefix,
        "suffix": highlight.suffix,
        "regions": highlight.regions,
        "open_version": None if state == CURRENT else versions.get(highlight.manuscript_revision),
        "created_at": highlight.created_at,
    }


def unavailable(highlight) -> dict:
    """The only thing said of a highlight whose Record the reader cannot read: ids they supplied."""
    return {"id": highlight.pk, "record_id": highlight.record_id, "available": False}


def version_numbers(record) -> dict:
    """`{manuscript_revision: lowest Version number}` for a Record's Versions."""
    numbers = {}
    for revision, number in (
        RecordVersion.objects.filter(record=record, manuscript_revision__isnull=False)
        .order_by("-number").values_list("manuscript_revision", "number")
    ):
        numbers[revision] = number
    return numbers
