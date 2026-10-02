"""The verbatim history window is a token budget (IR-449).

Pure, like `test_resolution.py`'s own suite: Django settings are read (so
`django_required`), but no database and no HTTP. A duck-typed stand-in for
`Turn` is enough, because the window reads `pk`, `question` and `answer` and
nothing else.

The counting here is the real pinned tokenizer, not a fake. It is local, it
is deterministic across processes by construction (`tokens.TOKENIZER_SHA256`
pins the vocabulary), and the whole point of the ticket is that no vendor is
asked how long a prompt is -- so a fake counter would be testing the wrong
thing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.test import override_settings

from apps.ai import history
from apps.ai.chunking.tokens import count_tokens, truncate_to_tokens
from apps.ai.resolution import build_resolution_prompt, resolution_cache_key

pytestmark = [pytest.mark.django_required]


@dataclass
class _Turn:
    """Stands in for `apps.ai.models.Turn` -- see `test_resolution.py`."""

    pk: int
    question: str
    answer: str = ""


#: Roughly 350 words, the scale of the separate-universe answer IR-443 was
#: written about: one of these is a sizeable fraction of any sane budget.
_LONG_ANSWER = (
    "The separate-universe approach treats a long-wavelength perturbation as "
    "a background shift in a locally homogeneous patch, so the local "
    "expansion history differs from the global one by an amount set by the "
    "curvature perturbation. " * 20
)

#: The old fixed window, for the comparisons the acceptance criteria ask for.
_OLD_FIXED_WINDOW = 6


def _short_turns(count: int) -> list[_Turn]:
    return [
        # Zero-padded so that no question is a substring of another: a
        # "step 3" that matches "step 31" would make an exclusion assertion
        # below pass for the wrong reason.
        _Turn(
            pk=i,
            question=f"and then what about step {i:03d}",
            answer=f"Step {i:03d} holds.",
        )
        for i in range(count)
    ]


def _long_turns(count: int) -> list[_Turn]:
    return [
        _Turn(pk=i, question=f"explain approach {i} in full", answer=_LONG_ANSWER)
        for i in range(count)
    ]


class TheBudgetReplacesTheCountTests:
    """The old bound is gone, and the new one is a number of tokens read per
    request rather than a constant compiled into the resolver."""

    def test_the_turn_count_no_longer_exists(self):
        from apps.ai import resolution

        assert not hasattr(resolution, "MAX_HISTORY_TURNS")

    def test_the_budget_is_read_per_request(self):
        with override_settings(AI_HISTORY_TOKEN_BUDGET=77):
            assert history.history_token_budget() == 77
        with override_settings(AI_HISTORY_TOKEN_BUDGET=1234):
            assert history.history_token_budget() == 1234

    def test_the_default_mirrors_the_setting(self):
        from django.conf import settings

        assert settings.AI_HISTORY_TOKEN_BUDGET == (
            history.DEFAULT_HISTORY_TOKEN_BUDGET
        )
        assert settings.AI_HISTORY_TOKEN_MARGIN == history.DEFAULT_TOKEN_MARGIN


class TheMarginTests:
    """A conservative estimate, not a measurement -- see the setting's
    comment and IR-330."""

    def test_the_estimate_is_at_least_the_real_count_and_is_monotonic(self):
        short, long = "a brief question", _LONG_ANSWER
        assert history.estimate_tokens(short) >= count_tokens(short)
        assert history.estimate_tokens(long) >= count_tokens(long)
        assert history.estimate_tokens(long) > history.estimate_tokens(short)

    def test_a_larger_margin_admits_less_history(self):
        turns = _short_turns(40)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=400, AI_HISTORY_TOKEN_MARGIN=1.0):
            lenient = len(history.history_window(turns))
        with override_settings(AI_HISTORY_TOKEN_BUDGET=400, AI_HISTORY_TOKEN_MARGIN=2.0):
            strict = len(history.history_window(turns))
        assert strict < lenient

    def test_a_margin_below_one_is_clamped(self):
        """A margin that made the estimate *smaller* than the count would
        defeat its own purpose, so it is floored rather than honoured."""
        with override_settings(AI_HISTORY_TOKEN_MARGIN=0.1):
            assert history.token_margin() == 1.0
            assert history.estimate_tokens(_LONG_ANSWER) >= count_tokens(_LONG_ANSWER)

    def test_the_cost_of_a_turn_includes_the_prompt_lines_it_becomes(self):
        """Measured on the rendered `Q: `/`A: ` lines, so the prefixes are
        inside the budget rather than silently over it."""
        turn = _Turn(pk=1, question="what about its limitations", answer="It finds X.")
        assert history.turn_tokens(turn) > history.estimate_tokens(
            turn.question + turn.answer
        )


class WhatTheBudgetAdmitsTests:
    """The behaviour the ticket exists for: the window follows the size of
    the history, not its row count."""

    def test_many_short_turns_admit_more_than_the_old_fixed_six(self):
        turns = _short_turns(40)
        window = history.history_window(turns)
        assert len(window) > _OLD_FIXED_WINDOW

    def test_turns_short_enough_are_bounded_by_the_fetch_not_the_budget(self):
        """Honest about where the ceiling actually is: Turns this short do
        not come near the budget, so what bounds them is
        `HISTORY_CANDIDATE_LIMIT` -- the bound on the *query* the view
        makes. Reaching further back than that is memory's job (IR-297)."""
        turns = _short_turns(history.HISTORY_CANDIDATE_LIMIT)
        assert len(history.history_window(turns)) == history.HISTORY_CANDIDATE_LIMIT
        assert sum(history.turn_tokens(t) for t in turns) < (
            history.history_token_budget()
        )

    def test_very_long_turns_admit_fewer_than_the_old_fixed_six(self):
        turns = _long_turns(40)
        window = history.history_window(turns)
        assert len(window) < _OLD_FIXED_WINDOW

    def test_the_same_budget_admits_more_short_turns_than_long_ones(self):
        """The two assertions above, pinned as one comparison so the pair
        cannot drift apart if the default moves."""
        with override_settings(AI_HISTORY_TOKEN_BUDGET=2000):
            assert len(history.history_window(_short_turns(40))) > len(
                history.history_window(_long_turns(40))
            )

    def test_it_fills_newest_first_and_stops(self):
        turns = _short_turns(40)
        window = history.history_window(turns)
        assert window[-1] is turns[-1]
        assert [t.pk for t in window] == sorted(t.pk for t in window)
        assert window == turns[-len(window) :]

    def test_it_stops_rather_than_skipping_to_a_smaller_older_turn(self):
        """History with a hole in it is a conversation that did not happen."""
        turns = [
            _Turn(pk=1, question="tiny", answer="tiny"),
            _Turn(pk=2, question="explain in full", answer=_LONG_ANSWER),
            _Turn(pk=3, question="tiny follow-up", answer="tiny"),
        ]
        with override_settings(AI_HISTORY_TOKEN_BUDGET=60):
            window = history.history_window(turns)
        assert [t.pk for t in window] == [3]

    def test_it_stays_within_the_budget(self):
        turns = _short_turns(40)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=500):
            window = history.history_window(turns)
        assert sum(history.turn_tokens(t) for t in window) <= 500

    def test_no_history_is_an_empty_window(self):
        assert history.history_window([]) == []

    def test_an_explicit_budget_overrides_the_setting(self):
        turns = _short_turns(40)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=100000):
            assert len(history.history_window(turns, budget=200)) < len(
                history.history_window(turns)
            )


class TheNewestTurnIsAlwaysPresentTests:
    """A follow-up with nothing immediately preceding it in view is the
    IR-445 failure again, so the newest Turn is truncated, never dropped."""

    def test_a_turn_larger_than_the_whole_budget_is_kept_and_truncated(self):
        turns = _long_turns(3)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=80):
            window = history.history_window(turns)
        assert len(window) == 1
        kept = window[0]
        assert kept.pk == turns[-1].pk
        assert kept.question == turns[-1].question
        assert kept.answer != turns[-1].answer
        assert kept.answer.endswith(history.TRUNCATION_MARKER)
        assert history.turn_tokens(kept) <= 80

    def test_the_truncated_text_is_a_prefix_of_the_original(self):
        """Cut, not reworded: a reader comparing the prompt against the
        transcript must find the one inside the other."""
        turns = _long_turns(1)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=100):
            kept = history.history_window(turns)[0]
        body = kept.answer[: -len(history.TRUNCATION_MARKER)]
        assert turns[-1].answer.startswith(body)

    def test_the_stored_turn_is_not_mutated(self):
        """The truncation is for one prompt and must not reach the reader's
        transcript, so the window copies rather than clips in place."""
        turns = _long_turns(1)
        original = turns[-1].answer
        with override_settings(AI_HISTORY_TOKEN_BUDGET=100):
            window = history.history_window(turns)
        assert turns[-1].answer == original
        assert window[0] is not turns[-1]

    def test_an_enormous_question_is_cut_too_and_the_answer_goes(self):
        """Last resort: the question is kept whole where it can be, but a
        question that alone exceeds the budget still has to fit."""
        turn = _Turn(pk=1, question=_LONG_ANSWER, answer=_LONG_ANSWER)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=60):
            window = history.history_window([turn])
        assert len(window) == 1
        assert window[0].answer == ""
        assert window[0].question != turn.question
        assert history.turn_tokens(window[0]) <= 60

    def test_a_non_positive_budget_still_returns_the_newest_turn(self):
        with override_settings(AI_HISTORY_TOKEN_BUDGET=0):
            window = history.history_window(_short_turns(5))
        assert len(window) == 1
        assert window[0].pk == 4


class OneCounterForBothPromptsTests:
    """The resolver prompt and the answering prompt are built from the same
    windowed list, and neither narrows it again."""

    def test_neither_prompt_slices_the_window_it_is_given(self):
        from apps.ai.answers.citations import build_prompt

        turns = _short_turns(40)
        # Tight enough that the budget excludes some of them: 40 Turns this
        # short all fit inside the default, which is the point of the
        # ticket but makes this particular assertion vacuous.
        with override_settings(AI_HISTORY_TOKEN_BUDGET=200):
            window = history.history_window(turns)

        resolver_prompt = build_resolution_prompt("and after that?", window)
        answering_prompt = build_prompt("and after that?", chunks=(), history=window)

        for turn in window:
            assert turn.question in resolver_prompt
            assert turn.question in answering_prompt
        excluded = turns[: -len(window)]
        assert excluded, "the budget must have excluded something for this to mean anything"
        for turn in excluded:
            assert turn.question not in resolver_prompt
            assert turn.question not in answering_prompt

    def test_both_prompts_hold_the_same_history_lines(self):
        from apps.ai.answers.citations import build_prompt

        window = history.history_window(_short_turns(40))
        in_resolver = [
            line
            for line in build_resolution_prompt("q", window).splitlines()
            if line.startswith(("Q: ", "A: "))
        ]
        in_answering = [
            line
            for line in build_prompt("q", chunks=(), history=window).splitlines()
            if line.startswith(("Q: ", "A: "))
        ]
        # The answering prompt's own `Question:` line is not a `Q: ` line.
        assert in_resolver == in_answering


class NoVendorCallToCountTokensTests:
    """AC: no vendor token-counting call is made anywhere on this path --
    there is no such endpoint to call, and the counting is local."""

    def test_the_counter_is_the_pinned_tokenizer_in_this_repository(self):
        from apps.ai.chunking import tokens

        assert history.count_tokens is tokens.count_tokens
        assert tokens.TOKENIZER_PATH.exists()

    def test_counting_a_prompt_makes_no_http_call(self, monkeypatch):
        """Pins the guarantee at the seam every vendor call in this codebase
        goes through: `httpx`. A budget that cost a round trip would be the
        thing this ticket set out to avoid."""
        import httpx

        def _forbidden(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the history budget made a network call")

        monkeypatch.setattr(httpx, "post", _forbidden)
        monkeypatch.setattr(httpx, "get", _forbidden)
        monkeypatch.setattr(httpx.Client, "request", _forbidden)

        window = history.history_window(_long_turns(10))
        assert window
        assert history.estimate_tokens("a question about the budget") > 0


class TruncationPrimitiveTests:
    """`truncate_to_tokens` -- the cut the window makes, on its own."""

    def test_it_returns_a_literal_prefix_on_a_token_boundary(self):
        text = "The Jordan frame bound is 0.37 under the separate-universe approach."
        cut = truncate_to_tokens(text, 5)
        assert text.startswith(cut)
        assert count_tokens(cut) == 5

    def test_text_inside_the_ceiling_comes_back_unchanged(self):
        text = "a short line"
        assert truncate_to_tokens(text, 500) == text

    def test_a_non_positive_ceiling_gives_nothing(self):
        assert truncate_to_tokens("anything at all", 0) == ""
        assert truncate_to_tokens("anything at all", -3) == ""

    def test_it_does_not_split_a_multibyte_character(self):
        """A decode-the-first-n-ids roundtrip would hand back a replacement
        character here; cutting on offsets cannot."""
        cut = truncate_to_tokens("héllo wörld naïve café", 3)
        assert "�" not in cut
        assert "héllo wörld naïve café".startswith(cut)


class TheCacheKeyFollowsTheWindowTests:
    """AC: one key per (question, history) pair, computed from the Turns
    actually used -- a variable window changes which ids are folded in."""

    def test_a_different_window_makes_a_different_key(self):
        turns = _short_turns(40)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=300):
            small = history.history_window(turns)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=3000):
            large = history.history_window(turns)
        assert len(small) < len(large)
        assert resolution_cache_key("q", small) != resolution_cache_key("q", large)

    def test_the_same_window_and_question_share_a_key(self):
        window = history.history_window(_short_turns(10))
        assert resolution_cache_key("its limitations?", window) == (
            resolution_cache_key("  Its Limitations?  ", window)
        )

    def test_two_truncations_of_one_turn_do_not_share_a_key(self):
        """The ids are identical and the prompts are not, which is why the
        key folds in the text's length as well as the Turn's id."""
        turns = _long_turns(1)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=100):
            short_cut = history.history_window(turns)
        with override_settings(AI_HISTORY_TOKEN_BUDGET=400):
            long_cut = history.history_window(turns)
        assert [t.pk for t in short_cut] == [t.pk for t in long_cut]
        assert build_resolution_prompt("q", short_cut) != build_resolution_prompt(
            "q", long_cut
        )
        assert resolution_cache_key("q", short_cut) != resolution_cache_key(
            "q", long_cut
        )
