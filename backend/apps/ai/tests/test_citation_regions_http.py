"""Citation regions on the wire (IR-334).

Rectangles that stop at the database are useless to a reader — this is the
assertion that they actually reach `/ai/ask/`, `/ai/search/` and a replayed
Conversation, in the shape a viewer draws directly (fractions of the page,
never PDF points).
"""

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    LETTER,
    ask,
    make_record,
    make_user,
    root_with,
    search,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: A box occupying the left half of the first quarter of a letter page.
FIGURE_BOX = {"page": 4, "left": 61.2, "top": 79.2, "right": 306.0, "bottom": 158.4}


class RegionsOnAskTests:
    def test_a_citation_carries_the_normalized_region_of_its_chunk(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder,
            space=space, bboxes=[FIGURE_BOX], page_sizes=LETTER,
        )

        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        body = response.json()
        (citation,) = body["citations"]
        assert citation["record_id"] == flood.pk
        assert citation["regions"] == [
            {"page": 4, "left": 0.1, "top": 0.1, "right": 0.5, "bottom": 0.2}
        ]

    def test_a_chunk_with_no_recovered_rectangle_carries_an_empty_list(
        self, embedder, space, client_for
    ):
        """Not an error, and not omitted: the page still opens (`page` is
        still sent), a viewer just draws nothing on it."""
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space,
        )

        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        (citation,) = response.json()["citations"]
        assert citation["regions"] == []
        assert citation["page"] == 4


class RegionsOnSearchTests:
    def test_a_search_result_carries_its_regions_too(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder,
            space=space, bboxes=[FIGURE_BOX], page_sizes=LETTER,
        )

        with use_composition_root(root_with(embedder=embedder)):
            response = search(client_for(reader), FLOOD_QUESTION)

        (result,) = response.json()["results"]
        assert result["regions"] == [
            {"page": 4, "left": 0.1, "top": 0.1, "right": 0.5, "bottom": 0.2}
        ]


class RegionsSurviveConversationReplayTests:
    def test_a_replayed_turn_re_resolves_regions_the_same_way_it_re_resolves_quotes(
        self, embedder, space, client_for
    ):
        """ADR-019: a stored citation is a pointer, re-resolved on every read.
        Regions are resolved from the *live* chunk, not carried on the row,
        so they must survive that trip too."""
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder,
            space=space, bboxes=[FIGURE_BOX], page_sizes=LETTER,
        )
        client = client_for(reader)

        with use_composition_root(root_with(embedder=embedder)):
            conv = client.post(
                reverse("ai-conversations"), {"title": ""}, format="json"
            ).json()
            ask(client, FLOOD_QUESTION, conversation_id=conv["id"])

        replayed = client.get(reverse("ai-conversation-detail", args=[conv["id"]])).json()
        (turn,) = replayed["turns"]
        (citation,) = turn["citations"]
        assert citation["regions"] == [
            {"page": 4, "left": 0.1, "top": 0.1, "right": 0.5, "bottom": 0.2}
        ]
