"""A passage the reader selected in the paper, and what the runtime finds about it (IR-581).

The browser sends the Record, the Manuscript revision it was shown, the page
and the quoted text. None of it is taken as evidence on the reader's word,
and none of it is refused for not matching: the question is always asked.
Just before the model is called, the runtime checks the selection under the
reader's own grant and tells the model what it found, so the model can look
for the passage itself:

- whether the quote starts on that page of the text the model can read;
- whether it was selected on that same Manuscript version, a different one,
  or one the page did not name.

One thing withholds it: a paper this reader cannot read, or one with no
indexed text (the disclosure gate has not let it through). Then the quote
never reaches the model, which is told only that the selection could not be
used.

The comparison is on the quote's letters and digits, in order: case,
spacing, punctuation and layout are ignored, because the PDF's text layer
and the indexed text disagree on them ("ad-dresses" against "addresses",
"TPS20,21" against "TPS 20,21", curly against straight quotes). The words and
numbers must still be the paper's, and a decimal point or digit group inside a
number is kept, so "1.5" never passes for "15". It is as precise as chunks
are: a chunk is labelled by the page it starts on, so the chunk that runs onto
a page counts for that page too.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

#: As for a highlight's quote (ADR-065 §3, `comments.MAX_QUOTE_LENGTH`).
MAX_QUOTE = 2_000

#: The runtime answers with a pin that cannot be sent a selection (before research-12).
UNSUPPORTED = "selection_unsupported"

#: How the selection's version compares with the one the model can read.
SAME_VERSION = "same"
OTHER_VERSION = "different"
UNKNOWN_VERSION = "unknown"


class Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Selection:
    record_id: int
    #: The Manuscript revision (UUID) the reader was shown; None where the page named none.
    revision: str | None
    page: int
    #: Whitespace collapsed and trimmed, as the reader's browser stores it.
    quote: str

    def to_json(self) -> dict:
        return {"record_id": self.record_id, "revision": self.revision, "page": self.page, "quote": self.quote}

    @classmethod
    def from_json(cls, raw: dict) -> "Selection":
        revision = raw.get("revision")
        return cls(int(raw["record_id"]), str(revision) if revision else None, int(raw["page"]), str(raw["quote"]))


@dataclass(frozen=True)
class Assessed:
    """A selection, and what the runtime found about it just now."""

    selection: Selection
    #: The quote starts on its page of the indexed text the model can read.
    found_on_page: bool
    #: SAME_VERSION, OTHER_VERSION or UNKNOWN_VERSION.
    version: str

    def to_json(self) -> dict:
        return {**self.selection.to_json(), "found_on_page": self.found_on_page, "version": self.version}


def _positive(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(name)
    return value


def parse(raw: dict) -> Selection:
    """The selection a request names; ValueError when malformed. Checks shape only."""
    record_id = _positive(raw.get("record_id"), "record_id")
    page = _positive(raw.get("page"), "page")
    revision = raw.get("manuscript_revision")
    if revision is not None:
        try:
            revision = str(uuid.UUID(str(revision)))
        except ValueError:
            raise ValueError("manuscript_revision") from None
    quote = " ".join(str(raw.get("quote") or "").split())
    if len(quote) < 2 or len(quote) > MAX_QUOTE:
        raise ValueError("quote")
    return Selection(record_id, revision, page, quote)


#: A "." or "," between two digits: part of the number, so kept.
_IN_NUMBER = re.compile(r"(?<=\d)[.,](?=\d)")


def canonical(text: str) -> str:
    """`text`'s letters and digits in order, casefolded, with the separators inside numbers kept."""
    text = unicodedata.normalize("NFKC", text).casefold()
    # One stand-in each, so "1.5" and "15" stay different while other punctuation goes.
    text = _IN_NUMBER.sub(lambda m: "\x01" if m.group(0) == "." else "\x02", text)
    return "".join(ch for ch in text if ch.isalnum() or ch in "\x01\x02")


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


async def assess(conn, selection: Selection) -> Assessed | None:
    """What this reader's grant finds about `selection` now; None when its paper may not be read.

    `conn` is inside a transaction that `iris_authz.begin_research` bound to
    the reader's grant, so visibility, the disclosure gate (nothing unindexed
    is read) and a Paper Chat scope are PostgreSQL's, not this function's.
    None means the quote must not reach a model; anything else is told to it.
    """
    revision = await conn.fetchval("SELECT iris_ai.research_source_revision($1)", selection.record_id)
    if revision is None:
        return None
    rows = await conn.fetch(
        """SELECT c.source_page, c.content FROM iris_ai.research_chunks() c
             JOIN iris_ai.research_chunksets() cs ON cs.id = c.chunk_set_id AND cs.is_active
            WHERE c.record_id = $1 AND c.deleted_at IS NULL ORDER BY c.sequence, c.id""",
        selection.record_id,
    )
    if not rows:
        return None
    version = (UNKNOWN_VERSION if selection.revision is None
               else SAME_VERSION if selection.revision == revision else OTHER_VERSION)
    found = anchored(selection.quote, selection.page, [(r["source_page"], r["content"]) for r in rows])
    return Assessed(selection, found, version)
