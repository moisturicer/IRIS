"""Outline numbering: the depth a heading's own number claims (IR-314).

Docling does not infer outline depth — it labels every heading
``section_header`` and reports level 1 for all of them — so the document's
own numbering is the only reliable signal of nesting. Reading it used to
mean dotted decimals and nothing else, which is the CIT-U thesis
convention but not the scientific-paper one:

    I. INTRODUCTION
       A. Transition Path Sampling
       E. The GenAIMMD algorithm
          Self-consistency loop

Roman numerals for sections, letters for subsections, unnumbered
sub-subsections. None of those matched, so every heading reported "no
depth" and the whole paper flattened to a depth-2 path — all 717 chunks of
the 20-record corpus.

**Why a whole-document pass rather than a per-heading function:** ``I``,
``V``, ``X``, ``L``, ``C``, ``D`` and ``M`` are simultaneously letters and
roman numerals. ``C. Committors`` between ``B. AIMMD`` and ``D. Shooting``
is plainly a subsection; the same string opening a paper is plainly section
100. Nothing in the heading itself tells them apart — only the sequence
does, so the sequence is what this module reads.

Pure: no Django, no I/O, no clock, no randomness.
"""

import re
from typing import Optional, Sequence

#: A dotted-decimal section number: ``3``, ``3.2``, ``2.1.1``, with an
#: optional trailing dot, then whitespace and actual words.
#:
#: The trailing ``\s+\S`` matters. Without it ``1,000 Samples`` matches its
#: leading ``1`` and a heading about a sample size is read as a top-level
#: section; requiring the separator to be whitespace rejects it, because a
#: comma is not a dot. A bare number with no text after it is not an outline
#: entry either, and is rejected the same way.
DECIMAL_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")

#: A roman numeral opening a heading, closed by a dot or parenthesis. The
#: alternation is the strict form — ``IIII`` and ``VX`` are not numerals —
#: so a word that merely begins with roman letters ("MIX Design") cannot be
#: read as one: ``MIX`` matches ``M`` but then meets ``I``, not a separator.
#:
#: The leading lookahead is load-bearing: every group in the alternation is
#: optional, so without it the pattern matches the *empty* numeral and a
#: heading opening with bare punctuation — ". Foo" — reads as section one.
_ROMAN_SECTION = re.compile(
    r"^(?=[MDCLXVI])"
    r"(M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))[.)]\s+\S"
)

#: A single capital letter opening a heading, closed by a dot or parenthesis.
#: The separator is what keeps "A Contributions" — a word — unnumbered.
_LETTER_SECTION = re.compile(r"^([A-Z])[.)]\s+\S")

#: The depth a lettered subsection claims when no numbered section is open —
#: still a subsection of *something*, just of nothing this document names.
_UNPARENTED_LETTER_DEPTH = 2


def outline_depths(headings: Sequence[str]) -> list[Optional[int]]:
    """The depth each heading's own numbering claims, in document order.

    ``None`` for a heading that carries no number — front matter
    ("Abstract"), an unnumbered sub-subsection ("Self-consistency loop"),
    or a document that numbers nothing at all. Placing those is the
    caller's job (IR-248), and it needs to know which headings are
    numbered in order to do it.

    Takes the whole sequence because neither of the two new styles can be
    read from a heading alone. An ambiguous single letter needs the run it
    does or does not continue, and a letter's *depth* is relative — ``A.``
    is one level below whatever numbered section is open, which is depth 2
    under ``I.`` and depth 3 under ``3.2``. The state carried across
    headings is exactly that: the open numbered section's depth, and the
    last lettered subsection under it.

    **Known false positive, inherited rather than introduced:** a decimal
    measurement is lexically identical to a section number, so "3.5 kg of
    Feed" still reads as depth 2 (IR-242). Nothing here makes that more
    likely — the two new styles both require a separator a measurement does
    not have.
    """
    depths: list[Optional[int]] = []
    # The numbered section a lettered subsection would hang off, and the
    # last letter seen under it. Any new numbered heading opens a fresh
    # scope and so clears the run — subsections restart at `A.` under `3.2`
    # just as they do under `3.`
    open_section_depth = 0
    last_letter: Optional[str] = None

    for heading in headings:
        text = heading.strip()

        decimal = DECIMAL_SECTION_NUMBER.match(text)
        if decimal is not None:
            depth = decimal.group(1).count(".") + 1
            open_section_depth, last_letter = depth, None
            depths.append(depth)
            continue

        letter = _LETTER_SECTION.match(text)
        roman = _ROMAN_SECTION.match(text)

        # The precedence rule, in one expression: a letter wins unless it is
        # also a roman numeral, and even then it wins if it is continuing an
        # open lettered run.
        if letter is not None and (
            roman is None or _continues_letter_run(letter.group(1), last_letter)
        ):
            last_letter = letter.group(1)
            depths.append(
                open_section_depth + 1
                if open_section_depth
                else _UNPARENTED_LETTER_DEPTH
            )
            continue

        if roman is not None:
            open_section_depth, last_letter = 1, None
            depths.append(1)
            continue

        depths.append(None)

    return depths


def _continues_letter_run(letter: str, last_letter: Optional[str]) -> bool:
    """Whether this letter is the next one in an open lettered run.

    Checked *before* the roman test, so that the six letters which are also
    numerals are read as subsections when the document is plainly still
    lettering: ``A``, ``B``, then ``C`` is a subsection, while ``C`` with no
    run open is section 100. A run has to be consecutive to count — ``B.``
    followed by ``I.`` is a new section, not subsection nine.
    """
    if last_letter is None:
        return False
    return ord(letter) == ord(last_letter) + 1
