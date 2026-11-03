"""Publish upload and submission outcomes for readable Manuscript matches."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connections
from django.urls import reverse
from django.core.management import call_command
from django.db.models.fields.files import FieldFile
from io import StringIO
import uuid
from rest_framework.test import APIClient

from apps.documents.testing import pdf_upload
from apps.records.models import Author, Record, RecordOwner, RecordType
from apps.records.tests import make_user


pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def author(tmp_path, settings, monkeypatch):
    from apps.documents.tasks import extract_manuscript_text

    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr(extract_manuscript_text, "delay", lambda *args: None)
    user = make_user("duplicates-author@cit.edu", "Student")
    client = APIClient()
    client.force_authenticate(user)
    kind = RecordType.objects.get_or_create(name="Thesis / Research")[0]
    return client, user, kind


def draft(user, kind, title):
    record = Record.objects.create(title=title, added_by=user, record_type=kind)
    RecordOwner.objects.create(record=record, user=user, is_primary=True)
    return record


def upload(client, record, name="manuscript.pdf", content=b"A"):
    return client.patch(reverse("record-detail", args=[record.pk]),
                        {"abstract_file": pdf_upload(name, content)}, format="multipart")


def test_renamed_exact_file_is_blocked_but_same_record_retry_is_idempotent(author):
    client, user, kind = author
    first = draft(user, kind, "Original work")
    second = draft(user, kind, "Another record")
    assert upload(client, first).status_code == 200
    first.refresh_from_db()
    revision = first.manuscript_revision
    assert upload(client, first, "renamed.pdf").status_code == 200
    first.refresh_from_db()
    assert first.manuscript_revision == revision

    refused = upload(client, second, "renamed-again.pdf")
    assert refused.status_code == 409
    assert refused.json()["code"] == "exact_duplicate"
    assert refused.json()["matches"][0]["action"] == "resume_draft"
    second.refresh_from_db()
    assert not second.abstract_file
    assert upload(client, second, content=b"B").status_code == 200


def test_hidden_file_never_changes_an_unrelated_authors_upload_outcome(author):
    client, user, kind = author
    hidden_owner = make_user("duplicates-hidden@cit.edu", "Student")
    hidden = draft(hidden_owner, kind, "Private paper")
    other_client = APIClient()
    other_client.force_authenticate(hidden_owner)
    assert upload(other_client, hidden).status_code == 200
    mine = draft(user, kind, "My paper")
    response = upload(client, mine)
    assert response.status_code == 200
    assert response.json()["id"] == mine.pk
    assert client.get(reverse("record-duplicate-matches", args=[mine.pk])).json()["exact"] == []
    RecordOwner.objects.create(record=hidden, user=user)
    retry = upload(client, mine, "same-bytes-new-name.pdf")
    assert retry.status_code == 409
    assert retry.json()["matches"][0]["id"] == hidden.pk


def test_likely_matches_require_current_acknowledgement(author):
    client, user, kind = author
    prior = draft(user, kind, "Water quality in Cebu 2025")
    current = draft(user, kind, "Water quality in Cebu 2025")
    Author.objects.create(record=prior, name="A. Researcher")
    Author.objects.create(record=current, name="Another Author")
    url = reverse("record-duplicate-matches", args=[current.pk])
    matches = client.get(url).json()["likely"]
    assert [(item["id"], item["reason"]) for item in matches] == [(prior.pk, "same_title")]
    submit_url = reverse("record-submit", args=[current.pk])
    refused = client.post(submit_url, {"dpa_accepted": True}, format="json")
    assert refused.status_code == 409
    assert refused.json()["code"] == "acknowledgement_required"
    acknowledge = reverse("record-acknowledge-duplicates", args=[current.pk])
    assert client.post(acknowledge, {"candidate_ids": [prior.pk]}, format="json").status_code == 200
    assert client.get(url).json()["acknowledged"] is True
    assert client.post(submit_url, {"dpa_accepted": True}, format="json").status_code == 400  # Adviser still required.
    assert client.patch(reverse("record-detail", args=[current.pk]), {"title": "Different work"}, format="json").status_code == 200
    assert client.get(url).json()["acknowledged"] is False


def test_competing_accessible_uploads_cannot_both_pass(author):
    _, user, kind = author
    first = draft(user, kind, "First")
    second = draft(user, kind, "Second")
    start = Barrier(2)

    def attempt(record):
        connections.close_all()
        client = APIClient()
        client.force_authenticate(user)
        start.wait(timeout=15)
        try:
            return upload(client, record).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, record) for record in (first, second)]
        assert sorted(future.result(timeout=30) for future in futures) == [200, 409]


def test_likely_policy_ranks_exact_before_supported_similar_titles(author):
    client, user, kind = author
    current = draft(user, kind, "Cebu water quality study 2025")
    Author.objects.create(record=current, name="María Santos")
    near = draft(user, kind, "Cebu water quality study")
    Author.objects.create(record=near, name="MARÍA SANTOS")
    exact = draft(user, kind, "CEBU: water quality study 2025!")
    unrelated_author = draft(user, kind, "Cebu water quality study")
    Author.objects.create(record=unrelated_author, name="Someone Else")
    matches = client.get(reverse("record-duplicate-matches", args=[current.pk])).json()["likely"]
    assert [(item["id"], item["reason"]) for item in matches] == [
        (exact.pk, "same_title"), (near.pk, "similar_title_and_author"),
    ]


def test_backfill_is_dry_first_and_skips_a_replaced_source(author, monkeypatch):
    client, user, kind = author
    record = draft(user, kind, "Historical paper")
    assert upload(client, record).status_code == 200
    record.refresh_from_db()
    path = record.abstract_file.name
    Record.objects.filter(pk=record.pk).update(manuscript_sha256="")
    report = StringIO()
    call_command("backfill_manuscript_fingerprints", limit=1, stdout=report)
    assert "mode=dry_run" in report.getvalue()
    record.refresh_from_db()
    assert record.manuscript_sha256 == ""

    original_open = FieldFile.open
    changed = False

    def replaced_during_open(field, *args, **kwargs):
        nonlocal changed
        if field.instance.pk == record.pk and not changed:
            changed = True
            Record.objects.filter(pk=record.pk).update(manuscript_revision=uuid.uuid4())
        return original_open(field, *args, **kwargs)

    monkeypatch.setattr(FieldFile, "open", replaced_during_open)
    report = StringIO()
    call_command("backfill_manuscript_fingerprints", apply=True, limit=1, stdout=report)
    assert "replaced=1" in report.getvalue()
    record.refresh_from_db()
    assert record.manuscript_sha256 == ""
    assert record.abstract_file.name == path

    call_command("backfill_manuscript_fingerprints", apply=True, limit=1, stdout=StringIO())
    record.refresh_from_db()
    assert len(record.manuscript_sha256) == 64
