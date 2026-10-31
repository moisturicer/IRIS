import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.records.models import Author, Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def run_correction(tmp_path, actor, rows, **options):
    manifest = tmp_path / "metadata.json"
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    call_command("correct_research_metadata", str(manifest), actor=actor.email,
                 reason="Verified against publisher metadata", stdout=StringIO(), **options)


def test_explicit_correction_is_atomic_and_audited_without_changing_workflow(tmp_path):
    admin = User.objects.create_superuser(email="metadata-admin@cit.edu", password="test")
    record = Record.objects.create(title="Published imported paper", pipeline_status="published", year_accomplished=2020)
    row = {"id": record.pk, "origin": "imported_reference", "publication_year": 2017,
           "authors": ["Ada Reyes"], "evidence": "https://arxiv.org/abs/1706.03762"}
    run_correction(tmp_path, admin, [row], dry_run=True)
    record.refresh_from_db()
    assert record.origin == "unknown"
    assert not AuditEvent.objects.filter(record=record).exists()
    with pytest.raises(CommandError):
        run_correction(tmp_path, admin, [row, {**row, "id": record.pk + 99999}])
    record.refresh_from_db()
    assert record.origin == "unknown"
    run_correction(tmp_path, admin, [row])
    record.refresh_from_db()
    assert (record.origin, record.publication_year, record.year_accomplished, record.pipeline_status) == (
        "imported_reference", 2017, 2020, "published")
    assert list(record.authors.values_list("name", flat=True)) == ["Ada Reyes"]
    event = AuditEvent.objects.get(record=record, event_type="RESEARCH_METADATA_CORRECTED")
    assert event.user_id == admin.pk
    assert event.metadata["before"]["authors"] == []
    assert event.metadata["after"]["authors"] == ["Ada Reyes"]
    assert event.metadata["evidence"] == row["evidence"]


def test_correction_refuses_a_non_admin_and_invalid_manifests(tmp_path):
    actor = User.objects.create_user(email="metadata-owner@cit.edu", password="test")
    record = Record.objects.create(title="Untouched")
    Author.objects.create(record=record, name="Recorded Author")
    row = {"id": record.pk, "origin": "synthetic", "evidence": "Reviewed fixture manifest"}
    with pytest.raises(CommandError):
        run_correction(tmp_path, actor, [row])
    actor.is_superuser = True
    actor.save()
    for invalid in [{**row, "origin": "guessed"}, {**row, "publication_year": -1},
                    {**row, "authors": [""]}, {**row, "pipeline_status": "draft"}]:
        with pytest.raises(CommandError):
            run_correction(tmp_path, actor, [invalid])
    assert list(record.authors.values_list("name", flat=True)) == ["Recorded Author"]
