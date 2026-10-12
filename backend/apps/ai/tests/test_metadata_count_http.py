"""IR-543: exact metadata counts through the authenticated Ask IRIS boundary.

Every case is driven through `POST /ai/ask/` and the `/ai/ask/stream/` `done`
event, then the reopened conversation, with the composition root overridden.
The count is a database aggregate, so the answer model, the screening model
and the network are all forbidden: any of them being reached fails the test.
"""

import json
import re

import httpx
import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import Conversation
from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.providers.ports import LLMProvider
from apps.ai.routing.router import LANES
from apps.records.models import (
    Classification, PSCEDClassification, Record, RecordOwner, RecordType,
)
from core.enums import PipelineStatus
from core.permissions import ROLE_KTTO

from .corpus import make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

ENDPOINTS = ["ai-ask", "ai-ask-stream"]
EVERYTHING = "How many papers are in the repository?"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("a metadata count reached the network")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def lane(settings, monkeypatch):
    settings.AI_RESEARCH_LANE = "on"
    probabilities = {name: 0.01 for name in LANES}
    probabilities["count"] = 0.95
    probabilities["injection"] = 0.01
    # One scripted answer per ask: the model consumes its script as it is read.
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers",
                        lambda **kwargs: (ScriptedDecisionModel(probabilities), None))


def add(embedder, space, title, *, year=None, classification=None, psced=None,
        record_type=None, is_ip=False, status=PipelineStatus.PUBLISHED, owner=None):
    record = make_record(title=title, text=f"{title} body text", embedder=embedder,
                         space=space, status=status, owner=owner)
    Record.objects.filter(pk=record.pk).update(
        year_completed=year, is_ip=is_ip,
        classification=(Classification.objects.get_or_create(name=classification)[0]
                        if classification else None),
        psced=(PSCEDClassification.objects.get_or_create(name=psced)[0] if psced else None),
        record_type=(RecordType.objects.get_or_create(name=record_type)[0]
                     if record_type else None),
    )
    return record


def ask(client, endpoint, question, *, root, conversation=None, **options):
    payload = {"question": question, **options}
    if conversation is not None:
        payload["conversation_id"] = conversation.pk
    with use_composition_root(root):
        response = client.post(reverse(endpoint), payload, format="json")
    assert response.status_code == 200
    if endpoint == "ai-ask":
        return response.json()
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        if block:
            name, data = block.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return next(data for name, data in events if name == "done")


class _NeverCalled(LLMProvider):
    def __init__(self, task):
        self.task = task

    def generate(self, system, user):
        pytest.fail(f"a metadata count called the {self.task} model")

    def stream(self, system, user):
        pytest.fail(f"a metadata count called the {self.task} model")


@pytest.fixture
def make_root(embedder, monkeypatch):
    def build(refused=()):
        root = CompositionRoot(
            embedder=embedder, reranker=ScriptedReranker(), llm=ScriptedLLM(),
            permits=lambda record: record.title not in refused,
        )

        def forbidden(task):
            # A conversation builds its resolver up front; building is free, so
            # the model it holds is what must never be called.
            return _NeverCalled(task)

        monkeypatch.setattr(root, "llm_for", forbidden)
        return root
    return build


def number(body):
    return body["listing"]["count"]["total"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_every_record_is_counted_once_across_owner_and_chunk_joins(
    endpoint, lane, embedder, space, client_for, make_root
):
    reader, other, third = (make_user(f"{n}@cit.edu") for n in ("reader", "other", "third"))
    joined = add(embedder, space, "Owned By Everyone", owner=reader)
    RecordOwner.objects.create(record=joined, user=other)
    RecordOwner.objects.create(record=joined, user=third)
    # A second chunk set's worth of chunks must not multiply the Record.
    chunk = joined.chunk_sets.get().chunks.get()
    for sequence in (1, 2):
        chunk.pk = None
        chunk.sequence, chunk.text_hash = sequence, f"extra{sequence}"
        chunk.save()
    add(embedder, space, "Plain One")
    add(embedder, space, "Plain Two")

    body = ask(client_for(reader), endpoint, EVERYTHING, root=make_root())

    assert body["routing"]["lane"] == "count"
    assert number(body) == 3
    assert body["listing"]["completeness"] == "exact_count"
    assert body["listing"]["records"] == []
    assert "**3 records**" in body["answer"]
    assert "not of unique scholarly works" in body["answer"]
    assert body["listing"]["count"]["unit"].endswith("not unique scholarly works")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_drafts_and_other_readers_hidden_records_are_never_counted(
    endpoint, lane, embedder, space, client_for, make_root
):
    reader, other = make_user("reader@cit.edu"), make_user("other@cit.edu")
    add(embedder, space, "Public")
    add(embedder, space, "Mine Draft", status=PipelineStatus.DRAFT, owner=reader)
    add(embedder, space, "Their Draft", status=PipelineStatus.DRAFT, owner=other)

    body = ask(client_for(reader), endpoint, EVERYTHING, root=make_root())

    assert number(body) == 1
    assert body["listing"]["count"]["visible"] == 1
    assert "Their Draft" not in json.dumps(body)


def test_staff_and_a_student_get_the_same_catalogue_count(
    lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Public")
    add(embedder, space, "A Draft", status=PipelineStatus.DRAFT, owner=make_user("o@cit.edu"))
    student = make_user("student@cit.edu")
    staff = make_user("staff@cit.edu", ROLE_KTTO)

    counts = {number(ask(client_for(u), "ai-ask", EVERYTHING, root=make_root()))
              for u in (student, staff)}

    assert counts == {1}


@pytest.mark.parametrize("question,expected,wording", [
    ("How many records are classified as Software Engineering?", 2,
     "classification is Software Engineering"),
    ("How many papers are in the PSCED area Agriculture?", 1, "PSCED area is Agriculture"),
    ("How many theses are there?", 2, "record type is Thesis"),
    ("How many papers were completed in 2023?", 2, "completion year is 2023"),
    ("How many papers were completed between 2021 and 2022?", 1,
     "completion year is 2021 to 2022"),
    ("How many papers were completed since 2022?", 3, "2022 or later"),
    ("How many papers were completed after 2022?", 2, "2023 or later"),
    ("How many papers were completed before 2023?", 1, "2022 or earlier"),
    ("How many IP records are there?", 1, "flagged as intellectual property"),
    ("How many Software Engineering theses were completed in 2023?", 1,
     "classification is Software Engineering and record type is Thesis"),
])
def test_supported_predicates_count_exactly_and_state_themselves(
    question, expected, wording, lane, embedder, space, client_for, make_root
):
    add(embedder, space, "A", year=2023, classification="Software Engineering",
        record_type="Thesis", is_ip=True)
    add(embedder, space, "B", year=2022, classification="Software Engineering",
        psced="Agriculture", record_type="Project")
    add(embedder, space, "C", year=2023, classification="Networks", record_type="Thesis")
    add(embedder, space, "D", year=None, classification="Networks", record_type="Project")
    # Not in the catalogue, so never part of any count.
    add(embedder, space, "E", year=2023, classification="Software Engineering",
        record_type="Thesis", status=PipelineStatus.DRAFT)
    RecordOwner.objects.create(record=Record.objects.get(title="E"), user=make_user("r@cit.edu"))

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask", question, root=make_root())

    assert number(body) == expected
    assert wording in body["listing"]["count"]["predicate"]
    assert str(expected) in body["answer"]
    assert body["listing"]["count"]["population"] == "published records you can see"


def test_year_predicate_reports_records_with_no_completion_year(
    lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Dated", year=2023)
    add(embedder, space, "Undated One")
    add(embedder, space, "Undated Two")

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask",
               "How many papers were completed in 2023?", root=make_root())

    assert number(body) == 1
    assert body["listing"]["count"]["undated"] == 2
    assert "2 records with no completion year" in body["answer"]


def test_an_empty_result_is_zero_and_claims_no_absence(
    lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Only", year=2020)

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask",
               "How many papers were completed in 1999?", root=make_root())

    assert number(body) == 0
    assert body["answer"].startswith("No records you can see match")
    assert "says nothing about records outside your view" in body["answer"]
    assert "ai_assessable" in body["listing"]["count"]


def test_an_empty_catalogue_counts_zero(lane, client_for, make_root):
    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask", EVERYTHING, root=make_root())

    assert number(body) == 0
    assert body["listing"]["count"]["visible"] == 0


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_ai_ineligible_records_are_counted_and_described_without_a_title(
    endpoint, lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Readable One")
    add(embedder, space, "Readable Two")
    add(embedder, space, "Withheld Paper")
    add(embedder, space, "Secret Draft", status=PipelineStatus.DRAFT,
        owner=make_user("other@cit.edu"))

    body = ask(client_for(make_user("reader@cit.edu")), endpoint, EVERYTHING,
               root=make_root(refused={"Withheld Paper"}))

    assert number(body) == 3
    assert body["listing"]["count"]["ai_assessable"] == 2
    assert body["listing"]["count"]["not_ai_assessable"] == 1
    assert "2 of these can be read by AI and 1 cannot" in body["answer"]
    wire = json.dumps(body)
    assert "Withheld Paper" not in wire and "Secret Draft" not in wire
    # Only the asker's own visible set is described; no hidden total leaks.
    assert "4" not in re.findall(r"\b\d+\b", body["answer"])


def test_possible_duplicate_works_are_flagged_but_counted_separately(
    lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Flood Prediction with Gauges")
    add(embedder, space, "flood  prediction with gauges!")
    add(embedder, space, "Something Else")

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask", EVERYTHING, root=make_root())

    assert number(body) == 3
    assert body["listing"]["count"]["possible_duplicate_titles"] == 1
    assert "may be the same work" in body["answer"]


@pytest.mark.parametrize("question,fragment", [
    ("How many papers were published in 2023?", "not a publication year"),
    ("How many papers are there by publication year 2022?", "not a publication year"),
    ("How many papers were completed last year?", "relative date"),
    ("How many papers were authored by Maria Santos?", "does not store"),
])
def test_unsupported_fields_are_declined_by_name_with_no_count(
    question, fragment, lane, embedder, space, client_for, make_root
):
    add(embedder, space, "A", year=2023)

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask", question, root=make_root())

    assert body["answer"] is None
    assert fragment in body["message"]
    assert "listing" not in body
    assert not re.search(r"\*\*|\bmatch", body["message"])


def test_publication_year_is_never_answered_from_completion_year(
    lane, embedder, space, client_for, make_root
):
    add(embedder, space, "Completed 2023", year=2023)

    body = ask(client_for(make_user("reader@cit.edu")), "ai-ask",
               "How many papers were published in 2023?", root=make_root())

    assert "completion year" in body["message"]
    assert body["answer"] is None and "listing" not in body


def test_a_topic_question_is_not_taken_for_a_metadata_count(
    lane, embedder, space, client_for, make_root, monkeypatch
):
    add(embedder, space, "Flooding Study")
    root = make_root()
    # Topic counting needs the screening model; reaching it is the point here.
    asked = []
    monkeypatch.setattr(root, "llm_for", lambda task: asked.append(task) or ScriptedLLM())

    ask(client_for(make_user("reader@cit.edu")), "ai-ask",
        "How many papers are about flooding?", root=root)

    assert asked, "a topic question must still go to the screening workflow"


def test_the_transcript_keeps_the_original_snapshot_after_permissions_change(
    lane, embedder, space, client_for, make_root
):
    reader = make_user("reader@cit.edu")
    first = add(embedder, space, "First")
    add(embedder, space, "Second")
    client = client_for(reader)
    conversation = Conversation.objects.create(user=reader)

    original = ask(client, "ai-ask", EVERYTHING, root=make_root(), conversation=conversation)
    assert number(original) == 2

    # The catalogue changes: one Record leaves it.
    Record.objects.filter(pk=first.pk).update(pipeline_status=PipelineStatus.DRAFT)

    reopened = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()
    turn, = reopened["turns"]
    assert turn["listing"] == original["listing"]
    assert turn["listing"]["count"]["total"] == 2

    fresh = ask(client, "ai-ask", EVERYTHING, root=make_root())
    assert number(fresh) == 1
    assert fresh["listing"]["count"]["snapshot"] >= original["listing"]["count"]["snapshot"]
    # The original turn still reads as it did when it was asked.
    first_turn = client.get(
        reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][0]
    assert first_turn["listing"]["count"]["total"] == 2


def test_a_reader_who_loses_access_gets_the_smaller_count_on_the_next_ask(
    lane, embedder, space, client_for, make_root
):
    reader = make_user("reader@cit.edu")
    add(embedder, space, "Public")
    kept = add(embedder, space, "Withdrawn Later")
    client = client_for(reader)

    assert number(ask(client, "ai-ask", EVERYTHING, root=make_root())) == 2
    Record.objects.filter(pk=kept.pk).update(is_deleted=True)
    assert number(ask(client, "ai-ask", EVERYTHING, root=make_root())) == 1


def test_paper_chat_scope_is_never_widened_by_a_count_question(
    lane, embedder, space, client_for, make_root
):
    reader = make_user("reader@cit.edu")
    scoped = add(embedder, space, "The Scoped Paper")
    add(embedder, space, "Another Paper")
    conversation = Conversation.objects.create(user=reader, record=scoped)

    body = ask(client_for(reader), "ai-ask", EVERYTHING,
               root=_passage_root(embedder), conversation=conversation)

    assert body["routing"]["lane"] == "passage"
    assert "listing" not in body


def _passage_root(embedder):
    return CompositionRoot(embedder=embedder, reranker=ScriptedReranker(), llm=ScriptedLLM(),
                           permits=lambda record: True)
