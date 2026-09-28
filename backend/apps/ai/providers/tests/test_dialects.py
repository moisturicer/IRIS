"""The dialect seam, tested with no vendor account and no network (IR-382)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from apps.ai.answers.citations import parse_citations
from apps.ai.providers.dialects import (
    DEFAULT_DIALECT,
    GROQ,
    GroqDialect,
    VendorDialect,
    dialect_for,
)
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.retrieval.ports import RetrievedChunk


@dataclass
class FakeDelta:
    """One streamed delta, shaped like the SDK's."""

    content: Optional[str] = None
    reasoning: Optional[str] = None
    reasoning_content: Optional[str] = None


class TestGroqRequestShaping:
    def test_reasoning_configuration_travels_in_extra_body(self):
        """The `openai` SDK does not type these fields, so a Groq request
        carries them out of band or not at all."""
        assert GROQ.request_extras("high") == {
            "extra_body": {"reasoning_effort": "high", "include_reasoning": True}
        }

    def test_an_unset_effort_sends_no_reasoning_configuration(self):
        """Not a default effort -- a task with hidden Reasoning pays for no
        reasoning tokens (IR-380)."""
        assert GROQ.request_extras("") == {}


class TestReadingAStreamedDelta:
    def test_text_is_read_off_content(self):
        assert GROQ.read_text(FakeDelta(content="hello")) == "hello"

    def test_a_delta_carrying_no_text_reads_as_empty(self):
        assert GROQ.read_text(FakeDelta()) == ""

    @pytest.mark.parametrize("field", ["reasoning", "reasoning_content"])
    def test_reasoning_arrives_on_its_own_channel(self, field):
        """IR-327's separation: reasoning is never concatenated into the
        answer text, whichever attribute the vendor puts it on."""
        delta = FakeDelta(content="answer", **{field: "thinking"})
        assert GROQ.read_text(delta) == "answer"
        assert GROQ.read_reasoning(delta) == "thinking"


class TestCitationMarkerNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("【1】", "[1]"),
            ("［1］", "[1]"),
            ("【1†L1-L5】", "[1]"),
            ("[1†L1-L5]", "[1]"),
            ("【1, 2】", "[1][2]"),
            ("[1]", "[1]"),
        ],
    )
    def test_variant_markers_become_canonical(self, raw, expected):
        assert GROQ.normalize_citation_markers(f"Yes {raw}.") == f"Yes {expected}."

    def test_an_unclosed_marker_does_not_swallow_the_prose_after_it(self):
        """A greedy suffix would run to the next closing bracket and delete
        the model's own sentence along with a genuine marker."""
        normalised = GROQ.normalize_citation_markers("A【1†L1-L5 and more 【2】")
        assert "and more" in normalised
        assert normalised.endswith("[2]")

    def test_text_with_no_markers_is_returned_unchanged(self):
        assert GROQ.normalize_citation_markers("No citations here.") == (
            "No citations here."
        )

    def test_a_normalised_variant_still_resolves_to_its_source(self):
        """The point of normalising: parsing sees the canonical form, and the
        citation matches the source the prompt numbered."""
        chunk = RetrievedChunk(
            chunk_id=7,
            record_id=3,
            record_title="A Thesis",
            content="the passage",
            context_path=(),
            source_page=1,
            score=1.0,
        )
        raw = GROQ.normalize_citation_markers("Yes 【1†L1-L5】.")

        text, citations = parse_citations(raw, [chunk])

        assert text == "Yes [1]."
        assert [c.record_id for c in citations] == [3]


class TestChoosingADialect:
    def test_groq_is_selected_by_name(self):
        assert isinstance(dialect_for("groq"), GroqDialect)

    @pytest.mark.parametrize("vendor", ["GROQ", " groq "])
    def test_the_name_is_matched_case_and_space_insensitively(self, vendor):
        assert dialect_for(vendor) is GROQ

    @pytest.mark.parametrize("vendor", [None, "", "openrouter", "a-self-hosted-vllm"])
    def test_a_vendor_with_no_dialect_of_its_own_gets_the_default(self, vendor):
        """Non-raising by design: OpenRouter's dialect is IR-384, and a base
        URL is also how a self-hosted model is reached. Refusing here would
        break deployments this refactor promised not to touch."""
        assert dialect_for(vendor) is DEFAULT_DIALECT


class _RecordingDialect(VendorDialect):
    """A dialect that is nothing like Groq's, so delegation is visible."""

    name = "recording"

    def request_extras(self, reasoning_effort):
        return {"extra_body": {"seen": reasoning_effort}}

    def read_text(self, delta):
        return (getattr(delta, "content", None) or "").upper()

    def read_reasoning(self, delta):
        return getattr(delta, "thoughts", None) or ""

    def normalize_citation_markers(self, text):
        return text.replace("<1>", "[1]")


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [type("C", (), {"delta": delta})()]


class _FakeClient:
    """The one call the adapter makes, and a record of how it was made."""

    def __init__(self, reply="An answer.", stream_deltas=None):
        self.calls = []
        self._reply = reply
        self._stream_deltas = stream_deltas

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter([_FakeChunk(d) for d in (self._stream_deltas or [])])
        message = type("M", (), {"content": self._reply})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()

    @property
    def chat(self):
        client = self

        class _Completions:
            create = staticmethod(lambda **kw: client._create(**kw))

        return type("Chat", (), {"completions": _Completions()})()


class TestTheAdapterDelegatesToItsDialect:
    def test_an_adapter_built_with_no_dialect_gets_the_default(self):
        """Which is what it sent unconditionally before dialects existed --
        the refactor is invisible to every existing caller."""
        assert OpenAICompatibleAdapter().dialect is DEFAULT_DIALECT

    def test_the_request_extras_are_the_dialect_s(self):
        delta = type("D", (), {"content": "yes"})()
        client = _FakeClient(stream_deltas=[delta])
        list(
            OpenAICompatibleAdapter(
                client=client, reasoning_effort="low", dialect=_RecordingDialect()
            ).stream(system="s", user="u")
        )

        assert client.calls[0]["extra_body"] == {"seen": "low"}

    def test_a_streamed_delta_is_read_through_the_dialect(self):
        delta = type("D", (), {"content": "yes", "thoughts": "hmm"})()
        deltas = list(
            OpenAICompatibleAdapter(
                client=_FakeClient(stream_deltas=[delta]), dialect=_RecordingDialect()
            ).stream(system="s", user="u")
        )

        assert deltas[0].text == "YES"
        assert deltas[0].reasoning == "hmm"

    def test_a_whole_answer_is_normalised_before_it_leaves_the_adapter(self):
        text = OpenAICompatibleAdapter(
            client=_FakeClient(reply="Yes <1>."), dialect=_RecordingDialect()
        ).generate(system="s", user="u")

        assert text == "Yes [1]."
