"""Candidate selection stays inside reader access, explicit filters and conversation scope (IR-546)."""

import pytest

from apps.ai.models import Conversation
from apps.ai.research.listing import select_candidates

from .helpers import root, start_run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def ids(selection):
    return set(selection.ids)


def test_selection_reads_only_what_the_reader_can_see(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    chosen = ids(select_candidates(run, "flooding"))
    assert corpus["public"].pk in chosen and corpus["pond"].pk in chosen
    assert corpus["draft"].pk not in chosen


def test_an_explicit_filter_narrows_the_candidates(corpus, embedder):
    run = start_run(corpus["student"], root(embedder))
    assert ids(select_candidates(run, "flooding", filters={"classification": "Engineering"})
               ) == {corpus["public"].pk}
    assert ids(select_candidates(run, "flooding", filters={"year_from": 2022})) == set()
    assert ids(select_candidates(run, "flooding", filters={"year_to": 2021})) == {corpus["public"].pk}


def test_a_conversation_scope_is_never_widened(corpus, embedder):
    conversation = Conversation.objects.create(user=corpus["student"], record=corpus["pond"])
    run = start_run(corpus["student"], root(embedder), conversation=conversation)
    assert ids(select_candidates(run, "flooding")) == {corpus["pond"].pk}
