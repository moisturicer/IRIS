"""The normalizer: cleans a document before it is chunked (IR-113).

Drops running headers and footers and the sections excluded from chunking,
such as the bibliography: 10-20% of a thesis by tokens, and it retrieves
uniformly badly. The Docling-era repairs (repeated furniture, stranded page
numbers, hyphen rejoining) were deleted with Docling (IR-843): LlamaParse
labels its own furniture and rejoins its own line-end hyphens (IR-851).

The critical constraint: this module **drops document elements, it does not
rewrite a string**, so every surviving element keeps its ``prov``.

Pure: no I/O, no clock, no randomness.
"""

import re
from dataclasses import replace

from .document import (
    HEADING,
    PAGE_FOOTER,
    PAGE_HEADER,
    DocumentElement,
    NormalizedDocument,
)
from .values import ChunkingOptions


def normalize(document: NormalizedDocument, options: ChunkingOptions) -> NormalizedDocument:
    """Return a cleaned copy of ``document``. ``document`` itself is left
    untouched."""
    elements = list(document.elements)
    if document.structure_is_authoritative:
        return replace(document, elements=tuple(_drop_excluded_sections(
            [e for e in elements if e.kind not in {"header", "footer"}], options.exclude_sections,
        )))
    elements = _drop_running_headers_and_footers(elements)
    elements = _drop_excluded_sections(elements, options.exclude_sections)

    return NormalizedDocument(
        title=document.title,
        elements=tuple(elements),
        page_sizes=document.page_sizes,
    )


def _drop_running_headers_and_footers(
    elements: list[DocumentElement],
) -> list[DocumentElement]:
    return [e for e in elements if e.kind not in (PAGE_HEADER, PAGE_FOOTER)]


# A section number opening a heading -- "5. ", "1.4.   ", "2.1.1 " -- which
# names the section's position rather than the section. Stripped before an
# exclusion name is compared, because `AI_CHUNK_EXCLUDE_SECTIONS` lists what a
# section *is* ("References"), not where it sits in a particular document.
#
# The trailing `\s+` is what keeps this from eating a real title: it requires
# whitespace after the number, so "3.5 kg of Feed" loses "3.5 " and compares as
# "kg of feed", which matches no exclusion name and is therefore kept anyway.
_SECTION_NUMBER_PREFIX = re.compile(r"^\d+(?:\.\d+)*\.?\s+")

# Punctuation a heading may carry that its name does not: "References:",
# "References."
_HEADING_PUNCTUATION = ".:;-–—"


def _comparable_heading(text: str) -> str:
    """A heading reduced to the form an exclusion name is written in.

    Drops any leading section number, strips edge punctuation, collapses
    internal whitespace -- record 30 writes "1.4.   References" with three
    spaces -- and lowercases. Comparison stays *exact* on what remains: a
    substring rule would drop "Reference Architecture" and
    "References and Further Reading", and losing a real section is worse than
    keeping a bibliography (IR-244).
    """
    without_number = _SECTION_NUMBER_PREFIX.sub("", text.strip())
    trimmed = without_number.strip().strip(_HEADING_PUNCTUATION).strip()
    return " ".join(trimmed.split()).lower()


def _drop_excluded_sections(
    elements: list[DocumentElement], exclude_sections: tuple[str, ...]
) -> list[DocumentElement]:
    """Drop each named section, and everything under it up to the next heading.

    Both sides go through `_comparable_heading`, so the configured name and the
    document's own heading are compared in the same form. Before IR-244 this
    compared whole heading text, which meant the shipped default list only ever
    fired on a heading reading exactly "References" -- and both real CIT-U
    submissions number their sections, so both kept their bibliography, where it
    then outranked real content on a third of test queries.
    """
    if not exclude_sections:
        return elements

    excluded = {_comparable_heading(name) for name in exclude_sections}
    excluded.discard("")
    if not excluded:
        return elements

    result: list[DocumentElement] = []
    dropping = False
    for element in elements:
        if element.kind == HEADING:
            dropping = _comparable_heading(element.text) in excluded
        if not dropping:
            result.append(element)
    return result
