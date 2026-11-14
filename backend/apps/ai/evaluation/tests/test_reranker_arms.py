"""IR-1125's paired comparison: shared candidates, free identity, the rule."""

from types import SimpleNamespace

import pytest

from apps.ai.evaluation import reranker_arms
from apps.ai.evaluation.labels import parse_question_set
from apps.ai.evaluation.reranker_arms import DECISION_RULE, Paired, compare
from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.ai.regions import Region
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk, Retriever
from apps.ai.retrieval.reranking import RerankingRetriever

FIG_DESC = "A bar chart of accuracy by model with five bars."


def chunk(chunk_id, content, embedded, kinds=("narrative",), page=1):
    return RetrievedChunk(
        chunk_id=chunk_id, record_id=1, record_title="Paper", content=content,
        context_path=("Results",), source_page=page, score=0.1,
        regions=(Region(page, 0.1, 0.1, 0.9, 0.9),), embedded=embedded, element_kinds=kinds,
    )


FIGURE = chunk(1, "", f"Results\n\n{FIG_DESC}", ("image",), page=3)
FILLER = [
    chunk(i, f"Unrelated filler passage number {i} about other topics entirely.",
          f"Results\n\nUnrelated filler passage number {i} about other topics entirely.")
    for i in range(2, 14)
]
PROSE = chunk(20, "The proposed model converges within ten epochs on every benchmark.",
              "Results\n\nThe proposed model converges within ten epochs on every benchmark.")


class Recall(Retriever):
    def __init__(self):
        self.calls = 0

    def retrieve(self, question, user, limit=20):
        self.calls += 1
        # The live text index holds no blank-shown chunk; the figure papers do.
        figure = (FIGURE,) if "accuracy" in question else ()
        return RetrievalResult(passages=(*FILLER, PROSE, *figure)[:limit])


class Vendor(Reranker):
    """Ranks a passage first when it mentions the question's last word."""

    transmits_externally = False

    def __init__(self):
        self.calls = []

    def rerank(self, query, candidates):
        self.calls.append(list(candidates))
        key = query.rstrip("?").split()[-1].lower()
        order = sorted(range(len(candidates)), key=lambda i: key not in candidates[i].lower())
        return [RerankedCandidate(index=i, text=candidates[i], score=-n) for n, i in enumerate(order)]


class Root:
    def __init__(self):
        self.recall = Recall()

    def recall_stage(self):
        return self.recall

    def reranking_over(self, inner, reranker, reads):
        return RerankingRetriever(inner, reranker=reranker, policy_enabled=False, reads=reads)

    def source_selection(self, max_sources):
        return SimpleNamespace(apply=lambda chunks: list(chunks)[:max_sources])


TEXT = parse_question_set({"name": "text", "questions": [{
    "id": "t1", "question": "How fast does it converge?",
    "expected": [{"record": "Paper", "quote": "converges within ten epochs on every benchmark"}],
}]})
FIGURES = parse_question_set({"name": "figures", "questions": [{
    "id": "f1", "kind": "figure-uncaptioned", "question": "Which model has the best accuracy?",
    "expected": [{"record": "Paper", "page": 3,
                  "region": {"left": 0.2, "top": 0.2, "right": 0.8, "bottom": 0.8}}],
}]})


def run(reranker):
    root = Root()
    roots = {"text": root, "figure": root}
    return root, compare(roots, {"text": TEXT, "figure": FIGURES}, user=None, reranker=reranker)


def test_every_arm_reranks_the_same_candidates_and_only_the_input_differs():
    vendor = Vendor()
    root, result = run(vendor)

    assert root.recall.calls == 2  # once per question, not once per arm
    figure_inputs = [c for c in vendor.calls if any(FIG_DESC in t for t in c)]
    assert len({len(c) for c in figure_inputs}) == 1  # A and C send the full list
    assert all(len(c) == len(FILLER) + 1 for c in vendor.calls if not any(FIG_DESC in t for t in c))


def test_b_and_c_cost_nothing_on_the_text_set_and_match_today():
    _, result = run(Vendor())

    for arm in ("described", "fallback"):
        assert result.identical_to_today("text", arm)
        assert result.tokens[("text", arm)] == 0
        assert result.recall("text", arm) == result.recall("text", "today")
    assert not result.identical_to_today("text", "embedded")


def test_today_cannot_cite_the_uncaptioned_figure_and_c_can():
    _, result = run(Vendor())

    assert result.recall("figure", "today")[0] == 0.0
    assert result.recall("figure", "fallback")[0] == 1.0
    assert result.recall("figure", "fallback", "figure-uncaptioned")[2] == 1
    assert result.paired("figure", "fallback", "today").wins == ("f1",)


def test_a_dry_run_estimates_tokens_and_reranks_nothing():
    vendor = Vendor()
    _, result = run(None)

    assert result.dry_run and result.total_tokens > 0 and not vendor.calls
    assert result.decision() == ["No decision: a dry run reranks nothing."]
    assert result.as_dict(cost_per_million=0.05)["cost_usd"] is not None


def test_the_rule_is_copied_into_every_report_unchanged():
    _, result = run(None)

    assert result.as_dict()["decision_rule"] == DECISION_RULE
    assert DECISION_RULE in result.render()


def test_a_drifted_arm_is_a_defect_not_a_result(monkeypatch):
    monkeypatch.setattr(reranker_arms, "changes_expected", lambda c, arm: arm == "embedded")
    _, result = run(Vendor())

    assert result.defects
    assert result.decision()[0].startswith("BLOCKED")


@pytest.mark.parametrize("wins, losses, p", [(0, 0, 1.0), (6, 0, 0.03125), (5, 1, 0.21875)])
def test_the_exact_sign_test(wins, losses, p):
    pair = Paired("embedded", "fallback", tuple(map(str, range(wins))),
                  tuple(f"l{i}" for i in range(losses)), 0)
    assert pair.p_value == pytest.approx(p)


def test_c_stands_when_a_does_not_win_significantly():
    _, result = run(Vendor())

    lines = result.decision()
    assert lines[0].startswith("Rules 1-2: C stands")
    assert lines[1].startswith("Rule 3")
