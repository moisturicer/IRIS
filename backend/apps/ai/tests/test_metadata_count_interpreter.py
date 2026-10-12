"""IR-543: which questions are metadata counts, decided without a database or a model."""

import pytest

from apps.ai.research.metadata_count import Declined, Predicate, interpret

pytestmark = pytest.mark.django_required

TAXONOMIES = {
    "classification": ["Software Engineering", "Networks", "Engineering"],
    "psced": ["Agriculture"],
    "record_type": ["Thesis", "Project", "Proposal"],
}


def read(question):
    return interpret(question, lambda: TAXONOMIES)


@pytest.mark.parametrize("question", [
    "How many papers are about flooding?",
    "How many papers on neural networks are there?",
    "How many studies use convolutional networks?",
    "How many papers are about software engineering?",
    "What are the papers on flooding?",
    "aquaponics",
    "How many papers are about budget planning?",
    "How many papers study college students?",
    "How many papers cover recent advances in flood control?",
    "How many papers were published on climate change?",
    "How many papers study the library?",
    "How many papers on intellectual property are there?",
    "How many papers on Networks are there?",
    "How many papers did Maria Santos author?",
])
def test_topics_and_non_counts_are_left_to_the_topic_workflow(question):
    assert read(question) is None


def test_no_taxonomy_query_is_made_for_a_question_that_cannot_be_a_count():
    def boom():
        raise AssertionError("taxonomies were read")

    assert interpret("aquaponics", boom) is None
    assert isinstance(interpret("How many papers were published in 2023?", boom), Declined)


def test_the_whole_repository_has_no_filter():
    verdict = read("How many papers are in the repository?")
    assert isinstance(verdict, Predicate)
    assert dict(verdict.filters) == {}
    assert verdict.conditions == ()
    assert verdict.describe("published records you can see") == "all published records you can see"


def test_the_longest_name_wins_over_a_name_it_contains():
    verdict = read("How many Software Engineering papers are there?")
    assert dict(verdict.filters) == {"classification": "Software Engineering"}


def test_plural_and_irregular_plural_forms_match():
    assert dict(read("How many theses are there?").filters) == {"record_type": "Thesis"}
    assert dict(read("How many projects are there?").filters) == {"record_type": "Project"}


@pytest.mark.parametrize("question,filters", [
    ("How many papers were completed in 2023?", {"year_from": 2023, "year_to": 2023}),
    ("How many papers were completed between 2020 and 2022?", {"year_from": 2020, "year_to": 2022}),
    ("How many papers were completed between 2022 and 2020?", {"year_from": 2020, "year_to": 2022}),
    ("How many papers were completed since 2021?", {"year_from": 2021}),
    ("How many papers were completed after 2021?", {"year_from": 2022}),
    ("How many papers were completed before 2021?", {"year_to": 2020}),
    ("How many IP records are there?", {"is_ip": True}),
    ("How many theses in Networks were completed in 2020?",
     {"record_type": "Thesis", "classification": "Networks",
      "year_from": 2020, "year_to": 2020}),
])
def test_year_ip_and_combined_predicates(question, filters):
    assert dict(read(question).filters) == filters


@pytest.mark.parametrize("question,fragment", [
    ("How many papers were published in 2023?", "not a publication year"),
    ("How many papers have a publication date in 2021?", "not a publication year"),
    ("How many papers were completed last year?", "relative date"),
    ("How many papers were completed in recent years?", "relative date"),
    ("How many papers were authored by Maria Santos?", "does not store"),
    ("How many records from 2020?", "could mean that year only"),
    ("How many papers were completed in 2020 or 2021?", "more than one year"),
    ("How many papers were completed after 2020 and before 2023?", "more than one year"),
    ("How many papers did each author write?", "does not store"),
    ("How many papers are advised by Dr Cruz?", "does not store"),
    ("How many Networks and Software Engineering papers?", "more than one"),
])
def test_unsupported_questions_are_declined_by_name(question, fragment):
    verdict = read(question)
    assert isinstance(verdict, Declined)
    assert fragment in verdict.text


def test_a_plain_published_papers_question_is_not_a_publication_year_question():
    verdict = read("How many published papers are there?")
    assert isinstance(verdict, Predicate)
    assert dict(verdict.filters) == {}


def test_place_words_are_removed_only_after_a_preposition():
    for question in ("How many papers are in the repository?",
                     "How many papers are in IRIS?",
                     "How many records of the collection are there?"):
        assert isinstance(read(question), Predicate)
    assert read("How many papers study the archive?") is None


def test_a_scoped_count_says_so_and_pluralises():
    from apps.ai.research.metadata_count import SCOPED_POPULATION, MetadataCount, render

    result = MetadataCount(total=1, visible=1, ai_assessable=1, duplicate_groups=0, undated=None,
                           predicate=Predicate({}, ()), population=SCOPED_POPULATION,
                           snapshot="2026-10-12T00:00:00+00:00")
    text, listing = render(result)
    assert "**1 record** matches" in text
    assert "limited to the paper this chat is about" in text
    assert listing["count"]["population"] == SCOPED_POPULATION
