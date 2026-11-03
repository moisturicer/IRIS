"""One backend test run per Postgres server (IR-835).

Two runs sharing a server took the suite from 24 minutes to a projected two
hours. A run holds a session advisory lock in the maintenance database, which
every test database on the server shares, so a second run is refused at once.
The lock dies with its connection, so a crashed run cannot leave it behind.
"""

from __future__ import annotations

import os

#: Children of a locked run (e.g. a nested pytest) inherit this and skip the lock.
HELD_ENV_VAR = "IRIS_TEST_RUN_LOCK_HELD"
LOCK_KEY = 835_000_001
APPLICATION_PREFIX = "iris-pytest"


class ConcurrentTestRun(Exception):
    pass


def application_name(pid: int, cwd: str) -> str:
    # Postgres truncates application_name to 63 bytes; keep the pid first.
    return f"{APPLICATION_PREFIX} pid={pid} {cwd}"[:63]


def refusal(holder: str | None) -> str:
    held_by = holder or "another session"
    return (
        "Another backend test run is already using this Postgres server "
        f"({held_by}). Two runs on one server slow each other several-fold. "
        "Wait for it to finish or stop it, then run again (IR-835)."
    )


def acquire(connection, key: int = LOCK_KEY):
    """Take the run lock on ``connection`` or raise ConcurrentTestRun.

    The connection must stay open for the whole run; closing it releases the lock.
    """
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        if cursor.fetchone()[0]:
            return connection
        cursor.execute(
            """
            SELECT a.application_name FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory' AND l.granted
              AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
              AND l.classid = 0 AND l.objid = %s AND l.objsubid = 1
              AND a.pid <> pg_backend_pid()
            LIMIT 1
            """,
            [key],
        )
        row = cursor.fetchone()
    connection.close()
    raise ConcurrentTestRun(refusal(row[0] if row and row[0] else None))


def should_lock(*, environ, collect_only: bool, xdist_worker: bool, needs_database: bool) -> bool:
    if collect_only or xdist_worker or not needs_database:
        return False
    return not environ.get(HELD_ENV_VAR)


def connect_to_maintenance_database(settings_dict):
    import psycopg2

    return psycopg2.connect(
        dbname="postgres",
        user=settings_dict.get("USER"),
        password=settings_dict.get("PASSWORD"),
        host=settings_dict.get("HOST") or "localhost",
        port=settings_dict.get("PORT") or 5432,
        application_name=application_name(os.getpid(), os.getcwd()),
        connect_timeout=5,
    )
