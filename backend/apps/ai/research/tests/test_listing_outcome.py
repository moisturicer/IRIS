"""The listing's selection cap and its code-written wording (IR-546). No database, no vendor."""

from types import SimpleNamespace

import pytest

from apps.ai.research import listing
from apps.ai.research.listing import Candidate, Outcome, Selection, select_candidates


def outcome(states, **options):
    return Outcome(tuple(Candidate(n, f"Paper {n}", state) for n, state in enumerate(states, 1)), **options)


def test_selection_keeps_each_record_once_in_rank_order_and_stops_at_twenty(monkeypatch):
    facets_fused = [n % 30 for n in range(60)]  # every record shows up twice or more
    monkeypatch.setattr(listing, "rank_record_candidates",
                        lambda run, args: (facets_fused, False, {}))
    chosen = select_candidates(SimpleNamespace(), "flooding")
    assert chosen.ids == tuple(range(20))
    assert chosen.more_available is True and chosen.degraded is False


def test_selection_reports_no_more_when_it_found_no_more(monkeypatch):
    monkeypatch.setattr(listing, "rank_record_candidates", lambda run, args: ([3, 1, 3, 2], True, {}))
    assert select_candidates(SimpleNamespace(), "x") == Selection((3, 1, 2), False, True)


def test_the_limit_is_a_code_constant_not_an_environment_setting():
    assert listing.CANDIDATE_LIMIT == 20


@pytest.mark.parametrize("states,expected", [
    (["included", "excluded", "uncertain", "unassessed"],
     "Screened 4 candidate papers: 1 matched, 1 did not match, 1 uncertain, 1 could not be assessed."),
    (["excluded", "excluded"],
     "No matches found among the assessed candidates; other relevant papers may exist."),
    (["unassessed", "unassessed"], "Inconclusive: none of the 2 candidate papers could be assessed"),
])
def test_wording_states_each_total_and_never_a_certain_absence(states, expected):
    text = outcome(states).wording()
    assert expected in text
    assert "no papers" not in text.lower() and "none exist" not in text.lower()


def test_only_an_all_unassessed_list_is_inconclusive():
    assert outcome(["unassessed"] * 3).completeness == "inconclusive"
    assert outcome(["uncertain", "unassessed"]).completeness == "matches_found"
    assert outcome([]).completeness == "matches_found"


def test_a_pending_candidate_is_never_counted_as_a_match():
    only_pending = outcome(["pending", "pending"])
    assert only_pending.count("included") == 0 and only_pending.decided == 0
    assert only_pending.wire()["records"] == []


def test_notes_disclose_the_cap_degraded_search_and_changed_access():
    text = outcome(["included"], more_available=True, search_degraded=True, changed=True).wording()
    assert "More candidates were found than were screened (limit 20)." in text
    assert "Meaning-based search was unavailable" in text
    assert "changed while this ran" in text


def test_a_withheld_candidate_is_counted_but_never_named():
    rows = Outcome((Candidate(1, "Secret Title", "unassessed", withheld=True),
                    Candidate(2, "Open", "included")))
    wire = rows.wire()
    assert wire["candidates"][0] == {"record_id": 1, "state": "unassessed", "withheld": True}
    assert "Secret Title" not in str(wire)
    assert wire["coverage"]["selected"] == 2 and wire["coverage"]["unassessed"] == 1
