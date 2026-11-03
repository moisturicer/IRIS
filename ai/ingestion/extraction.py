"""Local extraction into immutable pending revisions (IR-738)."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import uuid
from dataclasses import asdict

import asyncpg
from pypdf import PdfReader

from apps.ai.chunking import build_context_path_chunker, normalize
from apps.ai.extraction import document_to_json, extraction_hash
from apps.ai.extraction.ports import IncompleteExtraction


class IncompleteCoverage(Exception):
    pass


async def _source(conn, token):
    await conn.fetchval("SELECT iris_authz.begin_research($1, 'ingestion')", token)
    return await conn.fetchrow(
        "SELECT s.*, (iris_authz.current_research_claims()->>'wgen')::bigint AS generation"
        " FROM iris_authz.lock_processing_source() s")


def build_output(source, load, extractor, options):
    content = load(source['source_file'])
    pages = set(range(1, len(PdfReader(io.BytesIO(content)).pages) + 1))
    extracted = extractor.extract(content, filename=source['source_file'].rsplit('/', 1)[-1])
    document = extracted.document
    if extracted.failed_pages:
        raise IncompleteCoverage()
    covered = {e.page for e in document.elements if e.text.strip()}
    if (not pages or set(document.page_sizes) != pages or not pages <= covered
            or any(e.page not in pages for e in document.elements)):
        raise IncompleteCoverage()
    chunks = build_context_path_chunker(options).chunk(normalize(document, options), options)
    if not chunks.chunks or any(c.source_page not in pages for c in chunks.chunks):
        raise IncompleteCoverage()
    return {
        'version': 1, 'source_sha256': hashlib.sha256(content).hexdigest(),
        'provenance': asdict(extracted.provenance), 'extraction_hash': extraction_hash(document),
        'document': document_to_json(document), 'chunk_hash': chunks.content_hash,
        'strategy': chunks.strategy_id, 'options': asdict(options),
        'chunks': [{**asdict(c), 'element_kinds': sorted(c.element_kinds)} for c in chunks.chunks],
    }


async def process(dsn, token, *, load, extractor, options, pipeline, lease_seconds, profile=None):
    """Claim, compute outside the transaction, then fence and commit pending output.

    The pipeline identity pins extractor configuration, format and chunk options.
    A lease permits crash recovery; the attempt fences a late worker after takeover.
    No output is ever written into the live Django extraction/chunk tables.
    """
    if not pipeline or not 1 <= lease_seconds <= 86400:
        raise ValueError('a pipeline identity and lease of 1..86400 seconds are required')
    if profile is not None and hashlib.sha256(
            json.dumps(profile, sort_keys=True).encode()).hexdigest() != pipeline:
        raise ValueError('pipeline identity does not match its profile')
    conn = await asyncpg.connect(dsn)
    attempt = uuid.uuid4()
    try:
        async with conn.transaction():
            source = await _source(conn, token)
            if source is None:
                return 'stale'
            work = source['work_id']
            # Canonical lock gives every claimant the same record -> job lock order.
            job = await conn.fetchrow(
                'SELECT * FROM iris_ai.extraction_job WHERE work_id=$1 AND pipeline=$2 FOR UPDATE',
                work, pipeline)
            if job and job['state'] == 'extracted':
                await conn.execute('UPDATE iris_ai.extraction_job SET generation=$3'
                    ' WHERE work_id=$1 AND pipeline=$2', work, pipeline, source['generation'])
                return 'duplicate'
            if job and job['generation'] == source['generation']:
                if job['state'] != 'running':
                    return job['state']
                if await conn.fetchval('SELECT $1::timestamptz > clock_timestamp()', job['lease_until']):
                    return 'busy'
            await conn.execute(
                "INSERT INTO iris_ai.extraction_job(work_id,pipeline,generation,attempt,state,lease_until)"
                " VALUES($1,$2,$3,$4,'running',clock_timestamp()+$5*interval '1 second')"
                " ON CONFLICT(work_id,pipeline) DO UPDATE SET generation=excluded.generation,"
                " attempt=excluded.attempt,state=excluded.state,lease_until=excluded.lease_until,"
                " started_at=clock_timestamp()",
                work, pipeline, source['generation'], attempt, lease_seconds)

        state, output = 'extracted', None
        try:
            output = await asyncio.to_thread(build_output, source, load, extractor, options)
        except (IncompleteCoverage, IncompleteExtraction):
            state = 'incomplete'
        except Exception:
            # Exception text can contain manuscript content, storage keys or service bodies.
            state = 'failed'

        async with conn.transaction():
            current = await _source(conn, token)
            if current is None or current['work_id'] != work:
                return 'stale'
            claimed = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM iris_ai.extraction_job WHERE work_id=$1'
                " AND pipeline=$2 AND attempt=$3 AND state='running'"
                ' AND lease_until > clock_timestamp())', work, pipeline, attempt)
            if not claimed:
                return 'stale'
            if output is not None:
                output['profile'] = profile
                await conn.execute(
                    'INSERT INTO iris_ai.extraction_revision(work_id,pipeline,revision,record_id,payload)'
                    ' VALUES($1,$2,$3,$4,$5::jsonb)', work, pipeline,
                    source['revision'], source['record_id'], json.dumps(output))
            await conn.execute('UPDATE iris_ai.extraction_job SET state=$3'
                ' WHERE work_id=$1 AND pipeline=$2 AND attempt=$4', work, pipeline, state, attempt)
        return state
    except asyncpg.InsufficientPrivilegeError:
        return 'stale'
    finally:
        await conn.close()
