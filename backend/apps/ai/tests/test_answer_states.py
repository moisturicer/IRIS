"""Every answer state has an explicit wire presentation (IR-458).

`answer_mode` used to fall back to "generative" for anything it did not know,
which showed a cut-off `partial` fragment as a finished answer. The fallback is
now `unavailable`, and this file is what stops a new state from relying on it.
"""
import pytest

from apps.ai.models import Turn
from apps.ai.presentation import (
    _WIRE_MODE,
    GENERATIVE_MODE,
    PARTIAL_MODE,
    UNAVAILABLE_MODE,
    answer_body,
    answer_mode,
)


def _turn_states():
    return [value for value, _label in Turn._meta.get_field("state").choices]


class EveryStateIsMappedTests:
    @pytest.mark.parametrize("state", _turn_states())
    def test_each_turn_state_has_an_explicit_mapping(self, state):
        assert state in _WIRE_MODE, (
            f"Turn.state {state!r} has no entry in presentation._WIRE_MODE; "
            "add one rather than relying on the unavailable fallback"
        )

    def test_the_mapping_names_no_state_a_turn_cannot_hold(self):
        assert set(_WIRE_MODE) == set(_turn_states())


class PresentationTests:
    def test_a_partial_state_is_not_generative(self):
        assert answer_mode("partial") == PARTIAL_MODE != GENERATIVE_MODE

    def test_a_partial_fragment_is_a_message_not_an_answer(self):
        body = answer_body(answer_mode("partial"), "Flooding is caused by")
        assert body == {"answer": None, "message": "Flooding is caused by"}

    def test_a_generated_state_is_still_an_answer(self):
        body = answer_body(answer_mode("generated"), "A finished answer.")
        assert body == {"answer": "A finished answer.", "message": None}

    def test_an_unrecognised_state_is_unavailable(self):
        assert answer_mode("some_future_state") == UNAVAILABLE_MODE

    def test_an_unrecognised_state_never_renders_as_an_answer(self):
        body = answer_body(answer_mode("some_future_state"), "Looks like a finding.")
        assert body["answer"] is None
        assert body["message"]
