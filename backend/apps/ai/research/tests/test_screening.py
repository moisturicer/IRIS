import json
from dataclasses import replace

import pytest

from apps.ai.composition import CompositionRoot
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import LLMProvider
from apps.ai.providers.deadline import model_call_deadline
from apps.ai.research.budget import Spend
from apps.ai.research.results import Completeness, ToolStatus

from .helpers import call, start_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class ScreeningModel(LLMProvider):
    def __init__(self, failure=False):
        self.failure = failure
        self.requests = []

    def generate(self, system, user):
        self.requests.append(json.loads(user))
        if self.failure:
            raise TimeoutError("scripted outage")
        return json.dumps({"decisions": [
            {"record": row["record"], "decision": "include", "quote": row["title"]}
            for row in self.requests[-1]["records"]
        ]})


def screening_run(corpus, embedder, model, permits=lambda r: True, conversation=None):
    root = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                           llm=model, permits=permits)
    run = start_run(corpus["student"], root, conversation=conversation)
    for record in (corpus["public"], corpus["pond"]):
        run.ledger.add_record(record_id=record.pk, title=record.title, abstract=record.abstract)
    return run


def test_screening_keeps_each_decision_and_verbatim_quote(corpus, embedder):
    model = ScreeningModel()
    result = call(screening_run(corpus, embedder, model), "screen_records",
                  criterion="Is about aquaponics")
    assert result.status is ToolStatus.OK
    assert result.coverage.label is Completeness.SCREENED
    assert result.detail["rows"] == [
        {"record": "R1", "decision": "include", "quote": "Flood forecasting"},
        {"record": "R2", "decision": "include", "quote": "Tilapia ponds"},
    ]
    assert model.requests[0]["criterion"] == "Is about aquaponics"


def test_vendor_failure_keeps_every_paper_unassessed(corpus, embedder):
    result = call(screening_run(corpus, embedder, ScreeningModel(failure=True)),
                  "screen_records", criterion="Is about aquaponics")
    assert result.status is ToolStatus.DEGRADED
    assert result.detail["checked"] == 0
    assert result.detail["unassessed"] == 2
    assert [row["decision"] for row in result.detail["rows"]] == ["unassessed"] * 2


@pytest.mark.parametrize("reply", [
    "not json", '{"decisions":[]}',
    '{"decisions":[{"record":"R1","decision":"exclude","quote":"invented quote"}]}',
    '{"decisions":[{"record":"R99","decision":"include","quote":"Flood forecasting"}]}',
    '{"decisions":[{"record":"R1","decision":"include","quote":"Flood forecasting"},'
    '{"record":"R1","decision":"exclude","quote":"Flood forecasting"}]}',
    '{"decisions":[{"record":"R1","decision":"exclude","quote":""}]}',
])
def test_malformed_or_unsupported_judgements_never_become_exclusions(corpus, embedder, reply):
    result = call(screening_run(corpus, embedder, ScriptedLLM(reply)),
                  "screen_records", criterion="Is about aquaponics")
    assert result.detail["checked"] == 0
    assert result.detail["unassessed"] == 2
    assert all(row["decision"] == "unassessed" for row in result.detail["rows"])


def test_withheld_content_never_enters_screening_or_planner_requests(corpus, embedder):
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model, lambda r: r.pk != corpus["public"].pk)
    result = call(run, "screen_records", criterion="Is about aquaponics")
    sent = json.dumps(model.requests) + result.planner_message()
    assert "Flood forecasting" not in sent
    assert corpus["public"].abstract not in sent
    assert result.detail["checked"] == 1
    assert result.detail["unassessed"] == 1
    assert "reason" not in result.planner_message()
    assert result.detail["rows"] == [
        {"record": "R2", "decision": "include", "quote": "Tilapia ponds"}]


def test_a_gate_change_between_batches_is_checked_before_the_next_request(corpus, embedder, settings):
    settings.AI_SCREEN_BATCH_SIZE = 1
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model,
                        lambda r: r.pk == corpus["public"].pk or not model.requests)
    result = call(run, "screen_records", criterion="Is about aquaponics")
    assert [row["title"] for req in model.requests for row in req["records"]] == ["Flood forecasting"]
    assert result.detail["unassessed"] == 1
    assert "Tilapia ponds" not in result.planner_message()


def test_an_unreadable_or_out_of_scope_candidate_is_not_screened(corpus, embedder):
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model)
    draft = corpus["draft"]
    run.ledger.add_record(record_id=draft.pk, title=draft.title, abstract=draft.abstract)
    result = call(run, "screen_records", criterion="Is about aquaponics")
    assert result.detail["checked"] == 2
    assert "Secret" not in str(model.requests) + result.planner_message()


def test_a_model_cannot_supply_candidate_ids_or_a_new_scope(corpus, embedder):
    run = screening_run(corpus, embedder, ScreeningModel())
    for injected in ({"records": [corpus["draft"].pk]}, {"scope": None}, {"user": "other"}):
        result = call(run, "screen_records", criterion="Is about aquaponics", **injected)
        assert result.status is ToolStatus.REJECTED


def test_a_failed_batch_does_not_undo_the_successful_batch(corpus, embedder, settings):
    settings.AI_SCREEN_BATCH_SIZE = 1

    class SecondBatchFails(ScreeningModel):
        def generate(self, system, user):
            self.failure = bool(self.requests)
            return super().generate(system, user)

    model = SecondBatchFails()
    result = call(screening_run(corpus, embedder, model), "screen_records", criterion="Is about aquaponics")
    assert result.detail["checked"] == result.detail["unassessed"] == 1
    assert [row["decision"] for row in result.detail["rows"]] == ["include", "unassessed"]


def test_a_spent_prompt_budget_sends_no_screening_request(corpus, embedder):
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model)
    budget = replace(run.ctx.budget, max_prompt_tokens=1)
    run = replace(run, ctx=replace(run.ctx, budget=budget), spend=Spend(budget))
    result = call(run, "screen_records", criterion="Is about aquaponics")
    assert model.requests == []
    assert result.detail["unassessed"] == 2


def test_a_late_response_is_unassessed_and_no_next_batch_is_sent(corpus, embedder, settings):
    settings.AI_SCREEN_BATCH_SIZE = 1
    now = [0.0]

    class LateScreening(ScreeningModel):
        def generate(self, system, user):
            reply = super().generate(system, user)
            now[0] = 3.0
            return reply

    model = LateScreening()
    with model_call_deadline(2, clock=lambda: now[0]):
        result = call(screening_run(corpus, embedder, model), "screen_records", criterion="Is about aquaponics")
    assert len(model.requests) == 1
    assert result.detail["checked"] == 0
    assert result.detail["unassessed"] == 2


def test_a_cached_screening_result_is_withheld_when_the_gate_changes(corpus, embedder):
    allowed = [True]
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model, lambda r: allowed[0])
    first = call(run, "screen_records", criterion="Is about aquaponics")
    repeated = call(run, "screen_records", criterion="Is about aquaponics")
    assert first.detail == repeated.detail and repeated.duplicate
    allowed[0] = False
    refused = call(run, "screen_records", criterion="Is about aquaponics")
    assert refused.detail["unassessed"] == 2
    assert "Flood" not in refused.planner_message()
    assert "Tilapia" not in refused.planner_message()
    assert len(model.requests) == 1


def test_a_paper_changed_after_discovery_is_screened_from_its_current_text(corpus, embedder):
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model)
    first = call(run, "screen_records", criterion="Is about aquaponics")
    assert first.detail["rows"][0]["quote"] == "Flood forecasting"
    corpus["public"].title = "Flood methods updated"
    corpus["public"].save()
    refreshed = call(run, "screen_records", criterion="Is about aquaponics")
    assert refreshed.detail["rows"][0]["quote"] == "Flood methods updated"
    assert model.requests[-1]["records"][0]["title"] == "Flood methods updated"


def test_restrictions_applied_during_a_screening_call_sanitize_its_result(corpus, embedder):
    allowed = [True]

    class GateClosesDuringCall(ScreeningModel):
        def generate(self, system, user):
            reply = super().generate(system, user)
            allowed[0] = False
            return reply

    run = screening_run(corpus, embedder, GateClosesDuringCall(), lambda r: allowed[0])
    result = call(run, "screen_records", criterion="Is about aquaponics")
    assert result.evidence == ()
    assert result.detail["rows"] == result.detail["possible_duplicates"] == []
    assert result.detail["checked"] == 0
    assert result.detail["unassessed"] == 2
    assert "Flood" not in result.planner_message()


def test_a_paper_edited_during_screening_is_unassessed_in_the_result(corpus, embedder):
    class PaperChangesDuringCall(ScreeningModel):
        def generate(self, system, user):
            reply = super().generate(system, user)
            corpus["public"].title = "Updated study"
            corpus["public"].save()
            return reply

    result = call(screening_run(corpus, embedder, PaperChangesDuringCall()),
                  "screen_records", criterion="Is about aquaponics")
    assert result.detail["checked"] == result.detail["unassessed"] == 1
    assert "Flood forecasting" not in result.planner_message()
