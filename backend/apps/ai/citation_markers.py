"""The grammar of a citation marker: what the models actually type.

Two modules need this and need it to agree. `apps/ai/answers/citations.py`
parses markers back to the sources they point at; `apps/ai/providers/
dialects.py` rewrites a vendor's variants to the canonical form before that
parsing runs (IR-382). Held apart from both, at the same level as
`regions.py`, so neither layer imports the other -- and so a change to the
suffix bound or the bracket set cannot reach one and miss the other.

**The bracket class is wider than the prompt asks for because a model is not
bound by it.** `openai/gpt-oss-120b`, the configured default, answers with the
CJK lenticular form -- `【1】` -- and against an ASCII-only pattern every
citation silently failed to resolve: zero citations, `is_grounded` false, and
the raw marker left sitting in the rendered text. Fullwidth brackets appear
for the same reason.

**Three balanced alternatives rather than one wide opening class and one wide
closing class.** The cheap version also matches `[1】` and `【1]`, which no
model produces and which a reader would have to squint at to call a citation.
Each branch captures the digits, so exactly one group is ever populated.

**`SUFFIX` tolerates trailing content between the number and the close** --
observed live, 2026-09-20: gpt-oss-120b sometimes appends an OpenAI-style
file/line-range suffix, `【1†L1-L5】` rather than `【1】`. Against a pattern
with no suffix allowance, every citation in an answer using that form
resolved to nothing.

**Every bracket character is excluded, opening as well as closing, and the
length is bounded.** Excluding only the closing brackets is the obvious
version and it is wrong: on an unclosed marker the suffix runs straight
across the prose to the next close, so `A【1†L1-L5 and more prose 【2】`
resolved to `A[1]` -- the model's own words deleted from what the reader
sees, and the genuine `【2】` swallowed. Dropping a citation is the parser's
stated failure direction; eating a sentence is not. A real suffix is under
ten characters (`†L13-L16`), so 64 is generous even for a filename-bearing
variant while keeping the damage from any pathological input bounded.
"""

from __future__ import annotations

import re

#: One number, or several separated by commas -- models produce `[1, 2]` and
#: `[1][2]` whether or not the prompt asks for them.
NUMBERS = r"\d+(?:\s*,\s*\d+)*"

#: What a marker may carry between its number and its closing bracket.
SUFFIX = r"[^\[\]【】［］]{0,64}"

#: Inline markers: `[1]`, `【1】`, `［1］`, with or without a suffix.
MARKER = re.compile(
    rf"\[\s*({NUMBERS})\s*{SUFFIX}\]"
    rf"|【\s*({NUMBERS})\s*{SUFFIX}】"
    rf"|［\s*({NUMBERS})\s*{SUFFIX}］"
)


def numbers_in(match: re.Match) -> list[int]:
    """The source numbers one `MARKER` match names.

    Exactly one alternative matched, so exactly one group is non-None; which
    bracket style it came from does not matter past here.
    """
    digits = next(group for group in match.groups() if group is not None)
    return [int(n) for n in digits.replace(" ", "").split(",") if n]
