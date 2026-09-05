"""The ingestion lifecycle as a table, not as conditionals (IR-115 G).

The question these tests exist to pin down is the one that would otherwise
be answered inconsistently in three different views: *can a record be
re-chunked after it has been approved and published?* Yes — chunking is an
index concern, not a record-state concern — and this is the single place
that says so.
"""

import pytest

from apps.ai.ingestion import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    IngestionState,
    assert_transition,
    is_allowed_transition,
    staleness_after,
)


def test_the_happy_path_runs_end_to_end():
    path = [
        IngestionState.UPLOADED,
        IngestionState.EXTRACTED,
        IngestionState.CHUNKED,
        IngestionState.INDEXED,
    ]
    for source, target in zip(path, path[1:]):
        assert is_allowed_transition(source, target)


def test_an_indexed_document_can_be_re_chunked():
    assert is_allowed_transition(IngestionState.INDEXED, IngestionState.CHUNKED)


def test_idempotent_re_runs_are_self_loops():
    assert is_allowed_transition(IngestionState.EXTRACTED, IngestionState.EXTRACTED)
    assert is_allowed_transition(IngestionState.INDEXED, IngestionState.INDEXED)


def test_failed_is_reachable_from_every_state():
    for state in IngestionState:
        if state is IngestionState.FAILED:
            continue
        assert is_allowed_transition(state, IngestionState.FAILED), state


def test_a_document_cannot_skip_extraction():
    assert not is_allowed_transition(IngestionState.UPLOADED, IngestionState.CHUNKED)


def test_stale_is_only_reachable_from_indexed():
    for state in IngestionState:
        expected = state is IngestionState.INDEXED
        assert is_allowed_transition(state, IngestionState.STALE) is expected, state


def test_a_stale_document_is_recovered_by_re_chunking():
    assert is_allowed_transition(IngestionState.STALE, IngestionState.CHUNKED)


def test_a_disallowed_transition_raises():
    with pytest.raises(IllegalTransition) as exc:
        assert_transition(IngestionState.UPLOADED, IngestionState.INDEXED)

    assert "uploaded" in str(exc.value)
    assert "indexed" in str(exc.value)


def test_an_allowed_transition_returns_the_target():
    assert (
        assert_transition(IngestionState.CHUNKED, IngestionState.INDEXED)
        is IngestionState.INDEXED
    )


def test_transitions_are_data_not_code():
    """Every state is a key, so adding one is an edit to the table rather
    than to a growing chain of conditionals."""
    assert set(ALLOWED_TRANSITIONS) == set(IngestionState)
    assert all(
        target in IngestionState
        for targets in ALLOWED_TRANSITIONS.values()
        for target in targets
    )


def test_transitions_accept_plain_strings():
    """The state is stored in a CharField; a value read back from the
    database is a string, and the table must not care."""
    assert is_allowed_transition("chunked", "indexed")
    assert assert_transition("chunked", "indexed") is IngestionState.INDEXED


def test_an_unknown_state_is_rejected_rather_than_silently_disallowed():
    with pytest.raises(IllegalTransition):
        assert_transition("indexed", "publushed")


class TestStaleness:
    """Stale is derived from the content hash, never from a timestamp and
    never from a user action."""

    def test_a_matching_hash_leaves_an_indexed_document_indexed(self):
        assert (
            staleness_after(IngestionState.INDEXED, stored_hash="a", current_hash="a")
            is IngestionState.INDEXED
        )

    def test_a_changed_hash_marks_an_indexed_document_stale(self):
        assert (
            staleness_after(IngestionState.INDEXED, stored_hash="a", current_hash="b")
            is IngestionState.STALE
        )

    def test_a_document_that_was_never_indexed_is_not_made_stale(self):
        assert (
            staleness_after(IngestionState.CHUNKED, stored_hash="a", current_hash="b")
            is IngestionState.CHUNKED
        )

    def test_an_already_stale_document_stays_stale(self):
        assert (
            staleness_after(IngestionState.STALE, stored_hash="a", current_hash="b")
            is IngestionState.STALE
        )
