"""Source-backed metadata suggestions (IR-833, IR-830 decisions 14-15).

`GET /records/<id>/metadata-suggestions/` keeps its legacy `suggestions`
projection and adds `fields`: one entry per suggested value, carrying the
value, where in the PDF it was found when that is known, and whether Publish
may fill it in without asking. Only title and abstract may be; authors,
keywords and publication year are offered for the author to accept, and only
when the PDF labels them.

Tests act at the REST seam. The stored structure is written with the
extraction package's own serializer, the established fake boundary: no
extractor runs and no vendor is called.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rest_framework.test import APITestCase

from apps.ai.chunking.document import (
    HEADING, PAGE_FOOTER, PAGE_HEADER, PARAGRAPH, BoundingBox, DocumentElement, NormalizedDocument,
)
from apps.ai.extraction.serialization import document_to_json
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus

TITLE = "Solar-Powered Irrigation for Upland Farms"


def _heading(text, page=None):
    return DocumentElement(kind=HEADING, text=text, page=page)


def _paragraph(text, page=None, bbox=None):
    return DocumentElement(kind=PARAGRAPH, text=text, page=page, bboxes=(bbox,) if bbox else ())


class SuggestionFieldsTests(APITestCase):
    def setUp(self):
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        self.record = Record.objects.create(
            title="thesis", abstract="", record_type=record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.DRAFT,
            abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake", content_type="application/pdf"),
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _read(self, *elements, title=TITLE):
        PdfExtraction.objects.filter(record=self.record).delete()
        PdfExtraction.objects.create(
            record=self.record, kind=DocumentKind.MANUSCRIPT, status="done",
            source_revision=self.record.manuscript_revision,
            structure=document_to_json(NormalizedDocument(title=title, elements=tuple(elements))),
        )
        self.client.force_authenticate(self.owner)
        return self.client.get(reverse("record-metadata-suggestions", args=[self.record.id])).data

    def _value(self, data, field):
        entry = data["fields"][field]
        return None if entry is None else entry["value"]

    # ── Abstracts ────────────────────────────────────────────────────────

    def test_an_inline_abstract_label_starts_the_abstract(self):
        data = self._read(
            _heading(TITLE),
            _paragraph("Abstract— Upland farms lose most of their dry-season yield."),
            _paragraph("We built a solar pump and measured it for a year."),
            _heading("1. Introduction"),
            _paragraph("Irrigation in the uplands has always been hard."),
        )

        expected = ("Upland farms lose most of their dry-season yield.\n\n"
                    "We built a solar pump and measured it for a year.")
        self.assertEqual(self._value(data, "abstract"), expected)
        self.assertEqual(data["suggestions"]["abstract"], expected)

    def test_a_numbered_abstract_heading_is_an_abstract_heading(self):
        for heading in ("1. Abstract", "I. ABSTRACT", "Abstract:"):
            with self.subTest(heading=heading):
                data = self._read(_heading(heading), _paragraph("We measured a solar pump."), _heading("2. Methods"))

                self.assertEqual(self._value(data, "abstract"), "We measured a solar pump.")

    def test_filipino_and_spanish_abstract_headings_are_abstract_headings(self):
        for heading in ("Abstrak", "BUOD", "Resumen:"):
            with self.subTest(heading=heading):
                data = self._read(_heading(heading), _paragraph("Sinukat namin ang solar pump."), _heading("Panimula"))

                self.assertEqual(self._value(data, "abstract"), "Sinukat namin ang solar pump.")

    def test_an_inline_label_deep_in_a_paper_with_no_headings_is_not_read(self):
        body = [_paragraph(f"Paragraph {n} of the body.") for n in range(80)]
        data = self._read(
            *body,
            _paragraph("Abstract: a summary quoted from another paper."),
            _paragraph("Keywords: these belong to a later chapter."),
        )

        self.assertIsNone(data["fields"]["abstract"])
        self.assertIsNone(data["fields"]["keywords"])

    def test_a_sentence_that_merely_begins_with_the_word_is_not_an_abstract(self):
        data = self._read(_paragraph("Abstract reasoning is hard to measure in children."))

        self.assertIsNone(data["fields"]["abstract"])

    def test_the_abstract_keeps_its_paragraphs_drops_page_furniture_and_stops_at_keywords(self):
        data = self._read(
            _heading("Abstract"),
            _paragraph("Upland farms lose most of their dry-season yield."),
            DocumentElement(kind=PAGE_FOOTER, text="iii"),
            DocumentElement(kind=PAGE_HEADER, text="CIT University"),
            _paragraph("We built a solar pump\nand measured it for a year."),
            _paragraph("Keywords: irrigation; solar pumps"),
            _paragraph("This is not the abstract."),
        )

        self.assertEqual(
            self._value(data, "abstract"),
            "Upland farms lose most of their dry-season yield.\n\nWe built a solar pump\nand measured it for a year.",
        )

    def test_an_overlong_abstract_is_offered_whole_for_review_and_not_filled_in(self):
        long_text = "word " * 1200
        data = self._read(_heading("Abstract"), _paragraph(long_text))

        entry = data["fields"]["abstract"]
        self.assertEqual(entry["value"], long_text.strip())
        self.assertTrue(entry["exceeds_limit"])
        self.assertFalse(entry["auto_apply"])

    def test_non_english_text_is_kept_as_written(self):
        data = self._read(
            _heading("Buod"),
            _heading("Abstract"),
            _paragraph("Ang pag-aaral na ito ay sumusuri sa patubig — résumé, naïve, 日本語."),
            title="Patubig sa Kabundukan: Isang Pag-aaral",
        )

        self.assertEqual(self._value(data, "title"), "Patubig sa Kabundukan: Isang Pag-aaral")
        self.assertEqual(self._value(data, "abstract"), "Ang pag-aaral na ito ay sumusuri sa patubig — résumé, naïve, 日本語.")

    # ── What may be filled in unasked ────────────────────────────────────

    def test_only_title_and_abstract_are_filled_in_unasked(self):
        data = self._read(
            _heading(TITLE),
            _paragraph("Authors: Juan dela Cruz; Maria Santos"),
            _paragraph("Keywords: irrigation, solar pumps, upland farming"),
            _paragraph("Publication year: 2024"),
            _heading("Abstract"),
            _paragraph("We built a solar pump."),
        )

        self.assertTrue(data["fields"]["title"]["auto_apply"])
        self.assertTrue(data["fields"]["abstract"]["auto_apply"])
        for field in ("authors", "keywords", "publication_year"):
            with self.subTest(field=field):
                self.assertFalse(data["fields"][field]["auto_apply"])

    # ── Labelled front matter ────────────────────────────────────────────

    def test_labelled_authors_keywords_and_year_are_offered_in_order(self):
        data = self._read(
            _heading(TITLE),
            _paragraph("Proponents: Juan dela Cruz1, Maria Santos* and Jose Rizal"),
            _paragraph("Index Terms— irrigation; solar pumps; upland farming."),
            _paragraph("Date published: March 2024"),
            _heading("1. Introduction"),
        )

        self.assertEqual(self._value(data, "authors"), ["Juan dela Cruz", "Maria Santos", "Jose Rizal"])
        self.assertEqual(self._value(data, "keywords"), ["irrigation", "solar pumps", "upland farming"])
        self.assertEqual(self._value(data, "publication_year"), 2024)
        self.assertEqual(data["fields"]["authors"]["basis"], "labelled_front_matter")

    def test_names_written_surname_first_are_ambiguous_and_offered_not_at_all(self):
        data = self._read(_paragraph("Authors: Cruz, Juan, Santos, Maria"))

        self.assertIsNone(data["fields"]["authors"])

    def test_two_different_years_are_ambiguous(self):
        data = self._read(_paragraph("Published: 2023, revised 2024"))

        self.assertIsNone(data["fields"]["publication_year"])

    def test_unlabelled_names_and_dates_are_not_read(self):
        """The line under a title is usually its authors, and the cover page
        names a year -- but nothing labels them, so nothing is offered. Above
        all, the account submitting is never taken for an author."""
        data = self._read(
            _heading(TITLE),
            _paragraph("Juan dela Cruz, Maria Santos"),
            _paragraph("Cebu City, 2024"),
            _heading("Abstract"),
            _paragraph("We built a solar pump."),
        )

        for field in ("authors", "keywords", "publication_year"):
            with self.subTest(field=field):
                self.assertIsNone(data["fields"][field])

    def test_a_label_in_the_body_is_not_front_matter(self):
        data = self._read(
            _heading(TITLE),
            _heading("1. Introduction"),
            _paragraph("Keywords: these belong to a later chapter."),
        )

        self.assertIsNone(data["fields"]["keywords"])

    def test_nothing_is_read_into_completion_year_origin_adviser_or_routing(self):
        data = self._read(_paragraph("Publication year: 2024"), _paragraph("Adviser: Dr. Maria Santos"))

        self.assertEqual(set(data["fields"]), {"title", "abstract", "authors", "keywords", "publication_year"})

    # ── Provenance ───────────────────────────────────────────────────────

    def test_a_value_names_its_page_and_region_only_when_the_structure_records_them(self):
        box = BoundingBox(page=1, left=72.0, top=100.0, right=520.0, bottom=180.0)
        data = self._read(_paragraph("Abstract: We built a solar pump.", page=1, bbox=box))
        self.assertEqual(data["fields"]["abstract"]["page"], 1)
        self.assertEqual(data["fields"]["abstract"]["region"],
                         {"page": 1, "left": 72.0, "top": 100.0, "right": 520.0, "bottom": 180.0})

        data = self._read(_heading("Abstract", page=2), _paragraph("We built a solar pump."))
        self.assertEqual(data["fields"]["abstract"]["page"], 2)
        self.assertIsNone(data["fields"]["abstract"]["region"])

        data = self._read(_heading("Abstract"), _paragraph("We built a solar pump."))
        self.assertIsNone(data["fields"]["abstract"]["page"])
        self.assertIsNone(data["fields"]["abstract"]["region"])

    def test_no_raw_structure_or_storage_path_is_exposed(self):
        data = self._read(_heading("Abstract"), _paragraph("We built a solar pump."))

        flat = repr(data)
        self.assertNotIn("abstracts/", flat)
        self.assertNotIn("elements", flat)
        self.assertNotIn("confidence", flat)

    def test_a_scan_with_no_text_is_ready_with_nothing_to_offer(self):
        data = self._read(title="")

        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["fields"], dict.fromkeys(("title", "abstract", "authors", "keywords", "publication_year")))
