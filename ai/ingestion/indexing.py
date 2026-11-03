"""Resumable, admitted indexing of one immutable Manuscript revision (IR-751)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass

import asyncpg

from ai.admission.errors import AdmissionDenied
from ai.admission.ledger import Ledger, Request, Usage, estimate_tokens


@dataclass(frozen=True)
class Bounds:
    lease_seconds: int
    timeout_seconds: float
    max_attempts: int
    max_input_tokens: int
    max_cost_usd: float

    def __post_init__(self):
        if (
            not all(math.isfinite(x) and x > 0 for x in asdict(self).values())
            or self.lease_seconds <= self.timeout_seconds
            or self.lease_seconds > 86400
        ):
            raise ValueError("explicit positive bounds and lease longer than timeout are required")

    @property
    def allowance(self):
        return {**asdict(self), "max_output_tokens": 0}


@dataclass(frozen=True)
class Binding:
    run_id: int
    fence: uuid.UUID
    token: str

    @property
    def key(self):
        return f"ingestion:{self.run_id}"


class IndexingLedger(Ledger):
    """Ingestion spends the SAME campaign, with its own persisted job ceiling."""

    async def _work(self, conn, binding):
        await conn.fetchval("SELECT iris_authz.begin_research($1,'ingestion')", binding.token)
        return await conn.fetchrow(
            "SELECT state,attempt AS fence,allowance,lease_until AS deadline_at"
            " FROM iris_ai.index_job WHERE id=$1"
            " AND EXISTS(SELECT 1 FROM iris_authz.indexing_source() s WHERE s.work_id=index_job.work_id)",
            binding.run_id,
        )

    async def _reserve(self, conn, limits, request, binding, wanted):
        if request.lane != "ingestion":
            raise AdmissionDenied("wrong_lane")
        return await super()._reserve(conn, limits, request, binding, wanted)


async def connect(dsn):
    conn = await asyncpg.connect(dsn)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn


async def source(conn, token):
    await conn.fetchval("SELECT iris_authz.begin_research($1,'ingestion')", token)
    await conn.fetchrow("SELECT * FROM iris_authz.lock_processing_source()")
    return await conn.fetchrow("SELECT * FROM iris_authz.indexing_source()")


async def space(conn, provider):
    row = await conn.fetchrow(
        "SELECT id,model_id,dimensions,metric FROM public.ai_embeddingspace" " WHERE state='active'"
    )
    if (
        row is None
        or row["model_id"] != provider.model
        or row["dimensions"] != provider.dimensions
        or row["dimensions"] != 1024
        or row["metric"] != "cosine"
        or provider.data_policy != "no-training"
    ):
        raise AdmissionDenied("incompatible_embedding_space")
    return row


def checked_vectors(vectors, count, dimensions):
    if len(vectors) != count or any(
        len(v) != dimensions
        or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
        or not any(v)
        for v in vectors
    ):
        raise ValueError("incomplete or incompatible embedding output")
    return vectors


async def process(dsn, token, *, pipeline, provider, limits, bounds: Bounds):
    """One bounded attempt. Completed batches survive takeover; no hidden retries.

    Every physical send has a shared-ledger reservation. A crash after sending
    but before durable output is an unknown outcome, never exactly-once billing.
    """
    from apps.ai.providers.batching import window_for_embedding

    if not pipeline:
        raise ValueError("a pinned extraction pipeline is required")
    conn = await connect(dsn)
    fence = uuid.uuid4()
    try:
        async with conn.transaction():
            current = await source(conn, token)
            if current is None:
                return "withheld"
            embedding_space = await space(conn, provider)
            extraction = await conn.fetchval(
                "SELECT payload FROM iris_ai.extraction_revision WHERE work_id=$1 AND pipeline=$2",
                current["work_id"],
                pipeline,
            )
            if extraction is None:
                return "pending_extraction"
            chunks = extraction["chunks"]
            if not chunks or len(chunks) >= 1000000:
                return "incomplete"
            summary = f"{current['title']}. {current['abstract']}"
            windows = [[summary], *window_for_embedding([c["text"] for c in chunks])]
            payload = {**extraction, "windows": [len(w) for w in windows], "summary": summary}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            job = await conn.fetchrow(
                "SELECT *,lease_until>clock_timestamp() AS leased FROM iris_ai.index_job"
                " WHERE work_id=$1 AND generation=$2 AND pipeline=$3 AND space_id=$4 AND input_hash=$5 FOR UPDATE",
                current["work_id"],
                current["generation"],
                pipeline,
                embedding_space["id"],
                digest,
            )
            if job and job["state"] == "complete":
                await activate(conn, job)
                return "duplicate"
            if job and job["leased"]:
                return "busy"
            if job:
                await conn.execute(
                    "UPDATE iris_ai.index_job SET attempt=$2,lease_until=clock_timestamp()"
                    "+$3*interval '1 second' WHERE id=$1",
                    job["id"],
                    fence,
                    bounds.lease_seconds,
                )
                job = {**job, "attempt": fence}
            else:
                job = await conn.fetchrow(
                    "INSERT INTO iris_ai.index_job(work_id,revision,record_id,generation,pipeline,space_id,"
                    "model,dimensions,input_hash,payload,allowance,state,attempt,lease_until)"
                    " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'running',$12,clock_timestamp()+$13*interval '1 second') RETURNING *",
                    current["work_id"],
                    current["revision"],
                    current["record_id"],
                    current["generation"],
                    pipeline,
                    embedding_space["id"],
                    provider.model,
                    provider.dimensions,
                    digest,
                    payload,
                    bounds.allowance,
                    fence,
                    bounds.lease_seconds,
                )
        binding = Binding(job["id"], fence, token)
        ledger = IndexingLedger(dsn, limits)
        for ordinal, texts in enumerate(windows):
            async with conn.transaction():
                now = await source(conn, token)
                if not same_source(now, job) or not await claimed(conn, binding):
                    return "stale"
                if await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM iris_ai.embedding_batch WHERE job_id=$1 AND ordinal=$2)",
                    job["id"],
                    ordinal,
                ):
                    continue
            ticket = await ledger.admit(
                Request(
                    operation="embed",
                    purpose="index_document",
                    purpose_version="index-1",
                    lane="ingestion",
                    account=provider.account,
                    models=(provider.model,),
                    input_tokens=estimate_tokens(json.dumps(texts)),
                    output_tokens=0,
                    timeout_seconds=bounds.timeout_seconds,
                ),
                binding,
            )
            usage = Usage()
            try:
                async with conn.transaction():
                    now = await source(conn, token)
                    if not same_source(now, job) or not await claimed(conn, binding):
                        return "stale"
                    checked_space = await space(conn, provider)
                    if checked_space["id"] != job["space_id"]:
                        return "stale"
                    # Canonical facts stay locked from final authorization through send/output commit.
                    usage.sent = True
                    response = await asyncio.wait_for(
                        provider.embed(texts, input_type="document"), ticket.timeout_seconds
                    )
                    vectors = checked_vectors(response.vectors, len(texts), provider.dimensions)
                    usage.input_tokens, usage.output_tokens, usage.model = (
                        response.input_tokens,
                        0,
                        provider.model,
                    )
                    if not await claimed(conn, binding):
                        return "stale"
                    await conn.execute(
                        "INSERT INTO iris_ai.embedding_batch(job_id,ordinal,vectors,reservation_id)"
                        " VALUES($1,$2,$3,$4)",
                        job["id"],
                        ordinal,
                        vectors,
                        ticket.pk,
                    )
            finally:
                await ticket.settle(usage)
        async with conn.transaction():
            now = await source(conn, token)
            if not same_source(now, job) or not await claimed(conn, binding):
                return "stale"
            checked_space = await space(conn, provider)
            if checked_space["id"] != job["space_id"]:
                return "stale"
            batches = await conn.fetch(
                "SELECT ordinal,vectors FROM iris_ai.embedding_batch WHERE job_id=$1 ORDER BY ordinal",
                job["id"],
            )
            if [b["ordinal"] for b in batches] != list(range(len(windows))):
                return "incomplete"
            for b, texts in zip(batches, windows):
                checked_vectors(b["vectors"], len(texts), provider.dimensions)
            await conn.execute(
                "UPDATE iris_ai.index_job SET state='complete' WHERE id=$1", job["id"]
            )
            await activate(conn, job)
        return "ready"
    except asyncpg.InsufficientPrivilegeError:
        return "stale"
    finally:
        await conn.close()


def same_source(current, job):
    return current is not None and all(
        current[k] == job[k] for k in ("work_id", "revision", "record_id", "generation")
    )


async def claimed(conn, binding):
    return await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM iris_ai.index_job WHERE id=$1 AND attempt=$2"
        " AND state='running' AND lease_until>clock_timestamp())",
        binding.run_id,
        binding.fence,
    )


async def activate(conn, job):
    await conn.execute(
        "INSERT INTO iris_ai.active_source(record_id,job_id) VALUES($1,$2)"
        " ON CONFLICT(record_id) DO UPDATE SET job_id=excluded.job_id",
        job["record_id"],
        job["id"],
    )
