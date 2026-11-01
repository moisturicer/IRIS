"""AI-owned run and Conversation state in PostgreSQL (IR-722, ADR-049 §10, §21).

Each operation is one short transaction on its own connection; none is open
while an executor runs. Reader operations bind a `reader_session` grant
through `iris_authz.begin_research`; a run belongs to the grant's reader
alone, and anything else is the same NotFound as a missing row.

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

import asyncpg

from ai.runs.executor import Result

APP_NAME = "iris-ai-runs"
ACTIVE = ("queued", "running")
TERMINAL = ("completed", "cancelled", "conflict", "expired", "failed", "deleted")

RUN_COLUMNS = (
    "id, reader_id, conversation_id, request_hash, question, base_revision, state, end_reason,"
    " deadline_at, allowance, pinned, fence, version, turn_id, created_at, finished_at"
)


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


class _Raced(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    fence: int
    question: str
    pinned: dict
    #: The Conversation's Paper Chat scope, if any (IR-719).
    scope_record_id: int | None = None


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
    async def _principal(conn, grant: str | None) -> tuple[int, int | None]:
        """The verified reader and Paper Chat scope, bound for this transaction."""
        if not grant:
            raise Unauthorized
        try:
            claims = await conn.fetchval("SELECT iris_authz.begin_research($1, 'reader_session')", grant)
        except asyncpg.InsufficientPrivilegeError:
            raise Unauthorized from None
        scope = claims.get("rec")
        return int(claims["sub"]), int(scope) if scope is not None else None

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
                    deadline_seconds: int, allowance: dict, pinned: dict) -> tuple[dict, bool]:
        """The run for this request identity, and whether it is new."""
        digest = request_hash(question, conversation_id, base_revision)
        async with self._connect() as conn:
            for _ in range(2):
                try:
                    async with conn.transaction():
                        return await self._admit(
                            conn, grant, key, question, conversation_id, base_revision,
                            digest, deadline_seconds, allowance, pinned,
                        )
                except _Raced:
                    continue
        raise Conflict("request_in_flight")

    async def _admit(self, conn, grant, key, question, conversation_id, base_revision,
                     digest, deadline_seconds, allowance, pinned):
        reader, scope = await self._principal(conn, grant)
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
        row = await conn.fetchrow(
            f"""INSERT INTO iris_ai.ask_run
                    (id, reader_id, conversation_id, request_key, request_hash, question,
                     base_revision, deadline_at, allowance, pinned)
                VALUES ($1, $2, $3, $4, $5, $6, $7, now() + make_interval(secs => $8), $9, $10)
                ON CONFLICT (reader_id, request_key) DO NOTHING
                RETURNING {RUN_COLUMNS}""",
            uuid.uuid4(), reader, conversation_id, key, digest, question, revision,
            float(deadline_seconds), allowance, pinned,
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

    async def claim(self, run_id, *, worker: str, lease_seconds: int, executor: str,
                    reserved_units: int) -> Claim | None:
        """Take the run's lease under a new fence; None if it cannot run now."""
        async with self._connect() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE iris_ai.ask_run r
                          SET state = 'running', fence = r.fence + 1, lease_owner = $2,
                              lease_expires_at = now() + make_interval(secs => $3),
                              version = r.version + 1
                         FROM iris_ai.conversation c
                        WHERE r.id = $1 AND c.id = r.conversation_id AND c.deleted_at IS NULL
                          AND r.state IN ('queued', 'running') AND r.deadline_at > now()
                          AND (r.lease_expires_at IS NULL OR r.lease_expires_at <= now())
                    RETURNING r.fence, r.question, r.allowance, r.pinned, c.scope_record_id""",
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
                used = await conn.fetchval(
                    "SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = $1", run_id,
                )
                if used >= row["allowance"]["max_attempts"]:
                    await self._end(conn, run_id, "failed", "attempts_exhausted")
                    return None
                await conn.execute(
                    """INSERT INTO iris_ai.attempt_accounting (run_id, fence, executor, reserved_units)
                       VALUES ($1, $2, $3, $4)""",
                    run_id, row["fence"], executor, reserved_units,
                )
                await self._journal(conn, run_id, "started", {"attempt": used + 1})
                return Claim(fence=row["fence"], question=row["question"], pinned=row["pinned"],
                             scope_record_id=row["scope_record_id"])

    async def _end(self, conn, run_id, state: str, reason: str, *, move_fence=False,
                   reported_units: int | None = None) -> str:
        await conn.execute(
            f"""UPDATE iris_ai.ask_run
                   SET state = $2, end_reason = $3, finished_at = now(), lease_owner = NULL,
                       lease_expires_at = NULL, version = version + 1
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
        await self._journal(conn, run_id, state, {"reason": reason})
        return state

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
                    """INSERT INTO iris_ai.turn (id, conversation_id, run_id, ordinal, question, answer)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    turn_id, conversation_id, run_id, ordinal, run["question"], result.answer,
                )
                if result.citations:
                    await conn.executemany(
                        """INSERT INTO iris_ai.citation (turn_id, position, record_id, page, quote, revision)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        [(turn_id, n, c.record_id, c.page, c.quote, c.revision)
                         for n, c in enumerate(result.citations, start=1)],
                    )
                await conn.execute(
                    "UPDATE iris_ai.conversation SET revision = $2 WHERE id = $1",
                    conversation_id, ordinal,
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

    async def cancel(self, grant, run_id) -> dict:
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
                return await self._projection(conn, run_id)

    async def status(self, grant, run_id) -> dict:
        async with self._connect() as conn:
            async with conn.transaction():
                reader, scope = await self._principal(conn, grant)
                await self._owned_run(conn, reader, scope, run_id)
                return await self._projection(conn, run_id)

    @staticmethod
    async def _projection(conn, run_id) -> dict:
        run = await conn.fetchrow(f"SELECT {RUN_COLUMNS} FROM iris_ai.ask_run WHERE id = $1", run_id)
        events = await conn.fetch(
            "SELECT sequence, name, data FROM iris_ai.run_event WHERE run_id = $1 ORDER BY sequence",
            run_id,
        )
        return {
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
            "events": [dict(e) for e in events],
        }

    async def reopen(self, grant, conversation_id) -> dict:
        """The Conversation's committed Turns, in order, with their citations."""
        async with self._connect() as conn:
            async with conn.transaction():
                reader, scope = await self._principal(conn, grant)
                revision = await conn.fetchval(
                    f"""SELECT revision FROM iris_ai.conversation
                         WHERE id = $1 AND reader_id = $3 AND deleted_at IS NULL AND {IN_SCOPE}""",
                    conversation_id, scope, reader,
                )
                if revision is None:
                    raise NotFound
                turns = await conn.fetch(
                    """SELECT t.id, t.run_id, t.ordinal, t.question, t.answer, t.created_at, r.pinned
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
        by_turn: dict = {}
        for c in citations:
            by_turn.setdefault(c["turn_id"], []).append(
                {"record_id": c["record_id"], "page": c["page"], "quote": c["quote"],
                 "revision": c["revision"]}
            )
        return {
            "id": str(conversation_id),
            "revision": revision,
            "turns": [{
                "id": str(t["id"]), "run_id": str(t["run_id"]), "ordinal": t["ordinal"],
                "question": t["question"], "answer": t["answer"],
                "created_at": t["created_at"].isoformat(),
                "pinned": t["pinned"],
                "citations": by_turn.get(t["id"], []),
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
            "UPDATE iris_ai.conversation SET deleted_at = now() WHERE id = $1", conversation_id,
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
