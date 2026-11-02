"""An abstract recovered from a record's own manuscript (IR-703).

Bulk-loaded records arrive with no abstract; the controller answers from
abstracts, so this reads one back out of the paper's first chunks.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

#: Only the front matter is searched.
FRONT_CHUNKS = 8
MIN_CHARS = 200

_HEADING = re.compile(r"^\s*a\s?b\s?s\s?t\s?r\s?a\s?c\s?t\b[\s.:—-]*", re.I)
_INLINE = re.compile(r"\b(?:Abstract|ABSTRACT|A BSTRACT)\b[\s.:—-]*")
_DATED = re.compile(r"\(Dated:[^)]*\)\s*")
_TAIL = re.compile(r"\s*(?:Index Terms|Keywords|Key words)\b.*$", re.S)
_SENTENCE_END = re.compile(r".*[.!?](?=\s|$)", re.S)


def abstract_from(chunks: Iterable[tuple[Sequence[str], str]]) -> Optional[str]:
    """The abstract in (context_path, content) chunks in reading order, or None."""
    chunks = list(chunks)[:FRONT_CHUNKS]
    text = _headed(chunks) or _inline(chunks) or _dated(chunks)
    if text is None:
        return None
    text = " ".join(_TAIL.sub("", text).split())
    return text if len(text) >= MIN_CHARS else None


def _headed(chunks):
    for path, content in chunks:
        if path and _HEADING.match(str(path[-1])):
            return _HEADING.sub("", content, count=1)
    return None


def _inline(chunks):
    for _, content in chunks:
        match = _INLINE.search(content)
        if match:
            return content[match.end():]
    return None


def _dated(chunks):
    if not chunks:
        return None
    match = _DATED.search(chunks[0][1])
    if not match:
        return None
    # The chunk may end mid-sentence; keep only complete ones.
    complete = _SENTENCE_END.match(chunks[0][1][match.end():])
    return complete.group(0) if complete else None
