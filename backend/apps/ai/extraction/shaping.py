"""Shaping rules shared by the Extractor's shaping and the evidence rules.

LlamaParse's shaping lived here until the cutover deleted it (IR-988, ADR-067).
"""

import re
from dataclasses import replace

from apps.ai.extraction.formulas import DISPLAY_FORMULA

# "Table 1:", "TABLE I:", "Fig. 3", but not "Table of Contents" or "TABLES".
CAPTION = re.compile(r"^(?:(?i:table|figure)(?![A-Za-z])|(?i:tab|fig)\.)\s*(?:\d+|[IVXLC]+|[A-Z]\d*)\b")
FRONT_MATTER = re.compile(r"^(abstract|keywords|contents|table of contents|summary|a preprint)\b", re.IGNORECASE)


def split_formulas(element):
    if element.kind != "text":
        return [element]
    parts = []
    start = 0
    for match in DISPLAY_FORMULA.finditer(element.text):
        if match.start() > start:
            parts.append(replace(element, text=element.text[start:match.start()]))
        parts.append(replace(element, kind="formula", text=match.group("dollar") or match.group("bracket") or ""))
        start = match.end()
    if start < len(element.text) or not parts:
        parts.append(replace(element, text=element.text[start:]))
    return parts
