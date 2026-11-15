"""IR-989: the extractor quality gate's rule and measures."""

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.evaluation.extractor_gate import Arm, measure_document, verdict

BOX = (BoundingBox(page=1, left=0, top=0, right=10, bottom=10),)


def _heading(text, level, source="numbering", page=1):
    return DocumentElement(kind="heading", text=text, level=level, page=page,
                           level_source=source, bboxes=BOX)


def _paper(*elements):
    return NormalizedDocument(title="Paper", elements=tuple(elements))


def test_a_numbered_heading_off_its_usual_level_is_wrongly_nested():
    measures = measure_document(_paper(
        _heading("1 Introduction", 2),
        _heading("1.1 Background", 3),
        _heading("2 Method", 2),
        _heading("2.1 Setup", 2),  # a subsection at its parent's level
        _heading("3 Results", 2),
        _heading("3.1 Data", 3),
    ))

    assert measures["numbered_headings"] == 6
    assert measures["off_level"] == 1
    assert measures["off_level_examples"] == [[2, "2.1 Setup"]]


def test_roman_sections_and_lettered_subsections_are_read_as_numbering():
    measures = measure_document(_paper(
        _heading("I. INTRODUCTION", 2), _heading("A. Scope", 3),
        _heading("II. DESIGN", 2), _heading("B. Flits", 2),
    ))

    assert measures["numbered_headings"] == 4
    assert measures["off_level"] == 1


def test_captions_returned_as_headings_and_the_deciding_signals_are_counted():
    measures = measure_document(_paper(
        _heading("1 Introduction", 2, source="numbering"),
        _heading("Table 1: Results", 2, source="font"),
        _heading("Abstract", 2, source="bookmark"),
    ))

    assert measures["false_headings"] == ["Table 1: Results"]
    assert measures["heading_signals"] == {"numbering": 1, "font": 1, "bookmark": 1}


def test_formulas_count_as_latex_only_when_they_arrive_as_formula_text():
    measures = measure_document(_paper(
        DocumentElement(kind="formula", text=r"\frac{a}{b}", source_label="Formula", page=1),
        DocumentElement(kind="image", text="N-1 |A) = >>", source_label="Formula", figure="f2", page=1),
        DocumentElement(kind="paragraph", text="where $x_i$ and $y$ are given", page=1),
    ))

    assert measures["formulas"] == 2
    assert measures["latex_formulas"] == 1
    assert measures["inline_math"] == 2


def test_box_share_and_printed_pages_are_over_the_whole_document():
    measures = measure_document(_paper(
        DocumentElement(kind="paragraph", text="a", page=1, bboxes=BOX, printed_page_number="iv"),
        DocumentElement(kind="paragraph", text="b", page=2),
        DocumentElement(kind="paragraph", text="c", page=2, bboxes=BOX),
        DocumentElement(kind="paragraph", text="d", page=3, bboxes=BOX, printed_page_number="2"),
    ))

    assert measures["elements"] == 4
    assert measures["boxed_share"] == 0.75
    assert measures["pages"] == 3
    assert measures["printed_pages"] == 2

PAPERS = {"Paper A": 10, "Paper B": 3}


def _arm(recall, off_level, latex=None):
    return Arm(recall_reranked=recall, off_level=off_level, latex=latex or dict(PAPERS))


def test_unstructured_within_every_limit_is_eligible():
    result = verdict(llamaparse=_arm(0.929, 0), unstructured=_arm(0.909, 5))

    assert result.eligible
    assert [c.passed for c in result.checks] == [True, True, True]


def test_recall_lower_by_more_than_two_points_is_not_eligible():
    result = verdict(llamaparse=_arm(0.929, 0), unstructured=_arm(0.857, 0))

    assert not result.eligible
    assert [c.name for c in result.checks if not c.passed] == ["recall"]


def test_six_more_wrongly_nested_headings_is_not_eligible():
    result = verdict(llamaparse=_arm(0.9, 2), unstructured=_arm(0.9, 8))

    assert [c.name for c in result.checks if not c.passed] == ["headings"]


def test_a_paper_losing_all_its_latex_is_not_eligible():
    result = verdict(
        llamaparse=_arm(0.9, 0),
        unstructured=_arm(0.9, 0, {"Paper A": 12, "Paper B": 0}),
    )

    failed = [c for c in result.checks if not c.passed]
    assert [c.name for c in failed] == ["latex"]
    assert "Paper B" in failed[0].detail


def test_a_paper_with_no_latex_under_llamaparse_cannot_fail_the_latex_rule():
    result = verdict(
        llamaparse=_arm(0.9, 0, {"Paper A": 10, "Paper B": 0}),
        unstructured=_arm(0.9, 0, {"Paper A": 1, "Paper B": 0}),
    )

    assert result.eligible


# -- swapping stored reads on a database copy --------------------------------

import json  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import override_settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "extraction" / "tests" / "fixtures"
UNSTRUCTURED_RAW = FIXTURES / "unstructured_platform" / "figures" / "result.json"
LLAMAPARSE_RAW = FIXTURES / "llamaparse" / "numbered_headings" / "result.json"
FORMULA_ID = "88cc438785c425daf6435f2ebaf20200"


def _unstructured_paper(title):
    from apps.ai.extraction import document_to_json, extraction_hash
    from apps.ai.extraction.shaping_unstructured import shape_unstructured
    from apps.documents.models import DocumentKind, ExtractionFormula, PdfExtraction
    from apps.records.models import Record

    revision = uuid.uuid4()
    raw = {"elements": json.loads(UNSTRUCTURED_RAW.read_text(encoding="utf-8"))}
    document = shape_unstructured(raw)
    record = Record.objects.create(title=title, abstract="An abstract.", is_ip=False)
    Record.objects.filter(pk=record.pk).update(manuscript_revision=revision)
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, status="done", extractor="unstructured",
        extractor_version="general/v0:hi_res", raw_result=raw, pages_read=1,
        structure=document_to_json(document), content_hash=extraction_hash(document),
    )
    PdfExtraction.objects.filter(pk=extraction.pk).update(source_revision=revision)
    ExtractionFormula.objects.create(
        extraction=extraction, source_revision=revision, name=FORMULA_ID, page=1,
        image="formulas/x.png", latex=r"a^{2} + b^{2} = c^{2}",
    )
    return record


def _measure(question_set, out):
    call_command("extractor_gate", "measure", "--question-set", str(question_set), "--out", str(out))
    return json.loads(out.read_text(encoding="utf-8"))["papers"]["Gate paper"]


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_a_llamaparse_read_swaps_in_and_the_unstructured_read_swaps_back(tmp_path):
    _unstructured_paper("Gate paper")
    question_set = tmp_path / "set.json"
    question_set.write_text(json.dumps({"questions": [
        {"id": "q1", "question": "?", "expected": [{"record": "Gate paper", "page": 1, "quote": "x"}]},
    ]}), encoding="utf-8")
    shelf = tmp_path / "unstructured"
    call_command("extractor_gate", "export", "--question-set", str(question_set), "--out", str(shelf))
    before = _measure(question_set, tmp_path / "m0.json")

    llama = tmp_path / "llamaparse"
    llama.mkdir()
    (llama / "gate.json").write_text(json.dumps({
        "title": "Gate paper", "extractor": "llamaparse", "extractor_version": "2026-09-28",
        "raw_result": json.loads(LLAMAPARSE_RAW.read_text(encoding="utf-8")), "pages_read": 2,
        "credits": 50,
    }), encoding="utf-8")
    call_command("extractor_gate", "install", str(llama))
    swapped = _measure(question_set, tmp_path / "m1.json")

    call_command("extractor_gate", "install", str(shelf))
    restored = _measure(question_set, tmp_path / "m2.json")

    assert before["extractor"] == "unstructured" and before["latex_formulas"] == 1
    assert swapped["extractor"] == "llamaparse"
    assert swapped["content_hash"] != before["content_hash"]
    assert swapped["formula_crops"] == 0  # Unstructured's transcriptions do not apply
    assert swapped["numbered_headings"] > 0
    assert restored == before


def _files(tmp_path, name, recall, papers):
    measures = tmp_path / f"{name}-measures.json"
    measures.write_text(json.dumps({"papers": {
        title: {"off_level": off, "latex_formulas": latex} for title, (off, latex) in papers.items()
    }}), encoding="utf-8")
    run = tmp_path / f"{name}-run.json"
    run.write_text(json.dumps({"runs": [
        {"config": {"reranking": False}, "measures": {"recall@10": 0.5}},
        {"config": {"reranking": True}, "measures": {"recall@10": recall}},
    ]}), encoding="utf-8")
    return str(measures), str(run)


def test_the_verdict_reads_reranked_recall_and_sums_headings_across_papers(tmp_path):
    out = tmp_path / "verdict.json"
    call_command(
        "extractor_gate", "verdict",
        "--llamaparse", *_files(tmp_path, "lp", 0.929, {"A": (1, 40), "B": (2, 5)}),
        "--unstructured", *_files(tmp_path, "un", 0.857, {"A": (4, 38), "B": (3, 0)}),
        "--out", str(out),
    )

    result = json.loads(out.read_text(encoding="utf-8"))
    assert not result["eligible"]
    assert {c["name"]: c["passed"] for c in result["checks"]} == {
        "recall": False, "headings": True, "latex": False,
    }
