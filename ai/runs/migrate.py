"""The `iris_ai` schema's only migrator (IR-722, ADR-049 §1).

`python -m ai.runs.migrate` with RUNS_MIGRATION_DATABASE_URL, a maintenance
login. Applies `migrations/*.sql` in name order, each once, then (re)grants
the runtime role. Refuses to run as a runtime login.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).with_name("migrations")
RUNTIME_ROLE = "iris_ai_runtime"
RUNTIME_ROLES = ("iris_ai_runtime", "iris_django_runtime")

#: What the AI runtime may do; Django's runtime gets nothing here.
GRANTS = (
    "GRANT USAGE ON SCHEMA iris_ai TO {role}",
    "GRANT SELECT, INSERT, UPDATE ON iris_ai.conversation, iris_ai.ask_run TO {role}",
    "GRANT SELECT, INSERT, DELETE ON iris_ai.turn, iris_ai.citation, iris_ai.run_event,"
    " iris_ai.research_handle TO {role}",
    "GRANT SELECT, INSERT, UPDATE ON iris_ai.attempt_accounting TO {role}",
    "GRANT USAGE ON SEQUENCE iris_ai.attempt_accounting_id_seq TO {role}",
    "GRANT SELECT, INSERT, DELETE ON iris_ai.manuscript_receipt TO {role}",
    "GRANT UPDATE (authority_generation, acknowledged_at) ON iris_ai.manuscript_receipt TO {role}",
    "GRANT SELECT, INSERT ON iris_ai.manuscript_invalidation_receipt TO {role}",
)


class RefusedLogin(Exception):
    pass


async def _refuse_runtime_login(conn) -> None:
    superuser = await conn.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    if superuser:
        return
    for role in RUNTIME_ROLES:
        member = await conn.fetchval(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)"
            " THEN pg_has_role(current_user, $1, 'MEMBER') ELSE false END", role,
        )
        if member:
            raise RefusedLogin(f"migrations must not run as a runtime login ({role})")


async def migrate(dsn: str) -> list[str]:
    """Apply pending migrations; the names applied."""
    conn = await asyncpg.connect(dsn)
    try:
        await _refuse_runtime_login(conn)
        applied = []
        async with conn.transaction():
            # Serialises concurrent migrators.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('iris_ai.migrate'))")
            await conn.execute(
                "CREATE SCHEMA IF NOT EXISTS iris_ai;"
                " REVOKE ALL ON SCHEMA iris_ai FROM PUBLIC;"
                " CREATE TABLE IF NOT EXISTS iris_ai.schema_migration"
                " (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r["name"] for r in await conn.fetch("SELECT name FROM iris_ai.schema_migration")}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.name in done:
                    continue
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO iris_ai.schema_migration (name) VALUES ($1)", path.name)
                applied.append(path.name)
            if await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", RUNTIME_ROLE):
                for grant in GRANTS:
                    await conn.execute(grant.format(role=RUNTIME_ROLE))
        return applied
    finally:
        await conn.close()


def main() -> None:
    from ai.infrastructure.settings import settings

    if not settings.RUNS_MIGRATION_DATABASE_URL:
        raise SystemExit("RUNS_MIGRATION_DATABASE_URL is required")
    applied = asyncio.run(migrate(settings.RUNS_MIGRATION_DATABASE_URL))
    print("applied: " + (", ".join(applied) or "nothing"))


if __name__ == "__main__":
    main()
