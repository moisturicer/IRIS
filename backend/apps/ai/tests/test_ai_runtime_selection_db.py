"""Ask about a text selection, through the reader routes on real PostgreSQL (IR-581).

A Paper Chat question may carry the passage the reader selected. Nothing about
the passage is refused: the question is always asked. Just before the model is
called, the runtime checks the selection under the reader's own grant and tells
the model what it found (whether the quote is on that page, and whether it is
the same version), so the model can look for it. A paper this reader may not
read, or one with no indexed text, withholds the quote: the recording provider
shows it never reaches the model.
"""

import dataclasses
import json
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
QUOTE = "rose by forty percent after the dam"


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


def answered():
    """A provider that answers every attempt, repairs included."""
    return recording(*[reply("It reports the rise the survey found.")] * 4)


def indexed(title="Delta flooding", revision=None):
    """A published paper indexed from a known Manuscript revision, results on page 3."""
    record = paper(title, {2: [("Methods", METHOD)], 3: [("Results", RESULT)]})
    revision = revision or str(uuid.uuid4())
    ChunkSet.objects.filter(record=record, is_active=True).update(source_revision=revision)
    return record, revision


def selected(record, revision, page=3, quote=QUOTE):
    return {"record_id": record.pk, "manuscript_revision": revision, "page": page, "quote": quote}


def scoped(user, record):
    return {**as_reader(issue.reader_session_grant(user, record.pk).token), **PUBLIC}


def everywhere(user):
    return {**as_reader(issue.reader_session_grant(user).token), **PUBLIC}


def ask(client, headers, key, selection, question="What does this passage mean?"):
    return client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": key},
                       json={"question": question, "selection": selection})


def sent(provider) -> str:
    return "\n".join(str(m.get("content")) for p in provider.requests for m in p["messages"])


def told(provider) -> dict:
    """What the first model call was told about the selection."""
    [note] = [m["content"] for m in provider.requests[0]["messages"]
              if m["role"] == "user" and str(m["content"]).startswith(SELECTION_PREFIX)]
    return json.loads(note[len(SELECTION_PREFIX):])


def stored_runs() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run")
        return cursor.fetchone()[0]


def test_a_selection_found_on_its_page_reaches_the_model_and_replays_with_its_turn(api, runtime):
    client, holder = api
    provider = answered()
    holder["service"] = chat_service(runtime, provider)
    record, revision = indexed()
    headers = scoped(make_user("selection-ok@cit.edu"), record)

    response = ask(client, headers, "selection-0001", selected(record, revision))
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "completed"
    assert response.json()["selection"] == {
        "available": True, "record_id": record.pk, "page": 3, "manuscript_revision": revision,
        "quote": QUOTE, "current": True,
    }
    note = told(provider)
    assert (note["found_on_page"], note["version"], QUOTE in note["quote"]) == (True, "same", True)

    conversation = client.get(f"/api/v1/ai/conversations/{response.json()['conversation_id']}", headers=headers)
    assert conversation.status_code == 200, conversation.text
    [turn] = conversation.json()["turns"]
    assert turn["question"] == "What does this passage mean?"
    assert turn["selection"]["quote"] == QUOTE and turn["selection"]["current"] is True


@pytest.mark.parametrize("change, found, version", [
    pytest.param({"quote": "rose by sixty percent after the dam"}, False, "same", id="altered quote"),
    pytest.param({"page": 2}, False, "same", id="other page"),
    pytest.param({"manuscript_revision": str(uuid.uuid4())}, True, "different", id="other version"),
    pytest.param({"manuscript_revision": None}, True, "unknown", id="no version"),
])
def test_a_selection_that_does_not_match_is_asked_anyway_and_the_model_is_told(api, runtime, change, found,
                                                                               version):
    client, holder = api
    provider = answered()
    holder["service"] = chat_service(runtime, provider)
    record, revision = indexed()
    headers = scoped(make_user("selection-unmatched@cit.edu"), record)

    response = ask(client, headers, "selection-0002", {**selected(record, revision), **change})
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "completed"
    note = told(provider)
    assert (note["found_on_page"], note["version"]) == (found, version)


def test_a_selection_from_another_readable_paper_names_that_paper(api, runtime):
    client, holder = api
    provider = answered()
    holder["service"] = chat_service(runtime, provider)
    record, revision = indexed()
    other, other_revision = indexed("Upland drought")
    # Widened to every paper: the run may read both, so the other paper is looked at, not refused.
    headers = everywhere(make_user("selection-other-paper@cit.edu"))

    response = ask(client, headers, "selection-0003", selected(other, other_revision))
    assert response.status_code == 201, response.text
    note = told(provider)
    assert note["found_on_page"] is True and "Upland drought" in note["title"]


def test_a_paper_the_reader_may_not_read_never_sends_its_text(api, runtime):
    client, holder = api
    provider = answered()
    holder["service"] = chat_service(runtime, provider)
    user = make_user("selection-hidden@cit.edu")
    record, revision = indexed()
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)
    unindexed = Record.objects.create(title="Not yet read", abstract="", pipeline_status=PipelineStatus.PUBLISHED)

    for n, (target, headers) in enumerate(((record, scoped(user, record)), (unindexed, scoped(user, unindexed)))):
        provider.requests.clear()
        provider.responses[:] = [reply("The passage could not be used.")] * 4
        response = ask(client, headers, f"selection-hidden-{n}", selected(target, revision))
        assert response.status_code == 201, response.text
        text = sent(provider)
        assert SELECTION_WITHDRAWN in text
        assert QUOTE not in text


def test_each_malformed_shape_is_the_one_named_refusal(api, runtime):
    client, holder = api
    holder["service"] = chat_service(runtime, answered())
    record, revision = indexed()
    headers = scoped(make_user("selection-shapes@cit.edu"), record)
    for n, bad in enumerate(({"page": 0}, {"page": "3"}, {"quote": "x" * 5000}, {"record_id": None},
                             {"manuscript_revision": "not-a-uuid"})):
        response = ask(client, headers, f"selection-shape-{n}", {**selected(record, revision), **bad})
        assert response.status_code == 422 and response.json() == {"status": "invalid_selection"}, bad
    assert stored_runs() == 0


def test_a_runtime_on_an_earlier_pin_refuses_a_selection_rather_than_drop_it(api, runtime):
    client, holder = api
    provider = recording(reply("Never sent."))
    holder["service"] = chat_service(runtime, provider, pin=PIN)
    record, revision = indexed()
    headers = scoped(make_user("selection-old-pin@cit.edu"), record)
    assert ask(client, headers, "selection-0008", selected(record, revision)).json() == {
        "status": "selection_unsupported"}
    assert stored_runs() == 0 and provider.requests == []


def test_a_paper_replaced_while_the_question_waits_is_looked_for_in_the_new_version(api, runtime):
    client, holder = api
    provider = answered()
    holder["service"] = service = chat_service(runtime, provider, drain=False)
    record, revision = indexed()
    headers = scoped(make_user("selection-replaced@cit.edu"), record)

    queued = ask(client, headers, "selection-0004", selected(record, revision))
    assert queued.status_code == 201, queued.text
    assert queued.json()["state"] == "queued"
    write_source(record, {3: [("Results", "Flooding fell after the levee was raised.")]}, "2")
    ChunkSet.objects.filter(record=record, is_active=True).update(source_revision=str(uuid.uuid4()))
    while run(service.run_next()):
        pass

    note = told(provider)
    assert (note["found_on_page"], note["version"]) == (False, "different")
    done = client.get(f"/api/v1/ai/runs/{queued.json()['id']}", headers=headers).json()
    assert done["state"] == "completed"
    # Replayed as selected on an earlier version.
    assert done["selection"]["current"] is False


def test_a_paper_revoked_while_the_question_waits_never_sends_its_text(api, runtime):
    client, holder = api
    provider = recording(*[reply("The passage could not be used.")] * 4)
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
    assert QUOTE not in text
    status = client.get(f"/api/v1/ai/runs/{queued.json()['id']}", headers=headers).json()
    assert status["selection"] == {"available": False}


def test_deleting_the_conversation_removes_the_selection(api, runtime):
    client, holder = api
    holder["service"] = chat_service(runtime, answered())
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
