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

from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.resolution import (
    MAX_HISTORY_TURNS,
    QuestionResolver,
    build_resolution_prompt,
    has_back_reference,
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


class BackReferenceTests:
    @pytest.mark.parametrize(
        "question",
        [
            "what about its limitations?",
            "What does THIS mean?",
            "did they replicate it elsewhere",
            "how does hers compare",
        ],
    )
    def test_a_pronoun_is_a_back_reference(self, question):
        assert has_back_reference(question)

    @pytest.mark.parametrize(
        "question",
        [
            "what does the paper conclude?",
            "neural network rainfall flooding catchment",
            "",
        ],
    )
    def test_a_self_contained_question_has_no_back_reference(self, question):
        assert not has_back_reference(question)


class PromptTests:
    def test_the_prompt_carries_the_conversation_and_the_follow_up(self):
        turns = [_Turn(pk=1, question="What does it conclude?", answer="It finds X.")]
        prompt = build_resolution_prompt("what about its limitations?", turns)
        assert "What does it conclude?" in prompt
        assert "It finds X." in prompt
        assert "what about its limitations?" in prompt

    def test_only_the_most_recent_turns_are_included(self):
        """Bounded, not the whole history — reaching further back is
        memory's job (IR-297), not resolution's."""
        turns = [_Turn(pk=i, question=f"q{i}") for i in range(MAX_HISTORY_TURNS + 3)]
        prompt = build_resolution_prompt("its limitations?", turns)
        assert "q0" not in prompt
        assert f"q{MAX_HISTORY_TURNS + 2}" in prompt


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

    def test_a_self_contained_question_makes_no_call(self):
        llm = ScriptedLLM()
        resolver = QuestionResolver(llm=llm, cache={})
        turns = [_Turn(pk=1, question="q", answer="a")]

        assert resolver.resolve("what does the paper conclude?", turns) is None
        assert llm.calls == []

    def test_a_back_reference_with_history_calls_the_model_and_returns_its_reply(self):
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
