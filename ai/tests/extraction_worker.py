"""Independent deterministic extraction process for restricted-role tests."""
import asyncio
import base64
import json
import os
import sys

from apps.ai.chunking import ChunkingOptions
from apps.ai.extraction import ExtractedDocument, Provenance, document_from_json
from ai.ingestion.extraction import process


class Extractor:
    def extract(self, *args, **kwargs):
        print('extracting', flush=True)
        if '--pause' in sys.argv:
            sys.stdin.readline()
        return ExtractedDocument(document_from_json(json.loads(os.environ['SYNTHETIC_DOCUMENT'])),
                                 Provenance('deterministic'))


if __name__ == '__main__':
    result = asyncio.run(process(os.environ['RUNS_DATABASE_URL'], os.environ['SYNTHETIC_GRANT'],
        load=lambda key: base64.b64decode(os.environ['SYNTHETIC_PDF']), extractor=Extractor(),
        options=ChunkingOptions(), pipeline='synthetic-v1',
        lease_seconds=int(os.environ.get('SYNTHETIC_LEASE', '60'))))
    print(result, flush=True)
