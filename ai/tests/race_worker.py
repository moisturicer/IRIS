"""An independent process that commits or cancels one run (IR-722 race tests).

`python -m ai.tests.race_worker <dsn> commit <run_id> <fence> <answer>`
`python -m ai.tests.race_worker <dsn> stop <run_id> <grant>`

Waits on advisory lock 722 so the parent can release every worker at once;
prints the outcome.
"""

import asyncio
import sys

import asyncpg

from ai.runs.executor import Result
from ai.runs.store import Fenced, RunStore

BARRIER = 722


async def _barrier(dsn):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT pg_advisory_lock_shared($1)", BARRIER)
        await conn.execute("SELECT pg_advisory_unlock_shared($1)", BARRIER)
    finally:
        await conn.close()


async def main(dsn, action, run_id, *rest):
    await _barrier(dsn)
    store = RunStore(dsn)
    if action == "commit":
        fence, answer = int(rest[0]), rest[1]
        try:
            return await store.commit_final(run_id, fence, Result(answer=answer))
        except Fenced:
            return "fenced"
    return (await store.cancel(rest[0], run_id))["state"]


if __name__ == "__main__":
    print(asyncio.run(main(*sys.argv[1:])))
