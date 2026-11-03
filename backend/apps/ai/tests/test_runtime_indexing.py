"""Current indexed publication through isolated workers and authenticated readers."""

import asyncio
import json
from dataclasses import dataclass

import pytest
from django.db import connection
from django.utils import timezone

from . import test_runtime_extraction as extraction
from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_research_db import ask
from .test_ai_runtime_admission_db import limits
from apps.ai.models.admission import ProviderReservation
from apps.publication import authority
from apps.publication.models import ManuscriptWork
from apps.records.models import Record, RecordOwner
from .corpus import make_user
from ai.ingestion.indexing import Bounds, process
from ai.runs.executor import Citation, Result

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
api = runs_db.api


@pytest.fixture
def runtime(extraction_runtime):
    from apps.ai.models import EmbeddingSpace

    EmbeddingSpace.objects.get_or_create(
        state="active",
        defaults={"model_id": "voyage-context-4", "dimensions": 1024, "metric": "cosine"},
    )
    yield extraction_runtime
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE iris_ai.active_source,iris_ai.embedding_batch,iris_ai.index_job")


extraction_runtime = extraction.runtime


@dataclass
class Response:
    vectors: list
    input_tokens: int = 10


class Recording:
    model = "voyage-context-4"
    dimensions = 1024
    data_policy = "no-training"
    account = "recording"

    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    async def embed(self, texts, *, input_type):
        self.calls.append((list(texts), input_type))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("unknown remote outcome")
        return Response([[1.0] + [0.0] * 1023 for _ in texts])


def permitted():
    import uuid

    owner = make_user(f"indexed-{uuid.uuid4().hex[:10]}@cit.edu")
    record = Record.objects.create(
        title="Pond research",
        abstract="Ponds sampled weekly",
        abstract_file="manuscripts/pond.pdf",
        dpa_accepted_at=timezone.now(),
        embargo_answered_at=timezone.now(),
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    work = ManuscriptWork.objects.get(record=record, revoked_at=None)
    token = authority.issue_grant(work.pk).token
    return owner, record, token


def index(runtime, token, provider, *, bounds=None, **kw):
    return asyncio.run(
        process(
            runtime,
            token,
            pipeline="synthetic-v1",
            provider=provider,
            limits=limits(
                AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"ingestion": 1, "research": 2}),
                AI_ADMISSION_PRICES=json.dumps({"voyage-context-4": {"input": 1, "output": 0}}),
            ),
            bounds=bounds or Bounds(60, 10, 10, 100000, 1),
            **kw,
        )
    )


def test_resume_keeps_completed_batch_and_reader_cites_active_revision(runtime, api):
    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    broken = Recording(fail_at=2)
    with pytest.raises(RuntimeError):
        index(runtime, token, broken)
    assert extraction.status(owner, record)["state"] == "indexing"
    assert ProviderReservation.objects.filter(sent=True).count() == 2
    unknown = ProviderReservation.objects.order_by("pk").last()
    assert not unknown.usage_reported and unknown.charge_input_tokens > 0
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE iris_ai.index_job SET lease_until=clock_timestamp()-interval '1 second'"
        )
    resumed = Recording()
    assert index(runtime, token, resumed) == "ready"
    assert len(resumed.calls) == 1
    assert resumed.calls[0][1] == "document"
    assert all("Pond research." not in t for t in resumed.calls[0][0])
    assert index(runtime, token, Recording()) == "duplicate"
    assert extraction.status(owner, record)["state"] == "ready"
    api[1]["dsn"] = runtime

    async def question(tools):
        found = await tools.search("ponds")
        assert found.status == "ok" and found.passages
        passage = found.passages[0]
        opened = await tools.open_passage(passage.handle)
        assert opened.passages[0].source == passage.source
        return Result(
            answer="Twelve ponds were sampled weekly.",
            citations=(
                Citation(
                    record_id=record.pk,
                    page=passage.page,
                    quote=passage.text,
                    revision=passage.source.revision,
                ),
            ),
        )

    errors = []

    async def checked_question(tools):
        try:
            return await question(tools)
        except Exception as exc:
            errors.append(repr(exc))
            raise

    response, seen, grant = ask(api, owner, checked_question, key="indexed-question-0001")
    assert not errors, errors
    assert response.status_code == 201 and response.json()["state"] == "completed"
    assert any(result.passages for _, result in seen)
    from .test_ai_runtime_runs_db import as_reader

    transcript = (
        api[0]
        .get(
            f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
            headers=as_reader(grant),
        )
        .json()
    )
    saved = transcript["turns"][0]["citations"][0]
    assert (
        saved["record_id"] == record.pk
        and saved["revision"] == seen[0][1].passages[0].source.revision
    )
    assert saved["quote"] == "Twelve ponds were sampled weekly. All twelve ponds improved."
    Record.objects.filter(pk=record.pk).update(dpa_accepted_at=None)
    revoked = (
        api[0]
        .get(
            f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
            headers=as_reader(grant),
        )
        .json()
    )
    assert revoked["turns"] == []


@pytest.mark.parametrize("change", ["replace", "delete", "consent", "summary"])
def test_late_indexing_cannot_activate_changed_source(runtime, change):
    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    first = Recording(fail_at=2)
    with pytest.raises(RuntimeError):
        index(runtime, token, first)
    if change == "replace":
        Record.objects.filter(pk=record.pk).update(abstract_file="manuscripts/new.pdf")
    elif change == "delete":
        Record.objects.filter(pk=record.pk).update(is_deleted=True)
    elif change == "consent":
        Record.objects.filter(pk=record.pk).update(dpa_accepted_at=None)
    else:
        Record.objects.filter(pk=record.pk).update(abstract="Updated results")
    late = Recording()
    assert index(runtime, token, late) in ("withheld", "stale")
    assert not late.calls
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.active_source")
        assert cursor.fetchone()[0] == 0


def test_wrong_space_and_disclosure_call_no_provider(runtime):
    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    provider = Recording()
    provider.dimensions = 3
    from ai.admission.errors import AdmissionDenied

    with pytest.raises(AdmissionDenied):
        index(runtime, token, provider)
    assert not provider.calls
    Record.objects.filter(pk=record.pk).update(dpa_accepted_at=None)
    token = authority.issue_grant(
        ManuscriptWork.objects.get(record=record, revoked_at=None).pk
    ).token
    assert index(runtime, token, Recording()) == "withheld"


def independent(runtime, token):
    import os
    import subprocess
    import sys
    from .test_ai_runtime_admission_db import ADMISSION

    cfg = {
        **ADMISSION,
        "AI_ADMISSION_LANE_CONCURRENCY": json.dumps({"ingestion": 1, "research": 2}),
        "AI_ADMISSION_PRICES": json.dumps({"voyage-context-4": {"input": 1, "output": 0}}),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "ai.tests.index_worker"],
        input=json.dumps({"dsn": runtime, "token": token, "limits": cfg}),
        text=True,
        capture_output=True,
        cwd=extraction.ROOT,
        env={**os.environ, "PYTHONPATH": str(extraction.ROOT / "backend")},
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_new_revision_publishes_and_older_independent_worker_cannot_reactivate(runtime, api):
    owner, record, old_token = permitted()
    assert extraction.run(runtime, old_token) == "extracted"
    assert independent(runtime, old_token) == {"state": "ready", "calls": 2}
    Record.objects.filter(pk=record.pk).update(abstract_file="manuscripts/revised.pdf")
    record.refresh_from_db()
    new_token = authority.issue_grant(
        ManuscriptWork.objects.get(record=record, revoked_at=None).pk
    ).token
    assert extraction.run(runtime, new_token) == "extracted"
    assert independent(runtime, new_token) == {"state": "ready", "calls": 2}
    assert independent(runtime, old_token) == {"state": "stale", "calls": 0}
    assert independent(runtime, new_token) == {"state": "duplicate", "calls": 0}
    api[1]["dsn"] = runtime

    async def question(tools):
        found = await tools.search("ponds")
        assert found.status == "ok"
        assert {p.source.chunk_set_id for p in found.passages} == {expected_id}
        return Result(answer="Current revision found.")

    with connection.cursor() as cursor:
        cursor.execute("SELECT -job_id FROM iris_ai.active_source WHERE record_id=%s", [record.pk])
        expected_id = cursor.fetchone()[0]
    response, _, _ = ask(api, owner, question, key="indexed-newest-0001")
    assert response.json()["state"] == "completed"


def test_redelivery_cannot_increase_persisted_job_spend_allowance(runtime):
    from ai.admission.errors import AdmissionDenied

    _, _, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    provider = Recording()
    with pytest.raises(AdmissionDenied):
        index(runtime, token, provider, bounds=Bounds(60, 10, 1, 100000, 1))
    assert len(provider.calls) == 1
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE iris_ai.index_job SET lease_until=clock_timestamp()-interval '1 second'"
        )
    retry = Recording()
    with pytest.raises(AdmissionDenied):
        index(runtime, token, retry, bounds=Bounds(60, 10, 100, 1000000, 100))
    assert not retry.calls
    assert ProviderReservation.objects.count() == 1


def test_query_embedding_uses_same_space_with_its_own_run_admission(runtime, api):
    from ai.admission.ledger import Ledger
    from ai.runs.service import RunService
    from .test_ai_runtime_research_db import ScriptedResearch
    from apps.ai.grants import issue

    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    assert index(runtime, token, Recording()) == "ready"
    query_provider = Recording()
    observed = []

    async def question(tools):
        result = await tools.semantic_search("pond sampling")
        observed.append(result)
        assert result.status == "ok" and result.passages[0].record_id == record.pk
        return Result(answer="Ponds found.")

    initial = runs_db.service(runtime, ScriptedResearch(question))
    built = RunService(
        initial.store,
        initial.cfg,
        initial.executor,
        initial.notifier,
        embedding_provider=query_provider,
        embedding_ledger=Ledger(
            runtime,
            limits(AI_ADMISSION_PRICES=json.dumps({"voyage-context-4": {"input": 1, "output": 0}})),
        ),
    )
    built.notifier.service = built
    api[1]["service"] = built
    grant = issue.reader_session_grant(owner).token
    response = runs_db.submit(api[0], grant, "indexed-semantic-0001")
    assert observed and observed[0].status == "ok"
    assert response.json()["state"] == "completed"
    assert query_provider.calls == [(["pond sampling"], "query")]
    assert (
        ProviderReservation.objects.filter(purpose="query", lane="research", owner="ai").count()
        == 1
    )
