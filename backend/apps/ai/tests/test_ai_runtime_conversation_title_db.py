"""A reader renames a Conversation (IR-1160) and downloads it as Markdown (IR-1167).

Both run on the AI runtime under the reader's own `reader_session` grant, on
real PostgreSQL: another reader's Conversation is "not found", and the
download is the reopen view rendered, nothing more.
"""

import uuid

import pytest

from apps.ai.grants import issue
from apps.records.models import PipelineStatus

from .corpus import make_user
from . import test_ai_runtime_conversation_search_db as search_db
from .test_ai_runtime_conversation_search_db import PATH, found, listing, revision_of, seed
from .test_ai_runtime_research_db import paper
from .test_ai_runtime_runs_db import LIMITS, as_reader, run, session
from ai.runs.executor import Citation, Result  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

# Fixtures of the search and runs tests, made visible to pytest here.
api = search_db.api
runtime = search_db.runtime
reader_api = search_db.reader_api


def follow_up(dsn, grant, key, conversation, question, answer):
    """A second completed Turn in `conversation`, committed the way a worker commits one."""
    store = RunStore(dsn)
    revision = run(store.reopen(grant, uuid.UUID(conversation)))["revision"]
    row, _ = run(store.admit(grant, key=key, question=question, conversation_id=uuid.UUID(conversation),
                             base_revision=revision, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=5))
    assert run(store.commit_final(row["id"], claim.fence, Result(answer=answer))) == "completed"


def rename(client, grant, conversation, title):
    return client.patch(f"{PATH}/{conversation}", json={"title": title}, headers=as_reader(grant))


def export(client, grant, conversation):
    return client.get(f"{PATH}/{conversation}/export", headers=as_reader(grant))


def titles(client, grant):
    return {c["id"]: c["title"] for c in listing(client, grant).json()["conversations"]}


def test_a_renamed_title_shows_in_the_list_and_on_reopen(reader_api, runtime):
    grant = session(make_user("rename-shown@cit.edu"))
    conversation = seed(runtime, grant, "rename-0001", "What did the flood study find?")
    assert titles(reader_api, grant)[conversation] == "What did the flood study find?"

    response = rename(reader_api, grant, conversation, "  Flood notes  ")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Flood notes"
    assert titles(reader_api, grant)[conversation] == "Flood notes"
    reopened = reader_api.get(f"{PATH}/{conversation}", headers=as_reader(grant))
    assert reopened.json()["title"] == "Flood notes"


def test_an_empty_title_restores_the_first_question(reader_api, runtime):
    grant = session(make_user("rename-empty@cit.edu"))
    conversation = seed(runtime, grant, "rename-0002", "Pond sampling methods")
    rename(reader_api, grant, conversation, "Ponds")
    for blank in ("", "   ", None):
        assert rename(reader_api, grant, conversation, blank).json()["title"] == "Pond sampling methods"
        assert titles(reader_api, grant)[conversation] == "Pond sampling methods"


def test_an_over_long_title_is_refused_and_the_old_one_kept(reader_api, runtime):
    grant = session(make_user("rename-long@cit.edu"))
    conversation = seed(runtime, grant, "rename-0003", "Gauge readings")
    rename(reader_api, grant, conversation, "Gauges")
    response = rename(reader_api, grant, conversation, "x" * 201)
    assert response.status_code == 422
    assert response.json() == {"status": "title_too_long", "max_length": 200}
    assert titles(reader_api, grant)[conversation] == "Gauges"
    assert rename(reader_api, grant, conversation, "y" * 200).status_code == 200
    assert titles(reader_api, grant)[conversation] == "y" * 200


def test_another_readers_conversation_is_not_found(reader_api, runtime):
    mine = session(make_user("rename-mine@cit.edu"))
    theirs = session(make_user("rename-theirs@cit.edu"))
    conversation = seed(runtime, theirs, "rename-0004", "Their question")
    assert rename(reader_api, mine, conversation, "Mine now").status_code == 404
    assert export(reader_api, mine, conversation).status_code == 404
    assert titles(reader_api, theirs)[conversation] == "Their question"


def test_paper_chat_renames_within_its_paper(reader_api, runtime):
    reader = make_user("rename-paper-scope@cit.edu")
    source = paper("Scoped paper", {1: [("Intro", "alpha")]})
    other = paper("Other paper", {1: [("Intro", "beta")]})
    scoped = issue.reader_session_grant(reader, source.pk).token
    elsewhere = issue.reader_session_grant(reader, other.pk).token
    conversation = seed(runtime, scoped, "rename-0005", "About this paper")
    assert rename(reader_api, scoped, conversation, "Paper notes").status_code == 200
    # Paper Chat's history shows the chosen title.
    assert titles(reader_api, scoped)[conversation] == "Paper notes"
    assert rename(reader_api, elsewhere, conversation, "Elsewhere").status_code == 404
    assert titles(reader_api, scoped)[conversation] == "Paper notes"


def test_a_deleted_conversation_cannot_be_renamed_or_downloaded(reader_api, runtime):
    grant = session(make_user("rename-deleted@cit.edu"))
    conversation = seed(runtime, grant, "rename-0006", "Short-lived")
    assert reader_api.delete(f"{PATH}/{conversation}", headers=as_reader(grant)).status_code == 204
    assert rename(reader_api, grant, conversation, "Ghost").status_code == 404
    assert export(reader_api, grant, conversation).status_code == 404


def test_the_download_holds_every_turn_in_order_with_numbered_sources(reader_api, runtime):
    grant = session(make_user("export-turns@cit.edu"))
    source = paper("Estuary salinity", {3: [("Methods", "titration at dawn")]})
    cited = Citation(record_id=source.pk, page=3, quote="titration at dawn", revision=revision_of(source))
    conversation = seed(runtime, grant, "export-0001", "Describe the methods",
                        "They titrated at dawn [1].", [cited])
    follow_up(runtime, grant, "export-0002", conversation, "How often?", "Monthly.")
    rename(reader_api, grant, conversation, "Estuary notes")

    response = export(reader_api, grant, conversation)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="Estuary-notes.md"'
    assert response.text == (
        "# Estuary notes\n\n"
        "## Question\n\nDescribe the methods\n\n"
        "## Answer\n\nThey titrated at dawn [1].\n\n"
        "### Sources\n\n"
        "[1] Estuary salinity, page 3\n\n> titration at dawn\n\n"
        "## Question\n\nHow often?\n\n"
        "## Answer\n\nMonthly.\n"
    )


def test_an_unreadable_answer_downloads_as_the_notice_without_sources(reader_api, runtime):
    grant = session(make_user("export-revoked@cit.edu"))
    source = paper("Private paper", {1: [("Methods", "secret protocol")]})
    cited = Citation(record_id=source.pk, page=1, quote="secret protocol", revision=revision_of(source))
    conversation = seed(runtime, grant, "export-0003", "What protocol?", "A secret one [1].", [cited])
    source.pipeline_status = PipelineStatus.DRAFT
    source.save(update_fields=["pipeline_status"])

    text = export(reader_api, grant, conversation).text
    assert "This answer is unavailable because its sources changed or are no longer readable." in text
    assert "secret" not in text.split("## Answer", 1)[1]
    assert "Sources" not in text and "Private paper" not in text


def test_the_download_carries_no_internal_state(reader_api, runtime):
    grant = session(make_user("export-clean@cit.edu"))
    conversation = seed(runtime, grant, "export-0004", "Plain question", "Plain answer.")
    text = export(reader_api, grant, conversation).text
    assert text == "# Plain question\n\n## Question\n\nPlain question\n\n## Answer\n\nPlain answer.\n"
    for internal in ("revision", "run_id", "reasoning", "plan", "tokens", "completed"):
        assert internal not in text


def test_rename_and_export_need_a_valid_reader_session(reader_api, runtime):
    grant = session(make_user("export-auth@cit.edu"))
    conversation = seed(runtime, grant, "export-0005", "Who may read this?")
    assert reader_api.get(f"{PATH}/{conversation}/export").status_code == 401
    assert reader_api.patch(f"{PATH}/{conversation}", json={"title": "x"}).status_code == 401
    assert found(listing(reader_api, grant)) == [conversation]
