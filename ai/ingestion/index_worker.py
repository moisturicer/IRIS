"""Separately enabled ingestion worker; no reader slots or automatic deployment."""

from __future__ import annotations

import argparse
import asyncio
import os
from types import SimpleNamespace

from ai.admission.limits import NotConfigured, read
from ai.admission.errors import AdmissionDenied
from .embeddings import VoyageContextEmbeddings
from .indexing import Bounds, connect, process


async def consume(dsn, *, limit, pipeline, provider, limits, bounds, after=None):
    conn = await connect(dsn)
    try:
        work = await conn.fetch(
            "SELECT * FROM iris_authz.pending_manuscript_work($1,$2)", limit, after
        )
    finally:
        await conn.close()
    outcomes = {}
    for row in work:
        try:
            result = await process(
                dsn,
                row["grant_token"],
                pipeline=pipeline,
                provider=provider,
                limits=limits,
                bounds=bounds,
            )
        except AdmissionDenied:
            result = "admission_refused"
        except Exception:
            # Do not expose provider bodies, storage details or Manuscript text.
            result = "retry_pending"
        outcomes[result] = outcomes.get(result, 0) + 1
    return outcomes, work[-1]["work_id"] if len(work) == limit else None


async def serve(dsn, *, once, poll_seconds, **kw):
    after = None
    while True:
        outcomes, after = await consume(dsn, after=after, **kw)
        print(outcomes, flush=True)
        if once:
            return
        if after is None:
            await asyncio.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    for flag, kind in [
        ("limit", int),
        ("poll-seconds", float),
        ("lease-seconds", int),
        ("timeout-seconds", float),
        ("max-attempts", int),
        ("max-input-tokens", int),
        ("max-cost-usd", float),
    ]:
        parser.add_argument("--" + flag, type=kind, required=True)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--dimensions", type=int, required=True)
    parser.add_argument("--data-policy", choices=["no-training"], required=True)
    args = parser.parse_args()
    dsn = os.environ.get("RUNS_DATABASE_URL", "")
    if not dsn or not 1 <= args.limit <= 1000 or not 0 < args.poll_seconds <= 60:
        parser.error(
            "restricted RUNS_DATABASE_URL, limit 1..1000 and polling 0..60 seconds required"
        )
    try:
        limits = read(SimpleNamespace(**os.environ))
        bounds = Bounds(
            args.lease_seconds,
            args.timeout_seconds,
            args.max_attempts,
            args.max_input_tokens,
            args.max_cost_usd,
        )
        provider = VoyageContextEmbeddings(
            os.environ.get("VOYAGE_API_KEY", ""),
            model=args.model,
            dimensions=args.dimensions,
            data_policy=args.data_policy,
        )
    except (ValueError, NotConfigured) as exc:
        parser.error(str(exc))
    asyncio.run(
        serve(
            dsn,
            once=args.once,
            poll_seconds=args.poll_seconds,
            limit=args.limit,
            pipeline=args.pipeline,
            provider=provider,
            limits=limits,
            bounds=bounds,
        )
    )


if __name__ == "__main__":
    main()
