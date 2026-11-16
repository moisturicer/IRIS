"""A reader searches and pages their own past Conversations (IR-1161).

The runtime's list route on real PostgreSQL under the reader's own
`reader_session` grant: no other reader's or deleted Conversation, no answer
text whose sources the reader can no longer read, and Paper Chat stays inside
its paper.
"""

import uuid

import pytest
from django.db import connection

from apps.ai.grants import issue
from apps.ai.models import ChunkSet
from apps.records.models import PipelineStatus

from .corpus import make_user
from .test_ai_runtime_research_db import paper
from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import LIMITS, ScriptedExecutor, as_reader, run, service, session
from ai.runs.executor import Citation, Result  # noqa: E402  (the runs test puts the repo root on sys.path)
from ai.runs.store import RunStore  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

PATH = "/api/v1/ai/conversations"
PUBLIC = {"X-IRIS-Protocol": "runs-reader-1"}

# Fixtures of the runs tests, made visible to pytest here.
api = runs_db.api
runtime = runs_db.runtime


class ReaderExecutor(ScriptedExecutor):
    """Named like the agent, so the reader protocol is served; the list never runs it."""
    name = "agent"


def seed(runtime, grant, key, question, answer="An answer.", citations=()):
    """A completed Turn in a new Conversation, written the way a worker commits one."""
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key=key, question=question, conversation_id=None,
                             base_revision=None, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=5))
    state = run(store.commit_final(row["id"], claim.fence, Result(answer=answer, citations=tuple(citations))))
    assert state == "completed"
    return str(row["conversation_id"])


@pytest.fixture
def reader_api(api, runtime):
    client, holder = api
    holder["service"] = service(runtime, ReaderExecutor())
    return client


def listing(client, grant, **params):
    return client.get(PATH, params=params, headers={**as_reader(grant), **PUBLIC})


def found(response):
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()["conversations"]]


def revision_of(record):
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    return f"{chunk_set.pk}:{chunk_set.extraction_hash}"


def test_a_phrase_from_an_old_question_or_answer_finds_its_conversation(reader_api, runtime):
    grant = session(make_user("search-phrase@cit.edu"))
    flood = seed(runtime, grant, "search-0001", "Flood forecasting methods", "Gauges fed a recurrent network.")
    pond = seed(runtime, grant, "search-0002", "Pond sampling", "Water was sampled monthly.")

    assert found(listing(reader_api, grant)) == [pond, flood]
    assert found(listing(reader_api, grant, q="recurrent network")) == [flood]
    assert found(listing(reader_api, grant, q="POND SAMPLING")) == [pond]
    assert found(listing(reader_api, grant, q="sampled monthly")) == [pond]
    assert found(listing(reader_api, grant, q="  recurrent  ")) == [flood]
    # A wildcard is text, not a pattern that matches everything.
    assert found(listing(reader_api, grant, q="%")) == []
    assert found(listing(reader_api, grant, q="never asked")) == []
    # A blank box is no search.
    assert found(listing(reader_api, grant, q="   ")) == [pond, flood]


def test_an_entry_carries_its_title_and_never_the_answer(reader_api, runtime):
    grant = session(make_user("search-shape@cit.edu"))
    seed(runtime, grant, "shape-0001", "What did the paper find?", "Secret answer text.")
    response = listing(reader_api, grant, q="secret")
    body = response.json()
    assert body["next"] is None
    (entry,) = body["conversations"]
    assert entry["title"] == "What did the paper find?"
    assert "Secret answer text." not in response.text


def test_results_never_include_another_readers_or_a_deleted_conversation(reader_api, runtime):
    mine = session(make_user("search-mine@cit.edu"))
    theirs = session(make_user("search-theirs@cit.edu"))
    seed(runtime, theirs, "other-0001", "Salinity of the estuary", "Brackish.")
    gone = seed(runtime, mine, "mine-0001", "Salinity in the delta", "Brackish too.")
    kept = seed(runtime, mine, "mine-0002", "Salinity of the lake", "Fresh.")

    assert sorted(found(listing(reader_api, mine, q="salinity"))) == sorted([gone, kept])
    run(RunStore(runtime).delete_conversation(mine, uuid.UUID(gone)))
    assert found(listing(reader_api, mine, q="salinity")) == [kept]
    assert found(listing(reader_api, mine)) == [kept]
    assert found(listing(reader_api, mine, q="Brackish")) == []


def test_an_answer_whose_sources_are_no_longer_readable_is_not_matched_on_its_text(reader_api, runtime):
    grant = session(make_user("search-revoked@cit.edu"))
    source = paper("Private methods", {1: [("Methods", "titration at dawn")]})
    cited = Citation(record_id=source.pk, page=1, quote="titration at dawn", revision=revision_of(source))
    conversation = seed(runtime, grant, "revoked-0001", "Describe the methods",
                        "They used a secret salinity protocol.", [cited])
    assert found(listing(reader_api, grant, q="salinity protocol")) == [conversation]

    source.pipeline_status = PipelineStatus.DRAFT
    source.save(update_fields=["pipeline_status"])

    assert found(listing(reader_api, grant, q="salinity protocol")) == []
    # The reader's own question is still theirs to find.
    assert found(listing(reader_api, grant, q="Describe the methods")) == [conversation]


def test_paper_chat_search_stays_within_that_papers_conversations(reader_api, runtime):
    reader = make_user("search-scope@cit.edu")
    first = paper("First paper", {1: [("Intro", "alpha")]})
    second = paper("Second paper", {1: [("Intro", "beta")]})
    on_first = issue.reader_session_grant(reader, first.pk).token
    on_second = issue.reader_session_grant(reader, second.pk).token

    in_first = seed(runtime, on_first, "scope-0001", "Tracer dye in the first paper")
    in_second = seed(runtime, on_second, "scope-0002", "Tracer dye in the second paper")

    assert found(listing(reader_api, on_first, q="tracer dye")) == [in_first]
    assert found(listing(reader_api, on_second, q="tracer dye")) == [in_second]
    assert found(listing(reader_api, on_first)) == [in_first]


def test_the_list_pages_past_fifty_without_a_gap_or_a_repeat(reader_api, runtime):
    reader = make_user("search-paging@cit.edu")
    grant = session(reader)
    with connection.cursor() as cursor:
        # 52 Conversations, two sharing one timestamp so the cursor must break the tie by id.
        cursor.execute(
            """INSERT INTO iris_ai.conversation (id, reader_id, created_at)
               SELECT gen_random_uuid(), %s, now() - (least(n, 51) || ' minutes')::interval
                 FROM generate_series(1, 52) n""", [reader.pk])
        cursor.execute("SELECT id::text FROM iris_ai.conversation ORDER BY created_at DESC, id DESC")
        expected = [row[0] for row in cursor.fetchall()]

    page = listing(reader_api, grant).json()
    assert len(page["conversations"]) == 50 and page["next"]
    rest = listing(reader_api, grant, before=page["next"]).json()
    assert len(rest["conversations"]) == 2 and rest["next"] is None
    assert [c["id"] for c in page["conversations"] + rest["conversations"]] == expected

    seen, cursor_ = [], None
    while True:
        part = listing(reader_api, grant, limit=20, **({"before": cursor_} if cursor_ else {})).json()
        seen += [c["id"] for c in part["conversations"]]
        cursor_ = part["next"]
        if not cursor_:
            break
    assert seen == expected


def test_paging_composes_with_search(reader_api, runtime):
    grant = session(make_user("search-paging-q@cit.edu"))
    asked = [seed(runtime, grant, f"pageq-{n:04d}", f"Gauge reading {n}") for n in range(3)]
    seed(runtime, grant, "pageq-other", "Unrelated topic")
    first = listing(reader_api, grant, q="gauge reading", limit=2).json()
    assert [c["id"] for c in first["conversations"]] == [asked[2], asked[1]] and first["next"]
    last = listing(reader_api, grant, q="gauge reading", limit=2, before=first["next"]).json()
    assert [c["id"] for c in last["conversations"]] == [asked[0]] and last["next"] is None


def test_a_bad_page_size_or_cursor_is_refused(reader_api, runtime):
    grant = session(make_user("search-bad@cit.edu"))
    assert listing(reader_api, grant, limit=0).status_code == 422
    assert listing(reader_api, grant, limit=101).status_code == 422
    assert listing(reader_api, grant, before="not-a-cursor").status_code == 422
    assert listing(reader_api, grant, q="x" * 201).status_code == 422


def test_listing_needs_a_valid_reader_session(reader_api, runtime):
    client = reader_api
    assert client.get(PATH, headers=PUBLIC).status_code == 401
    assert client.get(PATH, headers={**as_reader("irg1.k1.forged.sig"), **PUBLIC}).status_code == 401
    wrong = issue.record_read_grant(make_user("search-wrong-purpose@cit.edu")).token
    assert client.get(PATH, headers={**as_reader(wrong), **PUBLIC}).status_code == 401


def test_nothing_found_is_an_empty_list(reader_api, runtime):
    grant = session(make_user("search-empty@cit.edu"))
    assert listing(reader_api, grant, q="anything").json() == {
        "protocol": "runs-reader-1", "conversations": [], "next": None,
    }
