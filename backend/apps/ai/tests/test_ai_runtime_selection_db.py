"""Ask about a verified text selection, through the reader routes on real PostgreSQL (IR-581).

A Paper Chat question may carry the passage the reader selected. The runtime
checks the Record, Manuscript revision, page and quote against the indexed
text under the reader's own grant, stores nothing it cannot verify, and
checks again before any model call: the recording provider shows a passage
that stopped holding in between never reaches it.
"""

import dataclasses
import uuid

import pytest

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_agent_loop_db import PIN, PROFILES, LIMITS, recording, reply
from .test_ai_runtime_research_db import paper, write_source
from .test_ai_runtime_runs_db import as_reader, run
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.prompts import SELECTION_PREFIX, SELECTION_WITHDRAWN  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.ai.models.chunk import ChunkSet  # noqa: E402
from apps.records.models import Record  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from django.db import connection  # noqa: E402
from .corpus import make_user  # noqa: E402
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime
api = runs_db.api

PUBLIC = {"X-IRIS-Protocol": "runs-reader-1"}
RESULT = "Flooding in the delta rose by forty percent after the dam opened."
METHOD = "We surveyed two hundred households along the river."


class Quiet:
    """A wakeup that does nothing, so the test decides when the queue runs."""

    async def notify(self):
        pass

    async def wait(self, timeout):
        pass


#: The pin that can be sent a selection (IR-581).
PIN_12 = dataclasses.replace(PIN, prompt_version="agent-research-12", tool_version="research-12")


def chat_service(dsn, provider, *, drain=True, pin=PIN_12):
    cfg = runs_config.RunsConfig(database_url=dsn, executor="deterministic", limits=LIMITS,
                                 dispatch=runs_db.DISPATCH)
    executor = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    built = RunService(RunStore(dsn), cfg, executor, runs_db.Drain() if drain else Quiet())
    if drain:
        built.notifier.service = built
    return built


def indexed(title="Delta flooding", revision=None):
    """A published paper indexed from a known Manuscript revision, results on page 3."""
    record = paper(title, {2: [("Methods", METHOD)], 3: [("Results", RESULT)]})
    revision = revision or str(uuid.uuid4())
    ChunkSet.objects.filter(record=record, is_active=True).update(source_revision=revision)
    return record, revision


def selected(record, revision, page=3, quote="rose by forty percent after the dam"):
    return {"record_id": record.pk, "manuscript_revision": revision, "page": page, "quote": quote}


def scoped(user, record):
    return {**as_reader(issue.reader_session_grant(user, record.pk).token), **PUBLIC}


def ask(client, headers, key, selection, question="What does this passage mean?"):
    return client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": key},
                       json={"question": question, "selection": selection})


def sent(provider) -> str:
    return "\n".join(str(m.get("content")) for p in provider.requests for m in p["messages"])


def stored_runs() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run")
        return cursor.fetchone()[0]


def test_a_verified_selection_reaches_the_model_and_replays_with_its_turn(api, runtime):
    client, holder = api
    provider = recording(reply("It reports the rise the survey found."))
    holder["service"] = chat_service(runtime, provider)
    record, revision = indexed()
    headers = scoped(make_user("selection-ok@cit.edu"), record)

    response = ask(client, headers, "selection-0001", selected(record, revision))
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "completed"
    assert response.json()["selection"] == {
        "available": True, "record_id": record.pk, "page": 3, "manuscript_revision": revision,
        "quote": "rose by forty percent after the dam", "current": True,
    }
    text = sent(provider)
    assert SELECTION_PREFIX in text and "rose by forty percent after the dam" in text

    conversation = client.get(f"/api/v1/ai/conversations/{response.json()['conversation_id']}", headers=headers)
    assert conversation.status_code == 200, conversation.text
    [turn] = conversation.json()["turns"]
    assert turn["question"] == "What does this passage mean?"
    assert turn["selection"]["quote"] == "rose by forty percent after the dam"
    assert turn["selection"]["current"] is True


@pytest.mark.parametrize("tamper", [
    pytest.param(lambda s, other: {**s, "quote": "rose by sixty percent after the dam"}, id="quote"),
    pytest.param(lambda s, other: {**s, "page": 2}, id="page"),
    pytest.param(lambda s, other: {**s, "manuscript_revision": str(uuid.uuid4())}, id="version"),
    pytest.param(lambda s, other: {**s, "record_id": other.pk}, id="record"),
])
def test_a_tampered_selection_is_refused_and_nothing_is_stored(api, runtime, tamper):
    client, holder = api
    provider = recording(reply("Never sent."))
    holder["service"] = chat_service(runtime, provider)
    record, revision = indexed()
    other, _ = indexed("Upland drought")
    headers = scoped(make_user("selection-tampered@cit.edu"), record)

    response = ask(client, headers, "selection-0002", tamper(selected(record, revision), other))
    assert response.status_code == 422, response.text
    assert response.json()["status"] in {"selection_unverified", "selection_version", "selection_out_of_scope"}
    assert stored_runs() == 0
    assert provider.requests == []


def test_each_refusal_names_what_the_reader_can_do(api, runtime):
    client, holder = api
    holder["service"] = chat_service(runtime, recording(reply("Never sent.")))
    record, revision = indexed()
    user = make_user("selection-codes@cit.edu")
    headers = scoped(user, record)
    codes = {
        "selection_unverified": {**selected(record, revision), "quote": "not in this paper at all"},
        "selection_version": {**selected(record, revision), "manuscript_revision": str(uuid.uuid4())},
    }
    for n, (code, selection) in enumerate(codes.items()):
        assert ask(client, headers, f"selection-code-{n}", selection).json() == {"status": code}
    # Only Paper Chat asks about a selection: a whole-repository grant names no paper.
    unscoped = {**as_reader(issue.reader_session_grant(user).token), **PUBLIC}
    assert ask(client, unscoped, "selection-code-9", selected(record, revision)).json() == {
        "status": "selection_out_of_scope"}
    # Every malformed shape is the one named refusal, never a framework error the page cannot read.
    for n, bad in enumerate(({"page": 0}, {"page": "3"}, {"quote": "x" * 5000}, {"record_id": None})):
        response = ask(client, headers, f"selection-shape-{n}", {**selected(record, revision), **bad})
        assert response.status_code == 422 and response.json() == {"status": "invalid_selection"}, bad


def test_a_runtime_on_an_earlier_pin_refuses_a_selection_rather_than_drop_it(api, runtime):
    client, holder = api
    provider = recording(reply("Never sent."))
    holder["service"] = chat_service(runtime, provider, pin=PIN)
    record, revision = indexed()
    headers = scoped(make_user("selection-old-pin@cit.edu"), record)
    assert ask(client, headers, "selection-0008", selected(record, revision)).json() == {
        "status": "selection_unsupported"}
    assert stored_runs() == 0 and provider.requests == []


def test_an_unindexed_or_unreadable_paper_is_refused(api, runtime):
    client, holder = api
    holder["service"] = chat_service(runtime, recording(reply("Never sent.")))
    user = make_user("selection-hidden@cit.edu")
    record, revision = indexed()
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)
    assert ask(client, scoped(user, record), "selection-0003", selected(record, revision)).json() == {
        "status": "selection_unavailable"}
    # Readable, but nothing indexed: there is no text to check the quote against.
    unindexed = Record.objects.create(title="Not yet read", abstract="", pipeline_status=PipelineStatus.PUBLISHED)
    assert ask(client, scoped(user, unindexed), "selection-0007", selected(unindexed, revision)).json() == {
        "status": "selection_unavailable"}
    assert stored_runs() == 0


def test_a_paper_replaced_before_the_run_starts_never_sends_the_old_passage(api, runtime):
    client, holder = api
    provider = recording(reply("The passage could not be used."))
    holder["service"] = service = chat_service(runtime, provider, drain=False)
    record, revision = indexed()
    headers = scoped(make_user("selection-replaced@cit.edu"), record)

    queued = ask(client, headers, "selection-0004", selected(record, revision))
    assert queued.status_code == 201, queued.text
    assert queued.json()["state"] == "queued"
    # A new Manuscript is indexed while the run waits.
    write_source(record, {3: [("Results", "Flooding fell after the levee was raised.")]}, "2")
    ChunkSet.objects.filter(record=record, is_active=True).update(source_revision=str(uuid.uuid4()))
    while run(service.run_next()):
        pass

    text = sent(provider)
    assert SELECTION_WITHDRAWN in text
    assert "rose by forty percent" not in text
    done = client.get(f"/api/v1/ai/runs/{queued.json()['id']}", headers=headers).json()
    assert done["state"] == "completed"
    # Replayed as selected on an earlier version, never as the new paper's text.
    assert done["selection"]["current"] is False


def test_a_revoked_paper_withholds_the_passage_from_the_model_and_the_replay(api, runtime):
    client, holder = api
    provider = recording(reply("The passage could not be used."))
    holder["service"] = service = chat_service(runtime, provider, drain=False)
    record, revision = indexed()
    headers = scoped(make_user("selection-revoked@cit.edu"), record)

    queued = ask(client, headers, "selection-0005", selected(record, revision))
    assert queued.status_code == 201, queued.text
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)
    while run(service.run_next()):
        pass

    text = sent(provider)
    assert SELECTION_WITHDRAWN in text, "the run reached the model, told the passage is gone"
    assert "rose by forty percent" not in text
    status = client.get(f"/api/v1/ai/runs/{queued.json()['id']}", headers=headers).json()
    assert status["selection"] == {"available": False}


def test_deleting_the_conversation_removes_the_selection(api, runtime):
    client, holder = api
    holder["service"] = chat_service(runtime, recording(reply("Answered.")))
    record, revision = indexed()
    headers = scoped(make_user("selection-deleted@cit.edu"), record)
    done = ask(client, headers, "selection-0006", selected(record, revision)).json()

    deleted = client.delete(f"/api/v1/ai/conversations/{done['conversation_id']}", headers=headers)
    assert deleted.status_code in (200, 204), deleted.text
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run WHERE selection IS NOT NULL")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM iris_ai.turn")
        assert cursor.fetchone()[0] == 0
