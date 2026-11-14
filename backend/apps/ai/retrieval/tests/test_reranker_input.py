"""What the reranker reads, per IR-1125 arm. No database: the gate is off."""

import pytest

from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk, Retriever
from apps.ai.retrieval.reranker_input import (
    AI_LABEL,
    ai_description,
    changes_expected,
    reranker_text,
)
from apps.ai.retrieval.reranking import RerankingRetriever

TRAIL = ("Results", "Figure 3")


def chunk(chunk_id=1, content="", embedded="", kinds=("narrative",), trail=TRAIL):
    return RetrievedChunk(
        chunk_id=chunk_id, record_id=1, record_title="Paper", content=content,
        context_path=trail, source_page=3, score=0.5,
        embedded=embedded, element_kinds=kinds,
    )


UNCAPTIONED = chunk(
    1, "", "Results > Figure 3\n\nA bar chart of accuracy by model.", ("image",)
)
CAPTIONED = chunk(
    2, "Figure 2: Loss curves.", "Results > Figure 3\n\nFigure 2: Loss curves.\nTwo falling lines.",
    ("image",),
)
PROSE = chunk(3, "The model converges.", "Results > Figure 3\n\nThe model converges.")


def test_today_reads_only_what_the_paper_printed():
    assert reranker_text(UNCAPTIONED, "today") == ""
    assert reranker_text(CAPTIONED, "today") == "Figure 2: Loss curves."


def test_embedded_reads_the_vector_text_for_every_chunk():
    assert reranker_text(PROSE, "embedded") == PROSE.embedded
    assert reranker_text(UNCAPTIONED, "embedded") == UNCAPTIONED.embedded


def test_fallback_reads_embedded_text_only_where_shown_text_is_blank():
    assert reranker_text(UNCAPTIONED, "fallback") == UNCAPTIONED.embedded
    assert reranker_text(CAPTIONED, "fallback") == CAPTIONED.content
    assert reranker_text(PROSE, "fallback") == PROSE.content


def test_described_labels_the_ai_text_and_adds_nothing_to_prose():
    assert reranker_text(UNCAPTIONED, "described") == f"{AI_LABEL} A bar chart of accuracy by model."
    assert reranker_text(CAPTIONED, "described") == (
        f"Figure 2: Loss curves.\n\n{AI_LABEL} Two falling lines."
    )
    assert reranker_text(PROSE, "described") == PROSE.content


def test_a_description_is_recovered_only_from_a_lone_figure():
    assert ai_description(UNCAPTIONED) == "A bar chart of accuracy by model."
    mixed = chunk(4, "Text.", "Results > Figure 3\n\nText.\nMore.", ("narrative", "image"))
    assert ai_description(mixed) == ""
    drifted = chunk(5, "Other caption", "Results > Figure 3\n\nCaption\nDesc", ("image",))
    assert ai_description(drifted) == ""


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        reranker_text(PROSE, "caption")
    with pytest.raises(ValueError):
        RerankingRetriever(_Fixed([]), reads="caption")


def test_which_chunks_each_arm_is_meant_to_change():
    assert not changes_expected(PROSE, "fallback")
    assert changes_expected(UNCAPTIONED, "fallback")
    assert not changes_expected(PROSE, "described")
    assert changes_expected(CAPTIONED, "described")
    assert changes_expected(PROSE, "embedded")


class _Fixed(Retriever):
    def __init__(self, passages):
        self.passages = tuple(passages)
        self.calls = 0

    def retrieve(self, question, user, limit=20):
        self.calls += 1
        return RetrievalResult(passages=self.passages[:limit])


class _Recording(Reranker):
    transmits_externally = False

    def __init__(self):
        self.seen = []

    def rerank(self, query, candidates):
        self.seen.append(list(candidates))
        return [
            RerankedCandidate(index=i, text=t, score=float(-i))
            for i, t in enumerate(candidates)
        ]


@pytest.mark.parametrize("reads, cited", [
    ("today", {2, 3}),
    ("embedded", {1, 2, 3}),
    ("described", {1, 2, 3}),
    ("fallback", {1, 2, 3}),
])
def test_only_today_leaves_an_uncaptioned_figure_uncitable(reads, cited):
    reranker = _Recording()
    retriever = RerankingRetriever(
        _Fixed([UNCAPTIONED, CAPTIONED, PROSE]), reranker=reranker,
        policy_enabled=False, reads=reads,
    )

    result = retriever.retrieve("accuracy?", user=None, limit=10)

    assert {p.chunk_id for p in result.passages} == cited
    assert reranker.seen[0] == [
        reranker_text(c, reads) for c in (UNCAPTIONED, CAPTIONED, PROSE)
        if reranker_text(c, reads).strip()
    ]
    # Readers still see the shown text whatever the reranker read.
    assert {p.content for p in result.passages} <= {"", CAPTIONED.content, PROSE.content}


def test_a_cached_ranking_is_never_served_to_another_mode():
    cache = {}
    first, second = _Recording(), _Recording()
    inner = _Fixed([CAPTIONED, PROSE])
    RerankingRetriever(inner, reranker=first, policy_enabled=False, cache=cache).retrieve("q", None)
    RerankingRetriever(
        inner, reranker=second, policy_enabled=False, cache=cache, reads="embedded"
    ).retrieve("q", None)

    assert second.seen, "the embedded arm reused today's ranking"


def test_voyage_reports_the_tokens_it_billed():
    from apps.ai.providers.voyage import VoyageReranker

    reranker = VoyageReranker(model="rerank-test", transport=lambda path, payload: {
        "data": [{"index": 0, "relevance_score": 0.9}], "usage": {"total_tokens": 42},
    })
    reranker.rerank("q", ["only passage"])

    assert reranker.last_usage == 42
