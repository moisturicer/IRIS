"""A run's spending, for operators (IR-725).

`python -m ai.admission.report <run_id>` with RUNS_DATABASE_URL. Each
physical attempt's purpose, version, model, state and reserved and charged
usage, the totals, and what remains of the run's original allowance. The
ledger holds no prompt, answer or opaque payload, so none can appear here.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import asyncpg

from .ledger import OWNER
from .limits import Ceiling
from .scope import run_key

_ATTEMPT = (
    "id", "operation", "purpose", "purpose_version", "model", "lane", "state", "sent",
    "usage_reported", "reserved_input_tokens", "reserved_output_tokens", "reserved_cost_micros",
    "charge_attempts", "charge_input_tokens", "charge_output_tokens", "charge_cost_micros",
)


async def run_report(dsn: str, run_id) -> dict:
    run_id = uuid.UUID(str(run_id))
    conn = await asyncpg.connect(dsn)
    try:
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        allowance = await conn.fetchval("SELECT allowance FROM iris_ai.ask_run WHERE id = $1", run_id)
        rows = await conn.fetch(
            f"""SELECT {", ".join(_ATTEMPT)} FROM public.ai_providerreservation
                 WHERE run_key = $1 AND owner = $2 ORDER BY id""",
            run_key(run_id), OWNER,
        )
    finally:
        await conn.close()
    attempts = [dict(row) for row in rows]
    charged = {name: sum(a[f"charge_{name}"] for a in attempts)
               for name in ("attempts", "input_tokens", "output_tokens", "cost_micros")}
    report = {"run_id": str(run_id), "attempts": attempts, "charged": charged,
              "unreported": sum(1 for a in attempts if a["sent"] and not a["usage_reported"])}
    if allowance is not None:
        ceiling = Ceiling.of_allowance(allowance)
        report["allowance"] = allowance
        report["remaining"] = {name: getattr(ceiling, name) - charged[name] for name in charged}
    return report


def main() -> None:
    from ai.infrastructure.settings import settings

    if len(sys.argv) != 2 or not settings.RUNS_DATABASE_URL:
        raise SystemExit("usage: python -m ai.admission.report <run_id> (needs RUNS_DATABASE_URL)")
    print(json.dumps(asyncio.run(run_report(settings.RUNS_DATABASE_URL, sys.argv[1])), indent=2))


if __name__ == "__main__":
    main()
