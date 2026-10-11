import pytest

from apps.ai.research.results import Completeness
from apps.ai.models.conversation import Conversation
from apps.records.models import RecordOwner, RecordVersion
from core.enums import VersionCause
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.tests.corpus import make_record
from apps.ai.providers.fakes import ScriptedLLM

from .test_screening import ScreeningModel, screening_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def test_a_topic_count_screens_every_visible_paper_and_words_the_computed_count(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    model = ScreeningModel()
    result = topic_count(screening_run(corpus, embedder, model), "Is about aquaponics")
    assert result.coverage.label is Completeness.SCREENED
    assert result.detail["total"] == 2
    assert result.detail["checked"] == 2
    assert result.detail["unassessed"] == 0
    assert result.detail["wording"] == "2 matched out of 2 checked; 0 could not be assessed."
    assert len(result.detail["matches"]) == 2
    assert "Secret flood draft" not in str(model.requests)


def test_owners_versions_and_chunks_do_not_multiply_a_topic_match(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    record = corpus["public"]
    RecordOwner.objects.create(record=record, user=corpus["student"])
    RecordOwner.objects.create(record=record, user=corpus["other"])
    for number, cause in ((1, VersionCause.SUBMISSION), (2, VersionCause.REVISION)):
        RecordVersion.objects.create(record=record, number=number, cause=cause)
    result = topic_count(screening_run(corpus, embedder, ScreeningModel()), "Is about aquaponics")
    assert result.detail["total"] == 2


def test_gated_visible_papers_are_unassessed_without_individual_reasons(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    model = ScreeningModel()
    result = topic_count(screening_run(corpus, embedder, model, lambda r: False), "Is about aquaponics")
    assert not model.requests
    assert result.detail["wording"] == "0 matched out of 0 checked; 2 could not be assessed."
    assert result.detail["rows"] == []
    assert result.detail["matches"] == []
    assert "Secret" not in result.planner_message()
    assert "Flood" not in result.planner_message()


def test_paper_chat_cannot_screen_or_count_a_second_paper(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    chat = Conversation.objects.create(user=corpus["student"], record=corpus["pond"])
    model = ScreeningModel()
    result = topic_count(screening_run(corpus, embedder, model, conversation=chat), "Is about aquaponics")
    assert result.detail["total"] == 1
    assert "Flood forecasting" not in str(model.requests)


def test_above_the_ceiling_the_count_reports_only_screened_matches(corpus, embedder, settings):
    from apps.ai.research.workflows import topic_count

    settings.AI_SCREEN_MAX_RECORDS = 1
    result = topic_count(screening_run(corpus, embedder, ScreeningModel()), "rainfall flooding neural network")
    assert result.coverage.label is Completeness.MATCHES_FOUND
    assert result.coverage.truncated
    assert result.detail["total"] == result.detail["checked"] == 1
    assert result.detail["wording"].endswith(" These are matches found; other visible papers were not checked.")


def test_possible_duplicate_titles_are_flagged_but_never_merged(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    corpus["pond"].title = "FLOOD: forecasting!"
    corpus["pond"].save()
    result = topic_count(screening_run(corpus, embedder, ScreeningModel()), "Is about aquaponics")
    assert result.detail["total"] == 2
    assert result.detail["possible_duplicates"] == [
        {"records": ["R1", "R2"], "reasons": ["normalized_title"]}]


def test_ranked_candidates_refused_by_the_gate_still_count_as_unassessed(corpus, embedder, settings):
    from apps.ai.research.workflows import topic_count

    settings.AI_SCREEN_MAX_RECORDS = 1
    model = ScreeningModel()
    result = topic_count(screening_run(corpus, embedder, model, lambda r: False),
                         "rainfall flooding neural network")
    assert not model.requests
    assert result.detail["total"] == result.detail["checked"] == 0
    assert result.detail["unassessed"] == 1
    assert result.coverage.label is Completeness.MATCHES_FOUND


def test_the_same_criterion_on_a_different_candidate_set_is_screened_again(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    corpus["pond"].year_completed = 2023
    corpus["pond"].save()
    model = ScreeningModel()
    run = screening_run(corpus, embedder, model)
    first = topic_count(run, "Is about aquaponics", filters={"year_to": 2021})
    second = topic_count(run, "Is about aquaponics", filters={"year_from": 2023})
    assert first.detail["total"] == second.detail["total"] == 1
    assert first.detail["matches"][0]["quote"] == "Flood forecasting"
    assert second.detail["matches"][0]["quote"] == "Tilapia ponds"


def test_a_small_corpus_is_screened_beyond_the_retrievers_top_ten(corpus, embedder, space, settings):
    from apps.ai.research.workflows import topic_count

    for index in range(10):
        make_record(title=f"Unrelated study {index}", text="orchids gardens", embedder=embedder, space=space)
    settings.AI_SCREEN_MAX_RECORDS = 12
    settings.AI_SCREEN_BATCH_SIZE = 3
    model = ScreeningModel()
    result = topic_count(screening_run(corpus, embedder, model), "Is about aquaponics")
    assert result.detail["total"] == result.detail["checked"] == 12
    assert result.coverage.label is Completeness.SCREENED
    assert [len(req["records"]) for req in model.requests] == [3, 3, 3, 3]


def test_only_included_papers_contribute_to_the_topic_count(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    model = ScriptedLLM('{"decisions":['
                        '{"record":"R1","decision":"exclude","quote":"Flood forecasting"},'
                        '{"record":"R2","decision":"include","quote":"Tilapia ponds"}]}')
    result = topic_count(screening_run(corpus, embedder, model), "Is about aquaponics")
    assert result.detail["total"] == 1
    assert result.detail["checked"] == 2
    assert result.detail["matches"] == [
        {"record": "R2", "decision": "include", "quote": "Tilapia ponds"}]


def test_near_identical_record_vectors_are_flagged_without_merging_records(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    seed = RecordEmbedding.objects.get(record=corpus["public"])
    RecordEmbedding.objects.filter(record=corpus["pond"]).update(
        embedding=seed.embedding, model_name=seed.model_name)
    result = topic_count(screening_run(corpus, embedder, ScreeningModel()), "Is about aquaponics")
    assert result.detail["total"] == 2
    assert result.detail["possible_duplicates"] == [
        {"records": ["R1", "R2"], "reasons": ["record_embedding"]}]


def test_vectors_from_different_models_never_flag_duplicates(corpus, embedder):
    from apps.ai.research.workflows import topic_count

    seed = RecordEmbedding.objects.get(record=corpus["public"])
    RecordEmbedding.objects.filter(record=corpus["pond"]).update(
        embedding=seed.embedding, model_name="different-model")
    result = topic_count(screening_run(corpus, embedder, ScreeningModel()), "Is about aquaponics")
    assert result.detail["possible_duplicates"] == []
