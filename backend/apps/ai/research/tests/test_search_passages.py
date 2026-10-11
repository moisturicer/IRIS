"""The tool foundation through `search_passages` (IR-509, ADR-038 §2, §5)."""

import json

import pytest
from django.core.management import call_command

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models.chunk import DocumentChunk
from apps.ai.models.conversation import Conversation
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.research.results import Completeness, ToolStatus
from apps.ai.tests.corpus import FLOOD_TEXT, make_user
from core.permissions import ROLE_KTTO

from .helpers import TOOLS, TOPIC, call, record_ids, registry_logs, root, sent_to_planner, start_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _search(run, **arguments):
    return call(run, "search_passages", **{"query": TOPIC, **arguments})


# -- visibility -----------------------------------------------------------


def test_a_student_never_receives_another_users_draft(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    result = _search(run)
    assert corpus["draft"].pk not in record_ids(result)
    assert "Secret" not in result.planner_message()
    assert corpus["draft"].pk not in {r.record_id for r in run.ledger.records()}


def test_an_owner_never_receives_someone_elses_draft(corpus, embedder, space):
    from apps.ai.tests.corpus import make_record
    from core.enums import PipelineStatus

    third = make_user("third@cit.edu")
    hidden = make_record(title="Third draft", text=FLOOD_TEXT, embedder=embedder,
                         space=space, status=PipelineStatus.DRAFT, owner=third)
    run = start_run(corpus["other"], root(embedder))
    found = record_ids(_search(run))
    assert corpus["draft"].pk in found and hidden.pk not in found


def test_the_owner_and_office_staff_receive_the_draft(corpus, embedder):
    for user in (corpus["other"], make_user("ktto@cit.edu", ROLE_KTTO)):
        assert corpus["draft"].pk in record_ids(_search(start_run(user, root(embedder))))


def test_a_handle_set_narrows_and_never_widens(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    handles = {e.record_id: e.handle for e in _search(run).evidence if e.kind == "record"}
    pond = handles[corpus["pond"].pk]
    assert record_ids(_search(run, records=[pond])) == {corpus["pond"].pk}


def test_paper_chat_scope_cannot_be_widened(corpus, embedder):
    student, public, pond = corpus["student"], corpus["public"], corpus["pond"]
    chat = Conversation.objects.create(user=student, record=pond)
    run = start_run(student, root(embedder), conversation=chat)
    assert run.ctx.scope_record_id == pond.pk

    # A handle for another paper, as if issued, still reaches nothing.
    other = run.ledger.add_record(record_id=public.pk, title=public.title, abstract="")
    assert record_ids(_search(run)) == {pond.pk}
    assert _search(run, records=[other.handle]).evidence == ()


# -- the disclosure gate --------------------------------------------------


def test_the_gate_runs_before_a_passage_reaches_the_planner(corpus, embedder):
    withheld = corpus["public"]
    asked = []

    def permits(record):
        asked.append(record.pk)
        return record.pk != withheld.pk

    run = start_run(corpus["student"], root(embedder, permits))
    sent = sent_to_planner(_search(run))
    assert withheld.pk in asked
    assert "Flood forecasting" not in sent and FLOOD_TEXT not in sent
    assert "Tilapia ponds" in sent


def test_a_withheld_record_is_indistinguishable_from_an_absent_one(corpus, embedder):
    # k=1, so a gap left by the withheld record would show as an empty result.
    refuse = corpus["public"].pk
    gated = _search(start_run(corpus["student"], root(embedder, lambda r: r.pk != refuse)), k=1)
    corpus["public"].delete()
    absent = _search(start_run(corpus["student"], root(embedder)), k=1)

    assert (gated.status, gated.coverage) == (absent.status, absent.coverage)
    assert record_ids(gated) == record_ids(absent) == {corpus["pond"].pk}


def test_the_default_gate_withholds_everything(corpus, embedder):
    run = start_run(corpus["student"], CompositionRoot(embedder=embedder, reranker=ScriptedReranker()))
    assert _search(run).evidence == ()


# -- handles and the closed set -------------------------------------------


@pytest.mark.parametrize("handle", ["R9", "E1", "R0", "r1"])
def test_an_unissued_handle_is_rejected_and_logged(corpus, embedder, handle, caplog):
    run = start_run(corpus["student"], root(embedder))
    _search(run)
    with registry_logs(caplog):
        result = _search(run, records=[handle])
    assert result.status is ToolStatus.REJECTED and result.evidence == ()
    logged = [r for r in caplog.records if r.getMessage() == "research tool call rejected"]
    assert logged and logged[0].run_id == run.ctx.run_id


def test_a_raw_database_id_is_rejected(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    _search(run)
    pk = corpus["public"].pk
    assert _search(run, records=[str(pk)]).status is ToolStatus.REJECTED
    assert TOOLS.call(run, "search_passages", {"query": TOPIC, "records": [pk]}).status \
        is ToolStatus.REJECTED


def test_context_fields_cannot_be_set_by_an_argument(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    for extra in ({"user": 1}, {"scope_record_id": 1}, {"permits": True}, {"record_id": 1}):
        assert _search(run, **extra).status is ToolStatus.REJECTED


def test_a_name_outside_the_set_is_rejected(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    assert TOOLS.call(run, "delete_records", "{}").status is ToolStatus.REJECTED


# -- the result -----------------------------------------------------------


def test_the_result_is_a_labelled_sample_with_handles_text_and_page(corpus, embedder):
    result = _search(start_run(corpus["student"], root(embedder)))
    assert result.coverage.label is Completeness.SAMPLE

    passage = next(e for e in result.evidence if e.kind == "passage")
    chunk = DocumentChunk.objects.get(pk=passage.chunk_id)
    assert passage.pointer == (chunk.record_id, chunk.pk, "cFlood forecasting")

    message = json.loads(result.planner_message())
    assert message["coverage"]["label"] == "sample"
    first = message["passages"][0]
    assert (first["handle"], first["text"], first["page"]) == ("E1", FLOOD_TEXT, 4)
    assert first["record"].startswith("R")


def test_a_passage_the_ledger_dropped_is_not_returned(corpus, embedder):
    run = start_run(corpus["student"], root(embedder), max_ledger_passages=1)
    result = _search(run, k=2)
    passages = [e for e in result.evidence if e.kind == "passage"]
    assert len(passages) == result.coverage.returned == 1
    assert all(run.ledger.holds(e) for e in result.evidence)


# -- budget and duplicates ------------------------------------------------


def test_a_repeated_call_is_a_counted_duplicate(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    first = _search(run)
    again = TOOLS.call(run, "search_passages", {"query": TOPIC})
    assert again.duplicate and not first.duplicate
    assert (again.status, again.evidence, again.coverage) == (
        first.status, first.evidence, first.coverage)
    assert json.loads(again.planner_message())["duplicate"] is True
    assert run.spend.tool_calls == 2


def test_the_registry_stops_at_the_call_limits(corpus, embedder):
    run = start_run(corpus["student"], root(embedder), max_calls_per_subtask=2, max_tool_calls=3)
    assert _search(run).status is ToolStatus.OK
    assert TOOLS.call(run, "nope", "{}").status is ToolStatus.REJECTED
    refused = _search(run, k=1)
    assert (refused.status, refused.reason) == (ToolStatus.REFUSED, "budget:max_calls_per_subtask")

    run.spend.begin_subtask()
    assert _search(run, k=2).status is ToolStatus.OK
    run.spend.begin_subtask()
    assert _search(run, k=3).reason == "budget:max_tool_calls"


def test_the_registry_stops_at_the_wall_clock(corpus, embedder):
    result = _search(start_run(corpus["student"], root(embedder), wall_clock_seconds=0.0))
    assert (result.status, result.reason) == (ToolStatus.REFUSED, "budget:wall_clock_seconds")


# -- the command ----------------------------------------------------------


def test_the_command_runs_a_search_as_a_user(corpus, embedder, capsys):
    with use_composition_root(root(embedder)):
        call_command(
            "run_research_tool", "--user", "student@cit.edu",
            "--call", f'search_passages={{"query": "{TOPIC}"}}',
        )
    out = capsys.readouterr().out
    assert "Flood forecasting" in out and "Secret" not in out
    assert '"label": "sample"' in out and "E1 -> (" in out
