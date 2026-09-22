"""Defending the text channel against leaked reasoning (IR-327).

Some vendors -- gpt-oss-120b on Groq, reported live -- sometimes emit
reasoning inside `<think>...</think>` tags in the ordinary content channel
instead of the dedicated `reasoning` field, even when reasoning is configured
hidden (no `reasoning_effort`, or `include_reasoning: false`). Left
unfiltered, that text would land in the stored answer and get scanned for
citation markers right alongside it.

`ThinkTagFilter` reclassifies it before either of those things can happen: a
span between `<think>` and `</think>` is reasoning, whatever channel it
arrived on. Stateful and streaming-safe -- a tag can split across two vendor
chunks, and this holds back only the shortest possible ambiguous suffix
rather than buffering whole chunks.
"""

from __future__ import annotations

_OPEN = "<think>"
_CLOSE = "</think>"


def _held_back_suffix(buffer: str, tag: str) -> str:
    """The longest suffix of ``buffer`` that could still grow into ``tag`` --
    what must stay unclassified because the next chunk might complete it.

    Checked longest first, so a genuine long match is never shadowed by a
    shorter one nested inside it.
    """
    limit = min(len(buffer), len(tag) - 1)
    for length in range(limit, 0, -1):
        suffix = buffer[-length:]
        if tag.startswith(suffix):
            return suffix
    return ""


class ThinkTagFilter:
    """Splits streamed text into ``(text, reasoning)``, treating
    ``<think>...</think>`` as leaked reasoning wherever it appears in the
    text channel.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    def feed(self, chunk: str) -> tuple[str, str]:
        """Classify one incoming chunk of raw content text.

        Returns everything that can be classified with certainty so far;
        anything that might still turn into (or out of) a tag stays in the
        internal buffer for the next call, or for ``flush()``.
        """
        self._buffer += chunk
        text_parts: list[str] = []
        reasoning_parts: list[str] = []

        while True:
            tag = _CLOSE if self._in_think else _OPEN
            index = self._buffer.find(tag)
            if index == -1:
                held = _held_back_suffix(self._buffer, tag)
                released = self._buffer[: len(self._buffer) - len(held)]
                self._buffer = held
                (reasoning_parts if self._in_think else text_parts).append(released)
                break

            before, self._buffer = self._buffer[:index], self._buffer[index + len(tag):]
            (reasoning_parts if self._in_think else text_parts).append(before)
            self._in_think = not self._in_think

        return "".join(text_parts), "".join(reasoning_parts)

    def flush(self) -> tuple[str, str]:
        """Whatever is still held back once the stream has ended.

        Classified by whether a ``<think>`` was open at that point: reasoning
        that never closed is still reasoning, not an answer fragment -- and a
        ``<``-prefixed tail that never turned into a real tag is ordinary
        text after all.
        """
        remaining, self._buffer = self._buffer, ""
        if self._in_think:
            return "", remaining
        return remaining, ""
