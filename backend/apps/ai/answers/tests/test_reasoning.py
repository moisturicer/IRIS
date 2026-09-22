"""`ThinkTagFilter` (IR-327): defending against reasoning that leaks into the
text channel.

Pure and vendor-free, like `citations.py`'s own tests: this is a streaming
text splitter, not an HTTP concern, so it is tested without a Conversation, a
request or a fake LLM.
"""

from apps.ai.answers.reasoning import ThinkTagFilter


class NoLeakTests:
    def test_plain_text_with_no_tag_passes_through_unchanged(self):
        f = ThinkTagFilter()
        text, reasoning = f.feed("Rainfall gauges feed the model [1].")
        assert text == "Rainfall gauges feed the model [1]."
        assert reasoning == ""
        assert f.flush() == ("", "")


class SingleChunkLeakTests:
    def test_a_think_block_fully_inside_one_chunk_is_classified_as_reasoning(self):
        f = ThinkTagFilter()
        text, reasoning = f.feed("<think>secret plan</think>Rainfall gauges feed the model.")
        assert text == "Rainfall gauges feed the model."
        assert reasoning == "secret plan"

    def test_text_before_and_after_a_think_block_is_both_kept(self):
        f = ThinkTagFilter()
        text, reasoning = f.feed("Before. <think>hidden</think> After.")
        assert text == "Before.  After."
        assert reasoning == "hidden"

    def test_two_think_blocks_in_one_chunk_are_both_captured(self):
        f = ThinkTagFilter()
        text, reasoning = f.feed("A<think>one</think>B<think>two</think>C")
        assert text == "ABC"
        assert reasoning == "onetwo"


class SplitAcrossChunksTests:
    def test_an_opening_tag_split_across_two_chunks_is_still_recognised(self):
        f = ThinkTagFilter()
        text1, reasoning1 = f.feed("Before <thi")
        text2, reasoning2 = f.feed("nk>secret</think> after")
        assert text1 + text2 == "Before  after"
        assert reasoning1 + reasoning2 == "secret"

    def test_a_closing_tag_split_across_two_chunks_is_still_recognised(self):
        f = ThinkTagFilter()
        text1, reasoning1 = f.feed("<think>secret</thi")
        text2, reasoning2 = f.feed("nk>after")
        assert text1 + text2 == "after"
        assert reasoning1 + reasoning2 == "secret"

    def test_reasoning_split_across_many_small_chunks_reassembles(self):
        f = ThinkTagFilter()
        pieces = ["<th", "ink>", "sec", "ret", "</th", "ink>", "answer"]
        text = ""
        reasoning = ""
        for piece in pieces:
            t, r = f.feed(piece)
            text += t
            reasoning += r
        assert text == "answer"
        assert reasoning == "secret"

    def test_ordinary_text_that_merely_contains_a_lone_angle_bracket_is_not_held_forever(self):
        """A caller that never closes with `flush()` should still see text that
        was never actually the start of a tag -- only a genuine prefix of
        `<think>`/`</think>` is worth withholding."""
        f = ThinkTagFilter()
        text, reasoning = f.feed("5 < 10 and 10 > 5")
        assert text == "5 < 10 and 10 > 5"
        assert reasoning == ""


class UnterminatedTagTests:
    def test_reasoning_still_streams_live_even_if_the_tag_never_closes(self):
        """Content already known to be inside `<think>` is reasoning as soon
        as it arrives -- it does not wait for `</think>` to be classified,
        which is what lets a reader see "Thinking..." progress live rather
        than only after the whole (possibly truncated) block is in."""
        f = ThinkTagFilter()
        text, reasoning = f.feed("<think>never finishes")
        assert text == ""
        assert reasoning == "never finishes"
        assert f.flush() == ("", "")

    def test_a_trailing_partial_close_tag_resolves_as_reasoning_on_flush(self):
        """The vendor behaviour this exists for: the stream can end (or
        fail) mid-tag. Whatever fragment was withheld while it might still
        have completed `</think>` must not leak into the stored answer --
        `flush()` resolves it as reasoning, since a `<think>` was open."""
        f = ThinkTagFilter()
        text, reasoning = f.feed("<think>secret</thi")
        assert text == ""
        assert reasoning == "secret"
        flushed_text, flushed_reasoning = f.flush()
        assert flushed_text == ""
        assert flushed_reasoning == "</thi"

    def test_flush_releases_a_false_positive_tag_prefix_as_text(self):
        """A `<` near the end of a chunk that never turns into `<think>`
        must not vanish -- once the stream ends, whatever was withheld
        waiting to see if a tag was starting comes back as ordinary text."""
        f = ThinkTagFilter()
        text, reasoning = f.feed("5 is less than 10, written <t")
        assert text == "5 is less than 10, written "
        assert reasoning == ""
        flushed_text, flushed_reasoning = f.flush()
        assert flushed_text == "<t"
        assert flushed_reasoning == ""
