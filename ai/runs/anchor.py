"""A passage the reader selected in the paper, and how the runtime checks it (IR-581).

The browser sends the Record, the Manuscript revision it was shown, the page
and the quoted text. None of it is taken as evidence on the reader's word:
the quote must occur in the indexed text of the current Manuscript, on that
page, read under the reader's own grant. Only then may it reach a model.

The comparison is on a canonical form that ignores layout (line breaks,
spacing, a word split at a line end, ligatures) and nothing else, so the
words and numbers are the paper's. It is as precise as chunks are: a chunk
is labelled by the page it starts on, so the chunk that runs onto a page
counts for that page too.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

#: As for a highlight's quote (ADR-065 §3, `comments.MAX_QUOTE_LENGTH`).
MAX_QUOTE = 2_000

#: Refusals a reader can be told about, as the `status` of a 422.
OUT_OF_SCOPE = "selection_out_of_scope"
UNAVAILABLE = "selection_unavailable"
VERSION = "selection_version"
UNVERIFIED = "selection_unverified"


class Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Selection:
    record_id: int
    #: The Manuscript revision (UUID) the reader was shown.
    revision: str
    page: int
    #: Whitespace collapsed and trimmed, as the reader's browser stores it.
    quote: str

    def to_json(self) -> dict:
        return {"record_id": self.record_id, "revision": self.revision, "page": self.page, "quote": self.quote}

    @classmethod
    def from_json(cls, raw: dict) -> "Selection":
        return cls(int(raw["record_id"]), str(raw["revision"]), int(raw["page"]), str(raw["quote"]))


def _positive(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(name)
    return value


def parse(raw: dict) -> Selection:
    """The selection a request names; ValueError when malformed. Checks shape only."""
    record_id = _positive(raw.get("record_id"), "record_id")
    page = _positive(raw.get("page"), "page")
    try:
        revision = str(uuid.UUID(str(raw.get("manuscript_revision"))))
    except ValueError:
        raise ValueError("manuscript_revision") from None
    quote = " ".join(str(raw.get("quote") or "").split())
    if len(quote) < 2 or len(quote) > MAX_QUOTE:
        raise ValueError("quote")
    return Selection(record_id, revision, page, quote)


_SPLIT_WORD = re.compile(r"(?<=\w)-\s+(?=\w)")
_SPACE = re.compile(r"\s+")


def canonical(text: str) -> str:
    """`text` without its layout: ligatures expanded, line-end hyphens joined, no whitespace."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return _SPACE.sub("", _SPLIT_WORD.sub("", text))


def anchored(quote: str, page: int, chunks) -> bool:
    """Whether `quote` starts on `page` of `chunks`, `(source_page, text)` in reading order.

    Page `page`'s text is its own chunks and the last chunk that started
    before it, which may run onto it. A page with no chunk of its own has
    only that one, and only while a later chunk shows the paper goes on. A
    selection may run past the page into the chunks after it.
    """
    needle = canonical(quote)
    if not needle:
        return False
    text, spans = [], []
    at = 0
    for source_page, content in chunks:
        part = canonical(content or "")
        spans.append((source_page, at, at + len(part)))
        text.append(part)
        at += len(part)
    whole = "".join(text)
    own = [i for i, (p, _, _) in enumerate(spans) if p == page]
    before = [i for i, (p, _, _) in enumerate(spans) if p is not None and p < page]
    if before and (own or any(p is not None and p > page for p, _, _ in spans)):
        own.append(before[-1])
    starts = [(spans[i][1], spans[i][2]) for i in own]
    found = whole.find(needle)
    while found >= 0:
        if any(lo <= found < hi for lo, hi in starts):
            return True
        found = whole.find(needle, found + 1)
    return False


async def verify(conn, selection: Selection, scope: int | None) -> Selection:
    """`selection`, checked against what this reader may read now; Refused otherwise.

    `conn` is inside a transaction that `iris_authz.begin_research` bound to
    the reader's grant, so visibility, the disclosure gate (nothing unindexed
    is read) and the Paper Chat scope are PostgreSQL's, not this function's.
    """
    if scope is None or selection.record_id != scope:
        raise Refused(OUT_OF_SCOPE)
    revision = await conn.fetchval("SELECT iris_ai.research_source_revision($1)", selection.record_id)
    if revision is None:
        raise Refused(UNAVAILABLE)
    if revision != selection.revision:
        # Never answered from other bytes than the reader selected on.
        raise Refused(VERSION)
    rows = await conn.fetch(
        """SELECT c.source_page, c.content FROM iris_ai.research_chunks() c
             JOIN iris_ai.research_chunksets() cs ON cs.id = c.chunk_set_id AND cs.is_active
            WHERE c.record_id = $1 AND c.deleted_at IS NULL ORDER BY c.sequence, c.id""",
        selection.record_id,
    )
    if not anchored(selection.quote, selection.page, [(r["source_page"], r["content"]) for r in rows]):
        raise Refused(UNVERIFIED)
    return selection
