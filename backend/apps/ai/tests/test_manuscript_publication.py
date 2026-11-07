"""Committed Manuscript work and its public processing status (IR-737)."""
import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.records.models import Record, RecordOwner
from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def test_save_rollback_and_duplicate_preserve_one_work_identity():
    from apps.publication.models import ManuscriptWork

    record = Record.objects.create(title="Work", abstract_file="manuscripts/one.pdf")
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    record.title = "Metadata only"
    record.save()
    assert ManuscriptWork.objects.filter(record=record).count() == 1
    with pytest.raises(RuntimeError), transaction.atomic():
        record.abstract_file = "manuscripts/rolled-back.pdf"
        record.save()
        raise RuntimeError("rollback")
    record.refresh_from_db()
    assert record.abstract_file.name == "manuscripts/one.pdf"
    assert ManuscriptWork.objects.get(record=record, revoked_at=None).pk == work.pk


def test_owner_status_reports_pending_without_extraction_claims():
    owner = make_user("publication-owner@cit.edu")
    other = make_user("publication-other@cit.edu")
    record = Record.objects.create(title="Pending", abstract_file="manuscripts/pending.pdf")
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(f"/api/v1/records/{record.pk}/metadata-suggestions/")
    assert response.status_code == 200
    assert response.data["runtime_processing"]["state"] == "pending_processing"
    assert set(response.data["runtime_processing"]) == {"state", "revision"}
    client.force_authenticate(other)
    assert client.get(f"/api/v1/records/{record.pk}/metadata-suggestions/").status_code == 404


def test_restricted_ingestion_grant_rechecks_exact_current_work(grant_db):
    import psycopg2
    from apps.publication import authority
    from apps.publication.models import ManuscriptWork
    from .grant_support import probe_login

    record = Record.objects.create(title="Bound", abstract_file="manuscripts/bound.pdf")
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    grant = authority.issue_grant(work.pk)
    with probe_login() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT iris_authz.begin_research(%s, 'ingestion')", [grant.token])
        cursor.execute("SELECT record_id, revision, source_file FROM iris_authz.processing_source()")
        assert cursor.fetchone() == (record.pk, work.revision, "manuscripts/bound.pdf")
        # Processing authority is neither a reader login nor general corpus access.
        cursor.execute("SELECT id FROM records_record")
        assert cursor.fetchall() == []
        conn.rollback()
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute("SELECT * FROM publication_manuscriptwork")
        conn.rollback()
        for token, purpose in [(grant.token + "x", "ingestion"), (grant.token, "reader_session")]:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute("SELECT iris_authz.begin_research(%s, %s)", [token, purpose])
            conn.rollback()
        from apps.ai.grants.tokens import sign
        import uuid
        for altered in ({"rec": record.pk + 1000}, {"rev": str(uuid.uuid4())},
                        {"wrk": str(uuid.uuid4())}, {"op": "provider_indexing"}):
            token = sign({**grant.claims, **altered}, "k1", b"a" * 32)
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute("SELECT iris_authz.begin_research(%s, 'ingestion')", [token])
            conn.rollback()
        record.abstract_file = "manuscripts/new.pdf"
        record.save()
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute("SELECT iris_authz.begin_research(%s, 'ingestion')", [grant.token])
        conn.rollback()
    with pytest.raises(authority.WorkRefused):
        authority.issue_grant(work.pk)


def test_deleted_and_explicitly_revoked_work_never_renews(grant_db):
    from django.utils import timezone
    from apps.publication import authority
    from apps.publication.models import ManuscriptWork

    for delete in (False, True):
        record = Record.objects.create(title="Revoked", abstract_file=f"manuscripts/{delete}.pdf")
        work = ManuscriptWork.objects.get(record=record, revoked_at=None)
        if delete:
            record.is_deleted = True
            record.save()
            record.is_deleted = False
            record.save()  # restoring a Record cannot resurrect the old processing grant
        else:
            ManuscriptWork.objects.filter(pk=work.pk).update(revoked_at=timezone.now())
        with pytest.raises(authority.WorkRefused):
            authority.issue_grant(work.pk)


def test_reconcile_lost_publication_and_race_independent_workers(grant_db):
    import asyncio
    import os
    import subprocess
    import sys
    from pathlib import Path
    from urllib.parse import quote
    from django.db import connection
    from django.test import override_settings
    from apps.publication.dispatch import reconcile
    from apps.publication.models import ManuscriptWork

    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from ai.runs.migrate import migrate
    from .grant_support import probe_credentials

    def dsn(user, password):
        cfg = connection.settings_dict
        return (f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
                f"{cfg['HOST'] or 'localhost'}:{cfg['PORT'] or '5432'}/{cfg['NAME']}")

    cfg = connection.settings_dict
    asyncio.run(migrate(dsn(cfg["USER"], cfg["PASSWORD"])))
    try:
        # Simulate a crash before the post-commit publisher could sign or notify.
        with override_settings(AI_RESEARCH_GRANTS=False):
            record = Record.objects.create(title="Recover", abstract_file="manuscripts/recover.pdf")
        work = ManuscriptWork.objects.get(record=record, revoked_at=None)
        assert work.grant_token == ""
        assert reconcile(limit=10) == 1
        script = ("import asyncio,os; from ai.ingestion.worker import consume; "
                  "print(asyncio.run(consume(os.environ['RUNS_DATABASE_URL'], limit=10)).acknowledged)")
        with probe_credentials() as (name, password):
            env = {**os.environ, "RUNS_DATABASE_URL": dsn(name, password)}
            processes = [subprocess.Popen([sys.executable, "-c", script], cwd=root, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
            outputs = [p.communicate(timeout=30) for p in processes]
            assert [p.returncode for p in processes] == [0, 0], outputs
            assert sorted(out.strip() for out, _ in outputs) == ["0", "1"]
        owner = make_user("recovered-owner@cit.edu")
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
        client = APIClient()
        client.force_authenticate(owner)
        url = f"/api/v1/records/{record.pk}/metadata-suggestions/"
        assert client.get(url).data["runtime_processing"]["state"] == "acknowledged_pending"
        record.pipeline_status = "published"
        record.save()
        from ai.ingestion.worker import consume
        with probe_credentials() as (name, password):
            runtime = dsn(name, password)
            assert asyncio.run(consume(runtime, limit=10)).acknowledged == 1
            assert asyncio.run(consume(runtime, limit=10)).acknowledged == 0
        # Replaying the older access fact cannot remove the new acknowledgement.
        assert client.get(url).data["runtime_processing"]["state"] == "acknowledged_pending"
        record.abstract_file = "manuscripts/next.pdf"
        record.save()
        assert client.get(url).data["runtime_processing"]["state"] == "pending_processing"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE iris_ai.manuscript_receipt, iris_ai.manuscript_invalidation_receipt")


def test_access_change_denies_bound_grant_before_cleanup(grant_db):
    from apps.publication import authority
    from apps.publication.models import ManuscriptWork, ManuscriptInvalidation
    from .grant_support import probe_login

    owner = make_user("revoked-publication-owner@cit.edu")
    record = Record.objects.create(title="Access", abstract_file="manuscripts/access.pdf")
    ownership = RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    grant = authority.issue_grant(work.pk)
    with probe_login() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT iris_authz.begin_research(%s, 'ingestion')", [grant.token])
        ownership.delete()
        cursor.execute("SELECT * FROM iris_authz.processing_source()")
        assert cursor.fetchall() == []  # no projection cleanup has run
        conn.rollback()
    assert ManuscriptInvalidation.objects.filter(work_id=work.pk, reason="access").count() == 1
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    renewed = authority.issue_grant(work.pk)
    assert renewed.claims["wgen"] == grant.claims["wgen"] + 1


def test_record_access_and_historical_revision_replay_are_fenced(grant_db):
    from apps.publication import authority
    from apps.publication.models import ManuscriptWork
    from django.db import IntegrityError

    record = Record.objects.create(title="Revision", abstract_file="manuscripts/revision.pdf")
    first = ManuscriptWork.objects.get(record=record, revoked_at=None)
    Record.objects.filter(pk=record.pk).update(pipeline_status="published")
    assert ManuscriptWork.objects.get(record=record, revoked_at=None).pk == first.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        ManuscriptWork.objects.create(record=record, revision=first.revision, source_file=first.source_file)
    assert ManuscriptWork.objects.filter(record=record, revision=first.revision).count() == 1
    Record.objects.filter(pk=record.pk).update(abstract_file="manuscripts/replacement.pdf")
    with pytest.raises(authority.WorkRefused):
        authority.issue_grant(first.pk)


def test_deletion_fact_survives_record_and_is_reconciled(grant_db):
    import asyncio
    import sys
    from pathlib import Path
    from django.db import connection
    from apps.publication.models import ManuscriptWork, ManuscriptInvalidation
    from .grant_support import probe_credentials
    from .test_ai_runtime_runs_db import admin_dsn, dsn

    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from ai.runs.migrate import migrate
    from ai.ingestion.worker import consume

    asyncio.run(migrate(admin_dsn()))
    try:
        record = Record.objects.create(title="Delete", abstract_file="manuscripts/delete.pdf")
        work = ManuscriptWork.objects.get(record=record, revoked_at=None)
        with probe_credentials() as (name, password):
            runtime = dsn(name, password)
            assert asyncio.run(consume(runtime, limit=10)).acknowledged == 1
            record.delete()
            assert ManuscriptInvalidation.objects.filter(work_id=work.pk, reason="deleted").exists()
            assert asyncio.run(consume(runtime, limit=10)).invalidated == 1
            assert asyncio.run(consume(runtime, limit=10)).invalidated == 0
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM iris_ai.manuscript_receipt WHERE work_id=%s", [str(work.pk)])
                assert cursor.fetchone()[0] == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE iris_ai.manuscript_receipt, iris_ai.manuscript_invalidation_receipt")


def test_authenticated_manuscript_upload_publishes_work(tmp_path, settings, monkeypatch):
    import sys
    if sys.platform != "linux":
        pytest.skip("bounded PDF intake requires Linux; run this seam in the backend container")
    from apps.documents.testing import pdf_upload
    from apps.documents.tasks import extract_manuscript_text
    from apps.publication.models import ManuscriptWork
    from apps.records.models import RecordType
    from django.utils import timezone

    settings.MEDIA_ROOT = str(tmp_path)
    owner = make_user("publication-upload@cit.edu")
    record = Record.objects.create(title="Upload", added_by=owner,
        is_embargoed=False, embargo_released_at=timezone.now(), embargo_released_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0])
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    # The existing extraction queue is external to this publication seam.
    monkeypatch.setattr(extract_manuscript_text, "delay", lambda *args: None)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.patch(f"/api/v1/records/{record.pk}/",
        {"abstract_file": pdf_upload("paper.pdf", b"Synthetic manuscript")}, format="multipart")
    assert response.status_code == 200, response.data
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    response = client.get(f"/api/v1/records/{record.pk}/metadata-suggestions/")
    assert response.data["runtime_processing"] == {"state": "pending_processing", "revision": str(work.revision)}


def test_authenticated_submission_keeps_current_work_recoverable(grant_db, monkeypatch):
    from apps.ai.grants.database import verify
    from apps.documents.tasks import extract_manuscript_text
    from apps.publication.models import ManuscriptWork
    from apps.records.models import RecordType
    from django.utils import timezone

    owner = make_user("publication-submit@cit.edu")
    adviser = make_user("publication-adviser@cit.edu", "Adviser")
    record = Record.objects.create(title="A complete research paper", abstract="Research abstract " * 5,
        added_by=owner, adviser=adviser, abstract_file="manuscripts/submit.pdf",
        is_embargoed=False, embargo_released_at=timezone.now(), embargo_released_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0])
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    old_token = work.grant_token
    monkeypatch.setattr(extract_manuscript_text, "delay", lambda *args: None)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(f"/api/v1/records/{record.pk}/submit/",
                           {"dpa_accepted": True}, format="json")
    assert response.status_code == 200, response.data
    current = ManuscriptWork.objects.get(record=record, revoked_at=None)
    assert current.pk == work.pk
    assert current.authority_generation > work.authority_generation
    assert verify(old_token, "ingestion") is None
    assert verify(current.grant_token, "ingestion") is not None
    assert client.get(f"/api/v1/records/{record.pk}/metadata-suggestions/").data[
        "runtime_processing"] == {"state": "pending_processing", "revision": str(work.revision)}


def test_canonical_embargo_change_invalidates_old_processing_grant(grant_db):
    from datetime import timedelta
    from django.utils import timezone
    from apps.ai.grants.database import verify
    from apps.publication.models import ManuscriptWork
    from apps.records.embargo import set_embargo

    owner = make_user("publication-embargo@cit.edu")
    record = Record.objects.create(title="Embargo", abstract_file="manuscripts/embargo.pdf")
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    old = ManuscriptWork.objects.get(record=record, revoked_at=None)
    assert verify(old.grant_token, "ingestion") is not None
    with transaction.atomic():
        locked = Record.objects.select_for_update().get(pk=record.pk)
        set_embargo(locked, timezone.localdate() + timedelta(days=30), actor=owner)
    assert verify(old.grant_token, "ingestion") is None
    current = ManuscriptWork.objects.get(record=record, revoked_at=None)
    assert current.pk == old.pk
    assert current.authority_generation > old.authority_generation
