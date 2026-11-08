"""Approved HTTP/task seams: accepted bytes, safe status and independent PG workers."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.urls import reverse
from django.db import connections
from rest_framework.test import APIClient

from apps.ai.extraction import ExtractorUnavailable, InMemoryExtractor, use_extractor
from apps.documents.models import PdfExtraction
from apps.documents.testing import pdf_upload
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def manuscript(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.ai.models import EmbeddingSpace
    EmbeddingSpace.objects.get_or_create(state="active", defaults={"model_id": "voyage-context-4", "dimensions": 1024})
    owner = make_user("source-owner@cit.edu", "Student")
    record = Record.objects.create(
        title="A research paper", added_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    client = APIClient()
    client.force_authenticate(owner)
    return client, record


def attach(client, record, content=b"A", name="paper.pdf"):
    return client.patch(reverse("record-detail", args=[record.pk]),
                        {"abstract_file": pdf_upload(name, content)}, format="multipart")


def status(client, record):
    return client.get(reverse("record-metadata-suggestions", args=[record.pk])).json()


def test_source_identity_is_persistent_and_unchanged_bytes_are_idempotent(manuscript, monkeypatch):
    from apps.documents.tasks import extract_manuscript_text

    client, record = manuscript
    queued = []
    monkeypatch.setattr(extract_manuscript_text, "delay", lambda *args: queued.append(args))
    assert attach(client, record).status_code == 200
    first = status(client, record)
    assert first["manuscript_revision"]
    record.refresh_from_db()
    original_path = record.abstract_file.name
    assert record.manuscript_sha256 == hashlib.sha256(pdf_upload(content=b"A").read()).hexdigest()
    assert queued == [(record.pk, first["manuscript_revision"])]
    assert attach(client, record, name="renamed.pdf").status_code == 200
    record.refresh_from_db()
    assert record.abstract_file.name == original_path
    assert status(client, record)["manuscript_revision"] == first["manuscript_revision"]
    assert len(queued) == 1
    rejected = client.patch(reverse("record-detail", args=[record.pk]),
                            {"abstract_file": pdf_upload(content=b"B")}, format="multipart")
    assert rejected.status_code == 200
    assert status(client, record)["manuscript_revision"] != first["manuscript_revision"]
    extraction = PdfExtraction.objects.get(record=record)
    assert not extraction.structure and not extraction.content_hash


@pytest.mark.parametrize("old_outcome", ["success", "retry", "failure"])
def test_replaced_source_cannot_finish_fail_retry_or_chunk_last(manuscript, monkeypatch, old_outcome):
    from apps.ai.chunking.document import DocumentElement, NormalizedDocument, PARAGRAPH
    from apps.ai.models import ChunkSet
    from apps.ai.tasks import chunk_extraction, embed_chunk_set
    from apps.documents import tasks

    client, record = manuscript
    queued = []
    handoffs = []
    embedded = []
    started, release = Event(), Event()
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: queued.append(args))
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: handoffs.append(args))
    monkeypatch.setattr(embed_chunk_set, "delay", lambda *args, **kwargs: embedded.append((args, kwargs)))

    def respond(content, filename):
        old = content.endswith(b"%A\n")
        if old:
            started.set()
            assert release.wait(20)
            if old_outcome == "retry":
                return ExtractorUnavailable("private parser path /secret/old.pdf")
            if old_outcome == "failure":
                return RuntimeError("private parser path /secret/old.pdf")
        title = "Old manuscript" if old else "Current manuscript"
        return NormalizedDocument(title=title, elements=(
            DocumentElement(kind=PARAGRAPH, text="A complete research passage about current findings.", page=1),
        ))

    with use_extractor(InMemoryExtractor(respond)):
        assert attach(client, record).status_code == 200
        first = queued[-1]

        def worker():
            connections.close_all()
            try:
                return tasks.extract_manuscript_text.apply(args=first, retries=3 if old_outcome == "failure" else 0)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as workers:
            old = workers.submit(worker)
            try:
                assert started.wait(20)
                assert attach(client, record, b"B").status_code == 200
                current = queued[-1]
                assert status(client, record)["suggestions"]["title"] is None
                assert tasks.extract_manuscript_text.apply(args=current).successful()
            finally:
                release.set()
            assert old.result(timeout=20).successful()

        assert status(client, record)["state"] == "ready"
        assert status(client, record)["suggestions"]["title"] == "Current manuscript"
        assert client.post(reverse("record-retry-extraction", args=[record.pk]),
                           {"manuscript_revision": first[1]}).status_code == 409
        extraction = PdfExtraction.objects.get(record=record)
        assert handoffs == [(extraction.pk, current[1])]
        assert chunk_extraction.apply(args=[extraction.pk, first[1]]).result is None
        result = chunk_extraction.apply(args=[extraction.pk, current[1]])
        assert result.successful(), result.result
        active = ChunkSet.objects.get(record=record, is_active=True)
        assert str(active.source_revision) == current[1]
        assert embedded == [((record.pk,), {"chunk_set_id": active.pk, "source_revision": current[1]})]
        assert tasks.extract_manuscript_text.apply(args=current).successful()
        assert len(handoffs) == 1


def test_failed_replacement_preserves_accepted_source_and_no_job_is_queued(manuscript, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.documents.tasks import extract_manuscript_text

    client, record = manuscript
    queued = []
    monkeypatch.setattr(extract_manuscript_text, "delay", lambda *args: queued.append(args))
    assert attach(client, record).status_code == 200
    first = status(client, record)
    record.refresh_from_db()
    path = record.abstract_file.name
    response = client.patch(reverse("record-detail", args=[record.pk]), {
        "abstract_file": SimpleUploadedFile("bad.pdf", b"%PDF-broken", content_type="application/pdf"),
    }, format="multipart")
    assert response.status_code == 400 and "abstract_file" in response.json()
    record.refresh_from_db()
    assert record.abstract_file.name == path
    assert status(client, record) == first
    assert len(queued) == 1


def test_retrying_is_pending_and_final_failure_requires_owner_action(manuscript, monkeypatch):
    from apps.documents import tasks

    client, record = manuscript
    queued = []
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: queued.append(args))
    assert attach(client, record).status_code == 200

    with use_extractor(InMemoryExtractor(ExtractorUnavailable("private parser path /secret.pdf"))):
        from celery.exceptions import Retry
        monkeypatch.setattr(tasks.extract_manuscript_text, "retry", lambda **kwargs: (_ for _ in ()).throw(Retry()))
        tasks.extract_manuscript_text.apply(args=queued[-1])
        payload = status(client, record)
        assert payload["state"] == "pending" and payload["phase"] == "retrying"
        assert payload["retryable"] is False
        tasks.extract_manuscript_text.apply(args=queued[-1], retries=3)
        payload = status(client, record)
        assert payload["state"] == "failed" and payload["retryable"] is True
        assert "secret" not in str(payload)
        assert tasks.extract_manuscript_text.apply(args=queued[-1]).successful()
        assert status(client, record)["state"] == "failed"
        stranger = APIClient()
        stranger.force_authenticate(make_user("other@cit.edu", "Student"))
        url = reverse("record-retry-extraction", args=[record.pk])
        assert stranger.post(url, {"manuscript_revision": payload["manuscript_revision"]}).status_code == 404
        assert client.post(url, {"manuscript_revision": "old"}).status_code == 409
        assert client.post(url, {"manuscript_revision": payload["manuscript_revision"]}).status_code == 202
        assert len(queued) == 2


def test_removed_source_and_old_unpinned_messages_cannot_extract(manuscript, monkeypatch):
    from apps.documents import tasks

    client, record = manuscript
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: None)
    assert attach(client, record).status_code == 200
    revision = status(client, record)["manuscript_revision"]
    assert tasks.extract_manuscript_text.apply(args=[record.pk]).successful()
    assert status(client, record)["phase"] == "queued"
    assert client.patch(reverse("record-detail", args=[record.pk]), {"abstract_file": None}, format="json").status_code == 200
    assert tasks.extract_manuscript_text.apply(args=[record.pk, revision]).successful()
    assert status(client, record)["state"] == "unsupported"
    assert not PdfExtraction.objects.filter(record=record).exists()


@pytest.mark.parametrize("route", ["manuscript", "submit", "legacy", "general"])
@pytest.mark.parametrize("kind", ["malformed", "encrypted", "active", "limited", "valid"])
def test_all_pdf_routes_share_acceptance_and_refusals_store_nothing(manuscript, settings, route, kind):
    from io import BytesIO
    from django.core.files.uploadedfile import SimpleUploadedFile
    from pypdf import PdfWriter
    from apps.documents.models import RecordFile, RecordUpload, UploadSlot
    from apps.reviews.models import RecordAssignment

    client, record = manuscript
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if kind == "encrypted":
        writer.encrypt("")
    if kind == "active":
        writer.add_js("app.alert('test')")
    if kind == "limited":
        writer.add_blank_page(width=200, height=200)
        settings.PDF_VALIDATION_MAX_PAGES = 1
    buffer = BytesIO()
    writer.write(buffer)
    file = SimpleUploadedFile("source.pdf", b"%PDF-invalid" if kind == "malformed" else buffer.getvalue(),
                              content_type="application/pdf")
    slot = UploadSlot.objects.create(name="Supporting paper", record_type=record.record_type)
    body = {"record": record.pk, "slot": slot.pk, "file": file}
    if route == "general":
        office = make_user("office@cit.edu", "RDCO")
        RecordAssignment.objects.create(record=record, party="rdco")
        client.force_authenticate(office)
    if route == "manuscript":
        response = client.patch(reverse("record-detail", args=[record.pk]), {"abstract_file": file}, format="multipart")
    else:
        name = {"submit": "document-submit", "legacy": "record-upload-create-legacy", "general": "record-file-upload"}[route]
        response = client.post(reverse(name), body, format="multipart")
    if kind == "valid":
        assert response.status_code in {200, 201}, response.data
        return
    assert response.status_code == 400, response.data
    assert ("abstract_file" if route == "manuscript" else "file") in response.json()
    record.refresh_from_db()
    assert not record.abstract_file
    assert not RecordUpload.objects.filter(record=record).exists()
    assert not RecordFile.objects.filter(record=record).exists()
    assert not PdfExtraction.objects.filter(record=record).exists()


@pytest.mark.parametrize("route", ["manuscript", "submit", "legacy", "general"])
def test_unauthorized_uploader_is_refused_before_parsing(manuscript, monkeypatch, route):
    from apps.documents.models import UploadSlot
    from apps.documents import views
    from apps.records import serializers

    client, record = manuscript
    client.force_authenticate(make_user("unauthorized@cit.edu", "Student"))
    def unexpected(file):
        pytest.fail("An unauthorized request reached the PDF parser")
    monkeypatch.setattr(views, "pdf_upload_problem", unexpected)
    monkeypatch.setattr(serializers, "pdf_upload_problem", unexpected)
    slot = UploadSlot.objects.create(name="Supporting paper", record_type=record.record_type)
    if route == "manuscript":
        response = attach(client, record)
    else:
        name = {"submit": "document-submit", "legacy": "record-upload-create-legacy", "general": "record-file-upload"}[route]
        response = client.post(reverse(name), {"record": record.pk, "slot": slot.pk, "file": pdf_upload()}, format="multipart")
    assert response.status_code in {403, 404}


def test_general_attachment_non_pdf_policy_is_unchanged(manuscript):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.reviews.models import RecordAssignment

    client, record = manuscript
    client.force_authenticate(make_user("office@cit.edu", "RDCO"))
    RecordAssignment.objects.create(record=record, party="rdco")
    response = client.post(reverse("record-file-upload"), {
        "record": record.pk, "file": SimpleUploadedFile("notes.txt", b"Office notes", content_type="text/plain"),
    }, format="multipart")
    assert response.status_code == 201, response.data


def test_different_original_bytes_with_identical_text_get_current_source_chunks(manuscript, monkeypatch):
    from apps.ai.chunking.document import DocumentElement, NormalizedDocument, PARAGRAPH
    from apps.ai.models import ChunkSet
    from apps.ai.tasks import chunk_extraction, embed_chunk_set
    from apps.documents import tasks

    client, record = manuscript
    same_text = NormalizedDocument(title="Same extracted paper", elements=(
        DocumentElement(kind=PARAGRAPH, text="The extracted text is unchanged despite new original bytes.", page=1),
    ))
    with use_extractor(InMemoryExtractor(same_text)):
        monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: None)
        monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: None)
        monkeypatch.setattr(embed_chunk_set, "delay", lambda *args, **kwargs: None)
        first = None
        for content in (b"A", b"B"):
            assert attach(client, record, content).status_code == 200
            revision = status(client, record)["manuscript_revision"]
            assert tasks.extract_manuscript_text.apply(args=[record.pk, revision]).successful()
            extraction = PdfExtraction.objects.get(record=record)
            result = chunk_extraction.apply(args=[extraction.pk, revision])
            assert result.successful(), result.result
            current = ChunkSet.objects.get(record=record, is_active=True)
            assert str(current.source_revision) == revision
            if first:
                assert current.pk != first.pk
                assert current.extraction_hash == first.extraction_hash
            first = current


def test_replacement_during_embedding_cannot_persist_old_vectors(manuscript, monkeypatch):
    from django.utils import timezone
    from apps.ai.chunking.document import DocumentElement, NormalizedDocument, PARAGRAPH
    from apps.ai.indexing import embed_active_chunk_set
    from apps.ai.models import ChunkSet
    from apps.ai.models.chunk import ChunkEmbedding
    from apps.ai.providers.fakes import DeterministicEmbeddingProvider
    from apps.ai.tasks import chunk_extraction, embed_chunk_set
    from apps.documents import tasks

    client, record = manuscript
    record.is_embargoed = False
    record.embargo_released_at = timezone.now()
    record.ai_consent = True
    record.save(update_fields=["is_embargoed", "embargo_released_at", "ai_consent"])
    paper = NormalizedDocument(title="Research paper", elements=(
        DocumentElement(kind=PARAGRAPH, text="The paper contains a passage for deterministic local embedding.", page=1),
    ))
    with use_extractor(InMemoryExtractor(paper)):
        monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: None)
        monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: None)
        monkeypatch.setattr(embed_chunk_set, "delay", lambda *args, **kwargs: None)
        assert attach(client, record).status_code == 200
        revision = status(client, record)["manuscript_revision"]
        assert tasks.extract_manuscript_text.apply(args=[record.pk, revision]).successful()
        extraction = PdfExtraction.objects.get(record=record)
        assert chunk_extraction.apply(args=[extraction.pk, revision]).successful()
        chunks = ChunkSet.objects.get(record=record, is_active=True)
        class ReplacingEmbedder(DeterministicEmbeddingProvider):
            def embed_document_chunks(self, documents):
                assert attach(client, record, b"B").status_code == 200
                return super().embed_document_chunks(documents)
        result = embed_active_chunk_set(record.pk, provider=ReplacingEmbedder(),
                                        chunk_set_id=chunks.pk, source_revision=revision)
        assert result.refused
        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()
        assert status(client, record)["manuscript_revision"] != revision
