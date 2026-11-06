"""A research tool fails part-way through a saved Conversation (IR-731).

The ticket's demonstration through the authenticated routes, on real
PostgreSQL under the restricted runtime login with Django-issued grants:
two permitted papers are compared, the second paper's read fails as a
dropped connection would, and the cited partial answer with its limitation
is the same live, reopened and in the reader protocol. The recording
provider proves the contract, never a vendor's behaviour.
"""

import json

import asyncpg
import pytest

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import as_reader, submit
from .test_ai_runtime_research_db import paper
from .test_ai_runtime_agent_loop_db import (  # noqa: E402
    FLOOD, POND, VALIDATION_CODES, agent_service, call, last_result, models, recording, reply, tools,
)
from ai.agent import assurance  # noqa: E402
from ai.research.tools import ResearchTools  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from .corpus import make_user  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime
api = runs_db.api

READER = "runs-reader-1"


@pytest.fixture
def pond_page_down(monkeypatch):
    """The pond paper's page read fails as a dropped connection would; every other read is real."""
    real = ResearchTools.read_page

    async def read_page(self, record_handle, page):
        if page == 2:
            raise asyncpg.ConnectionDoesNotExistError("connection was closed in the middle of operation")
        return await real(self, record_handle, page)

    monkeypatch.setattr(ResearchTools, "read_page", read_page)


def test_two_papers_compared_with_one_read_failing_keep_the_cited_finding_everywhere(
        api, runtime, pond_page_down):
    client, holder = api
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    grant = issue.reader_session_grant(make_user("agent-outage@cit.edu")).token
    seen = {}

    def read_both(payload):
        found = last_result(payload)
        handles = {p["title"]: p["paper"] for p in found["papers"]}
        seen["flood"] = next(p["passage"] for p in found["passages"] if p["paper"] == handles["Flood forecasting"])
        return tools(call("f", "read_page", paper=handles["Flood forecasting"], page=4),
                     call("p", "read_page", paper=handles["Pond sampling"], page=2))

    def compare(payload):
        flood_page, pond_page = [json.loads(m["content"]) for m in payload["messages"][-2:]]
        assert flood_page["status"] == "ok"
        # The failed read is unknown, not an empty page.
        assert pond_page == {"status": "unavailable", "reason": "tool_unavailable"}
        return reply(f"«Flood forecasting» trained a network on rainfall gauges and river levels "
                     f"[{seen['flood']}]. The pond paper's page could not be read, so the methods "
                     "cannot be compared yet.")

    provider = recording(tools(call("s", "search", query="water")), read_both, compare)
    holder["service"] = agent_service(runtime, provider)
    live = submit(client, grant, "agent-outage", "Compare the methods of the two water papers.").json()
    assert live["state"] == "completed", live
    assert [m["phase"] for m in models(live)] == ["gather", "gather", "gather"]

    expected = ("«Flood forecasting» trained a network on rainfall gauges and river levels [1]. "
                "The pond paper's page could not be read, so the methods cannot be compared yet.\n\n"
                + assurance.outage_limitation(["read_page"]))
    url = f"/api/v1/ai/conversations/{live['conversation_id']}"
    plain = client.get(url, headers=as_reader(grant))
    public = client.get(url, headers={**as_reader(grant), "X-IRIS-Protocol": READER})
    for reopened in (plain.json(), public.json()):
        [turn] = reopened["turns"]
        assert turn["kind"] == "answer" and turn["answer"] == expected
        [citation] = turn["citations"]
        assert (citation["record_id"], citation["page"]) == (flood.pk, 4)
    assert public.json()["runs"][0]["sources_available"] is True

    # Diagnostics never reach the reader: no reason or validation code, live or reopened.
    status = client.get(f"/api/v1/ai/runs/{live['id']}", headers={**as_reader(grant), "X-IRIS-Protocol": READER})
    for body in (plain.text, public.text, status.text):
        assert "tool_unavailable" not in body and "ConnectionDoesNotExist" not in body
        assert not any(code in body for code in (*VALIDATION_CODES, "outage_absence"))

    # A follow-up in the same Conversation still sees the shown order: the flood paper only.
    follow = recording(reply("Noted."))
    holder["service"] = agent_service(runtime, follow)
    assert submit(client, grant, "agent-outage-2", "Thanks.", conversation_id=live["conversation_id"],
                  base_revision=1).json()["state"] == "completed"
    state_note = next(m["content"] for m in follow.requests[0]["messages"]
                      if m["role"] == "user" and m["content"].startswith("[IRIS conversation state]"))
    assert [s["title"] for s in json.loads(state_note.split("] ", 1)[1])["shown"]] == ["Flood forecasting"]


def test_a_draft_turning_the_outage_into_an_absence_is_repaired_before_anything_is_saved(
        api, runtime, pond_page_down):
    client, holder = api
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    grant = issue.reader_session_grant(make_user("agent-outage-absence@cit.edu")).token
    seen = {}

    def read_pond(payload):
        # "water" is in both papers, so the search names both.
        found = last_result(payload)
        handles = {p["title"]: p["paper"] for p in found["papers"]}
        seen["flood"] = next(p["passage"] for p in found["passages"] if p["paper"] == handles["Flood forecasting"])
        return tools(call("p", "read_page", paper=handles["Pond sampling"], page=2))

    def absent(payload):
        return reply(f"Floods were forecast from gauges [{seen['flood']}]. No pond studies report methods.")

    def honest(payload):
        assert "No pond studies" in payload["messages"][-1]["content"]
        return reply(f"Floods were forecast from gauges [{seen['flood']}]. The pond paper could not be read.")

    provider = recording(tools(call("s", "search", query="water")), read_pond, absent, honest)
    holder["service"] = agent_service(runtime, provider)
    live = submit(client, grant, "agent-outage-absence", "How were floods and ponds studied?").json()
    assert live["state"] == "completed", live
    assert [m["phase"] for m in models(live)] == ["gather", "gather", "gather", "repair"]
    reopened = client.get(f"/api/v1/ai/conversations/{live['conversation_id']}", headers=as_reader(grant)).text
    assert "No pond studies" not in reopened and "could not be read" in reopened
