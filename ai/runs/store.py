"""AI-owned run and Conversation state in PostgreSQL (IR-722, IR-723, ADR-049 §10, §12, §21).

Each operation is one short transaction on its own connection; none is open
while an executor runs. Reader operations bind a `reader_session` grant
through `iris_authz.begin_research`; a run belongs to the grant's reader
alone, and anything else is the same NotFound as a missing row.

A queued run is durable work: workers find it by scanning (`claim_next`),
so a lost wakeup only delays it. Admission and dispatch each take one short
advisory lock to keep their populations exact.

Lock order is Conversation, then run. Only the holder of a run's current
fence may advance it; cancel and deletion move the fence.

Retention: an owner's Conversation deletion fences and removes its content
(questions, Turns, citations, journal) in one transaction. A deleted account
is purged the same way by `purge_departed`; a deactivated one is only
fenced. Attempt accounting carries no content and is kept.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Mapping

import asyncpg

from ai.admission.scope import run_key
from ai.runs.executor import PriorTurn, Result

APP_NAME = "iris-ai-runs"
ACTIVE = ("queued", "running")
TERMINAL = ("completed", "cancelled", "conflict", "expired", "failed", "deleted")

# An exact count stands only while the reader may still read every Record it
# counted; the row policy decides (IR-750). Correlated on Turn `t`.
COUNTED_UNREADABLE = """EXISTS (
    SELECT 1 FROM jsonb_array_elements(t.facts) fact,
                  jsonb_array_elements_text(coalesce(fact->'population', '[]'::jsonb)) counted(id)
     WHERE NOT EXISTS (SELECT 1 FROM public.records_record r WHERE r.id=counted.id::bigint))"""

# Every source used by research, including uncited and legacy revisions, must
# still be current before its derived answer can be replayed or recalled.
CURRENT_SOURCE_TURN = """NOT EXISTS (
    SELECT 1 FROM (
      SELECT ci.revision FROM iris_ai.citation ci WHERE ci.turn_id=t.id
      UNION
      SELECT jsonb_array_elements_text(ev.data->'sources') AS revision
        FROM iris_ai.run_event ev WHERE ev.run_id=t.run_id AND ev.name='tool'
    ) dependency WHERE dependency.revision IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM iris_ai.research_chunksets() cs WHERE cs.is_active
        AND cs.id::text || ':' || cs.extraction_hash=dependency.revision))
  AND NOT """ + COUNTED_UNREADABLE


def shown_facts(facts) -> list[dict]:
    """A Turn's facts as a reader sees them: allowlisted keys, never the counted Records (IR-750)."""
    shown = []
    for fact in facts or ():
        if fact.get("kind") == "exact_count":
            shown.append({
                **{k: fact.get(k) for k in ("kind", "total", "filters", "group_by", "groups", "ungrouped")},
                "scope": "paper_chat" if fact.get("scope_record_id") is not None else "readable_records",
                "relative_to": fact.get("relative_to"),
            })
        elif fact.get("kind") == "keyword_sample":
            shown.append({"kind": "keyword_sample", "papers": fact.get("papers"), "exhaustive": False})
    return shown

RUN_COLUMNS = (
    "id, reader_id, conversation_id, request_hash, question, base_revision, state, end_reason,"
    " deadline_at, allowance, pinned, fence, version, turn_id, created_at, finished_at,"
    " depth, started_at"
)

#: Earlier Turns a claim carries, newest kept (IR-728).
PRIOR_TURNS = 20

ADMIT_LOCK = "iris_ai.admit"
DISPATCH_LOCK = "iris_ai.dispatch"


#: A Paper Chat grant ($2) reaches only its own Record's Conversations (IR-719).
IN_SCOPE = "($2::bigint IS NULL OR scope_record_id = $2)"


class NotFound(Exception):
    pass


class Unauthorized(Exception):
    pass


class Fenced(Exception):
    """A superseded attempt tried to advance the run."""


class Conflict(Exception):
    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


class Busy(Exception):
    """Admission refused by a population bound; nothing was written."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _Raced(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    fence: int
    question: str
    #: The pin persisted at admission (IR-727).
    pinned: dict | None = None
    #: The Conversation's Paper Chat scope, if any (IR-719).
    scope_record_id: int | None = None
    run_id: uuid.UUID | None = None
    #: The reader's stored grant, which the run's tools read under (IR-723).
    grant: str | None = None
    depth: str = "ordinary"
    allowance: dict | None = None
    remaining_seconds: float = 0.0
    #: Earlier Turns, oldest first, and the Conversation state they left (IR-728).
    prior: tuple[PriorTurn, ...] = ()
    state: dict | None = None
    #: The last completed step an earlier fence saved, unverified: `step` and `body` (IR-724).
    checkpoint: dict | None = None
    #: Tokens the shared ledger has charged this run over every fence, open
    #: and uncertain attempts at their reservation (IR-724).
    spent: dict | None = None


def request_hash(question: str, conversation_id, base_revision) -> str:
    body = json.dumps(
        {"q": question, "c": str(conversation_id) if conversation_id else None, "r": base_revision},
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


class RunStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @asynccontextmanager
    async def _connect(self):
        conn = await asyncpg.connect(self.dsn, server_settings={"application_name": APP_NAME})
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        try:
            yield conn
        finally:
            await conn.close()

    @staticmethod
    async def _verify(conn, grant: str | None) -> dict:
        """The grant's verified claims, bound for this transaction."""
        if not grant:
            raise Unauthorized
        try:
            return await conn.fetchval("SELECT iris_authz.begin_research($1, 'reader_session')", grant)
        except asyncpg.InsufficientPrivilegeError:
            raise Unauthorized from None

    @staticmethod
    def _reader(claims: dict) -> tuple[int, int | None]:
        scope = claims.get("rec")
        return int(claims["sub"]), int(scope) if scope is not None else None

    async def _principal(self, conn, grant: str | None) -> tuple[int, int | None]:
        """The verified reader and Paper Chat scope, bound for this transaction."""
        return self._reader(await self._verify(conn, grant))

    @staticmethod
    async def _journal(conn, run_id, name: str, data: dict) -> None:
        await conn.execute(
            """INSERT INTO iris_ai.run_event (run_id, sequence, name, data)
               SELECT $1, coalesce(max(sequence), 0) + 1, $2, $3
                 FROM iris_ai.run_event WHERE run_id = $1""",
            run_id, name, data,
        )

    @staticmethod
    async def _owned_run(conn, reader: int, scope: int | None, run_id) -> None:
        """Lock the run's Conversation; NotFound unless the reader's, alive and in scope."""
        conversation_id = await conn.fetchval(
            "SELECT conversation_id FROM iris_ai.ask_run WHERE id = $1 AND reader_id = $2",
            run_id, reader,
        )
        if conversation_id is None:
            raise NotFound
        alive = await conn.fetchval(
            f"""SELECT deleted_at IS NULL FROM iris_ai.conversation
                 WHERE id = $1 AND {IN_SCOPE} FOR UPDATE""",
            conversation_id, scope,
        )
        if not alive:
            raise NotFound

    async def admit(self, grant, *, key: str, question: str, conversation_id, base_revision,
                    deadline_seconds: int, allowance: dict, pinned: dict, depth: str = "ordinary",
                    max_queued: int | None = None,
                    max_active_per_reader: int | None = None) -> tuple[dict, bool]:
        """The run for this request identity, and whether it is new.

        The queued run is committed before this returns; a caller notifies
        workers only afterwards. Raises Busy when a population is full.
        """
        digest = request_hash(question, conversation_id, base_revision)
        bounds = (max_queued, max_active_per_reader)
        async with self._connect() as conn:
            for _ in range(2):
                try:
                    async with conn.transaction():
                        return await self._admit(
                            conn, grant, key, question, conversation_id, base_revision,
                            digest, deadline_seconds, allowance, pinned, depth, bounds,
                        )
                except _Raced:
                    continue
        raise Conflict("request_in_flight")

    @staticmethod
    async def _bound_population(conn, reader: int, bounds) -> None:
        max_queued, per_reader = bounds
        if max_queued is None and per_reader is None:
            return
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", ADMIT_LOCK)
        counts = await conn.fetchrow(
            """SELECT count(*) AS everyone, count(*) FILTER (WHERE reader_id = $1) AS reader
                 FROM iris_ai.ask_run WHERE state = ANY($2) AND deadline_at > now()""",
            reader, list(ACTIVE),
        )
        if per_reader is not None and counts["reader"] >= per_reader:
            raise Busy("reader_queue_full")
        if max_queued is not None and counts["everyone"] >= max_queued:
            raise Busy("queue_full")

    async def _admit(self, conn, grant, key, question, conversation_id, base_revision,
                     digest, deadline_seconds, allowance, pinned, depth, bounds):
        claims = await self._verify(conn, grant)
        reader, scope = self._reader(claims)
        existing = await conn.fetchrow(
            f"SELECT {RUN_COLUMNS} FROM iris_ai.ask_run WHERE reader_id = $1 AND request_key = $2",
            reader, key,
        )
        if existing is not None:
            deleted = await conn.fetchval(
                "SELECT deleted_at IS NOT NULL FROM iris_ai.conversation WHERE id = $1",
                existing["conversation_id"],
            )
            if deleted:
                raise NotFound
            if existing["request_hash"] != digest:
                raise Conflict("request_mismatch")
            return dict(existing), False
        if conversation_id is None:
            conversation_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO iris_ai.conversation (id, reader_id, scope_record_id) VALUES ($1, $2, $3)",
                conversation_id, reader, scope,
            )
            revision = 0
        else:
            found = await conn.fetchrow(
                """SELECT revision, scope_record_id FROM iris_ai.conversation
                    WHERE id = $1 AND reader_id = $2 AND deleted_at IS NULL FOR UPDATE""",
                conversation_id, reader,
            )
            if found is None:
                raise NotFound
            # Paper Chat stays on its Record; widening is a new Conversation.
            if found["scope_record_id"] != scope:
                raise Conflict("scope_mismatch")
            revision = found["revision"]
            if base_revision != revision:
                raise Conflict("revision_conflict", revision=revision)
            await self._expire_overdue(conn, conversation_id)
            active = await conn.fetchval(
                "SELECT id FROM iris_ai.ask_run WHERE conversation_id = $1 AND state = ANY($2)",
                conversation_id, list(ACTIVE),
            )
            if active is not None:
                raise Conflict("run_in_progress", run_id=str(active))
        await self._bound_population(conn, reader, bounds)
        row = await conn.fetchrow(
            f"""INSERT INTO iris_ai.ask_run
                    (id, reader_id, conversation_id, request_key, request_hash, question,
                     base_revision, deadline_at, allowance, pinned, depth,
                     reader_grant, grant_expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, now() + make_interval(secs => $8), $9, $10,
                        $11, $12, to_timestamp($13))
                ON CONFLICT (reader_id, request_key) DO NOTHING
                RETURNING {RUN_COLUMNS}""",
            uuid.uuid4(), reader, conversation_id, key, digest, question, revision,
            float(deadline_seconds), allowance, pinned, depth, grant, claims["exp"],
        )
        if row is None:
            # A concurrent submission with this identity won; read it instead.
            raise _Raced
        await self._journal(conn, row["id"], "admitted", {})
        return dict(row), True

    async def _expire_overdue(self, conn, conversation_id) -> None:
        """End active runs past their deadline, so a dead attempt cannot hold the Conversation."""
        overdue = await conn.fetch(
            """SELECT id FROM iris_ai.ask_run
                WHERE conversation_id = $1 AND state = ANY($2) AND deadline_at <= now() FOR UPDATE""",
            conversation_id, list(ACTIVE),
        )
        for run in overdue:
            await self._end(conn, run["id"], "expired", "deadline", move_fence=True)

    async def claim(self, run_id, *, worker: str, lease_seconds: int, executor: str | None,
                    reserved_units: int | Mapping[str, int]) -> Claim | None:
        """Take the run's lease under a new fence; None if it cannot run now.

        `executor` None accounts the attempt to the run's pinned executor, with
        `reserved_units` then given per executor name (IR-862).
        """
        async with self._connect() as conn:
            async with conn.transaction():
                return await self._claim(conn, run_id, worker, lease_seconds, executor, reserved_units)

    async def _claim(self, conn, run_id, worker, lease_seconds, executor, reserved_units):
        row = await conn.fetchrow(
            """UPDATE iris_ai.ask_run r
                  SET state = 'running', fence = r.fence + 1, lease_owner = $2,
                      lease_expires_at = now() + make_interval(secs => $3),
                      started_at = coalesce(r.started_at, now()), version = r.version + 1
                 FROM iris_ai.conversation c
                WHERE r.id = $1 AND c.id = r.conversation_id AND c.deleted_at IS NULL
                  AND r.state IN ('queued', 'running') AND r.deadline_at > now()
                  AND (r.lease_expires_at IS NULL OR r.lease_expires_at <= now())
            RETURNING r.fence, r.question, r.allowance, r.pinned, r.reader_grant, r.reader_id, c.scope_record_id,
                      r.depth, r.conversation_id, c.state,
                      extract(epoch FROM r.deadline_at - now()) AS remaining""",
            run_id, worker, float(lease_seconds),
        )
        if row is None:
            overdue = await conn.fetchval(
                """SELECT id FROM iris_ai.ask_run
                    WHERE id = $1 AND state = ANY($2) AND deadline_at <= now() FOR UPDATE""",
                run_id, list(ACTIVE),
            )
            if overdue is not None:
                await self._end(conn, run_id, "expired", "deadline", move_fence=True)
            return None
        try:
            async with conn.transaction():
                reader, scope = await self._principal(conn, row["reader_grant"])
                if reader != row["reader_id"] or scope != row["scope_record_id"]:
                    raise Unauthorized
        except Unauthorized:
            await self._end(conn, run_id, "failed", "authorization_expired", move_fence=True)
            return None
        used = await conn.fetchval(
            "SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = $1", run_id,
        )
        if used >= row["allowance"]["max_attempts"]:
            await self._end(conn, run_id, "failed", "attempts_exhausted")
            return None
        if executor is None:
            # The executor the run is pinned to answers it (IR-862).
            executor = (row["pinned"] or {}).get("executor", "")
        if isinstance(reserved_units, Mapping):
            reserved_units = reserved_units.get(executor, 0)
        await conn.execute(
            """INSERT INTO iris_ai.attempt_accounting (run_id, fence, executor, reserved_units)
               VALUES ($1, $2, $3, $4)""",
            run_id, row["fence"], executor, reserved_units,
        )
        await self._journal(conn, run_id, "started", {"attempt": used + 1})
        prior = await conn.fetch(
            f"""SELECT question, answer, kind FROM iris_ai.turn t
                WHERE conversation_id = $1 AND {CURRENT_SOURCE_TURN} ORDER BY ordinal DESC LIMIT $2""",
            row["conversation_id"], PRIOR_TURNS,
        )
        checkpoint = await conn.fetchrow(
            "SELECT step, body FROM iris_ai.run_checkpoint WHERE run_id = $1", run_id,
        )
        # Every fence's attempts, including one a dead worker left open (IR-725).
        spent = await conn.fetchrow(
            """SELECT coalesce(sum(charge_input_tokens), 0) AS input_tokens,
                      coalesce(sum(charge_output_tokens), 0) AS output_tokens
                 FROM public.ai_providerreservation WHERE run_key = $1""",
            run_key(run_id),
        )
        return Claim(fence=row["fence"], question=row["question"], pinned=row["pinned"],
                     scope_record_id=row["scope_record_id"], run_id=run_id,
                     grant=row["reader_grant"], depth=row["depth"], allowance=row["allowance"],
                     remaining_seconds=float(row["remaining"]),
                     prior=tuple(PriorTurn(t["question"], t["answer"], t["kind"]) for t in reversed(prior)),
                     state=row["state"], checkpoint=dict(checkpoint) if checkpoint else None,
                     spent={k: int(v) for k, v in spent.items()})

    async def claim_next(self, *, worker: str, lease_seconds: int, executor: str | None,
                         reserved_units: int | Mapping[str, int], deep_concurrency: int,
                         max_running_per_reader: int, serves: list[dict] | None = None) -> Claim | None:
        """Claim the next runnable run, or None.

        Overdue runs are expired first. Deep runs are preferred while fewer
        than `deep_concurrency` run, so they cannot starve, and never past
        it, so ordinary runs keep the other slots. A reader already running
        `max_running_per_reader` waits. A run whose grant will not cover a
        whole lease waits for its reader to reconnect, until its deadline.

        `serves` lists the pins this worker can answer (`executor`,
        `executor_version`, `agent`); a run pinned otherwise waits for a
        worker that can, until its deadline (IR-862). None claims any run.
        """
        async with self._connect() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", DISPATCH_LOCK)
                await self._expire_all_overdue(conn)
                deep_running = await conn.fetchval(
                    """SELECT count(*) FROM iris_ai.ask_run
                        WHERE state = 'running' AND depth = 'deep' AND lease_expires_at > now()""",
                )
                deep_open = deep_running < deep_concurrency
                run_id = await conn.fetchval(
                    """SELECT r.id FROM iris_ai.ask_run r
                         JOIN iris_ai.conversation c ON c.id = r.conversation_id
                        WHERE c.deleted_at IS NULL AND r.deadline_at > now()
                          AND (r.state = 'queued'
                               OR (r.state = 'running' AND r.lease_expires_at <= now()))
                          AND r.grant_expires_at > now() + make_interval(secs => $3)
                          AND (r.depth = 'ordinary' OR $1)
                          AND (SELECT count(*) FROM iris_ai.ask_run o
                                WHERE o.reader_id = r.reader_id AND o.state = 'running'
                                  AND o.lease_expires_at > now()) < $2
                          AND ($4::jsonb IS NULL OR EXISTS (
                                SELECT 1 FROM jsonb_array_elements($4::jsonb) s
                                 WHERE s->'executor' = r.pinned->'executor'
                                   AND s->'executor_version' = r.pinned->'executor_version'
                                   -- A deterministic run has no `agent` key; its entry holds JSON null.
                                   AND nullif(s->'agent', 'null'::jsonb) IS NOT DISTINCT FROM r.pinned->'agent'))
                        ORDER BY (r.depth = 'deep') DESC, r.created_at
                        LIMIT 1""",
                    deep_open, max_running_per_reader, float(lease_seconds), serves,
                )
                if run_id is None:
                    return None
                return await self._claim(conn, run_id, worker, lease_seconds, executor, reserved_units)

    async def _expire_all_overdue(self, conn) -> None:
        overdue = await conn.fetch(
            """SELECT id FROM iris_ai.ask_run
                WHERE state = ANY($1) AND deadline_at <= now() FOR UPDATE SKIP LOCKED""",
            list(ACTIVE),
        )
        for run in overdue:
            await self._end(conn, run["id"], "expired", "deadline", move_fence=True)

    async def _end(self, conn, run_id, state: str, reason: str, *, move_fence=False,
                   reported_units: int | None = None) -> str:
        await conn.execute(
            f"""UPDATE iris_ai.ask_run
                   SET state = $2, end_reason = $3, finished_at = now(), lease_owner = NULL,
                       lease_expires_at = NULL, reader_grant = NULL, grant_expires_at = NULL,
                       version = version + 1
                       {", fence = fence + 1" if move_fence else ""}
                 WHERE id = $1""",
            run_id, state, reason,
        )
        # Unreported usage keeps its reservation.
        await conn.execute(
            """UPDATE iris_ai.attempt_accounting SET outcome = $2, reported_units = $3
                WHERE run_id = $1 AND outcome = 'reserved'""",
            run_id, state, reported_units,
        )
        # An ended run is never resumed; its evidence is not kept for one (IR-724).
        await conn.execute("DELETE FROM iris_ai.run_checkpoint WHERE run_id = $1", run_id)
        await self._journal(conn, run_id, state, {"reason": reason})
        return state

    async def save_checkpoint(self, run_id, fence: int, step: int, body: dict, *,
                              lease_seconds: int) -> None:
        """Replace the run's checkpoint after a completed step, and renew its lease (IR-724).

        Only the current fence of a running run, before its deadline, may
        write; anything else raises Fenced and writes nothing. A step never
        goes backwards.
        """
        async with self._connect() as conn:
            async with conn.transaction():
                renewed = await conn.fetchval(
                    """UPDATE iris_ai.ask_run
                          SET lease_expires_at = now() + make_interval(secs => $3)
                        WHERE id = $1 AND fence = $2 AND state = 'running' AND deadline_at > now()
                    RETURNING id""",
                    run_id, fence, float(lease_seconds),
                )
                if renewed is None:
                    raise Fenced
                saved = await conn.fetchval(
                    """INSERT INTO iris_ai.run_checkpoint (run_id, fence, step, body)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (run_id) DO UPDATE
                          SET fence = excluded.fence, step = excluded.step, body = excluded.body,
                              saved_at = now()
                        WHERE run_checkpoint.fence <= excluded.fence
                          AND run_checkpoint.step <= excluded.step
                    RETURNING step""",
                    run_id, fence, step, body,
                )
                if saved is None:
                    raise Fenced

    async def commit_final(self, run_id, fence: int, result: Result) -> str:
        """Turn, citations, Conversation revision and terminal journal, atomically.

        Returns the run's terminal state. A run that already ended is left
        as it is; a superseded fence raises Fenced and writes nothing.
        """
        async with self._connect() as conn:
            async with conn.transaction():
                conversation_id = await conn.fetchval(
                    "SELECT conversation_id FROM iris_ai.ask_run WHERE id = $1", run_id,
                )
                if conversation_id is None:
                    raise NotFound
                conversation = await conn.fetchrow(
                    "SELECT revision, deleted_at FROM iris_ai.conversation WHERE id = $1 FOR UPDATE",
                    conversation_id,
                )
                run = await conn.fetchrow(
                    f"SELECT {RUN_COLUMNS}, now() AS now FROM iris_ai.ask_run WHERE id = $1 FOR UPDATE",
                    run_id,
                )
                if run["state"] in TERMINAL:
                    return run["state"]
                if run["fence"] != fence:
                    raise Fenced
                if conversation["deleted_at"] is not None:
                    return await self._end(conn, run_id, "deleted", "conversation_deleted")
                reader = await conn.fetchval("SELECT iris_authz.reader_status($1)", run["reader_id"])
                if reader != "active":
                    return await self._end(conn, run_id, "cancelled", "reader_departed")
                if run["deadline_at"] <= run["now"]:
                    return await self._end(conn, run_id, "expired", "deadline")
                if conversation["revision"] != run["base_revision"]:
                    return await self._end(conn, run_id, "conflict", "revision_moved")

                turn_id = uuid.uuid4()
                ordinal = conversation["revision"] + 1
                await conn.execute(
                    """INSERT INTO iris_ai.turn (id, conversation_id, run_id, ordinal, question, answer, kind, facts)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    turn_id, conversation_id, run_id, ordinal, run["question"], result.answer, result.kind,
                    list(result.facts),
                )
                if result.citations:
                    await conn.executemany(
                        """INSERT INTO iris_ai.citation (turn_id, position, record_id, page, quote, revision)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        [(turn_id, n, c.record_id, c.page, c.quote, c.revision)
                         for n, c in enumerate(result.citations, start=1)],
                    )
                await conn.execute(
                    "UPDATE iris_ai.conversation SET revision = $2, state = coalesce($3, state) WHERE id = $1",
                    conversation_id, ordinal, result.state,
                )
                await conn.execute(
                    "UPDATE iris_ai.ask_run SET turn_id = $2 WHERE id = $1", run_id, turn_id,
                )
                return await self._end(
                    conn, run_id, "completed", "answered", reported_units=result.reported_units,
                )

    async def fail(self, run_id, fence: int, reason: str) -> None:
        """End a run the current attempt could not finish; fenced like a commit."""
        async with self._connect() as conn:
            async with conn.transaction():
                run = await conn.fetchrow(
                    "SELECT state, fence FROM iris_ai.ask_run WHERE id = $1 FOR UPDATE", run_id,
                )
                if run is None or run["state"] in TERMINAL or run["fence"] != fence:
                    return
                await self._end(conn, run_id, "failed", reason)

    async def cancel(self, grant, run_id, *, reader_projection=False) -> dict:
        """Stop: fence the run so no attempt can advance it. Idempotent."""
        async with self._connect() as conn:
            async with conn.transaction():
                reader, scope = await self._principal(conn, grant)
                await self._owned_run(conn, reader, scope, run_id)
                state = await conn.fetchval(
                    "SELECT state FROM iris_ai.ask_run WHERE id = $1 FOR UPDATE", run_id,
                )
                if state not in TERMINAL:
                    await self._end(conn, run_id, "cancelled", "stopped", move_fence=True)
                return await self._projection(conn, run_id, reader=reader_projection)

    async def status(self, grant, run_id, *, reader_projection=False) -> dict:
        """The run's projection. A reconnect renews an active run's grant."""
        async with self._connect() as conn:
            async with conn.transaction():
                claims = await self._verify(conn, grant)
                reader, scope = self._reader(claims)
                await self._owned_run(conn, reader, scope, run_id)
                # Only a grant of exactly the Conversation's scope renews,
                # so a reconnect never widens what the run reads.
                await conn.execute(
                    """UPDATE iris_ai.ask_run r SET reader_grant = $2, grant_expires_at = to_timestamp($3)
                         FROM iris_ai.conversation c
                        WHERE r.id = $1 AND c.id = r.conversation_id AND r.state = ANY($4)
                          AND c.scope_record_id IS NOT DISTINCT FROM $5::bigint
                          AND r.grant_expires_at < to_timestamp($3)""",
                    run_id, grant, claims["exp"], list(ACTIVE), scope,
                )
                return await self._projection(conn, run_id, reader=reader_projection)

    @staticmethod
    async def _projection(conn, run_id, *, reader=False) -> dict:
        run = await conn.fetchrow(
            f"""SELECT {RUN_COLUMNS},
                       extract(epoch FROM coalesce(started_at, finished_at, now()) - created_at)
                           AS queued_seconds,
                       extract(epoch FROM finished_at - created_at) AS latency_seconds,
                       state = 'queued' AND grant_expires_at <= now() AS awaiting_reader
                  FROM iris_ai.ask_run WHERE id = $1""",
            run_id,
        )
        events = await conn.fetch(
            "SELECT sequence, name, data FROM iris_ai.run_event WHERE run_id = $1 ORDER BY sequence",
            run_id,
        )
        evidence = {}
        if reader:
            # Recheck every evidence dependency under begin_research's live RLS,
            # including papers read but not finally cited (ADR-049 §8).
            dependencies = {source for event in events if event["name"] == "tool"
                            for source in event["data"].get("sources", [])}
            citations = await conn.fetch(
                "SELECT c.revision FROM iris_ai.citation c JOIN iris_ai.turn t ON t.id = c.turn_id"
                " WHERE t.run_id = $1", run_id,
            )
            dependencies.update(c["revision"] for c in citations)
            current = await conn.fetch(
                "SELECT cs.id::text || ':' || cs.extraction_hash AS revision"
                " FROM iris_ai.research_chunksets() cs JOIN public.records_record r ON r.id = cs.record_id"
                " WHERE cs.is_active AND cs.id::text || ':' || cs.extraction_hash = ANY($1::text[])",
                list(dependencies),
            ) if dependencies else []
            counted_unreadable = await conn.fetchval(
                f"SELECT EXISTS (SELECT 1 FROM iris_ai.turn t WHERE t.run_id = $1 AND {COUNTED_UNREADABLE})",
                run_id,
            )
            evidence["sources_available"] = (
                {row["revision"] for row in current} == dependencies and not counted_unreadable)
        return {
            **evidence,
            "id": str(run["id"]),
            "conversation_id": str(run["conversation_id"]),
            "state": run["state"],
            "end_reason": run["end_reason"],
            "question": run["question"],
            "base_revision": run["base_revision"],
            "deadline_at": run["deadline_at"].isoformat(),
            "allowance": run["allowance"],
            "pinned": run["pinned"],
            "version": run["version"],
            "turn_id": str(run["turn_id"]) if run["turn_id"] else None,
            "created_at": run["created_at"].isoformat(),
            "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
            "depth": run["depth"],
            # Queued on a lapsed grant: it starts once the reader reconnects.
            "awaiting_reader": bool(run["awaiting_reader"]),
            "started_at": run["started_at"].isoformat() if run["started_at"] else None,
            # Queue-inclusive: waiting counts against the deadline and the latency.
            "queued_seconds": float(run["queued_seconds"]),
            "latency_seconds": (float(run["latency_seconds"])
                                if run["latency_seconds"] is not None else None),
            "events": [dict(e) for e in events],
        }

    async def reopen(self, grant, conversation_id, *, include_runs=False) -> dict:
        """The Conversation's committed Turns, in order, with their citations."""
        async with self._connect() as conn:
            async with conn.transaction(isolation="repeatable_read"):
                reader, scope = await self._principal(conn, grant)
                revision = await conn.fetchval(
                    f"""SELECT revision FROM iris_ai.conversation
                         WHERE id = $1 AND reader_id = $3 AND deleted_at IS NULL AND {IN_SCOPE}""",
                    conversation_id, scope, reader,
                )
                if revision is None:
                    raise NotFound
                turns = await conn.fetch(
                    f"""SELECT t.id, t.run_id, t.ordinal, t.question, t.answer, t.kind, t.facts, t.created_at, r.pinned,
                              {CURRENT_SOURCE_TURN} AS sources_available
                         FROM iris_ai.turn t JOIN iris_ai.ask_run r ON r.id = t.run_id
                        WHERE t.conversation_id = $1 ORDER BY t.ordinal""",
                    conversation_id,
                )
                citations = await conn.fetch(
                    """SELECT c.turn_id, c.position, c.record_id, c.page, c.quote, c.revision
                         FROM iris_ai.citation c JOIN iris_ai.turn t ON t.id = c.turn_id
                        WHERE t.conversation_id = $1 ORDER BY c.turn_id, c.position""",
                    conversation_id,
                )
                run_ids = await conn.fetch(
                    "SELECT id FROM iris_ai.ask_run WHERE conversation_id = $1 ORDER BY created_at, id",
                    conversation_id,
                ) if include_runs else []
                runs = [await self._projection(conn, row["id"], reader=True) for row in run_ids]
        by_turn: dict = {}
        for c in citations:
            by_turn.setdefault(c["turn_id"], []).append(
                {"record_id": c["record_id"], "page": c["page"], "quote": c["quote"],
                 "revision": c["revision"]}
            )
        return {
            "id": str(conversation_id),
            "revision": revision,
            **({"runs": runs} if include_runs else {}),
            "turns": [{
                "id": str(t["id"]), "run_id": str(t["run_id"]), "ordinal": t["ordinal"],
                "question": t["question"],
                "answer": (t["answer"] if t["sources_available"] else
                           "This answer is unavailable because its sources changed or are no longer readable."),
                "kind": t["kind"],
                "created_at": t["created_at"].isoformat(),
                "pinned": t["pinned"],
                "citations": by_turn.get(t["id"], []) if t["sources_available"] else [],
                "facts": shown_facts(t["facts"]) if t["sources_available"] else [],
            } for t in turns],
        }

    async def delete_conversation(self, grant, conversation_id) -> None:
        async with self._connect() as conn:
            async with conn.transaction():
                reader, scope = await self._principal(conn, grant)
                found = await conn.fetchval(
                    f"""SELECT id FROM iris_ai.conversation
                         WHERE id = $1 AND reader_id = $3 AND deleted_at IS NULL AND {IN_SCOPE}
                         FOR UPDATE""",
                    conversation_id, scope, reader,
                )
                if found is None:
                    raise NotFound
                await self._delete(conn, conversation_id)

    async def _delete(self, conn, conversation_id) -> None:
        """Fence first, then remove content; the caller holds the Conversation lock."""
        await conn.execute(
            "UPDATE iris_ai.conversation SET deleted_at = now(), state = '{}' WHERE id = $1",
            conversation_id,
        )
        active = await conn.fetch(
            "SELECT id FROM iris_ai.ask_run WHERE conversation_id = $1 AND state = ANY($2) FOR UPDATE",
            conversation_id, list(ACTIVE),
        )
        for run in active:
            await self._end(conn, run["id"], "deleted", "conversation_deleted", move_fence=True)
        await conn.execute(
            """DELETE FROM iris_ai.run_event
                WHERE run_id IN (SELECT id FROM iris_ai.ask_run WHERE conversation_id = $1)""",
            conversation_id,
        )
        await conn.execute(
            """DELETE FROM iris_ai.research_handle
                WHERE run_id IN (SELECT id FROM iris_ai.ask_run WHERE conversation_id = $1)""",
            conversation_id,
        )
        await conn.execute(
            """DELETE FROM iris_ai.citation
                WHERE turn_id IN (SELECT id FROM iris_ai.turn WHERE conversation_id = $1)""",
            conversation_id,
        )
        await conn.execute("DELETE FROM iris_ai.turn WHERE conversation_id = $1", conversation_id)
        await conn.execute(
            # The hash would let a short question be guessed back.
            "UPDATE iris_ai.ask_run SET question = NULL, request_hash = '' WHERE conversation_id = $1",
            conversation_id,
        )

    async def purge_departed(self) -> int:
        """Delete every Conversation whose reader's account no longer exists."""
        purged = 0
        async with self._connect() as conn:
            readers = await conn.fetch(
                "SELECT DISTINCT reader_id FROM iris_ai.conversation WHERE deleted_at IS NULL",
            )
            for row in readers:
                async with conn.transaction():
                    status = await conn.fetchval(
                        "SELECT iris_authz.reader_status($1)", row["reader_id"],
                    )
                    if status != "gone":
                        continue
                    ids = await conn.fetch(
                        """SELECT id FROM iris_ai.conversation
                            WHERE reader_id = $1 AND deleted_at IS NULL FOR UPDATE""",
                        row["reader_id"],
                    )
                    for conversation in ids:
                        await self._delete(conn, conversation["id"])
                        purged += 1
        return purged
