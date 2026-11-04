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
    assert revoked["turns"][0]["citations"] == []
    assert "no longer readable" in revoked["turns"][0]["answer"]


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


def test_restricted_writer_cannot_mutate_paid_output_or_publish_incomplete_coverage(runtime):
    import asyncpg
    from ai.ingestion.indexing import connect

    _, _, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    with pytest.raises(RuntimeError):
        index(runtime, token, Recording(fail_at=2))

    async def probe():
        conn = await connect(runtime)
        try:
            async with conn.transaction():
                await conn.fetchval("SELECT iris_authz.begin_research($1,'ingestion')", token)
                job = await conn.fetchrow("SELECT id,record_id FROM iris_ai.index_job")
                for statement in [
                    "UPDATE iris_ai.embedding_batch SET vectors='[]'",
                    "DELETE FROM iris_ai.embedding_batch",
                    "UPDATE iris_ai.index_job SET allowance='{}'",
                    "UPDATE iris_ai.index_job SET payload='{}'",
                ]:
                    with pytest.raises(asyncpg.InsufficientPrivilegeError):
                        async with conn.transaction():
                            await conn.execute(statement)
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE iris_ai.index_job SET state='complete' WHERE id=$1", job["id"]
                        )
                        await conn.execute(
                            "INSERT INTO iris_ai.active_source(record_id,job_id) VALUES($1,$2)",
                            job["record_id"],
                            job["id"],
                        )
            assert await conn.fetchval("SELECT count(*) FROM iris_ai.index_job") == 0
            assert await conn.fetchval("SELECT count(*) FROM iris_ai.embedding_batch") == 0
        finally:
            await conn.close()

    asyncio.run(probe())


def test_independent_ingestion_workers_share_the_ingestion_lane_limit(runtime):
    import os
    import subprocess
    import sys
    from .test_ai_runtime_admission_db import ADMISSION
    from ai.admission.errors import AdmissionDenied

    _, _, first_token = permitted()
    _, _, second_token = permitted()
    assert extraction.run(runtime, first_token) == "extracted"
    assert extraction.run(runtime, second_token) == "extracted"
    cfg = {
        **ADMISSION,
        "AI_ADMISSION_LANE_CONCURRENCY": json.dumps({"ingestion": 1, "research": 2}),
        "AI_ADMISSION_PRICES": json.dumps({"voyage-context-4": {"input": 1, "output": 0}}),
    }
    child = subprocess.Popen(
        [sys.executable, "-m", "ai.tests.index_worker"],
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=extraction.ROOT,
        env={**os.environ, "PYTHONPATH": str(extraction.ROOT / "backend")},
    )
    try:
        child.stdin.write(
            json.dumps({"dsn": runtime, "token": first_token, "limits": cfg, "delay": 5})
        )
        child.stdin.close()
        child.stdin = None
        assert child.stdout.readline().strip() == "sending"
        refused = Recording()
        with pytest.raises(AdmissionDenied, match="lane_busy"):
            index(runtime, second_token, refused)
        assert not refused.calls
        stdout, stderr = child.communicate(timeout=20)
        assert child.returncode == 0, stderr
        assert json.loads(stdout) == {"state": "ready", "calls": 2}
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_disclosure_can_be_withdrawn_during_inference_without_waiting_for_provider(runtime):
    import asyncpg

    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"

    class WithdrawDuringInference(Recording):
        async def embed(self, texts, *, input_type):
            result = await super().embed(texts, input_type=input_type)
            conn = await asyncpg.connect(runs_db.admin_dsn())
            try:
                await conn.execute("SET statement_timeout='1s'")
                await conn.execute(
                    "UPDATE records_record SET dpa_accepted_at=NULL WHERE id=$1", record.pk
                )
            finally:
                await conn.close()
            return result

    provider = WithdrawDuringInference()
    assert index(runtime, token, provider) == "stale"
    assert len(provider.calls) == 1
    record.refresh_from_db()
    assert record.dpa_accepted_at is None
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.active_source")
        assert cursor.fetchone()[0] == 0


def test_uncited_research_dependency_is_withheld_on_replay_and_followup(runtime, api):
    owner, first, first_token = permitted()
    _, second, second_token = permitted()
    RecordOwner.objects.create(record=second, user=owner, is_primary=False)
    for token in (first_token, second_token):
        assert extraction.run(runtime, token) == "extracted"
        assert index(runtime, token, Recording()) == "ready"
    api[1]["dsn"] = runtime

    async def question(tools):
        found = await tools.search("ponds")
        assert {p.record_id for p in found.passages} == {first.pk, second.pk}
        cited = next(p for p in found.passages if p.record_id == second.pk)
        return Result(
            answer="Combined findings from both papers.",
            citations=(
                Citation(
                    record_id=second.pk,
                    page=cited.page,
                    quote=cited.text,
                    revision=cited.source.revision,
                ),
            ),
        )

    response, _, grant = ask(api, owner, question, key="indexed-dependencies-0001")
    assert response.json()["state"] == "completed"
    Record.objects.filter(pk=first.pk).update(dpa_accepted_at=None)
    reopened = (
        api[0]
        .get(
            f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
            headers=runs_db.as_reader(grant),
        )
        .json()
    )
    assert "Combined findings" not in json.dumps(reopened)
    assert all(not t["citations"] for t in reopened["turns"])

    class Followup:
        name = "context-probe"
        version = "1"
        reserved_units = 0
        takes_context = True

        async def answer(self, question, tools, *, context):
            assert not context.prior
            return Result(answer="Prior evidence withheld.")

    api[1]["service"] = runs_db.service(runtime, Followup())
    followup = runs_db.submit(
        api[0],
        grant,
        "indexed-dependencies-0002",
        conversation_id=response.json()["conversation_id"],
        base_revision=1,
    )
    assert followup.json()["state"] == "completed"


def test_legacy_saved_citation_is_withheld_when_ai_publication_supersedes_it(runtime, api):
    from .test_ai_runtime_research_db import write_source

    owner, record, token = permitted()
    write_source(record, {1: [("Methods", "The legacy experiment used four ponds.")]}, "legacy")
    api[1]["dsn"] = runtime

    async def question(tools):
        found = await tools.search("legacy ponds")
        hit = found.passages[0]
        assert hit.source.chunk_set_id > 0
        return Result(
            answer="The legacy experiment used four ponds.",
            citations=(
                Citation(record_id=record.pk, page=1, quote=hit.text, revision=hit.source.revision),
            ),
        )

    response, _, grant = ask(api, owner, question, key="indexed-legacy-0001")
    assert response.json()["state"] == "completed"
    assert extraction.run(runtime, token) == "extracted"
    assert index(runtime, token, Recording()) == "ready"
    reopened = (
        api[0]
        .get(
            f"/api/v1/ai/conversations/{response.json()['conversation_id']}",
            headers=runs_db.as_reader(grant),
        )
        .json()
    )
    assert "four ponds" not in json.dumps(reopened)
    assert reopened["turns"][0]["citations"] == []

def test_current_indexed_citation_remains_in_followup_context(runtime,api):
    owner,record,token=permitted()
    assert extraction.run(runtime,token)=='extracted'
    assert index(runtime,token,Recording())=='ready'
    api[1]['dsn']=runtime
    async def first(tools):
        found=await tools.search('ponds')
        hit=found.passages[0]
        return Result(answer='Remember the pond findings.',citations=(
            Citation(record_id=record.pk,page=hit.page,quote=hit.text,revision=hit.source.revision),))
    response,_,grant=ask(api,owner,first,key='indexed-remember-0001')
    assert response.json()['state']=='completed'
    class Followup:
        name='context-probe'
        version='1'
        reserved_units=0
        takes_context=True
        async def answer(self,question,tools,*,context):
            assert [turn.answer for turn in context.prior]==['Remember the pond findings.']
            return Result(answer='Authorized context recovered.')
    api[1]['service']=runs_db.service(runtime,Followup())
    followup=runs_db.submit(api[0],grant,'indexed-remember-0002',
                           conversation_id=response.json()['conversation_id'],base_revision=1)
    assert followup.json()['state']=='completed'

def test_reprovisioning_restores_space_reads_after_table_recreation(runtime):
    from django.core.management import call_command

    _, _, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    # Recreating a Django-owned table discards its grants while the independent
    # AI schema still records migration 0011 as applied, exactly as in CI.
    with connection.cursor() as cursor:
        cursor.execute("REVOKE SELECT ON public.ai_embeddingspace FROM iris_ai_runtime")
    call_command("provision_research_roles")
    assert index(runtime, token, Recording()) == "ready"


def test_a_whole_manuscript_is_read_from_the_active_indexed_revision(runtime, api):
    # IR-733: read_manuscript's index_job branch, with no Django chunk set to fall back on.
    owner, record, token = permitted()
    assert extraction.run(runtime, token) == "extracted"
    assert index(runtime, token, Recording()) == "ready"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT j.id,j.payload FROM iris_ai.index_job j"
            " JOIN iris_ai.active_source a ON a.job_id=j.id WHERE a.record_id=%s",
            [record.pk],
        )
        job, payload = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM ai_chunkset WHERE record_id=%s", [record.pk])
        assert cursor.fetchone()[0] == 0
    payload = json.loads(payload) if isinstance(payload, str) else payload
    api[1]["dsn"] = runtime

    async def script(tools):
        found = await tools.resolve(["Pond research"])
        await tools.read_manuscript(found.records[0].handle, max_bytes=1_000_000)

    response, seen, _ = ask(api, owner, script, key="indexed-manuscript-0001")
    assert response.json()["state"] == "completed"
    _, (_, read) = seen
    assert read.status == "ok"
    assert [p.text for p in read.passages] == [c["content"] for c in payload["chunks"]]
    assert [p.page for p in read.passages] == [c["source_page"] for c in payload["chunks"]]
    assert {p.source.revision for p in read.passages} == {f"{-job}:{payload['extraction_hash']}"}
    assert read.reading.pages == len(payload["document"]["page_sizes"])
    assert read.reading.missing == () and read.reading.continue_after is None
