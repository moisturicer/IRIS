"""Resolving a follow-up, isolated from HTTP (IR-296, ADR-026).

Pure, like `apps/ai/answers/citations.py`'s own suite: no Django, no
database, a duck-typed stand-in for `Turn` so these run without
`db_required`. The HTTP boundary — what a caller actually observes, and
where the "no resolution call" cost guarantees matter — is covered in
`test_conversations_http.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from apps.ai import resolution
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.resolution import (
    QuestionResolver,
    build_resolution_prompt,
    resolution_cache_key,
)


@dataclass
class _Turn:
    """Stands in for `apps.ai.models.Turn`: only `pk`, `question` and
    `answer` are ever read by this module, so a real row buys nothing here.
    """

    pk: int
    question: str
    answer: str = ""


class _BrokenLLM(LLMProvider):
    def generate(self, system, user):
        raise LLMUnavailable("vendor down")


class WordCheckRemovalTests:
    """IR-445: the back-reference word check is deleted, not bypassed. A
    follow-up with no listed pronoun skipped resolution and retrieved on text
    that was never meant to be a search query (ADR-026 §8, as amended)."""

    def test_the_word_check_and_its_word_list_no_longer_exist(self):
        assert not hasattr(resolution, "has_back_reference")
        assert not hasattr(resolution, "_BACK_REFERENCE_WORDS")


class PromptTests:
    def test_the_prompt_carries_the_conversation_and_the_follow_up(self):
        turns = [_Turn(pk=1, question="What does it conclude?", answer="It finds X.")]
        prompt = build_resolution_prompt("what about its limitations?", turns)
        assert "What does it conclude?" in prompt
        assert "It finds X." in prompt
        assert "what about its limitations?" in prompt

    def test_the_window_it_is_given_is_rendered_whole(self):
        """**This prompt no longer bounds anything** (IR-449). It used to
        keep `MAX_HISTORY_TURNS = 6` and slice its argument, so the caller
        could not see the bound and the bound had nothing to do with the
        size of what it bounded. The window is now a token budget, filled
        once in `apps.ai.history` and shared with the answering prompt;
        `test_history_window.py` covers what it admits, and what this
        asserts is that the prompt does not quietly narrow it again.
        """
        turns = [_Turn(pk=i, question=f"q{i:03d}") for i in range(9)]
        prompt = build_resolution_prompt("its limitations?", turns)
        for turn in turns:
            assert turn.question in prompt


class CacheKeyTests:
    def test_questions_differing_only_in_case_and_whitespace_share_a_key(self):
        turns = [_Turn(pk=1, question="q", answer="a")]
        assert resolution_cache_key("its limitations?", turns) == (
            resolution_cache_key("  Its Limitations?  ", turns)
        )

    def test_different_history_makes_a_different_key(self):
        assert resolution_cache_key(
            "its limitations?", [_Turn(pk=1, question="q")]
        ) != resolution_cache_key("its limitations?", [_Turn(pk=2, question="q")])

    def test_different_questions_do_not_collide(self):
        turns = [_Turn(pk=1, question="q")]
        assert resolution_cache_key("alpha", turns) != resolution_cache_key("beta", turns)


class ResolveTests:
    def test_the_first_turn_makes_no_call(self):
        """No history to resolve against (ADR-026 Decision 8)."""
        llm = ScriptedLLM()
        resolver = QuestionResolver(llm=llm, cache={})

        assert resolver.resolve("what about its limitations?", []) is None
        assert llm.calls == []

    @pytest.mark.parametrize(
        "question",
        [
            "give me a longer explanation",
            "expand on the second point",
            "why does the Jordan frame matter",
            "elaborate",
            "what about in the Einstein frame",
            "any criticism of the method",
        ],
    )
    def test_a_follow_up_with_no_pronoun_is_resolved(self, question):
        """The observed failure (IR-443): none of these contains a word the
        old list knew, so none was ever sent to the resolver."""
        llm = ScriptedLLM(reply="resolved")
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [_Turn(pk=1, question="What is the separate-universe approach?", answer="X.")]

        assert resolver.resolve(question, turns) == "resolved"
        assert len(llm.calls) == 1

    def test_a_self_contained_follow_up_is_resolved_too(self):
        """Rewritten, not deleted (IR-445). This used to assert that a
        question with no back-reference made no call; every follow-up now
        costs one, which is the price ADR-026 §8's amendment accepts."""
        llm = ScriptedLLM(reply="resolved")
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        assert resolver.resolve("what does the paper conclude?", turns) == "resolved"
        assert len(llm.calls) == 1

    def test_an_empty_model_reply_falls_back_to_none(self):
        resolver = QuestionResolver(llm=ScriptedLLM(reply="   "), cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        assert resolver.resolve("give me a longer explanation", turns) is None

    def test_a_follow_up_with_history_calls_the_model_and_returns_its_reply(self):
        llm = ScriptedLLM(reply="What are the limitations of the flood paper?")
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [
            _Turn(
                pk=1,
                question="What does the flood paper conclude?",
                answer="It finds X.",
            )
        ]

        resolved = resolver.resolve("what about its limitations?", turns)

        assert resolved == "What are the limitations of the flood paper?"
        assert len(llm.calls) == 1

    def test_a_failed_resolution_falls_back_to_none(self):
        resolver = QuestionResolver(llm=_BrokenLLM(), cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        assert resolver.resolve("what about its limitations?", turns) is None

    def test_a_repeated_question_and_history_costs_one_call(self):
        """The caching guarantee (ADR-026 Decision 8)."""
        llm = ScriptedLLM(reply="resolved")
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        for _ in range(5):
            resolver.resolve("what about its limitations?", turns)

        assert len(llm.calls) == 1

    def test_a_cache_hit_returns_the_same_resolution(self):
        llm = ScriptedLLM(reply="resolved")
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        first = resolver.resolve("what about its limitations?", turns)
        second = resolver.resolve("what about its limitations?", turns)

        assert first == second == "resolved"

    def test_a_failed_resolution_is_not_cached(self):
        """A transient vendor failure is retried, not remembered as a
        permanent "no resolution" — caching it would freeze that follow-up
        onto the raw-question fallback until the entry expired."""
        cache = {}
        turns = [_Turn(pk=1, question="q", answer="a")]
        QuestionResolver(llm=_BrokenLLM(), cache=cache).resolve(
            "what about its limitations?", turns
        )
        assert cache == {}

        healthy = QuestionResolver(llm=ScriptedLLM(reply="resolved"), cache=cache)
        assert healthy.resolve("what about its limitations?", turns) == "resolved"

    def test_works_with_no_cache_at_all(self):
        llm = ScriptedLLM(reply="resolved")
        resolver = QuestionResolver(llm=llm, cache=None)
        turns = [_Turn(pk=1, question="q", answer="a")]

        assert resolver.resolve("what about its limitations?", turns) == "resolved"
        assert resolver.resolve("what about its limitations?", turns) == "resolved"
        assert len(llm.calls) == 2
