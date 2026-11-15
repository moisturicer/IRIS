"""A reader lists and searches their own past Conversations (IR-1161).

The AI runtime's list route on real PostgreSQL, under the reader's own
`reader_session` grant: no other reader's or deleted Conversation, no answer
text whose sources the reader can no longer read, and Paper Chat stays inside
its paper.
"""

import pytest
from django.db import connection

from apps.ai.grants import issue
from apps.ai.models import ChunkSet
from apps.records.models import PipelineStatus

from .corpus import make_user
from .test_ai_runtime_research_db import paper
from .test_ai_runtime_runs_db import ScriptedExecutor, api, as_reader, runtime, service, session, submit  # noqa: F401
from ai.runs.executor import Citation, Result  # noqa: E402  (the runs test puts the repo root on sys.path)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

PATH = "/api/v1/ai/conversations"


def ask(api, runtime, grant, key, question, answer="An answer.", citations=()):
    client, holder = api
    holder["service"] = service(runtime, ScriptedExecutor(Result(answer=answer, citations=tuple(citations))))
    response = submit(client, grant, key, question)
    assert response.status_code == 201 and response.json()["state"] == "completed"
    return response.json()["conversation_id"]


def listing(api, grant, **params):
    client, _ = api
    return client.get(PATH, params=params, headers=as_reader(grant))


def found(response):
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()["conversations"]]


def revision_of(record):
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    return f"{chunk_set.pk}:{chunk_set.extraction_hash}"


def test_a_phrase_from_an_old_question_or_answer_finds_its_conversation(api, runtime):
    grant = session(make_user("search-phrase@cit.edu"))
    flood = ask(api, runtime, grant, "search-0001", "Flood forecasting methods", "Gauges fed a recurrent network.")
    pond = ask(api, runtime, grant, "search-0002", "Pond sampling", "Water was sampled monthly.")

    assert found(listing(api, grant)) == [pond, flood]
    assert found(listing(api, grant, q="recurrent network")) == [flood]
    assert found(listing(api, grant, q="POND SAMPLING")) == [pond]
    assert found(listing(api, grant, q="sampled monthly")) == [pond]
    assert found(listing(api, grant, q="  recurrent  ")) == [flood]
    # A wildcard is text, not a pattern that matches everything.
    assert found(listing(api, grant, q="%")) == []
    assert found(listing(api, grant, q="never asked")) == []
    # A blank box is no search.
    assert found(listing(api, grant, q="   ")) == [pond, flood]


def test_an_entry_carries_only_its_id_title_and_last_activity(api, runtime):
    grant = session(make_user("search-shape@cit.edu"))
    ask(api, runtime, grant, "shape-0001", "What did the paper find?", "Secret answer text.")
    body = listing(api, grant).json()
    assert body["next"] is None
    (entry,) = body["conversations"]
    assert set(entry) == {"id", "title", "updated_at"}
    assert entry["title"] == "What did the paper find?"
    assert "Secret answer text." not in listing(api, grant).text


def test_results_never_include_another_readers_or_a_deleted_conversation(api, runtime):
    client, _ = api
    mine = session(make_user("search-mine@cit.edu"))
    theirs = session(make_user("search-theirs@cit.edu"))
    ask(api, runtime, theirs, "other-0001", "Salinity of the estuary", "Brackish.")
    gone = ask(api, runtime, mine, "mine-0001", "Salinity in the delta", "Brackish too.")
    kept = ask(api, runtime, mine, "mine-0002", "Salinity of the lake", "Fresh.")

    assert sorted(found(listing(api, mine, q="salinity"))) == sorted([gone, kept])
    assert client.delete(f"{PATH}/{gone}", headers=as_reader(mine)).status_code == 204
    assert found(listing(api, mine, q="salinity")) == [kept]
    assert found(listing(api, mine)) == [kept]
    assert found(listing(api, mine, q="Brackish")) == []


def test_an_answer_whose_sources_are_no_longer_readable_is_not_matched_on_its_text(api, runtime):
    grant = session(make_user("search-revoked@cit.edu"))
    source = paper("Private methods", {1: [("Methods", "titration at dawn")]})
    cited = Citation(record_id=source.pk, page=1, quote="titration at dawn", revision=revision_of(source))
    conversation = ask(api, runtime, grant, "revoked-0001", "Describe the methods",
                       "They used a secret salinity protocol.", [cited])
    assert found(listing(api, grant, q="salinity protocol")) == [conversation]

    source.pipeline_status = PipelineStatus.DRAFT
    source.save(update_fields=["pipeline_status"])

    assert found(listing(api, grant, q="salinity protocol")) == []
    # The reader's own question is still theirs to find.
    assert found(listing(api, grant, q="Describe the methods")) == [conversation]
    assert found(listing(api, grant)) == [conversation]


def test_paper_chat_search_stays_within_that_papers_conversations(api, runtime):
    reader = make_user("search-scope@cit.edu")
    first = paper("First paper", {1: [("Intro", "alpha")]})
    second = paper("Second paper", {1: [("Intro", "beta")]})
    general = session(reader)
    on_first = issue.reader_session_grant(reader, first.pk).token
    on_second = issue.reader_session_grant(reader, second.pk).token

    in_first = ask(api, runtime, on_first, "scope-0001", "Tracer dye in the first paper")
    in_second = ask(api, runtime, on_second, "scope-0002", "Tracer dye in the second paper")
    outside = ask(api, runtime, general, "scope-0003", "Tracer dye across the corpus")

    assert found(listing(api, on_first, q="tracer dye")) == [in_first]
    assert found(listing(api, on_first)) == [in_first]
    assert found(listing(api, on_second, q="tracer dye")) == [in_second]
    # An unscoped grant lists only what it can continue; a paper's Conversation needs that paper's grant.
    assert found(listing(api, general, q="tracer dye")) == [outside]
    assert sorted(found(listing(api, general))) == [outside]


def test_the_list_pages_past_fifty_without_a_gap_or_a_repeat(api, runtime):
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

    first = listing(api, grant)
    assert first.status_code == 200
    page = first.json()
    assert len(page["conversations"]) == 50 and page["next"]
    rest = listing(api, grant, before=page["next"]).json()
    assert len(rest["conversations"]) == 2 and rest["next"] is None
    assert [c["id"] for c in page["conversations"] + rest["conversations"]] == expected

    # Paging walks smaller pages the same way.
    seen, cursor_ = [], None
    while True:
        part = listing(api, grant, limit=20, **({"before": cursor_} if cursor_ else {})).json()
        seen += [c["id"] for c in part["conversations"]]
        cursor_ = part["next"]
        if not cursor_:
            break
    assert seen == expected


def test_paging_composes_with_search(api, runtime):
    grant = session(make_user("search-paging-q@cit.edu"))
    asked = [ask(api, runtime, grant, f"pageq-{n:04d}", f"Gauge reading {n}") for n in range(3)]
    ask(api, runtime, grant, "pageq-other", "Unrelated topic")
    first = listing(api, grant, q="gauge reading", limit=2).json()
    assert [c["id"] for c in first["conversations"]] == [asked[2], asked[1]] and first["next"]
    last = listing(api, grant, q="gauge reading", limit=2, before=first["next"]).json()
    assert [c["id"] for c in last["conversations"]] == [asked[0]] and last["next"] is None


def test_a_bad_page_size_or_cursor_is_refused(api, runtime):
    grant = session(make_user("search-bad@cit.edu"))
    assert listing(api, grant, limit=0).status_code == 422
    assert listing(api, grant, limit=101).status_code == 422
    assert listing(api, grant, before="not-a-cursor").status_code == 422
    assert listing(api, grant, q="x" * 201).status_code == 422


def test_listing_needs_a_valid_reader_session(api, runtime):
    client, _ = api
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=as_reader("irg1.k1.forged.sig")).status_code == 401
    reader = make_user("search-wrong-purpose@cit.edu")
    wrong = issue.record_read_grant(reader).token
    assert client.get(PATH, headers=as_reader(wrong)).status_code == 401


def test_nothing_found_is_an_empty_list(api, runtime):
    grant = session(make_user("search-empty@cit.edu"))
    assert listing(api, grant).json()["conversations"] == []
    assert listing(api, grant, q="anything").json() == {
        "protocol": "runs-reader-1", "conversations": [], "next": None,
    }
