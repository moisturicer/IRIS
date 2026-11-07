"""Publish suggestions from a stored LlamaExtract reading (IR-846, ADR-056 §15).

Turns one ``ManuscriptMetadata`` result into IR-833's ``fields`` entries. Each
value keeps the page and the matching text LlamaExtract cited, the region of
the parse's line boxes holding that text, and the confidence LlamaExtract
reported. IRIS never computes or guesses a confidence: an unreported one is
``None`` (IR-830 decision 15).

Only a title or abstract may be filled in unasked, and only when
``PUBLISH_AUTOFILL_MIN_CONFIDENCE`` is set, the reported confidence reaches
it, and both the cited text and the value are found on the cited page of
the parse. Unset, every value is offered.
Nothing but the five fields is ever read from the vendor's values.

Pure: reads the stored result and the stored parse, calls nothing.
"""

import re
from typing import Any, Mapping, Optional

from django.conf import settings
from django.utils import timezone

SOURCE = "llamaextract"
BASIS = "cited_text"

# Past the task's own hard limit (its timeout plus 60 s), so a reading is
# never declared dead while its worker can still write it back.
STALE_GRACE_SECONDS = 120

_AUTO_FIELDS = frozenset({"title", "abstract"})
_WORD = re.compile(r"[^\W_]+")


def fields_from_reading(result: Mapping[str, Any], raw_parse: Mapping[str, Any], *, limits) -> dict:
    """One entry per field LlamaExtract read cleanly, ``None`` for the rest.

    ``limits`` is the suggestions module's (title, abstract, author, keyword,
    max keywords), so an overlong value is offered whole and never applied.
    """
    values = result.get("values") or {}
    metadata = result.get("field_metadata") or {}
    parsed = {
        "title": _text(values.get("title")),
        "abstract": _text(values.get("abstract")),
        "authors": _names(values.get("authors")),
        "keywords": _names(values.get("keywords")),
        "publication_year": _year(values.get("publication_year")),
    }
    exceeds = {
        "title": lambda v: len(v) > limits.title,
        "abstract": lambda v: len(v) > limits.abstract,
        "authors": lambda v: any(len(name) > limits.author for name in v),
        "keywords": lambda v: len(v) > limits.max_keywords or any(len(k) > limits.keyword for k in v),
        "publication_year": lambda v: False,
    }
    threshold = settings.PUBLISH_AUTOFILL_MIN_CONFIDENCE
    lines = _LineIndex(raw_parse)
    fields = {}
    for name, value in parsed.items():
        if value is None:
            fields[name] = None
            continue
        page, matching = _citation(metadata.get(name))
        confidence = _confidence(metadata.get(name))
        region = lines.locate(page, matching) if page is not None and matching else None
        too_long = exceeds[name](value)
        confident = threshold is not None and confidence is not None and confidence >= threshold
        # The value itself, not only the citation, must be on the cited page:
        # a citation can point at other text than the value it vouches for.
        found = region is not None and lines.locate(page, value) is not None
        fields[name] = {
            "value": value,
            "source": SOURCE,
            "basis": BASIS,
            "page": page,
            "region": region,
            "matching_text": matching,
            "confidence": confidence,
            "auto_apply": name in _AUTO_FIELDS and confident and found and not too_long,
            "exceeds_limit": too_long,
            "low_confidence": threshold is not None and confidence is not None and confidence < threshold,
        }
    return fields


def reading_is_stale(reading) -> bool:
    """A reading still queued or running past its budget: its worker died.

    A running reading is timed from its claim, a queued one from its
    creation, so a reading that waited behind other parses gets its whole
    budget once a worker takes it.
    """
    budget = settings.LLAMAEXTRACT_TIMEOUT_SECONDS + STALE_GRACE_SECONDS
    since = reading.started_at or reading.created_at
    return (timezone.now() - since).total_seconds() > budget


# -- values -------------------------------------------------------------------


def _text(value) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _names(value) -> Optional[list[str]]:
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if isinstance(item, str) and (name := " ".join(item.split())) and name not in out:
            out.append(name)
    return out or None


def _year(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        return None
    return value if 1000 <= value <= timezone.now().year + 1 else None


# -- citations ----------------------------------------------------------------


def _field_meta(meta) -> Mapping[str, Any]:
    # An array field may carry one entry per item; its first cited one stands.
    if isinstance(meta, list):
        return next((m for m in meta if isinstance(m, dict) and m.get("citation")), {})
    return meta if isinstance(meta, dict) else {}


def _citation(meta) -> tuple[Optional[int], Optional[str]]:
    for cited in _field_meta(meta).get("citation") or []:
        if not isinstance(cited, dict):
            continue
        page, text = cited.get("page"), cited.get("matching_text")
        if isinstance(page, int) and not isinstance(page, bool) and page >= 1 and isinstance(text, str) and text.strip():
            return page, text.strip()
    return None, None


def _confidence(meta) -> Optional[float]:
    # Only the field's own reported value; an array's items are never combined.
    value = (meta if isinstance(meta, dict) else {}).get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 <= value <= 1 else None


class _LineIndex:
    """The parse's grounded lines per page, as words, to find cited text in."""

    def __init__(self, raw_parse: Mapping[str, Any]):
        self._pages = {page.get("page_number"): page for page in raw_parse.get("grounded_items") or []}
        self._cache: dict[int, list[tuple[str, int, Mapping[str, float]]]] = {}

    def locate(self, page: int, text: str) -> Optional[dict]:
        """The box around the lines holding ``text`` on ``page``, or ``None``."""
        wanted = [w.lower() for w in _WORD.findall(text)]
        if not wanted:
            return None
        words = self._words(page)
        stream = [word for word, _, _ in words]
        for start in range(len(stream) - len(wanted) + 1):
            if stream[start:start + len(wanted)] == wanted:
                boxes = {line: box for _, line, box in words[start:start + len(wanted)]}
                return _union(page, boxes.values())
        return None

    def _words(self, page: int):
        if page not in self._cache:
            words = []
            for index, (line_text, box) in enumerate(_lines(self._pages.get(page, {}).get("items"))):
                words.extend((w.lower(), index, box) for w in _WORD.findall(line_text))
            self._cache[page] = words
        return self._cache[page]


def _lines(items):
    """Grounded lines in reading order, from the innermost items that have them."""
    for item in items or ():
        children = item.get("items") or []
        if any((child.get("grounding") or {}).get("lines") for child in children):
            yield from _lines(children)
            continue
        source = str(item.get("md") or "")
        for line in (item.get("grounding") or {}).get("lines") or []:
            span, box = line.get("span"), line.get("bbox")
            if isinstance(span, list) and len(span) == 2 and isinstance(box, dict):
                yield source[span[0]:span[1]], box


def _union(page: int, boxes) -> dict:
    boxes = list(boxes)
    return {
        "page": page,
        "left": min(float(b["x"]) for b in boxes),
        "top": min(float(b["y"]) for b in boxes),
        "right": max(float(b["x"]) + float(b["w"]) for b in boxes),
        "bottom": max(float(b["y"]) + float(b["h"]) for b in boxes),
    }
