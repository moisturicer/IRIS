"""Revoked evidence leaves every saved surface of a delivered research Turn (IR-721, ADR-049 §15).

One integrated flow on real PostgreSQL under the restricted `iris_ai_runtime`
login with Django-issued grants: deliver a cited answer through the
authenticated run routes, then unpublish, delete or replace its source, and
reach the Conversation again as its owner, as another reader and through the
Django record page a citation opens. Direct reads under the restricted role,
pooled connections and a revocation between the provider's send and the
Turn's commit are exercised too. The recording provider proves these
contracts; it says nothing about paid capacity or human-reviewed quality.
"""

import json
import threading
import uuid

import pytest
from django.db import connection

from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .grant_support import owned_run, probe_login
from .test_ai_runtime_agent_loop_db import FLOOD, POND, agent_service, call, last_result, recording, reply, tools
from .test_ai_runtime_research_db import paper, write_source
from .test_ai_runtime_runs_db import as_reader, session
from .test_research_read_policy_db import read_as
from apps.ai.grants import issue  # noqa: E402
from apps.records.models import Record  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from core.permissions import ROLE_ADVISER, ROLE_RDCO, ROLE_STUDENT  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

api = runs_db.api
runtime = runs_db.runtime

PUBLIC = {"X-IRIS-Protocol": "runs-reader-1"}
SECRET = "water sampling secret method"
TITLE = "Private methods"
UNAVAILABLE = "no longer readable"


def reader(email, role=ROLE_STUDENT):
    """A reader and the headers of their authenticated protocol requests."""
    user = make_user(email, role)
    return user, {**as_reader(session(user)), **PUBLIC}


def ask(client, headers, key, question, **body):
    return client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": key},
                       json={"question": question, **body})


def surfaces(client, headers, delivered):
    """Every saved surface a reader reaches a delivered run through."""
    conversation, run_id = delivered["conversation_id"], delivered["id"]
    return {
        "reopen": client.get(f"/api/v1/ai/conversations/{conversation}", headers=headers),
        "status": client.get(f"/api/v1/ai/runs/{run_id}", headers=headers),
        "replay": client.get(f"/api/v1/ai/runs/{run_id}?after=0", headers=headers),
    }


def cite(payload):
    passage = last_result(payload)["passages"][0]
    return reply(f"Water sampling secret method [{passage['passage']}].")


def search(query):
    return tools(call("find", "search", query=query))


def unpublish(record):
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)


def soft_delete(record):
    Record.objects.filter(pk=record.pk).update(is_deleted=True)


def replace_source(record):
    write_source(record, {1: [("Methods", "a rewritten paragraph about something else")]}, "2")


CAUSES = {"unpublished": unpublish, "deleted": soft_delete, "source_replaced": replace_source}


def rows(sql, *params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


# --- A delivered answer, then revoked ----------------------------------------

@pytest.mark.parametrize("cause", sorted(CAUSES))
def test_revoked_evidence_leaves_every_saved_surface_for_the_owner_and_everyone_else(
        api, runtime, client_for, cause):
    client, holder = api
    source = paper(TITLE, {1: [("Methods", SECRET)]})
    holder["service"] = agent_service(runtime, recording(search("water"), cite))
    _, headers = reader(f"rev-owner-{cause}@cit.edu")
    delivered = ask(client, headers, f"rev-{cause}-0001", "Find methods").json()
    assert delivered["state"] == "completed"

    stranger, other = reader(f"rev-stranger-{cause}@cit.edu")
    resolver = client_for(stranger)
    before = surfaces(client, headers, delivered)
    assert {name: r.status_code for name, r in before.items()} == {"reopen": 200, "status": 200, "replay": 200}
    assert SECRET in before["reopen"].text.lower()
    assert before["replay"].json()["journal"]
    # The citation opens the paper for any reader of the public catalogue, today.
    assert resolver.get(f"/api/v1/records/{source.pk}/").status_code == 200

    CAUSES[cause](source)

    after = surfaces(client, headers, delivered)
    for name, response in after.items():
        assert response.status_code == 200, name
        assert SECRET not in response.text.lower() and TITLE not in response.text, name
    [turn] = after["reopen"].json()["turns"]
    assert turn["citations"] == [] and turn["facts"] == [] and UNAVAILABLE in turn["answer"]
    assert after["status"].json()["sources_available"] is False
    assert after["replay"].json()["journal"] == []

    # Another reader never reached the Conversation at all, before or after: a missing id, exactly.
    missing = surfaces(client, other, {"conversation_id": uuid.uuid4(), "id": uuid.uuid4()})
    for name, response in surfaces(client, other, delivered).items():
        assert response.status_code == 404, name
        assert response.json() == missing[name].json(), name

    # Resolving a citation through Django follows current access too: a removed paper is a missing one.
    gone = resolver.get(f"/api/v1/records/{source.pk}/")
    if cause == "source_replaced":
        assert gone.status_code == 200
    else:
        absent = resolver.get("/api/v1/records/999999999/")
        assert (gone.status_code, gone.json()) == (absent.status_code, absent.json())


def test_an_unrelated_finding_survives_in_its_own_conversation_and_a_dependent_follow_up_is_unavailable(api, runtime):
    client, holder = api
    flood = paper("Flood forecasting", {1: [("Methods", FLOOD)]})
    pond = paper("Pond sampling", {1: [("Methods", POND)]})

    def cite_flood(payload):
        return reply(f"Rainfall gauges and river water levels trained a network to forecast floods "
                     f"[{last_result(payload)['passages'][0]['passage']}].")

    def cite_pond(payload):
        return reply(f"Brackish water ponds were sampled weekly for tilapia growth "
                     f"[{last_result(payload)['passages'][0]['passage']}].")

    holder["service"] = agent_service(runtime, recording(
        search("rainfall"), cite_flood,      # Conversation 1, Turn 1: the flood paper
        search("tilapia"), cite_pond,        # Conversation 1, Turn 2: a follow-up on the pond paper
        search("tilapia"), cite_pond))       # Conversation 2: the pond paper alone
    _, headers = reader("rev-partial@cit.edu")
    first = ask(client, headers, "rev-partial-0001", "Which paper forecasts floods?").json()
    mixed = f"/api/v1/ai/conversations/{first['conversation_id']}"
    revision = client.get(mixed, headers=headers).json()["revision"]
    follow = ask(client, headers, "rev-partial-0002", "Which paper samples ponds?",
                 conversation_id=first["conversation_id"], base_revision=revision).json()
    alone = ask(client, headers, "rev-partial-0003", "Which paper samples ponds?").json()
    assert (follow["state"], alone["state"]) == ("completed", "completed")
    assert alone["conversation_id"] != first["conversation_id"]
    separate = f"/api/v1/ai/conversations/{alone['conversation_id']}"
    assert [len(t["citations"]) for t in client.get(mixed, headers=headers).json()["turns"]] == [1, 1]

    unpublish(flood)

    # The pond finding in a Conversation that never touched the revoked paper is kept whole.
    [kept] = client.get(separate, headers=headers).json()["turns"]
    assert "tilapia" in kept["answer"].lower()
    assert [c["record_id"] for c in kept["citations"]] == [pond.pk]
    # The Conversation that read the revoked paper is unavailable as a whole: its follow-up recalled
    # the paper's title as context, so nothing in it is shown that might rest on what was removed.
    withheld = client.get(mixed, headers=headers)
    for turn in withheld.json()["turns"]:
        assert UNAVAILABLE in turn["answer"] and turn["citations"] == [] and turn["facts"] == []
    assert "rainfall" not in withheld.text.lower() and "flood forecasting" not in withheld.text.lower()


def test_a_follow_up_after_revocation_sends_nothing_derived_from_the_revoked_turn(api, runtime):
    client, holder = api
    source = paper(TITLE, {1: [("Methods", SECRET)]})
    provider = recording(search("water"), cite, reply("General background."))
    holder["service"] = agent_service(runtime, provider)
    _, headers = reader("rev-follow@cit.edu")
    first = ask(client, headers, "rev-follow-0001", "Find methods").json()
    path = f"/api/v1/ai/conversations/{first['conversation_id']}"
    revision = client.get(path, headers=headers).json()["revision"]
    sent = len(provider.requests)

    unpublish(source)

    follow = ask(client, headers, "rev-follow-0002", "Anything else to add?",
                 conversation_id=first["conversation_id"], base_revision=revision).json()
    assert follow["state"] == "completed"
    payload = json.dumps(provider.requests[sent:], default=str).lower()
    assert "anything else to add" in payload
    # Neither the stored answer, the quoted text, the title, nor the earlier question rides along.
    for removed in ("secret method", TITLE.lower(), "find methods"):
        assert removed not in payload, removed
    reopened = json.dumps(client.get(path, headers=headers).json()).lower()
    assert "secret method" not in reopened


# --- Direct reads, pooled readers -------------------------------------------

def test_direct_restricted_role_reads_follow_the_revocation_for_every_kind_of_reader(grant_db):
    owner = make_user("rev-direct-owner@cit.edu", ROLE_STUDENT)
    adviser = make_user("rev-direct-adviser@cit.edu", ROLE_ADVISER)
    office = make_user("rev-direct-office@cit.edu", ROLE_RDCO)
    stranger = make_user("rev-direct-stranger@cit.edu", ROLE_STUDENT)
    source = paper(TITLE, {1: [("Methods", SECRET)]}, owner=owner)
    Record.objects.filter(pk=source.pk).update(adviser=adviser)
    readers = {"owner": owner, "adviser": adviser, "office": office, "stranger": stranger}
    tables = ("SELECT id FROM records_record WHERE id = %s",
              "SELECT id FROM ai_chunkset WHERE record_id = %s",
              "SELECT id FROM ai_documentchunk WHERE record_id = %s")

    def reads(conn, names):
        found = {}
        for name in names:
            grant = issue.reader_grant(readers[name], owned_run(readers[name])).token
            found[name] = {sql: read_as(conn, grant, "reader_run", sql, (source.pk,)) for sql in tables}
        return found

    with probe_login("iris_ai_runtime") as conn:
        # Published: every reader reads the paper, its chunk set and its text.
        assert all(rows_ for found in reads(conn, readers).values() for rows_ in found.values())

        unpublish(source)
        # A draft: its owner, its adviser and the office still read it; a stranger reads nothing,
        # in any table, so no dependent text or vector can be reached around the Record.
        for order in (list(readers), list(reversed(readers))):
            # One connection serves every reader in turn, in either order: nothing carries over.
            found = reads(conn, order)
            for name in ("owner", "adviser", "office"):
                assert all(found[name].values()), name
            assert not any(found["stranger"].values())
            for name, user in readers.items():
                assert bool(found[name][tables[0]]) == Record.objects.visible_to(user).filter(pk=source.pk).exists()

        soft_delete(source)
        # Deleted: nobody reads it, not even the office.
        assert not any(rows_ for found in reads(conn, readers).values() for rows_ in found.values())


# --- Revoked between the provider's send and the Turn's commit ---------------

def test_a_source_revoked_after_the_send_is_not_committed_as_a_cited_turn(api, runtime):
    client, holder = api
    source = paper(TITLE, {1: [("Methods", SECRET)]})

    def revoke_then_cite(payload):
        # The provider has been sent the permitted passage; access ends before the answer returns.
        def revoke():
            try:
                unpublish(source)
            finally:
                connection.close()

        worker = threading.Thread(target=revoke)
        worker.start()
        worker.join(10)
        assert not worker.is_alive()
        return cite(payload)

    holder["service"] = agent_service(runtime, recording(search("water"), revoke_then_cite))
    _, headers = reader("rev-race@cit.edu")
    delivered = ask(client, headers, "rev-race-0001", "Find methods").json()

    # No Turn carries the revoked text or a citation to it, and no reader surface shows it.
    assert rows("SELECT count(*) FROM iris_ai.turn WHERE conversation_id = %s AND answer ILIKE %s",
                delivered["conversation_id"], "%secret method%") == [(0,)]
    assert rows("SELECT count(*) FROM iris_ai.citation c JOIN iris_ai.turn t ON t.id = c.turn_id "
                "WHERE t.conversation_id = %s AND c.record_id = %s",
                delivered["conversation_id"], source.pk) == [(0,)]
    for name, response in surfaces(client, headers, delivered).items():
        assert SECRET not in response.text.lower(), name
