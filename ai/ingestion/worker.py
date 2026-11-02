"""Isolated local-work acknowledgements; no extraction or model call (IR-737)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass

import asyncpg

log = logging.getLogger(__name__)
WAKEUP_KEY = "iris_ai:ingestion:wakeup"


@dataclass(frozen=True)
class Batch:
    after: uuid.UUID | None
    acknowledged: int


async def acknowledge(conn, token: str) -> bool:
    """A source is exposed only inside its verified processing transaction."""
    async with conn.transaction():
        try:
            await conn.fetchval("SELECT iris_authz.begin_research($1, 'ingestion')", token)
        except asyncpg.InsufficientPrivilegeError:
            return False
        source = await conn.fetchrow("SELECT work_id, record_id, revision FROM iris_authz.processing_source()")
        if source is None:
            return False
        result = await conn.execute(
            "INSERT INTO iris_ai.manuscript_receipt(work_id, record_id, revision)"
            " VALUES ($1, $2, $3) ON CONFLICT (work_id) DO NOTHING",
            source["work_id"], source["record_id"], source["revision"],
        )
        return result == "INSERT 0 1"


async def consume(dsn: str, *, limit: int, after: uuid.UUID | None = None) -> Batch:
    """Scan one bounded page of committed grants, regardless of queue delivery."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    conn = await asyncpg.connect(dsn)
    try:
        work = await conn.fetch("SELECT * FROM iris_authz.pending_manuscript_work($1, $2)", limit, after)
        count = 0
        for row in work:
            count += await acknowledge(conn, row["grant_token"])
        return Batch(work[-1]["work_id"] if len(work) == limit else None, count)
    finally:
        await conn.close()


async def serve(dsn: str, *, limit: int, poll_seconds: float, once=False, redis_url=""):
    after = None
    while True:
        batch = await consume(dsn, limit=limit, after=after)
        if once:
            return batch
        after = batch.after
        if after is not None:
            continue
        if redis_url:
            try:
                from redis.asyncio import Redis
                async with Redis.from_url(redis_url, socket_connect_timeout=1,
                                          socket_timeout=poll_seconds + 1) as client:
                    await client.blpop(WAKEUP_KEY, timeout=poll_seconds)
                continue
            except Exception:
                log.warning("ingestion wakeup unavailable; polling committed work")
        await asyncio.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--poll-seconds", type=float, required=True)
    args = parser.parse_args()
    dsn = os.environ.get("RUNS_DATABASE_URL", "")
    if not dsn or not 1 <= args.limit <= 1000 or not 0 < args.poll_seconds <= 60:
        parser.error("RUNS_DATABASE_URL, limit 1..1000 and poll-seconds >0 and <=60 are required")
    asyncio.run(serve(dsn, limit=args.limit, poll_seconds=args.poll_seconds,
                      once=args.once, redis_url=os.environ.get("INGESTION_REDIS_URL", "")))


if __name__ == "__main__":
    main()
