"""Display-math delimiters recognized by ADR-056 decision 11."""

import re


DISPLAY_FORMULA = re.compile(r"\$\$(?P<dollar>.*?)\$\$|\\\[(?P<bracket>.*?)\\\]", re.DOTALL)


def without_formulas(text: str) -> str:
    """Keep prose, with a separator where a display formula was printed."""
    return DISPLAY_FORMULA.sub(" ", text)
