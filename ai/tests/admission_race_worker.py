"""An independent process that asks for one reservation (IR-725 race tests).

`python -m ai.tests.admission_race_worker <dsn> <run_id> <fence> <limits.json>`

Waits on advisory lock 725 so the parent can release every worker at once;
prints `admitted` or the refusal reason. Never settles: the reservation stays.
"""

import asyncio
import json
import sys
from types import SimpleNamespace

import asyncpg

from ai.admission.errors import AdmissionDenied
from ai.admission.ledger import Ledger, Request
from ai.admission.scope import RunBinding

BARRIER = 725


async def main(dsn, run_id, fence, limits):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT pg_advisory_lock_shared($1)", BARRIER)
        await conn.execute("SELECT pg_advisory_unlock_shared($1)", BARRIER)
    finally:
        await conn.close()
    ledger = Ledger.from_settings(dsn, SimpleNamespace(**json.loads(limits)))
    try:
        await ledger.admit(Request(
            operation="llm", purpose="answer", purpose_version="race", lane="research",
            account="race", models=("scripted-model",), input_tokens=10, output_tokens=10,
        ), RunBinding(run_id, int(fence)))
    except AdmissionDenied as refused:
        return refused.reason
    return "admitted"


if __name__ == "__main__":
    print(asyncio.run(main(*sys.argv[1:])))
