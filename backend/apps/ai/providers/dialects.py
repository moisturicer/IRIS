"""One collaborator per vendor, behind the one OpenAI-compatible adapter
(IR-382, ADR-021 §Amendment).

Vendors that speak the same wire protocol still differ: what extra fields a
request carries, which attribute a reasoning token arrives on, and what
citation markers the models behind that vendor habitually emit. Today that
knowledge is written into `openai_compatible.py` as Groq's shape, applied to
every vendor -- which works only because Groq is the sole vendor in real use.

A **dialect** is that knowledge, named and separable. The adapter keeps its
HTTP, streaming and error-classification logic written **once**; a dialect
shapes the request and reads the response, and is unit-testable with no
vendor account and no network.

**Parameterised, not subclassed.** There is no `GroqAdapter`: the adapter is
handed a dialect. A subclass per vendor would re-inherit the transport every
time and give each vendor its own place for transport bugs to diverge.

**Groq is the default, deliberately.** An adapter built with no dialect gets
Groq's, which is exactly what `openai_compatible.py` sent before this module
existed -- so this refactor is invisible to every existing caller. OpenRouter
is reached through the same default until IR-384 gives it its own dialect;
that is today's behaviour, not an endorsement of it.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from apps.ai.citation_markers import MARKER, numbers_in


class VendorDialect(ABC):
    """How one vendor's requests are shaped and its responses read."""

    #: Matches `Vendor`'s value in `apps/ai/inference/profiles.py`. A string
    #: rather than that enum because `apps/ai/inference/` imports this
    #: package, and the reverse would close the loop.
    name: str = ""

    @abstractmethod
    def request_extras(self, reasoning_effort: str) -> dict[str, Any]:
        """Extra keyword arguments for `chat.completions.create`.

        Empty when the vendor needs nothing beyond the common fields, which
        is the whole non-reasoning case.
        """

    def read_text(self, delta: Any) -> str:
        """The answer text on one streamed delta."""
        return getattr(delta, "content", None) or ""

    def read_reasoning(self, delta: Any) -> str:
        """The reasoning text on one streamed delta, on its own channel.

        Separate from `read_text` because IR-327's separation depends on the
        two never being concatenated -- a vendor that interleaves reasoning
        into `content` would need its own dialect, not a wider `read_text`.
        """
        return (
            getattr(delta, "reasoning", None)
            or getattr(delta, "reasoning_content", None)
            or ""
        )

    def normalize_citation_markers(self, text: str) -> str:
        """Rewrite this vendor's marker variants to the canonical `[n]`.

        Nothing by default: a marker habit belongs to the models behind a
        vendor, and inventing one for a vendor nobody has observed would be
        rewriting text on a guess.
        """
        return text


#: Variant markers observed from `openai/gpt-oss-120b`, Groq's configured
#: default: the CJK lenticular form `【1】`, the fullwidth form `［1］`, and
#: either of those or a plain bracket carrying an OpenAI-style file/line
#: suffix -- `【1†L1-L5】`. Each resolves to the same source the prompt
#: numbered; only the characters around the digits differ.
#:
#: The grammar itself lives in `apps/ai/citation_markers.py`, shared with the
#: parser that reads markers back. One definition rather than two that agree
#: today: the suffix bound and the bracket set were both widened after a live
#: failure, and a copy that missed either widening would normalise a marker
#: into a form the parser then dropped.
#:
#: `_MARKER` in `apps/ai/answers/citations.py` matches these variants too, and
#: stays that way: it is the net for any provider reached without a dialect,
#: and it is where the parser's own correctness is tested. This normalises
#: *before* parsing so what is stored, logged and read back is canonical
#: rather than whatever the model happened to type.


def _canonical(match: re.Match) -> str:
    return "".join(f"[{n}]" for n in numbers_in(match))


class GroqDialect(VendorDialect):
    """Groq: `openai/gpt-oss-120b` and the reasoning extension it answers to."""

    name = "groq"

    def request_extras(self, reasoning_effort: str) -> dict[str, Any]:
        """`reasoning_effort` and `include_reasoning`, or nothing.

        A Groq extension the `openai` SDK does not type, so it travels in
        `extra_body`. `include_reasoning` is what puts a reasoning model's
        thinking on `delta.reasoning` instead of interleaving it into
        `delta.content` (IR-327). Sent only when an effort is configured --
        an unset effort means no reasoning configuration at all, not a
        default one.
        """
        if not reasoning_effort:
            return {}
        return {
            "extra_body": {
                "reasoning_effort": reasoning_effort,
                "include_reasoning": True,
            }
        }

    def normalize_citation_markers(self, text: str) -> str:
        return MARKER.sub(_canonical, text)


GROQ = GroqDialect()

#: What an adapter built with no dialect uses. Groq's, because Groq is the
#: default vendor and because this is what the adapter sent unconditionally
#: before dialects existed -- see the module docstring.
DEFAULT_DIALECT: VendorDialect = GROQ

_DIALECTS: dict[str, VendorDialect] = {GROQ.name: GROQ}


def dialect_for(vendor: str | None) -> VendorDialect:
    """The dialect for `vendor`, or the default when it has none yet.

    Non-raising, unlike `profiles.vendor()`: a base URL is also how a
    self-hosted vLLM or Ollama is reached, and OpenRouter has no dialect of
    its own until IR-384. Both reach the default, which is the vendor-neutral
    request every one of them already receives -- refusing them here would
    break deployments this refactor promised not to touch.
    """
    if not vendor:
        return DEFAULT_DIALECT
    return _DIALECTS.get(str(vendor).strip().lower(), DEFAULT_DIALECT)
