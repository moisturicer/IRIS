"""Local research tools for one run (IR-719, ADR-049 §5, §9).

One transaction per call under the run's grant; the row policy decides
what is readable. Handles resolve only in their run, until expiry, on the
source they were read from. Keyword search only; providers stay gated.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import asyncpg

from ai.research import metadata
from ai.runs.store import RunStore

APP_NAME = "iris-ai-research"
#: Mirrors Django's keyword index (`apps.ai.keyword_index.CONFIG`).
CONFIG = "english"
SEARCH_LIMIT = 20
PAGE_PASSAGES = 20
OUTLINE_CHUNKS = 2000
RECALL_LIMIT = 50
#: Passages one Manuscript may hold before a whole read is refused, not cut short (IR-733).
MANUSCRIPT_PASSAGES = 10000
#: Bytes a returned passage's handle, page and section add around its text, as an allowance.
PASSAGE_FRAME_BYTES = 200
#: Bytes a read's coverage block (spans, ranges, counts) adds, as an allowance; each listed page adds more.
READING_FRAME_BYTES = 800
PAGE_ENTRY_BYTES = 8
#: The shortest repeat at a passage's start taken as extraction overlap rather than coincidence.
MIN_OVERLAP_CHARS = 24
#: Element kinds whose rendering is not interpreted: the text carries them, never what they show.
FORMULA, CAPTION = "formula", "caption"

OK, NO_MATCH, PARTIAL, UNAVAILABLE = "ok", "no_match", "partial", "unavailable"
#: A reference fits several papers; the reader is asked, never answered for (IR-750).
AMBIGUOUS = "ambiguous"
#: A paper that can be named but has no Manuscript read: nothing to read, not nothing found (IR-731).
NO_MANUSCRIPT = "no_manuscript"


@dataclass(frozen=True)
class Source:
    """The Manuscript revision a read came from."""

    record_id: int
    chunk_set_id: int
    extraction_hash: str

    @property
    def revision(self) -> str:
        return f"{self.chunk_set_id}:{self.extraction_hash}"


@dataclass(frozen=True)
class RecordRef:
    handle: str
    record_id: int
    title: str
    #: None for a paper with no Manuscript read yet: it can be named, not read (IR-750).
    source: Source | None


@dataclass(frozen=True)
class PassageRef:
    handle: str
    record_id: int
    page: int | None
    section: str
    text: str
    source: Source
    #: Leading characters of `text` that repeat the previous passage, left out when shown (IR-733).
    overlap: int = 0


@dataclass(frozen=True)
class Section:
    section: str
    heading: str
    level: int
    first_page: int | None
    last_page: int | None


@dataclass(frozen=True)
class Coverage:
    returned: int = 0
    #: Unknown is None, never zero.
    total: int | None = None
    truncated: bool = False
    #: Readable Records with an active Manuscript that the call looked at.
    inspected_records: int | None = None


@dataclass(frozen=True)
class Span:
    """Passages `first`..`last`, 1-based in document order, and the pages they fall on."""

    first: int
    last: int
    first_page: int | None
    last_page: int | None


@dataclass(frozen=True)
class Reading:
    """What one read of a whole Manuscript returned, and what it did not (IR-733).

    Text is extracted text only: nothing here interprets a figure or a formula.
    """

    #: Passages in the Manuscript, all of which a complete read returns.
    passages: int
    #: The stretch this read returned; None when nothing fitted or nothing was left.
    covered: Span | None = None
    #: The stretches this read did not return, in document order.
    missing: tuple[Span, ...] = ()
    #: Pages the extraction reported; None when it did not say.
    pages: int | None = None
    #: Reported pages no passage starts on: either no text was extracted from them, or a
    #: passage starting on an earlier page runs onto them. Never claimed as either.
    pages_no_passage_starts_on: tuple[int, ...] = ()
    #: Passages carrying a formula or a caption, whose visual content is not interpreted.
    formulas: int = 0
    captions: int = 0
    #: Repeated characters left out of the returned passages.
    overlap_chars: int = 0
    #: The passage to continue after; None once the Manuscript is read to its end, or when a
    #: first read had no room for even one passage (`exceeds_room`).
    continue_after: str | None = None
    title: str = ""


@dataclass(frozen=True)
class Match:
    """One reference a reader used and the papers it names (IR-750)."""

    #: 1-based position among the call's references, names first, then ids.
    reference: int
    #: "title" or "record_id".
    kind: str
    #: exact_title, short_title, title_phrase, record_id, ambiguous or none.
    match: str
    records: tuple[RecordRef, ...] = ()
    #: The title tier an ambiguous reference matched at.
    basis: str | None = None


@dataclass(frozen=True)
class Count:
    """An exact metadata count over the reader's readable Records (IR-750).

    A total of the catalogue as this reader may see it, never a topic estimate.
    """

    total: int
    #: (name, value) pairs as applied, taxonomy names as the catalogue spells them.
    filters: tuple[tuple[str, object], ...] = ()
    group_by: str | None = None
    #: (value, count) per group, in value order.
    groups: tuple[tuple[object, int], ...] = ()
    #: Counted Records with no value for `group_by`.
    ungrouped: int = 0
    #: The Paper Chat Record the count was confined to, if any.
    scope_record_id: int | None = None
    #: The Records counted: provenance for rechecks, never shown to a model or reader.
    population: frozenset[int] = frozenset()
    relative_to: str = metadata.RELATIVE_TO

    @property
    def figures(self) -> set[int]:
        """Every number this count computed."""
        return {self.total, self.ungrouped, *(n for _, n in self.groups)}

    @property
    def stated(self) -> set[int]:
        """Numbers that, stated in an answer, report this count: its total or a group's size."""
        return {self.total, *(n for _, n in self.groups)}


@dataclass(frozen=True)
class ToolResult:
    status: str
    reason: str | None = None
    records: tuple[RecordRef, ...] = ()
    matches: tuple[Match, ...] = ()
    count: Count | None = None
    passages: tuple[PassageRef, ...] = ()
    sections: tuple[Section, ...] = ()
    reading: Reading | None = None
    coverage: Coverage = field(default_factory=Coverage)
    dependencies: frozenset[Source] = frozenset()
    #: Provider calls the tool would make; none runs here.
    provider_operations: tuple[str, ...] = ()

    @classmethod
    def unavailable(cls, reason: str, **kw) -> "ToolResult":
        return cls(UNAVAILABLE, reason, **kw)


def _headings(title: str, path) -> list[str]:
    return [part for part in path or () if part != title]


def section_id(path: tuple[str, ...]) -> str:
    """Django's `read_papers` section id, so outlines agree across runtimes."""
    key = "\x1f".join(part.casefold() for part in path)
    return "S" + hashlib.sha256(key.encode()).hexdigest()[:8]


def _is_int(value) -> bool:
    return type(value) is int


def overlap(previous: str, text: str) -> int:
    """Characters at the start of `text` that repeat the end of `previous`.

    Only a repeat of at least MIN_OVERLAP_CHARS counts, so a shared word is never dropped.
    """
    if len(text) < MIN_OVERLAP_CHARS:
        return 0
    probe = text[:MIN_OVERLAP_CHARS]
    start = previous.find(probe, max(0, len(previous) - len(text)))
    while start != -1:
        if text.startswith(previous[start:]):
            return len(previous) - start
        start = previous.find(probe, start + 1)
    return 0


def shown_bytes(text: str) -> int:
    """What `text` costs once JSON-encoded in a tool result and again as message content."""
    return len(json.dumps(json.dumps(text, ensure_ascii=False), ensure_ascii=False).encode("utf-8"))


def _span(rows, first: int, last: int) -> Span:
    """Rows `first`..`last` (0-based, inclusive) as a 1-based Span."""
    pages = [r["source_page"] for r in rows[first:last + 1] if r["source_page"] is not None]
    return Span(first + 1, last + 1, min(pages, default=None), max(pages, default=None))


def _journalled(reading: Reading) -> dict:
    """A read's coverage as numbers only, for the run journal."""
    covered = reading.covered
    return {
        "passages": reading.passages, "covered": [covered.first, covered.last] if covered else None,
        "missing": [[m.first, m.last] for m in reading.missing], "pages": reading.pages,
        "pages_no_passage_starts_on": len(reading.pages_no_passage_starts_on), "formulas": reading.formulas,
        "captions": reading.captions, "overlap_chars": reading.overlap_chars,
    }


class _Refused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ResearchTools:
    def __init__(self, dsn: str, grant: str | None, run_id, fence: int,
                 scope_record_id: int | None = None, *, embedding_provider=None, embedding_ledger=None):
        self.dsn = dsn
        self.grant = grant
        self.run_id = run_id
        self.fence = fence
        self.scope = scope_record_id
        self.embedding_provider = embedding_provider
        self.embedding_ledger = embedding_ledger

    @asynccontextmanager
    async def _session(self):
        conn = await asyncpg.connect(self.dsn, server_settings={"application_name": APP_NAME})
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        try:
            async with conn.transaction():
                if not self.grant:
                    raise _Refused("unauthorized")
                try:
                    claims = await conn.fetchval(
                        "SELECT iris_authz.begin_research($1, 'reader_session')", self.grant)
                except asyncpg.InsufficientPrivilegeError:
                    raise _Refused("unauthorized") from None
                # Held to commit, so Stop or deletion cannot interleave.
                run = await conn.fetchrow(
                    "SELECT state, fence, reader_id FROM iris_ai.ask_run WHERE id = $1 FOR SHARE",
                    self.run_id)
                if (run is None or run["state"] != "running" or run["fence"] != self.fence
                        or run["reader_id"] != int(claims["sub"])):
                    raise _Refused("run_ended")
                yield conn
        finally:
            await conn.close()

    async def _call(self, name: str, body) -> ToolResult:
        try:
            async with self._session() as conn:
                result = await body(conn)
                coverage = result.coverage
                await RunStore._journal(conn, self.run_id, "tool", {
                    "tool": name, "status": result.status, "returned": coverage.returned,
                    "total": coverage.total, "truncated": coverage.truncated,
                    "inspected_records": coverage.inspected_records,
                    "sources": sorted(d.revision for d in result.dependencies),
                    **({"reading": _journalled(result.reading)} if result.reading else {}),
                })
                return result
        except _Refused as refused:
            return ToolResult.unavailable(refused.reason)

    async def _handles(self, conn, rows) -> list[str]:
        """Issue one handle per (prefix, record, chunk set, chunk), expiring with the run."""
        handles = [prefix + secrets.token_hex(10) for prefix, *_ in rows]
        await conn.executemany(
            """INSERT INTO iris_ai.research_handle
                   (handle, run_id, record_id, chunk_set_id, chunk_id, expires_at)
               SELECT $1, id, $3, $4, $5, deadline_at FROM iris_ai.ask_run WHERE id = $2""",
            [(h, self.run_id, record, chunk_set, chunk)
             for h, (_, record, chunk_set, chunk) in zip(handles, rows)],
        )
        return handles

    async def _resolve(self, conn, handle, kind: str):
        """(title, Source or None, chunk id) for a live handle of this run, or raise _Refused.

        The Source is None for a paper with no Manuscript read, which has nothing to read.
        """
        if not isinstance(handle, str) or not handle.startswith(kind):
            raise _Refused("unknown_handle")
        bound = await conn.fetchrow(
            """SELECT record_id, chunk_set_id, chunk_id FROM iris_ai.research_handle
                WHERE handle = $1 AND run_id = $2 AND expires_at > now()""",
            handle, self.run_id,
        )
        if bound is None:
            raise _Refused("unknown_handle")
        current = await conn.fetchrow(
            """SELECT r.title, cs.id AS chunk_set_id, cs.extraction_hash
                 FROM public.records_record r
                 LEFT JOIN iris_ai.research_chunksets() cs ON cs.record_id = r.id AND cs.is_active
                WHERE r.id = $1 AND ($2::bigint IS NULL OR r.id = $2)""",
            bound["record_id"], self.scope,
        )
        # Unreadable now is indistinguishable from never issued.
        if current is None:
            raise _Refused("unknown_handle")
        if current["chunk_set_id"] != bound["chunk_set_id"]:
            raise _Refused("source_replaced")
        if current["chunk_set_id"] is None:
            return current["title"], None, None
        source = Source(bound["record_id"], current["chunk_set_id"], current["extraction_hash"])
        return current["title"], source, bound["chunk_id"]

    def _passages(self, title, rows, handles, source=None, overlaps=None):
        return tuple(
            PassageRef(
                handle=h, record_id=row["record_id"], page=row["source_page"],
                section=" > ".join(_headings(title or row["title"], row["context_path"])),
                text=row["content"],
                source=source or Source(row["record_id"], row["chunk_set_id"], row["extraction_hash"]),
                overlap=overlaps[n] if overlaps else 0,
            )
            for n, (row, h) in enumerate(zip(rows, handles))
        )

    async def search(self, query: str, limit: int = 10) -> ToolResult:
        """Keyword search over readable Passages, ranked as Django's full-text retriever does."""
        if not _is_int(limit):
            return ToolResult.unavailable("invalid_argument")
        limit = max(1, min(limit, SEARCH_LIMIT))

        async def body(conn):
            inspected = await conn.fetchval(
                """SELECT count(DISTINCT cs.record_id) FROM iris_ai.research_chunksets() cs
                     JOIN public.records_record r ON r.id = cs.record_id
                    WHERE cs.is_active AND ($1::bigint IS NULL OR cs.record_id = $1)""",
                self.scope,
            )
            if not (query or "").strip():
                return ToolResult(NO_MATCH, coverage=Coverage(inspected_records=inspected))
            rows = await conn.fetch(
                # Any query term matches, as Django intends; `rank > 0` alone admits
                # non-matching rows, which ts_rank scores 1e-20.
                f"""WITH q AS (SELECT replace(plainto_tsquery('{CONFIG}', $1)::text, '&', '|')::tsquery AS q),
                    hits AS (
                        SELECT c.id, c.record_id, c.chunk_set_id, cs.extraction_hash, c.source_page,
                               c.content, c.context_path, r.title, ts_rank(c.search_vector, q.q) AS rank
                          FROM q, iris_ai.research_chunks() c
                          JOIN iris_ai.research_chunksets() cs ON cs.id = c.chunk_set_id AND cs.is_active
                          JOIN public.records_record r ON r.id = c.record_id
                         WHERE c.deleted_at IS NULL AND c.search_vector @@ q.q
                           AND ($2::bigint IS NULL OR c.record_id = $2))
                    SELECT *, count(*) OVER () AS total FROM hits
                     ORDER BY rank DESC, id LIMIT $3""",
                query, self.scope, limit,
            )
            if not rows:
                return ToolResult(NO_MATCH, coverage=Coverage(total=0, inspected_records=inspected))
            firsts = list({row["record_id"]: row for row in rows}.values())
            record_handles = await self._handles(
                conn, [("R", r["record_id"], r["chunk_set_id"], None) for r in firsts])
            passage_handles = await self._handles(
                conn, [("P", r["record_id"], r["chunk_set_id"], r["id"]) for r in rows])
            passages = self._passages(None, rows, passage_handles)
            records = tuple(
                RecordRef(h, r["record_id"], r["title"],
                          Source(r["record_id"], r["chunk_set_id"], r["extraction_hash"]))
                for r, h in zip(firsts, record_handles)
            )
            total = rows[0]["total"]
            return ToolResult(
                OK, records=records, passages=passages,
                coverage=Coverage(len(passages), total, total > len(passages), inspected),
                dependencies=frozenset(p.source for p in passages),
            )

        return await self._call("search", body)

    async def open_passage(self, handle: str) -> ToolResult:
        async def body(conn):
            title, source, chunk_id = await self._resolve(conn, handle, "P")
            row = await conn.fetchrow(
                """SELECT record_id, source_page, content, context_path FROM iris_ai.research_chunks()
                    WHERE id = $1 AND chunk_set_id = $2 AND deleted_at IS NULL""",
                chunk_id, source.chunk_set_id,
            )
            if row is None:
                raise _Refused("source_replaced")
            passages = self._passages(title, [row], [handle], source)
            return ToolResult(OK, passages=passages, coverage=Coverage(1, 1),
                              dependencies=frozenset({source}))

        return await self._call_on_handle("open_passage", body)

    async def read_page(self, record_handle: str, page: int) -> ToolResult:
        if not _is_int(page):
            return ToolResult.unavailable("invalid_argument")

        async def body(conn):
            title, source, _ = await self._resolve(conn, record_handle, "R")
            # Named but never read: absent, not a page with no match (IR-731).
            if source is None:
                return ToolResult(NO_MATCH, NO_MANUSCRIPT, coverage=Coverage(total=0))
            rows = await conn.fetch(
                """SELECT id, record_id, source_page, content, context_path,
                          count(*) OVER () AS total
                     FROM iris_ai.research_chunks()
                    WHERE chunk_set_id = $1 AND source_page = $2 AND deleted_at IS NULL
                    ORDER BY sequence LIMIT $3""",
                source.chunk_set_id, page, PAGE_PASSAGES,
            )
            if not rows:
                return ToolResult(NO_MATCH, coverage=Coverage(total=0),
                                  dependencies=frozenset({source}))
            handles = await self._handles(
                conn, [("P", source.record_id, source.chunk_set_id, r["id"]) for r in rows])
            total = rows[0]["total"]
            return ToolResult(
                PARTIAL if total > len(rows) else OK,
                passages=self._passages(title, rows, handles, source),
                coverage=Coverage(len(rows), total, total > len(rows)),
                dependencies=frozenset({source}),
            )

        return await self._call_on_handle("read_page", body)

    async def outline(self, record_handle: str) -> ToolResult:
        async def body(conn):
            title, source, _ = await self._resolve(conn, record_handle, "R")
            if source is None:
                return ToolResult(NO_MATCH, NO_MANUSCRIPT)
            rows = await conn.fetch(
                """SELECT source_page, context_path FROM iris_ai.research_chunks()
                    WHERE chunk_set_id = $1 AND deleted_at IS NULL ORDER BY sequence LIMIT $2""",
                source.chunk_set_id, OUTLINE_CHUNKS + 1,
            )
            truncated = len(rows) > OUTLINE_CHUNKS
            sections: dict[str, dict] = {}
            for row in rows[:OUTLINE_CHUNKS]:
                path = _headings(title, row["context_path"])
                for level in range(1, len(path) + 1):
                    entry = sections.setdefault(section_id(tuple(path[:level])), {
                        "heading": path[level - 1], "level": level,
                        "first_page": row["source_page"], "last_page": row["source_page"],
                    })
                    entry["last_page"] = row["source_page"]
            found = tuple(Section(ident, **entry) for ident, entry in sections.items())
            status = PARTIAL if truncated else (OK if found else NO_MATCH)
            return ToolResult(status, sections=found,
                              coverage=Coverage(len(found), None if truncated else len(found), truncated),
                              dependencies=frozenset({source}))

        return await self._call_on_handle("outline", body)

    async def read_manuscript(self, record_handle: str, after: str | None = None, *,
                              max_bytes: int) -> ToolResult:
        """A paper's active Manuscript in document order, as much as `max_bytes` holds (IR-733).

        Starts at the beginning, or just after `after`, a passage handle an earlier
        read returned from the same Manuscript revision. Text repeated from the
        previous passage is left out of what is shown, never out of the passage a
        citation binds. What did not fit is reported as missing, never clipped.
        """
        if not _is_int(max_bytes) or max_bytes < 1 or (after is not None and not isinstance(after, str)):
            return ToolResult.unavailable("invalid_argument")

        async def body(conn):
            title, source, _ = await self._resolve(conn, record_handle, "R")
            if source is None:
                return ToolResult(NO_MATCH, coverage=Coverage(total=0))
            cursor = None
            if after is not None:
                _, from_source, cursor = await self._resolve(conn, after, "P")
                # A continuation reads on only in the Manuscript revision it came from.
                if from_source != source:
                    raise _Refused("foreign_continuation")
            rows = await conn.fetch(
                """SELECT id, record_id, source_page, content, context_path, element_kinds
                     FROM iris_ai.research_manuscript($1) ORDER BY sequence, id LIMIT $2""",
                source.chunk_set_id, MANUSCRIPT_PASSAGES + 1,
            )
            if len(rows) > MANUSCRIPT_PASSAGES:
                raise _Refused("manuscript_too_long")
            if not rows:
                return ToolResult(NO_MATCH, coverage=Coverage(total=0), dependencies=frozenset({source}))
            start = 0
            if cursor is not None:
                start = next((n + 1 for n, row in enumerate(rows) if row["id"] == cursor), None)
                if start is None:
                    raise _Refused("source_replaced")
            pages = await conn.fetchval("SELECT iris_ai.research_manuscript_pages($1)", source.chunk_set_id)
            starts = {r["source_page"] for r in rows}
            unstarted = tuple(p for p in range(1, (pages or 0) + 1) if p not in starts)
            repeats = [0, *(overlap(a["content"], b["content"]) for a, b in zip(rows, rows[1:]))]
            end, used = start, READING_FRAME_BYTES + PAGE_ENTRY_BYTES * len(unstarted)
            while end < len(rows):
                cost = shown_bytes(rows[end]["content"][repeats[end]:]) + PASSAGE_FRAME_BYTES
                if used + cost > max_bytes:
                    break
                used += cost
                end += 1
            chosen = rows[start:end]
            handles = await self._handles(
                conn, [("P", source.record_id, source.chunk_set_id, r["id"]) for r in chosen])
            passages = self._passages(title, chosen, handles, source, repeats[start:end])
            kinds = [set(r["element_kinds"] or ()) for r in rows]
            remaining = end < len(rows)
            reading = Reading(
                passages=len(rows), covered=_span(rows, start, end - 1) if chosen else None,
                missing=tuple(_span(rows, a, b) for a, b in ((0, start - 1), (end, len(rows) - 1)) if a <= b),
                pages=pages,
                pages_no_passage_starts_on=unstarted,
                formulas=sum(FORMULA in k for k in kinds), captions=sum(CAPTION in k for k in kinds),
                overlap_chars=sum(p.overlap for p in passages),
                continue_after=(handles[-1] if chosen else after) if remaining else None, title=title,
            )
            return ToolResult(
                PARTIAL if remaining else OK, reason="exceeds_room" if remaining and not chosen else None,
                passages=passages, reading=reading,
                coverage=Coverage(len(chosen), len(rows), remaining),
                dependencies=frozenset({source}),
            )

        return await self._call_on_handle("read_manuscript", body)

    async def resolve(self, references=(), record_ids=()) -> ToolResult:
        """Papers the reader named, by title or Record id, as fresh paper handles (IR-750).

        Several title matches are an ambiguity, never a silent choice. A Record the
        reader may not read is the same `none` as one that does not exist.
        """
        if (not isinstance(references, (list, tuple)) or not isinstance(record_ids, (list, tuple))
                or not all(isinstance(r, str) for r in references)
                or not all(_is_int(i) for i in record_ids)
                or not 0 < len(references) + len(record_ids) <= metadata.MAX_REFERENCES):
            return ToolResult.unavailable("invalid_argument")

        async def body(conn):
            rows = await conn.fetch(
                """SELECT r.id AS record_id, r.title, cs.id AS chunk_set_id, cs.extraction_hash
                     FROM public.records_record r
                     LEFT JOIN iris_ai.research_chunksets() cs ON cs.record_id = r.id AND cs.is_active
                    WHERE ($1::bigint IS NULL OR r.id = $1)
                    ORDER BY r.title, r.id""",
                self.scope,
            )
            by_id = {row["record_id"]: row for row in rows}
            found: list[tuple[str, str, list, str | None]] = []
            truncated = False
            for reference in references:
                basis, named = metadata.title_matches(rows, reference)
                truncated = truncated or len(named) > metadata.MAX_CANDIDATES
                if len(named) > 1:
                    found.append(("title", "ambiguous", named[:metadata.MAX_CANDIDATES], basis))
                else:
                    found.append(("title", basis, named, None))
            for record_id in record_ids:
                row = by_id.get(record_id)
                found.append(("record_id", "record_id", [row], None) if row
                             else ("record_id", "none", [], None))
            named = list({row["record_id"]: row for *_, chosen, _ in found for row in chosen}.values())
            handles = dict(zip(
                (row["record_id"] for row in named),
                await self._handles(conn, [("R", r["record_id"], r["chunk_set_id"], None) for r in named]),
            ))
            refs = {
                row["record_id"]: RecordRef(
                    handles[row["record_id"]], row["record_id"], row["title"],
                    Source(row["record_id"], row["chunk_set_id"], row["extraction_hash"])
                    if row["chunk_set_id"] is not None else None)
                for row in named
            }
            matches = tuple(
                Match(n, kind, match, tuple(refs[row["record_id"]] for row in chosen), basis)
                for n, (kind, match, chosen, basis) in enumerate(found, start=1)
            )
            resolved = sum(1 for m in matches if m.match not in ("ambiguous", "none"))
            if any(m.match == "ambiguous" for m in matches):
                status = AMBIGUOUS
            elif resolved == len(matches):
                status = OK
            else:
                status = PARTIAL if resolved else NO_MATCH
            return ToolResult(
                status, records=tuple(refs.values()), matches=matches,
                coverage=Coverage(resolved, len(matches), truncated),
                dependencies=frozenset(r.source for r in refs.values() if r.source is not None),
            )

        return await self._call("resolve", body)

    async def count(self, filters: dict, group_by: str | None = None) -> ToolResult:
        """Exactly how many readable Records match metadata filters, optionally grouped (IR-750).

        Computed afresh on every call under the run's grant, so a paper the reader
        lost access to is never counted. There is no topic filter: a topic total
        is a screened subset, never a count.
        """
        if (not isinstance(filters, dict) or set(filters) - set(metadata.FILTERS)
                or (group_by is not None and group_by not in metadata.GROUPS)
                or not all(isinstance(filters[n], str) and filters[n].strip()
                           for n in metadata.TAXONOMIES if n in filters)
                or not all(_is_int(filters[n]) and metadata.YEAR_RANGE[0] <= filters[n] <= metadata.YEAR_RANGE[1]
                           for n in ("year_from", "year_to") if n in filters)
                or ("is_ip" in filters and type(filters["is_ip"]) is not bool)):
            return ToolResult.unavailable("invalid_argument")

        async def body(conn):
            applied, ids = [], {}
            for name, (table, _) in metadata.TAXONOMIES.items():
                if name not in filters:
                    continue
                rows = await conn.fetch(
                    f"SELECT id, name FROM public.{table} WHERE lower(name) = lower($1)",
                    filters[name].strip())
                if not rows:
                    return ToolResult.unavailable("unknown_filter_value")
                # Entries differing only by case are never chosen between.
                if len(rows) > 1:
                    return ToolResult.unavailable("ambiguous_filter_value")
                ids[name] = rows[0]["id"]
                applied.append((name, rows[0]["name"]))
            applied += [(n, filters[n]) for n in ("year_from", "year_to", "is_ip") if n in filters]
            rows = await conn.fetch(
                """SELECT r.id, c.name AS classification, p.name AS psced, t.name AS record_type,
                          r.year_completed AS year
                     FROM public.records_record r
                     LEFT JOIN public.records_classification c ON c.id = r.classification_id
                     LEFT JOIN public.records_pscedclassification p ON p.id = r.psced_id
                     LEFT JOIN public.records_recordtype t ON t.id = r.record_type_id
                    WHERE ($1::bigint IS NULL OR r.id = $1)
                      AND ($2::bigint IS NULL OR r.classification_id = $2)
                      AND ($3::bigint IS NULL OR r.psced_id = $3)
                      AND ($4::bigint IS NULL OR r.record_type_id = $4)
                      AND ($5::int IS NULL OR r.year_completed >= $5)
                      AND ($6::int IS NULL OR r.year_completed <= $6)
                      AND ($7::boolean IS NULL OR r.is_ip = $7)""",
                self.scope, ids.get("classification"), ids.get("psced"), ids.get("record_type"),
                filters.get("year_from"), filters.get("year_to"), filters.get("is_ip"),
            )
            groups: dict = {}
            for row in rows:
                if group_by is not None:
                    groups[row[group_by]] = groups.get(row[group_by], 0) + 1
            fact = Count(
                total=len(rows), filters=tuple(sorted(applied)), group_by=group_by,
                groups=tuple(sorted((v, n) for v, n in groups.items() if v is not None)),
                ungrouped=groups.get(None, 0), scope_record_id=self.scope,
                population=frozenset(row["id"] for row in rows),
            )
            return ToolResult(OK if rows else NO_MATCH, count=fact,
                              coverage=Coverage(len(rows), len(rows)))

        return await self._call("count", body)

    async def recall(self, record_ids) -> ToolResult:
        """Fresh paper handles for Records a Conversation showed, still readable now (IR-728).

        Unreadable, out-of-scope and missing Records are left out alike.
        """
        ids = [i for i in record_ids if _is_int(i)][:RECALL_LIMIT]

        async def body(conn):
            rows = await conn.fetch(
                """SELECT r.id AS record_id, r.title, cs.id AS chunk_set_id, cs.extraction_hash
                     FROM public.records_record r
                     JOIN iris_ai.research_chunksets() cs ON cs.record_id = r.id AND cs.is_active
                    WHERE r.id = ANY($1::bigint[]) AND ($2::bigint IS NULL OR r.id = $2)""",
                ids, self.scope,
            )
            found = {row["record_id"]: row for row in rows}
            ordered = [found[i] for i in ids if i in found]
            if not ordered:
                return ToolResult(NO_MATCH, coverage=Coverage(total=0))
            handles = await self._handles(
                conn, [("R", r["record_id"], r["chunk_set_id"], None) for r in ordered])
            records = tuple(
                RecordRef(h, r["record_id"], r["title"],
                          Source(r["record_id"], r["chunk_set_id"], r["extraction_hash"]))
                for r, h in zip(ordered, handles)
            )
            return ToolResult(OK, records=records, coverage=Coverage(len(records), len(records)),
                              dependencies=frozenset(r.source for r in records))

        return await self._call("recall", body)

    async def reauthorize(self, handles, counted=()) -> str | None:
        """None when every recovered handle still reads its own source now (IR-724).

        A replacement worker's restored evidence confers nothing: each handle
        must resolve under the run's grant, scope and fence to the source it
        was issued on, each passage must still exist, and every Record an
        exact count counted must still be readable. "stale" otherwise, or the
        reason the run cannot continue. Journals nothing.
        """
        try:
            async with self._session() as conn:
                for handle in handles:
                    try:
                        async with conn.transaction():
                            _, source, chunk_id = await self._resolve(conn, handle, str(handle)[:1])
                            if chunk_id is not None and not await conn.fetchval(
                                    """SELECT EXISTS (SELECT 1 FROM iris_ai.research_chunks()
                                        WHERE id = $1 AND chunk_set_id = $2 AND deleted_at IS NULL)""",
                                    chunk_id, source.chunk_set_id):
                                return "stale"
                    except _Refused:
                        return "stale"
                ids = sorted({i for i in counted if _is_int(i)})
                if ids and await conn.fetchval(
                        "SELECT count(*) FROM public.records_record WHERE id = ANY($1::bigint[])", ids) != len(ids):
                    return "stale"
        except _Refused as refused:
            return refused.reason
        return None

    async def journal(self, name: str, data: dict) -> bool:
        """Append a run event under the grant; False once the run has ended (IR-728)."""
        try:
            async with self._session() as conn:
                await RunStore._journal(conn, self.run_id, name, data)
            return True
        except _Refused:
            return False

    async def semantic_search(self, query: str) -> ToolResult:
        """One admitted query embedding, pinned to the current document space."""
        if self.embedding_provider is None or self.embedding_ledger is None:
            async def gated(conn):
                return ToolResult.unavailable("provider_gated", provider_operations=("embed_query", "rerank"))
            return await self._call("semantic_search", gated)
        if not isinstance(query, str) or not query.strip():
            return ToolResult.unavailable("invalid_argument")
        import asyncio
        from types import SimpleNamespace
        from ai.admission.errors import AdmissionDenied
        from ai.admission.guard import SendGuard
        from ai.admission.ledger import Request, Usage, estimate_tokens
        from ai.admission.scope import RunBinding
        from ai.ingestion.indexing import checked_vectors, space
        provider = self.embedding_provider
        binding = RunBinding(self.run_id, self.fence)
        try:
            async with self._session() as conn:
                pinned = await space(conn, provider)
            ticket = await self.embedding_ledger.admit(Request(
                operation="embed", purpose="query", purpose_version="query-1", lane="research",
                account=provider.account, models=(provider.model,), input_tokens=estimate_tokens(query),
                output_tokens=0), binding)
            usage = Usage()
            try:
                await SendGuard(self.dsn).check(binding, SimpleNamespace(data_policy=provider.data_policy))
                usage.sent = True
                response = await asyncio.wait_for(provider.embed([query], input_type="query"), ticket.timeout_seconds)
                vector = checked_vectors(response.vectors, 1, provider.dimensions)[0]
                usage.input_tokens, usage.output_tokens, usage.model = response.input_tokens, 0, provider.model
            finally:
                await ticket.settle(usage)
        except AdmissionDenied as refused:
            return ToolResult.unavailable(refused.reason)
        except _Refused as refused:
            return ToolResult.unavailable(refused.reason)

        async def body(conn):
            current = await space(conn, provider)
            if current["id"] != pinned["id"]:
                return ToolResult.unavailable("embedding_space_changed")
            rows = await conn.fetch(
                "WITH candidates AS (SELECT rv.record_id FROM iris_ai.research_record_vectors($1) rv"
                " WHERE ($2::bigint IS NULL OR rv.record_id=$2)"
                " ORDER BY rv.embedding OPERATOR(public.<=>) $3::public.vector LIMIT 20)"
                " SELECT c.*,r.title,cs.extraction_hash FROM iris_ai.research_chunks() c"
                " JOIN iris_ai.research_chunksets() cs ON cs.id=c.chunk_set_id AND cs.is_active"
                " JOIN public.records_record r ON r.id=c.record_id"
                " JOIN iris_ai.research_vectors($1) v ON v.chunk_id=c.id"
                " JOIN candidates cr ON cr.record_id=c.record_id"
                " WHERE c.deleted_at IS NULL AND ($2::bigint IS NULL OR c.record_id=$2)"
                " ORDER BY v.embedding OPERATOR(public.<=>) $3::public.vector,c.id LIMIT $4",
                pinned["id"], self.scope, json.dumps(vector), SEARCH_LIMIT)
            handles = await self._handles(conn, [("P",r["record_id"],r["chunk_set_id"],r["id"]) for r in rows])
            passages = self._passages(None, rows, handles)
            return ToolResult(OK if passages else NO_MATCH, passages=passages,
                coverage=Coverage(len(passages),None, len(passages)==SEARCH_LIMIT),
                dependencies=frozenset(p.source for p in passages))
        return await self._call("semantic_search", body)

    async def _call_on_handle(self, name: str, body) -> ToolResult:
        """`_call` in a savepoint; a refused handle is journalled like any outcome."""
        async def wrapped(conn):
            try:
                async with conn.transaction():
                    return await body(conn)
            except _Refused as refused:
                return ToolResult.unavailable(refused.reason)

        return await self._call(name, wrapped)
