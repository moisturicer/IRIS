"""Runtime database connections, pooled per process when configured (IR-1012).

`configure(dsn, size, acquire_seconds)` turns pooling on for one DSN; until
then `connection(dsn)` opens and closes a connection per use, as before.
A pool belongs to one event loop. Release resets the session (asyncpg's
`RESET ALL`), and the grant binding is transaction-local anyway, so a
returned connection carries nothing to its next user.
"""

from __future__ import annotations

import asyncio
import json
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg

#: A pooled connection serves every caller, so it carries one name.
APP_NAME = "iris-ai-pooled"


class Exhausted(Exception):
    """No connection within the acquire timeout, or PostgreSQL refused one."""


@dataclass(frozen=True)
class PoolSize:
    size: int
    acquire_seconds: float


_configured: dict[str, PoolSize] = {}
#: loop -> {dsn: Task[Pool]}
_pools: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def configure(dsn: str, size: int, acquire_seconds: float) -> None:
    if size <= 0 or acquire_seconds <= 0:
        raise ValueError("pool size and acquire timeout must be positive")
    _configured[dsn] = PoolSize(size, acquire_seconds)


def unconfigure(dsn: str) -> None:
    _configured.pop(dsn, None)


async def _init(conn) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


def _pool(dsn: str, limits: PoolSize):
    loop = asyncio.get_running_loop()
    mine = _pools.setdefault(loop, {})
    task = mine.get(dsn)
    if task is None or (task.done() and task.exception() is not None):
        task = mine[dsn] = loop.create_task(_create(dsn, limits))
    return task


async def _create(dsn: str, limits: PoolSize):
    return await asyncpg.create_pool(dsn, min_size=0, max_size=limits.size, init=_init,
                                     server_settings={"application_name": APP_NAME})


@asynccontextmanager
async def connection(dsn: str, application_name: str = APP_NAME):
    limits = _configured.get(dsn)
    if limits is None:
        try:
            conn = await asyncpg.connect(dsn, server_settings={"application_name": application_name})
        except asyncpg.TooManyConnectionsError:
            raise Exhausted from None
        try:
            await _init(conn)
            yield conn
        finally:
            await conn.close()
        return
    try:
        pool = await _pool(dsn, limits)
        conn = await pool.acquire(timeout=limits.acquire_seconds)
    except (asyncio.TimeoutError, asyncpg.TooManyConnectionsError):
        raise Exhausted from None
    try:
        yield conn
    finally:
        await pool.release(conn)


async def close() -> None:
    """Close this loop's pools; the worker calls it on shutdown."""
    mine = _pools.pop(asyncio.get_running_loop(), {})
    for task in mine.values():
        if task.done() and task.exception() is None:
            await task.result().close()
