"""The verbatim history window -- a token budget, not a Turn count (IR-449).

Recent Turns go into the prompt verbatim (ADR-026 §6). *How many* was
`MAX_HISTORY_TURNS = 6`, and a Turn count is a proxy for the thing that
actually matters. Six one-line exchanges spent a fraction of the room they
could have used; six long answers -- the separate-universe answer in IR-443
is around 350 words by itself -- produced a prompt several times larger, in
the resolver call and the answering call both, with no ceiling anywhere.

So the window is filled newest-first until a **token budget** is reached, and
then it stops. The most recent Turn is always in it, truncated rather than
dropped if it alone exceeds the budget: a follow-up with nothing immediately
preceding it in view is the IR-445 failure again, and an empty window is a
worse answer than a clipped one.

Counting, without a vendor call
-------------------------------
**Nothing here calls a vendor to size a prompt, and there is no endpoint that
would.** OpenRouter reports `prompt_tokens` in the response `usage` field and
serves historical figures at `GET /api/v1/generation?id=`; Groq, the
development default, has the same shape. Both require the request to have
already been made, so neither can size one beforehand -- and a pre-flight
call would be the extra round trip a local budget exists to avoid.

Counting is therefore local, and reuses the tokenizer the repository already
pins: `apps.ai.chunking.tokens`, the SHA-256-pinned Qwen2 BPE vocabulary at
`chunking/tokenizer/voyage-context-4.json`, through the already-pinned
`tokenizers` runtime. No new dependency, nothing fetched at build or run
time, and real BPE tokens rather than words.

That vocabulary belongs to `voyage-context-4`, and the model being budgeted
for is a Llama- or Qwen-class model on Groq or one of OpenRouter's many, so
the count is an estimate and :func:`estimate_tokens` applies a safety margin
to it. The reason the margin is the right answer and a per-model vocabulary
is not: ADR-036 sanctions two vendors and OpenRouter alone fronts hundreds of
models, so shipping a vocabulary per answering model is unbounded
maintenance for a number that only has to be stable, conservative and
monotonic. `AI_HISTORY_TOKEN_MARGIN` in `config/settings/base.py` carries the
value and the reasoning.

**Calibrating the margin is IR-330's job, not this module's.** "Capture LLM
token usage per Turn" (Deferred Until Validation) would record the real
`usage` figures this estimate could be measured against, turning the margin
from a defensible guess into a number. Until then it is a margin, and this
docstring says so rather than implying a precision it does not have.

One counter, two prompts
------------------------
The resolver prompt and the answering prompt are built from the **same**
windowed list: `views.chatbot._recent_turns` windows once and hands the
result to `resolution.build_resolution_prompt` and to
`answers.citations.build_prompt`. Neither slices it again -- that is what
makes "the two prompts share one counter" a property of the shape rather
than of two functions agreeing to use the same constant.

The answering prompt holds more than history: recalled Turns and the
`Sources:` block as well. **Budgeting the sources half is IR-397**, which has
not shipped; this module caps history only, and `AI_HISTORY_TOKEN_BUDGET`'s
comment states the combined ceiling the two halves are meant to add up to so
that IR-397 reconciles against a written number instead of guessing.
"""

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Optional, Sequence

from django.conf import settings

from apps.ai.chunking.tokens import count_tokens, truncate_to_tokens
from apps.ai.resolution import turn_qa_lines

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.ai.models import Turn

#: Tokens of verbatim history the prompt may hold. Mirrored by
#: `AI_HISTORY_TOKEN_BUDGET`, which a test holds to this value.
DEFAULT_HISTORY_TOKEN_BUDGET = 3000

#: Multiplier applied to every count -- see the module docstring and the
#: setting's comment. Mirrored by `AI_HISTORY_TOKEN_MARGIN`.
DEFAULT_TOKEN_MARGIN = 1.15

#: How many Turns are *loaded* to fill the window from -- a bound on the
#: query, so a Conversation with five hundred Turns does not read five
#: hundred rows to spend a 3000-token budget on the newest few.
#:
#: **For short enough Turns this, and not the budget, is the real ceiling**,
#: and it is worth being plain about that rather than claiming the budget
#: always binds: fifty Turns averaging sixty tokens is the whole default
#: budget, so a conversation of one-line exchanges reaches this bound first.
#: That is the intended outcome -- fifty Turns back is far past what a
#: follow-up refers to, and reaching further is memory's job (IR-297), not
#: the verbatim window's.
HISTORY_CANDIDATE_LIMIT = 50

#: Appended where a Turn's text was cut, so the model is not shown a
#: sentence that stops mid-word as though that were the whole answer.
TRUNCATION_MARKER = " [...]"


def history_token_budget() -> int:
    """The budget for this request. Read per request, never cached, so a
    deployment can change it without a restart."""
    return int(
        getattr(settings, "AI_HISTORY_TOKEN_BUDGET", DEFAULT_HISTORY_TOKEN_BUDGET)
    )


def token_margin() -> float:
    """The safety margin for this request. Below 1.0 is treated as 1.0 --
    a margin that made the estimate *smaller* than the count would defeat
    the point of having one."""
    margin = float(getattr(settings, "AI_HISTORY_TOKEN_MARGIN", DEFAULT_TOKEN_MARGIN))
    return max(margin, 1.0)


def estimate_tokens(text: str) -> int:
    """``text`` in estimated answering-model tokens.

    `voyage-context-4` tokens, rounded up after the margin. Monotonic in the
    real count, which is what a budget needs: longer text never estimates
    cheaper.
    """
    return math.ceil(count_tokens(text) * token_margin())


def turn_tokens(turn: "Turn") -> int:
    """What ``turn`` costs in a prompt.

    Measured on the exact lines it contributes -- `turn_qa_lines` is what
    both prompts render it with -- rather than on the question and answer
    fields alone, so the `Q: `/`A: ` prefixes and the newline between them
    are inside the budget instead of silently over it.
    """
    return estimate_tokens("\n".join(turn_qa_lines([turn])))


def _clipped(turn: "Turn", budget: int) -> "Turn":
    """``turn`` with its text cut to fit ``budget``, answer first.

    The question is kept whole and the answer takes the cut, because a
    question clipped mid-phrase is unreadable as the thing that was asked
    while a clipped answer still reads as an answer that was cut short.
    Only when the question alone will not fit is it cut too, and then the
    answer goes entirely.

    Returns a **shallow copy**: the caller's Turn is never mutated, so a
    truncation made for one prompt cannot leak into the reader's transcript.
    The copy keeps the original's primary key, which is what
    `resolution_cache_key` and memory's `exclude_ids` identify it by. It is
    not saved and must not be -- it holds deliberately incomplete text.
    """
    clipped = copy.copy(turn)
    marker_cost = estimate_tokens(TRUNCATION_MARKER)
    question_cost = estimate_tokens(f"Q: {turn.question}")

    if question_cost + marker_cost > budget:
        clipped.question = _cut(turn.question, budget - estimate_tokens("Q: ") - marker_cost)
        clipped.answer = ""
        return clipped

    clipped.answer = _cut(
        turn.answer or "",
        budget - question_cost - estimate_tokens("\nA: ") - marker_cost,
    )
    return clipped


def _cut(text: str, estimated_budget: int) -> str:
    """``text`` cut to ``estimated_budget`` *estimated* tokens, marked.

    The budget is in estimated tokens and the tokenizer counts real ones, so
    the margin is divided back out before cutting; flooring that division
    keeps the result inside the budget rather than one token over it.
    """
    if estimated_budget <= 0:
        return ""
    cut = truncate_to_tokens(text, math.floor(estimated_budget / token_margin()))
    if not cut.strip():
        return ""
    return cut.rstrip() + TRUNCATION_MARKER


def history_window(
    turns: Sequence["Turn"], budget: Optional[int] = None
) -> list["Turn"]:
    """The Turns of ``turns`` that fit in ``budget``, oldest first.

    ``turns`` is a Conversation's candidate history, oldest first, already
    filtered to what may enter a prompt (`in_model_history`, IR-448). The
    window fills from the newest backwards and stops at the first Turn that
    will not fit -- it stops rather than skipping on to look for a smaller
    older Turn, because history with a hole in it is a conversation that did
    not happen.

    The newest Turn is always returned, truncated by :func:`_clipped` if it
    alone exceeds the budget. A non-positive budget means exactly that one
    Turn, cut to nothing, which is a configuration mistake rather than a
    state worth a separate code path.
    """
    if not turns:
        return []

    effective = history_token_budget() if budget is None else budget
    newest = turns[-1]
    newest_cost = turn_tokens(newest)
    if newest_cost > effective:
        return [_clipped(newest, effective)]

    window = [newest]
    spent = newest_cost
    for turn in reversed(turns[:-1]):
        cost = turn_tokens(turn)
        if spent + cost > effective:
            break
        window.append(turn)
        spent += cost
    return window[::-1]
