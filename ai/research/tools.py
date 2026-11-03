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

from ai.runs.store import RunStore

APP_NAME = "iris-ai-research"
#: Mirrors Django's keyword index (`apps.ai.keyword_index.CONFIG`).
CONFIG = "english"
SEARCH_LIMIT = 20
PAGE_PASSAGES = 20
OUTLINE_CHUNKS = 2000
RECALL_LIMIT = 50

OK, NO_MATCH, PARTIAL, UNAVAILABLE = "ok", "no_match", "partial", "unavailable"


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
    source: Source


@dataclass(frozen=True)
class PassageRef:
    handle: str
    record_id: int
    page: int | None
    section: str
    text: str
    source: Source


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
class ToolResult:
    status: str
    reason: str | None = None
    records: tuple[RecordRef, ...] = ()
    passages: tuple[PassageRef, ...] = ()
    sections: tuple[Section, ...] = ()
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
        """(title, Source, chunk id) for a live handle of this run, or raise _Refused."""
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
        source = Source(bound["record_id"], current["chunk_set_id"], current["extraction_hash"])
        return current["title"], source, bound["chunk_id"]

    def _passages(self, title, rows, handles, source=None):
        return tuple(
            PassageRef(
                handle=h, record_id=row["record_id"], page=row["source_page"],
                section=" > ".join(_headings(title or row["title"], row["context_path"])),
                text=row["content"],
                source=source or Source(row["record_id"], row["chunk_set_id"], row["extraction_hash"]),
            )
            for row, h in zip(rows, handles)
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
