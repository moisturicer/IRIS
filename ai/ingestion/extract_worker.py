"""Explicit, isolated local extraction worker; no live writer switch (IR-738)."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

import asyncpg

from apps.ai.chunking import ChunkingOptions
from apps.ai.chunking.tokens import TOKENIZER_SHA256
from apps.ai.extraction import DoclingExtractor

from .extraction import process


class LocalSource:
    """Read only the storage key supplied by verified processing authority."""

    def __init__(self, root, max_bytes):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or max_bytes < 1:
            raise ValueError('a media directory and positive byte limit are required')
        self.max_bytes = max_bytes

    def __call__(self, key):
        path = (self.root / key).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError('source is outside local storage')
        with path.open('rb') as source:
            content = source.read(self.max_bytes + 1)
        if len(content) > self.max_bytes:
            raise ValueError('source exceeds the configured extraction limit')
        return content


async def sweep(dsn, *, limit, after=None, **processing):
    conn = await asyncpg.connect(dsn)
    try:
        work = await conn.fetch('SELECT * FROM iris_authz.pending_manuscript_work($1,$2)', limit, after)
    finally:
        await conn.close()
    outcomes = []
    for row in work:
        outcomes.append(await process(dsn, row['grant_token'], **processing))
    return (work[-1]['work_id'] if len(work) == limit else None), outcomes


async def serve(dsn, *, limit, poll_seconds, once, **processing):
    after = None
    while True:
        after, outcomes = await sweep(dsn, limit=limit, after=after, **processing)
        # Counts only; never log source keys, grants, extracted text or private errors.
        print(json.dumps({state: outcomes.count(state) for state in sorted(set(outcomes))}), flush=True)
        if once:
            return
        if after is None:
            await asyncio.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--poll-seconds', type=float, required=True)
    parser.add_argument('--lease-seconds', type=int, required=True)
    parser.add_argument('--max-source-bytes', type=int, required=True)
    parser.add_argument('--media-root', required=True)
    parser.add_argument('--docling-url', required=True)
    parser.add_argument('--docling-timeout', type=float, required=True)
    parser.add_argument('--profile', required=True,
                        help='JSON with extractor_revision, extraction options and chunk options')
    args = parser.parse_args()
    dsn = os.environ.get('RUNS_DATABASE_URL', '')
    if (not dsn or not 1 <= args.limit <= 1000 or not 0 < args.poll_seconds <= 60
            or not 0 < args.docling_timeout < args.lease_seconds <= 86400):
        parser.error('database URL and valid bounds (timeout < lease <=86400) are required')
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    if not str(profile.get('extractor_revision', '')).strip():
        parser.error('profile must pin the deployed Docling revision')
    extraction_options = profile['extraction']
    flags = {'do_ocr', 'do_formula_enrichment', 'do_code_enrichment', 'do_picture_classification'}
    if set(extraction_options) != flags or any(type(v) is not bool for v in extraction_options.values()):
        parser.error('profile must explicitly set the four Docling boolean options')
    chunk_options = profile['chunks']
    required = {'strategy', 'max_tokens', 'min_tokens', 'context_path_max_tokens', 'exclude_sections'}
    if not required <= chunk_options.keys():
        parser.error('profile must explicitly set existing deployment chunking options')
    chunk_options['exclude_sections'] = tuple(chunk_options['exclude_sections'])
    options = ChunkingOptions(**chunk_options)
    extraction_options = {**extraction_options, 'require_complete': True}
    pin = {'format': 'pending-extraction-1', 'extractor': profile['extractor_revision'],
           'options': extraction_options, 'chunks': asdict(options), 'tokenizer': TOKENIZER_SHA256}
    pipeline = hashlib.sha256(json.dumps(pin, sort_keys=True).encode()).hexdigest()
    asyncio.run(serve(dsn, limit=args.limit, poll_seconds=args.poll_seconds, once=args.once,
        load=LocalSource(args.media_root, args.max_source_bytes),
        extractor=DoclingExtractor(args.docling_url, timeout=args.docling_timeout, **extraction_options),
        options=options, pipeline=pipeline, profile=pin, lease_seconds=args.lease_seconds))


if __name__ == '__main__':
    main()
