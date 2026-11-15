"""The extractor quality gate: Unstructured against LlamaParse (IR-989, ADR-067 decision 2).

The rule is fixed in advance and needs no sign-off. Proxy tier only (ADR-023).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from apps.ai.chunking.document import FORMULA, HEADING, NormalizedDocument

RECALL_MARGIN = 0.02
HEADING_MARGIN = 5

# Numbering patterns as IR-851's headings.py reads them.
_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+[A-Za-z]")
_ROMAN = re.compile(r"^(?=[IVX]+\.)(X{0,3})(IX|IV|V?I{0,3})\.\s+\S")
_LETTER = re.compile(r"^[A-H]\.\s+\S")
_FALSE = re.compile(r"^(table|fig\.?|figure)\s*[\dA-Z]|^a preprint$", re.I)
_INLINE_MATH = re.compile(r"(?<!\$)\$[^$\n]+\$(?!\$)")


def _depth(text: str, roman_paper: bool):
    if m := _DECIMAL.match(text):
        return m.group(1).count(".")
    if _ROMAN.match(text):
        return 0
    if roman_paper and _LETTER.match(text):
        return 1
    return None


def measure_document(document: NormalizedDocument) -> dict:
    """The gate's structure measures for one paper, as it would be chunked."""
    elements = document.elements
    headings = [e for e in elements if e.kind == HEADING]
    roman_paper = sum(1 for e in headings if _ROMAN.match(e.text)) >= 2
    numbered = [(e.level, e.text, _depth(e.text, roman_paper)) for e in headings]
    numbered = [(lv, t, d) for lv, t, d in numbered if d is not None and lv is not None]
    by_depth = defaultdict(list)
    for lv, _, d in numbered:
        by_depth[d].append(lv)
    usual = {d: Counter(v).most_common(1)[0][0] for d, v in by_depth.items()}
    off = [[lv, t] for lv, t, d in numbered if lv != usual[d]]
    formulas = [e for e in elements if e.kind == FORMULA or e.source_label == "Formula"]
    pages = {e.page for e in elements if e.page}
    return {
        "numbered_headings": len(numbered),
        "off_level": len(off),
        "off_level_examples": off[:6],
        "false_headings": [e.text for e in headings if _FALSE.match(e.text)],
        "heading_signals": dict(Counter(e.level_source or "unrecorded" for e in headings)),
        "formulas": len(formulas),
        "latex_formulas": sum(1 for e in formulas if e.kind == FORMULA and e.text.strip()),
        "inline_math": sum(len(_INLINE_MATH.findall(e.text)) for e in elements if e.kind != FORMULA),
        "elements": len(elements),
        "boxed_share": round(sum(1 for e in elements if e.bboxes) / len(elements), 3) if elements else None,
        "pages": len(pages),
        "printed_pages": len({e.page for e in elements if e.page and e.printed_page_number}),
    }


@dataclass(frozen=True)
class Arm:
    recall_reranked: float
    off_level: int
    #: LaTeX formulas per paper title.
    latex: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Verdict:
    checks: tuple[Check, ...]

    @property
    def eligible(self) -> bool:
        return all(c.passed for c in self.checks)


def arm_from_files(measures_path, run_path) -> Arm:
    """An arm from ``extractor_gate measure`` output and an ``eval_retrieval`` run file."""
    import json
    from pathlib import Path

    papers = json.loads(Path(measures_path).read_text(encoding="utf-8"))["papers"]
    runs = json.loads(Path(run_path).read_text(encoding="utf-8"))["runs"]
    reranked = [r for r in runs if r["config"].get("reranking")]
    if len(reranked) != 1:
        raise ValueError(f"{run_path}: expected one reranked run, found {len(reranked)}")
    return Arm(
        recall_reranked=reranked[0]["measures"]["recall@10"],
        off_level=sum(p["off_level"] for p in papers.values()),
        latex={title: p["latex_formulas"] for title, p in papers.items()},
    )


def verdict(*, llamaparse: Arm, unstructured: Arm) -> Verdict:
    drop = round(llamaparse.recall_reranked - unstructured.recall_reranked, 4)
    lost = sorted(t for t, n in llamaparse.latex.items() if n and not unstructured.latex.get(t))
    return Verdict((
        Check("recall", drop <= RECALL_MARGIN,
              f"recall@10 with reranking {unstructured.recall_reranked:.3f} against "
              f"{llamaparse.recall_reranked:.3f} (lower by {drop:+.3f}; limit {RECALL_MARGIN})"),
        Check("headings", unstructured.off_level <= llamaparse.off_level + HEADING_MARGIN,
              f"wrongly nested numbered headings {unstructured.off_level} against "
              f"{llamaparse.off_level} (limit {llamaparse.off_level + HEADING_MARGIN})"),
        Check("latex", not lost,
              "papers losing all LaTeX: " + (", ".join(lost) if lost else "none")),
    ))


# -- stored reads, swapped on a database copy --------------------------------

#: What a stored read is; everything else on the row is derived or bookkeeping.
READ_FIELDS = ("extractor", "extractor_version", "extractor_options", "raw_result",
               "pdf_evidence", "pages_read", "credits")


def export_read(extraction) -> dict:
    """The stored read of ``extraction``, keyed by its paper's title."""
    read = {name: getattr(extraction, name) for name in READ_FIELDS}
    read["credits"] = str(read["credits"]) if read["credits"] is not None else None
    read["source_revision"] = str(extraction.source_revision) if extraction.source_revision else None
    return {"title": extraction.record.title, **read}


def shape(read: dict):
    """The read re-shaped with today's code: the stored raw result is the record (ADR-067 decision 4)."""
    if read["extractor"] == "llamaparse":
        from apps.ai.extraction.shaping import shape_llamaparse

        return shape_llamaparse(read["raw_result"])
    if read["extractor"] == "unstructured":
        from apps.ai.extraction.shaping_unstructured import shape_unstructured

        return shape_unstructured(read["raw_result"], read.get("pdf_evidence") or None)
    raise ValueError(f"no shaping for extractor {read['extractor']!r}")


def install_read(read: dict) -> int:
    """Make ``read`` the stored manuscript read of the paper titled ``read['title']``.

    A read without a ``source_revision`` gets none, so Figures and formula
    transcriptions stored for another read never apply to it.
    """
    from apps.ai.extraction import document_to_json, extraction_hash, flatten_for_search
    from apps.documents.models import DocumentKind, PdfExtraction

    extraction = PdfExtraction.objects.get(record__title=read["title"], kind=DocumentKind.MANUSCRIPT)
    document = shape(read)
    # update(), not save(): no signal may queue a re-chunk of the live set.
    PdfExtraction.objects.filter(pk=extraction.pk).update(
        extractor=read["extractor"],
        extractor_version=read.get("extractor_version") or "",
        raw_result=read["raw_result"],
        pages_read=read.get("pages_read"),
        credits=read.get("credits"),
        extractor_options=read.get("extractor_options") or {},
        pdf_evidence=read.get("pdf_evidence") or {},
        source_revision=read.get("source_revision"),
        structure=document_to_json(document),
        extracted_text=flatten_for_search(document),
        content_hash=extraction_hash(document),
    )
    return extraction.pk


def measure_paper(extraction) -> dict:
    """The gate's measures for one stored read, as trial chunk sets would chunk it."""
    from apps.ai.extraction.shaping_unstructured import shaping_report
    from apps.ai.figure_descriptions import with_descriptions
    from apps.ai.formula_transcriptions import with_formulas

    document = with_formulas(with_descriptions(extraction.as_normalized_document(), extraction),
                             extraction)
    revision = {"source_revision": extraction.source_revision}
    measures = {
        "extractor": extraction.extractor,
        "extractor_version": extraction.extractor_version,
        "extractor_options": extraction.extractor_options,
        "content_hash": extraction.content_hash,
        "pages_billed": extraction.pages_read,
        "credits": str(extraction.credits) if extraction.credits is not None else None,
        "figures_stored": extraction.figures.filter(**revision).count(),
        "figures_described": extraction.figures.filter(**revision).exclude(description="").count(),
        "formula_crops": extraction.formulas.filter(**revision).count(),
        **measure_document(document),
    }
    if extraction.extractor == "unstructured":
        boxes = shaping_report(extraction.raw_result, extraction.pdf_evidence or None)["line_boxes"]
        lined = sum(boxes.values())
        measures["line_boxes"] = boxes
        measures["line_box_match_rate"] = round(boxes.get("matched", 0) / lined, 3) if lined else None
    return measures
