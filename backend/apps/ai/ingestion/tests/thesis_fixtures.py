"""Five thesis shapes, as documents rather than PDFs (IR-116 H).

The acceptance criteria name five fixture documents: a text-layer thesis, a
scanned one, one heavy with tables, one with a long bibliography, and one in
mixed English and Cebuano. They are built here as ``NormalizedDocument``
values, not as PDF files, for the reason the whole chunker is pure — the
pipeline's behaviour on each shape is decidable without a Docling container,
a database or a fixture binary in the repository.

That is not a substitute for the manual run on real submissions, which is
the ticket's actual exit criterion and cannot be automated. These fixtures
answer "does the pipeline handle this shape without dropping or emptying a
chunk"; a person reading fifty real chunks answers "is the output any good".

Every element carries a page, because "every chunk maps back to a page" is
one of the properties the pipeline is asserted on.
"""

from apps.ai.chunking.document import (
    CAPTION,
    HEADING,
    LIST_ITEM,
    PAGE_FOOTER,
    PAGE_HEADER,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)

PAGE_SIZE = (612.0, 792.0)


def _box(page: int, top: float) -> BoundingBox:
    return BoundingBox(page=page, left=72.0, top=top, right=540.0, bottom=top + 42.0)


def _element(kind: str, text: str, page: int, *, level=None, top: float = 100.0):
    return DocumentElement(
        kind=kind, text=text, level=level, page=page, bboxes=(_box(page, top),)
    )


def _pages(count: int) -> dict[int, tuple[float, float]]:
    return {page: PAGE_SIZE for page in range(1, count + 1)}


# ---------------------------------------------------------------------------
# 1 · A text-layer thesis — the ordinary case
# ---------------------------------------------------------------------------

_METHODOLOGY = (
    "Samples were collected weekly from twelve ponds across three barangays "
    "in Cebu province between January and December 2024. Each pond was "
    "sampled at three depths using a Van Dorn bottle, and the composite was "
    "fixed on site before transport to the laboratory."
)

_FINDINGS = (
    "Mean feed conversion ratio fell from 1.82 to 1.54 over the trial period. "
    "The reduction was significant at the five percent level in ponds "
    "receiving the supplemented diet, and was not significant in the control."
)

TEXT_LAYER_THESIS = NormalizedDocument(
    title="Optimization of Tilapia Feed Conversion in Freshwater Ponds",
    elements=(
        _element(HEADING, "1 Introduction", 4, level=1, top=90.0),
        _element(PARAGRAPH, "Aquaculture supplies a growing share of protein "
                 "consumed in the Visayas, and feed is its largest recurring "
                 "cost.", 4, top=140.0),
        _element(HEADING, "3 Methodology", 12, level=1, top=90.0),
        _element(HEADING, "3.2 Sampling Procedure", 12, level=2, top=130.0),
        _element(PARAGRAPH, _METHODOLOGY, 12, top=180.0),
        _element(PARAGRAPH, "Dissolved oxygen was logged every fifteen minutes "
                 "by a moored sonde, and the logger was calibrated fortnightly "
                 "against a Winkler titration.", 13, top=90.0),
        _element(HEADING, "4 Results", 18, level=1, top=90.0),
        _element(PARAGRAPH, _FINDINGS, 18, top=140.0),
        _element(CAPTION, "Figure 4.1 Feed conversion ratio by treatment.", 19, top=520.0),
    ),
    page_sizes=_pages(20),
)


# ---------------------------------------------------------------------------
# 2 · A scanned thesis — OCR artefacts the normalizer is there to remove
# ---------------------------------------------------------------------------
#
# Docling emits coordinates for OCR'd text too, so the regions are present;
# what a scan adds is running headers on every page, stranded folios, and
# words hyphenated across a line or page break.

SCANNED_THESIS = NormalizedDocument(
    title="Water Quality Monitoring in Coastal Barangays",
    elements=(
        _element(PAGE_HEADER, "WATER QUALITY MONITORING", 7, top=40.0),
        _element(HEADING, "2 Review of Related Literature", 7, level=1, top=90.0),
        _element(PARAGRAPH, "Earlier surveys of the same coastline reported "
                 "seasonal turbidity peaks that coincided with the south-west "
                 "monsoon, though the sampling method-", 7, top=140.0),
        _element(PARAGRAPH, "ology differed from the one adopted here in both "
                 "frequency and depth.", 8, top=90.0),
        _element(PAGE_FOOTER, "Cebu Institute of Technology - University", 7, top=740.0),
        _element(PARAGRAPH, "14", 7, top=760.0),
        _element(PARAGRAPH, "xiv", 8, top=760.0),
        _element(PARAGRAPH, "Turbidity was measured in nephelometric turbidity "
                 "units at each of the six stations, and the readings were "
                 "averaged over three consecutive tides.", 8, top=140.0),
    ),
    page_sizes=_pages(9),
)


# ---------------------------------------------------------------------------
# 3 · Table-heavy — forty rows under one header
# ---------------------------------------------------------------------------

TABLE_HEAVY_THESIS = NormalizedDocument(
    title="Growth Performance Across Forty Sampling Stations",
    elements=(
        _element(HEADING, "4 Results", 22, level=1, top=90.0),
        _element(TABLE_HEADER, "| Station | Mean weight (g) | Survival (%) |", 22, top=130.0),
        *(
            _element(
                TABLE_ROW,
                f"| S{index:02d} | {380 + index * 3} | {88 - index % 7} |",
                22 + index // 20,
                top=150.0 + (index % 20) * 15.0,
            )
            for index in range(40)
        ),
        _element(CAPTION, "Table 4.1 Growth performance by station.", 23, top=600.0),
    ),
    page_sizes=_pages(24),
)


# ---------------------------------------------------------------------------
# 4 · A long bibliography — 10-20% of a thesis by tokens, and pure noise
# ---------------------------------------------------------------------------

_REFERENCES = tuple(
    _element(
        LIST_ITEM,
        f"Author, A. B., and Cruz, D. E. ({1998 + index}). A study of pond "
        f"aquaculture in the Visayas. Philippine Journal of Fisheries, "
        f"{index + 1}(2), {index * 11 + 3}-{index * 11 + 19}.",
        60 + index // 8,
        top=100.0 + (index % 8) * 60.0,
    )
    for index in range(32)
)

BIBLIOGRAPHY_THESIS = NormalizedDocument(
    title="Pond Aquaculture Practices in the Central Visayas",
    elements=(
        _element(HEADING, "5 Conclusion", 58, level=1, top=90.0),
        _element(PARAGRAPH, "Weekly sampling proved sufficient to detect the "
                 "seasonal signal, and the supplemented diet paid for itself "
                 "within two production cycles.", 58, top=140.0),
        _element(HEADING, "References", 60, level=1, top=90.0),
        *_REFERENCES,
    ),
    page_sizes=_pages(64),
)


# ---------------------------------------------------------------------------
# 5 · Mixed English and Cebuano — combining marks that must not be split
# ---------------------------------------------------------------------------
#
# The interview quotes are written with decomposed combining marks (U+0303,
# U+0301) rather than precomposed characters, because that is the form a
# grapheme-level split can break and a precomposed one cannot.

_CEBUANO = (
    "Ang mga mananagat sa barangay nag-ingon nga ang anĩ sa isda "
    "mikunhod sukad sa miaging tuig. “Kaniadto, daghan pa mi og kuha,” "
    "matud pa ni Manó Berting, usa ka mananagat nga tres-katuig na "
    "nangisda sa maong dapit."
)

MIXED_LANGUAGE_THESIS = NormalizedDocument(
    title="Fisherfolk Perceptions of Declining Catch in Cordova, Cebu",
    elements=(
        _element(HEADING, "4.3 Interview Findings", 31, level=2, top=90.0),
        _element(PARAGRAPH, "Respondents consistently described a decline they "
                 "dated to the early 2010s.", 31, top=130.0),
        _element(PARAGRAPH, _CEBUANO, 31, top=200.0),
        _element(PARAGRAPH, "Translated, the respondent contrasts present catch "
                 "volumes with those he recalls from two decades earlier.", 32, top=90.0),
    ),
    page_sizes=_pages(33),
)


ALL_FIXTURES = {
    "text_layer": TEXT_LAYER_THESIS,
    "scanned": SCANNED_THESIS,
    "table_heavy": TABLE_HEAVY_THESIS,
    "bibliography": BIBLIOGRAPHY_THESIS,
    "mixed_language": MIXED_LANGUAGE_THESIS,
}
