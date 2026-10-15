"""The one-sentence hook written with the Overview (IR-604).

The hook rides on the Overview's completion, so the whole paper is sent once.
It is optional: a missing, blank or over-long hook is no hook.
"""

from __future__ import annotations

import re

from apps.ai.citation_markers import MARKER, PAGE_MARKER

HOOK_MAX_CHARS = 145

HOOK_INSTRUCTION = (
    "After everything else, end with one final line that starts 'HOOK: ' and "
    f"gives one or two sentences, at most {HOOK_MAX_CHARS} characters in "
    "total, saying what this work does and its strongest result, as a reader "
    "browsing a catalogue would want it. Use only what the paper states; add "
    "no citation, no heading and no formatting to that line. If the paper "
    "supports no such line, omit it."
)

_HOOK_LINE = re.compile(r"^[ \t]*HOOK:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_MARKUP = re.compile(r"[*_`#>]+")


def _clean(raw: str) -> str:
    text = PAGE_MARKER.sub("", raw)
    text = MARKER.sub("", text)
    text = _MARKUP.sub("", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def split_hook(raw: str) -> tuple[str, str]:
    """``(body, hook)``: the reply without its HOOK line, and the hook or ``""``.

    An over-long hook is dropped, not cut: a clipped sentence reads as a claim
    the paper never made.
    """
    matches = list(_HOOK_LINE.finditer(raw))
    if not matches:
        return raw, ""
    last = matches[-1]
    body = (raw[: last.start()] + raw[last.end():]).strip()
    hook = _clean(last.group(1))
    return body, hook if len(hook) <= HOOK_MAX_CHARS else ""
