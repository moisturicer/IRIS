"""Pending extraction through a restricted AI worker and owner HTTP status."""
import asyncio
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.publication import authority
from apps.publication.models import ManuscriptWork
from apps.records.models import Record, RecordOwner
from .corpus import make_user
from .grant_support import probe_credentials

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def dsn(user, password):
    cfg = connection.settings_dict
    return (f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
            f"{cfg['HOST'] or 'localhost'}:{cfg['PORT'] or '5432'}/{cfg['NAME']}")


@pytest.fixture
def runtime(grant_db):
    from ai.runs.migrate import migrate
    cfg = connection.settings_dict
    asyncio.run(migrate(dsn(cfg['USER'], cfg['PASSWORD'])))
    with probe_credentials() as (user, password):
        yield dsn(user, password)
    with connection.cursor() as cursor:
        cursor.execute('TRUNCATE iris_ai.extraction_revision, iris_ai.extraction_job')


def document():
    from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
    from apps.ai.extraction import ExtractedDocument, Provenance
    return ExtractedDocument(NormalizedDocument('Synthetic research', (
        DocumentElement('paragraph', 'Twelve ponds were sampled weekly.', page=1,
                        bboxes=(BoundingBox(1, 10, 10, 200, 30),)),
        DocumentElement('paragraph', 'All twelve ponds improved.', page=2),
    ), {1: (612, 792), 2: (612, 792)}), Provenance('deterministic'))


class Extractor:
    def extract(self, content, *, filename):
        assert content == b'synthetic PDF bytes'
        return document()


def run(runtime, token, extractor=None, *, pipeline='synthetic-v1', lease=60):
    from ai.ingestion.extraction import process
    from apps.ai.chunking import ChunkingOptions
    return asyncio.run(process(runtime, token, load=lambda path: b'synthetic PDF bytes',
        extractor=extractor or Extractor(), options=ChunkingOptions(),
        pipeline=pipeline, lease_seconds=lease))


def source():
    owner = make_user('pending-runtime-owner@cit.edu')
    record = Record.objects.create(title='Synthetic', abstract_file='manuscripts/synthetic.pdf')
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    return owner, record, authority.issue_grant(work.pk).token


def status(owner, record):
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(f'/api/v1/records/{record.pk}/metadata-suggestions/')
    assert response.status_code == 200
    return response.data['runtime_processing']


def test_pending_output_is_page_bound_immutable_and_reused(runtime):
    import json
    owner, record, token = source()
    assert status(owner, record)['state'] == 'pending_processing'
    assert run(runtime, token) == 'extracted'
    assert status(owner, record)['state'] == 'extracted_pending'

    class MustNotExtract:
        def extract(self, *args, **kwargs):
            pytest.fail('completed extraction was repeated')

    assert run(runtime, token, MustNotExtract()) == 'duplicate'
    with connection.cursor() as cursor:
        cursor.execute('SELECT payload FROM iris_ai.extraction_revision')
        payload = cursor.fetchone()[0]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        assert payload['document']['elements'][0]['page'] == 1
        assert payload['document']['elements'][0]['bbox']['rect'] == [10, 10, 200, 30]
        assert {c['source_page'] for c in payload['chunks']} <= {1, 2}
        assert payload['source_sha256']
        assert payload['extraction_hash']
        cursor.execute('SELECT count(*) FROM ai_chunkset WHERE record_id = %s', [record.pk])
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['error', 'incomplete'])
def test_failure_and_incomplete_coverage_are_safe_processing_states(runtime, failure):
    from dataclasses import replace
    from apps.ai.extraction import ExtractionError
    owner, record, token = source()

    class Broken:
        def extract(self, *args, **kwargs):
            if failure == 'error':
                raise ExtractionError('private storage path and content')
            result = document()
            return replace(result, document=replace(result.document, elements=result.document.elements[:1]))

    expected = 'failed' if failure == 'error' else 'incomplete'
    assert run(runtime, token, Broken()) == expected
    projection = status(owner, record)
    assert projection['state'] == expected
    assert set(projection) == {'state', 'revision'}
    other = make_user('unrelated-runtime-reader@cit.edu')
    client = APIClient()
    client.force_authenticate(other)
    assert client.get(f'/api/v1/records/{record.pk}/metadata-suggestions/').status_code == 404


@pytest.mark.parametrize('change', ['replace', 'delete', 'revoke'])
def test_source_changes_during_extraction_fence_write(runtime, change):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    owner, record, token = source()
    entered, release = threading.Event(), threading.Event()

    class Paused:
        def extract(self, *args, **kwargs):
            entered.set()
            assert release.wait(20)
            return document()

    with ThreadPoolExecutor() as pool:
        older = pool.submit(run, runtime, token, Paused())
        assert entered.wait(20)
        try:
            if change == 'replace':
                record.abstract_file = 'manuscripts/newer.pdf'
                record.save()
                work = ManuscriptWork.objects.get(record=record, revoked_at=None)
                assert run(runtime, authority.issue_grant(work.pk).token) == 'extracted'
            elif change == 'delete':
                record.delete()
            else:
                RecordOwner.objects.filter(record=record).delete()
        finally:
            release.set()
        assert older.result(timeout=20) == 'stale'
    with connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM iris_ai.extraction_revision')
        assert cursor.fetchone()[0] == (1 if change == 'replace' else 0)
    if change == 'replace':
        assert status(owner, record)['state'] == 'extracted_pending'


def start_worker(runtime, token, *, lease=60):
    import json
    import os
    import subprocess
    from apps.ai.extraction import document_to_json
    return subprocess.Popen([sys.executable, '-m', 'ai.tests.extraction_worker', '--pause'],
        env={**os.environ, 'RUNS_DATABASE_URL': runtime, 'SYNTHETIC_GRANT': token,
             'SYNTHETIC_DOCUMENT': json.dumps(document_to_json(document().document)),
             'SYNTHETIC_LEASE': str(lease)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_independent_workers_claim_once_and_recover_expired_attempt(runtime):
    import time
    owner, record, token = source()
    worker = start_worker(runtime, token, lease=1)
    try:
        assert worker.stdout.readline().strip() == 'extracting'
        assert status(owner, record)['state'] == 'processing'
        assert run(runtime, token) == 'busy'
        time.sleep(1.1)
        assert status(owner, record)['state'] == 'pending_processing'
        assert run(runtime, token) == 'extracted'
        out, error = worker.communicate('\n', timeout=20)
        assert worker.returncode == 0, error
        assert out.strip() == 'stale'
        assert status(owner, record)['state'] == 'extracted_pending'
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.communicate(timeout=10)


def test_pending_rows_are_scoped_and_output_has_no_mutation_grant(runtime):
    import asyncpg
    owner, record, token = source()
    assert run(runtime, token) == 'extracted'

    async def inspect():
        conn = await asyncpg.connect(runtime)
        try:
            assert await conn.fetchval('SELECT count(*) FROM iris_ai.extraction_revision') == 0
            async with conn.transaction():
                await conn.fetchval("SELECT iris_authz.begin_research($1,'ingestion')", token)
                assert await conn.fetchval('SELECT count(*) FROM iris_ai.extraction_revision') == 1
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with conn.transaction():
                        await conn.execute("UPDATE iris_ai.extraction_revision SET payload='{}'")
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with conn.transaction():
                        await conn.execute('DELETE FROM iris_ai.extraction_revision')
        finally:
            await conn.close()
    asyncio.run(inspect())


def test_new_profile_status_is_not_hidden_by_an_older_long_lease(runtime):
    from apps.ai.extraction import ExtractionError
    owner, record, token = source()

    class Broken:
        def extract(self, *args, **kwargs):
            raise ExtractionError('deterministic failure')

    assert run(runtime, token, Broken(), pipeline='older', lease=120) == 'failed'
    assert run(runtime, token, pipeline='corrected', lease=30) == 'extracted'
    assert status(owner, record)['state'] == 'extracted_pending'


def test_local_storage_refuses_escape_and_byte_limit(tmp_path):
    from ai.ingestion.extract_worker import LocalSource
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'inside.pdf').write_bytes(b'12345')
    (tmp_path / 'outside.pdf').write_bytes(b'private')
    load = LocalSource(media, 4)
    with pytest.raises(ValueError):
        load('../outside.pdf')
    with pytest.raises(ValueError):
        load('inside.pdf')


def test_final_write_lock_serializes_canonical_revocation(runtime):
    import asyncpg
    import psycopg2
    owner, record, token = source()
    cfg = connection.settings_dict

    def revoke():
        conn = psycopg2.connect(host=cfg['HOST'], port=cfg['PORT'], dbname=cfg['NAME'],
                                user=cfg['USER'], password=cfg['PASSWORD'])
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET lock_timeout = '100ms'")
                with pytest.raises(psycopg2.errors.LockNotAvailable):
                    cursor.execute('UPDATE records_record SET is_deleted=true WHERE id=%s', [record.pk])
        finally:
            conn.rollback()
            conn.close()

    async def hold_source():
        conn = await asyncpg.connect(runtime)
        try:
            async with conn.transaction():
                await conn.fetchval("SELECT iris_authz.begin_research($1,'ingestion')", token)
                assert await conn.fetchrow('SELECT * FROM iris_authz.lock_processing_source()')
                await asyncio.to_thread(revoke)
        finally:
            await conn.close()
    asyncio.run(hold_source())


def test_local_docling_extracts_synthetic_pdf_into_pending_output(runtime):
    import io
    import os
    from reportlab.pdfgen.canvas import Canvas
    from ai.ingestion.extraction import process
    from apps.ai.chunking import ChunkingOptions
    from apps.ai.extraction import DoclingExtractor

    endpoint = os.environ.get('IRIS_TEST_LOCAL_DOCLING')
    if not endpoint:
        pytest.skip('set IRIS_TEST_LOCAL_DOCLING to the on-prem test extractor')
    buffer = io.BytesIO()
    pdf = Canvas(buffer)
    pdf.drawString(72, 720, 'Synthetic pond study: twelve ponds were sampled weekly.')
    pdf.showPage()
    pdf.drawString(72, 720, 'Synthetic result: all twelve ponds improved.')
    pdf.save()
    owner, record, token = source()
    result = asyncio.run(process(runtime, token, load=lambda key: buffer.getvalue(),
        extractor=DoclingExtractor(endpoint, timeout=120, require_complete=True,
            do_ocr=False, do_formula_enrichment=False, do_code_enrichment=False,
            do_picture_classification=False),
        options=ChunkingOptions(), pipeline='synthetic-live-docling-1.36.0', lease_seconds=180))
    assert result == 'extracted'
    assert status(owner, record)['state'] == 'extracted_pending'


def test_reported_failed_page_prevents_complete_pending_output(runtime):
    from dataclasses import replace
    owner, record, token = source()

    class Partial:
        def extract(self, *args, **kwargs):
            return replace(document(), failed_pages=(2,))

    assert run(runtime, token, Partial()) == 'incomplete'
    assert status(owner, record)['state'] == 'incomplete'
