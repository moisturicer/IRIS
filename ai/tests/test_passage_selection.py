"""Which passages a search hands the agent (IR-397, IR-1055, ADR-033 §4)."""

import pytest

from ai.research.selection import Hit, Policy, select
from ai.runs import config
from tests.test_runs_config import settings

ON = Policy(per_paper=3, join=True, tokens_per_passage=700, section_mates=True)


def hit(id, record=1, sequence=None, section=("T", "1 Intro"), tokens=100, chunk_set=None):
    return Hit(id=id, record_id=record, chunk_set_id=chunk_set or record * 10,
               sequence=id if sequence is None else sequence, section_key=section, tokens=tokens)


def ids(placed):
    return [p.hit.id for p in placed]


def test_no_paper_contributes_more_than_the_cap_and_lower_ranks_fill_the_slots():
    ranked = [hit(1), hit(3), hit(5), hit(7), hit(20, record=2), hit(22, record=2)]
    assert ids(select(ranked, limit=4, policy=ON)) == [1, 3, 5, 20]


def test_paper_chat_ignores_the_cap():
    ranked = [hit(1), hit(3), hit(5), hit(7), hit(9)]
    assert ids(select(ranked, limit=5, policy=ON, scoped=True)) == [1, 3, 5, 7, 9]


def test_adjacent_hits_of_one_source_arrive_together_in_reading_order_and_linked():
    ranked = [hit(5), hit(20, record=2), hit(4), hit(6)]
    placed = select(ranked, limit=4, policy=ON)
    assert ids(placed) == [4, 5, 6, 20]
    assert [p.continues for p in placed] == [None, 4, 5, None]


def test_adjacency_is_within_one_chunk_set_not_across_papers():
    ranked = [hit(5, record=1), hit(6, record=2, sequence=6)]
    assert [p.continues for p in select(ranked, limit=2, policy=ON)] == [None, None]


def test_hits_stop_at_the_token_budget_of_the_requested_passages():
    small = Policy(per_paper=0, join=True, tokens_per_passage=100, section_mates=False)
    ranked = [hit(1, tokens=150), hit(3, tokens=150), hit(5, tokens=150)]
    # Three passages requested: a 300-token budget fits two.
    assert ids(select(ranked, limit=3, policy=small)) == [1, 3]


def test_a_hit_too_big_for_the_budget_is_skipped_for_a_smaller_one_below_it():
    small = Policy(per_paper=0, join=True, tokens_per_passage=100, section_mates=False)
    ranked = [hit(1, tokens=150), hit(3, tokens=200), hit(5, tokens=50)]
    assert ids(select(ranked, limit=3, policy=small)) == [1, 5]


def test_the_top_hit_is_always_returned_even_over_budget():
    small = Policy(per_paper=0, join=True, tokens_per_passage=100, section_mates=False)
    assert ids(select([hit(1, tokens=900)], limit=1, policy=small)) == [1]


def test_a_zero_budget_is_unbudgeted():
    free = Policy(per_paper=0, join=True, tokens_per_passage=0, section_mates=False)
    assert ids(select([hit(1, tokens=900), hit(3, tokens=900)], limit=2, policy=free)) == [1, 3]


def test_without_joining_hits_keep_their_rank_order():
    ranked = [hit(5), hit(4)]
    off = Policy(per_paper=3, join=False, tokens_per_passage=700, section_mates=False)
    placed = select(ranked, limit=2, policy=off)
    assert ids(placed) == [5, 4] and [p.continues for p in placed] == [None, None]


def test_selection_is_on_by_default():
    assert config.read(settings()).selection == Policy(
        per_paper=3, join=True, tokens_per_passage=700, section_mates=True)


def test_each_part_of_selection_switches_off_on_its_own():
    off = config.read(settings(RUNS_PASSAGES_PER_PAPER="0", RUNS_JOIN_PASSAGES="off",
                               RUNS_PASSAGE_TOKENS="0", RUNS_SECTION_MATES="off")).selection
    assert off == Policy(per_paper=0, join=False, tokens_per_passage=0, section_mates=False)


@pytest.mark.parametrize("name,value", [("RUNS_JOIN_PASSAGES", "yes"), ("RUNS_PASSAGE_TOKENS", "lots")])
def test_a_misspelt_selection_setting_refuses_runs(name, value):
    with pytest.raises(config.RunsUnavailable, match=name):
        config.read(settings(**{name: value}))
