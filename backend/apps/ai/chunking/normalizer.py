"""The normalizer: cleans a document before it is chunked (IR-113).

Extraction output from a Philippine university thesis carries artefacts that
would otherwise be embedded as though they were content: running headers
repeated on every page, page numbers stranded on their own line, words split
by a hyphen across a line break, and a references section that is 10-20% of
a thesis by tokens and retrieves uniformly badly.

The critical constraint: this module **drops and edits document elements, it
does not rewrite a string**. Rewriting to a cleaned string is simpler, and it
silently destroys the page and bounding-box data attached to each element —
nothing downstream could recover it, because matching chunk text back
against a PDF fails on ligatures, hyphenation across line breaks, and
multi-column reading order. Every surviving element keeps its ``prov``.

Pure: no I/O, no clock, no randomness — testable with before/after fixtures
and nothing else.
"""

import re

from .document import HEADING, PAGE_FOOTER, PAGE_HEADER, DocumentElement, NormalizedDocument
from .values import ChunkingOptions

# A line that is nothing but a page number: plain digits, or a lowercase
# roman numeral (front-matter pagination). Matched against the whole
# stripped text, so "Chapter 4" and "xiv centuries" are untouched — only a
# line that consists of the number and nothing else is a stranded folio.
_ARABIC_PAGE_NUMBER = re.compile(r"^\d{1,4}$")

# A *well-formed* roman numeral from i to xlix, not merely a word spelled
# out of roman letters. `^[ivxlcdm]{1,8}$` would have matched "civil",
# "did", "dill" and "mix", silently deleting a one-word caption, list item
# or table cell — content loss that no example using digits would catch.
# The ceiling is deliberate too: front matter is numbered in roman and runs
# to a few dozen pages, so "mix" (MIX, 1009) is not a page number this
# corpus can produce.
_ROMAN_PAGE_NUMBER = re.compile(r"^(xl|x{0,3})(ix|iv|v?i{0,3})$", re.IGNORECASE)

# A trailing hyphen counts as a line-break split only when the next element
# starts lowercase — an end-of-sentence dash is followed by a capital far
# more often than a genuine word continuation is.
_CONTINUATION = re.compile(r"^[a-z]")


def normalize(document: NormalizedDocument, options: ChunkingOptions) -> NormalizedDocument:
    """Return a cleaned copy of ``document``. ``document`` itself is left
    untouched."""
    elements = list(document.elements)
    elements = _drop_running_headers_and_footers(elements)
    elements = _drop_stranded_page_numbers(elements)
    elements = _rejoin_hyphenation(elements)
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


def _is_stranded_page_number(element: DocumentElement) -> bool:
    text = element.text.strip()
    if not text:
        # The roman pattern's every part is optional, so it matches the
        # empty string. Guarded here rather than in the pattern, where the
        # alternation would have to repeat itself to say so.
        return False
    return bool(_ARABIC_PAGE_NUMBER.match(text) or _ROMAN_PAGE_NUMBER.match(text))


def _drop_stranded_page_numbers(elements: list[DocumentElement]) -> list[DocumentElement]:
    return [e for e in elements if not _is_stranded_page_number(e)]


# A hyphen at a line break *inside* one element's text. Docling keeps a
# paragraph's own line breaks, so the split word is far more often within an
# element than across two. Same rule as the cross-element case: only a
# lowercase continuation counts, so "the appendix-\nChapter 5" is left alone.
_INTERNAL_HYPHENATION = re.compile(r"(\w)-\n\s*([a-z])")


def _rejoin_internal_hyphenation(text: str) -> str:
    return _INTERNAL_HYPHENATION.sub(r"\1\2", text)


def _rejoin_hyphenation(elements: list[DocumentElement]) -> list[DocumentElement]:
    elements = [
        DocumentElement(
            kind=e.kind,
            text=_rejoin_internal_hyphenation(e.text),
            level=e.level,
            page=e.page,
            bboxes=e.bboxes,
        )
        if "-\n" in e.text
        else e
        for e in elements
    ]
    result: list[DocumentElement] = []
    for element in elements:
        if (
            result
            and result[-1].kind == element.kind
            and result[-1].kind != HEADING
            and result[-1].text.endswith("-")
            and _CONTINUATION.match(element.text)
        ):
            prior = result.pop()
            result.append(
                DocumentElement(
                    kind=prior.kind,
                    text=prior.text[:-1] + element.text,
                    level=prior.level,
                    # `page` stays the first fragment's, so it agrees with
                    # the first region. Both fragments' regions are kept:
                    # when the break is a page break, the rejoined element
                    # genuinely occupies a rectangle on each page, and
                    # dropping the second would truncate the highlight.
                    page=prior.page,
                    bboxes=prior.bboxes + element.bboxes,
                )
            )
        else:
            result.append(element)
    return result


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
