"""GET /records/<id>/metadata-suggestions/ (IR-406, B1).

The IR-374 frontend redesign spec, §4.5 and Appendix D: the Publish dialog
offers the manuscript's own title and abstract as suggestions, read from the
Docling structure the manuscript extraction already stores. No LLM and no
vendor call -- the endpoint only reads a row that exists.

Tests act at the REST seam (spec §5, Seam 2). The extraction rows are built
with the extraction package's own serializer, so the stored structure is the
real wire format rather than a hand-written approximation of it.
"""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.chunking.document import (
    HEADING, PAGE_FOOTER, PAGE_HEADER, PARAGRAPH, DocumentElement, NormalizedDocument,
)
from apps.ai.extraction.serialization import document_to_json
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus


def _pdf(name="thesis.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.7 fake bytes", content_type="application/pdf")


def _structure(title, *elements):
    return document_to_json(NormalizedDocument(title=title, elements=tuple(elements)))


def _heading(text):
    return DocumentElement(kind=HEADING, text=text)


def _paragraph(text):
    return DocumentElement(kind=PARAGRAPH, text=text)


class MetadataSuggestionsTests(APITestCase):
    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        self.record = Record.objects.create(
            title="thesis", abstract="", record_type=self.record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.DRAFT,
            abstract_file=_pdf(),
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _extraction(self, status_value="done", structure=None):
        return PdfExtraction.objects.create(
            record=self.record,
            kind=DocumentKind.MANUSCRIPT,
            status=status_value,
            structure=structure or {},
        )

    def _store_as(self, name):
        # Only the stored name matters to this endpoint; no bytes are read.
        Record.objects.filter(pk=self.record.pk).update(abstract_file=name)

    def _get(self, user=None):
        if user is not None:
            self.client.force_authenticate(user)
        return self.client.get(
            reverse("record-metadata-suggestions", args=[self.record.id])
        )

    def test_a_read_manuscript_suggests_its_title(self):
        self._extraction(structure=_structure(
            "Solar-Powered Irrigation for Upland Farms",
            _heading("Solar-Powered Irrigation for Upland Farms"),
            _paragraph("Juan dela Cruz"),
        ))

        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "ready")
        self.assertEqual(
            response.data["suggestions"]["title"],
            "Solar-Powered Irrigation for Upland Farms",
        )
        self.assertEqual(response.data["source"], "pdf_structure")

    def test_the_abstract_is_the_text_under_the_abstract_heading(self):
        self._extraction(structure=_structure(
            "Solar-Powered Irrigation for Upland Farms",
            _heading("Solar-Powered Irrigation for Upland Farms"),
            _heading("ABSTRACT"),
            _paragraph("Upland farms lose most of their dry-season yield."),
            _paragraph("We built a solar pump and measured it for a year."),
            _heading("1. Introduction"),
            _paragraph("Irrigation in the uplands has always been hard."),
        ))

        response = self._get(self.owner)

        self.assertEqual(
            response.data["suggestions"]["abstract"],
            "Upland farms lose most of their dry-season yield.\n\n"
            "We built a solar pump and measured it for a year.",
        )

    def test_there_is_no_abstract_suggestion_without_an_abstract_heading(self):
        self._extraction(structure=_structure(
            "Solar-Powered Irrigation for Upland Farms",
            _heading("1. Introduction"),
            _paragraph("Irrigation in the uplands has always been hard."),
        ))

        response = self._get(self.owner)

        self.assertEqual(response.data["state"], "ready")
        self.assertIsNone(response.data["suggestions"]["abstract"])

    def test_a_title_that_is_only_the_file_name_is_not_suggested(self):
        """Docling falls back to the file name when a PDF names itself
        nothing. Offering that back would "suggest" the provisional title the
        draft already has (spec §4.5). Docling is handed the *stored* name,
        collision suffix and all, so that is what the fallback repeats."""
        self._store_as("abstracts/thesis_aB3dE9f.pdf")
        for title in ("thesis_aB3dE9f.pdf", "thesis_aB3dE9f"):
            with self.subTest(title=title):
                PdfExtraction.objects.filter(record=self.record).delete()
                self._extraction(structure=_structure(title, _paragraph("Body text.")))

                response = self._get(self.owner)

                self.assertEqual(response.data["state"], "ready")
                self.assertIsNone(response.data["suggestions"]["title"])

    def test_the_file_name_is_matched_the_way_storage_rewrote_it(self):
        """Storage turns spaces into underscores ("My Thesis Draft.pdf" is
        stored as My_Thesis_Draft.pdf), so a fallback title can differ from
        the stored name in case and separators and still be the file name."""
        self._store_as("abstracts/My_Thesis_Draft.pdf")
        self._extraction(structure=_structure("my thesis draft", _paragraph("Body.")))

        response = self._get(self.owner)

        self.assertIsNone(response.data["suggestions"]["title"])

    def test_a_scanned_pdf_with_no_text_is_ready_with_no_suggestions(self):
        self._extraction(structure=_structure(""))

        response = self._get(self.owner)

        self.assertEqual(response.data["state"], "ready")
        self.assertEqual(response.data["suggestions"], {"title": None, "abstract": None})

    def test_an_extraction_still_queued_or_running_is_pending(self):
        for stored_status in ("queued", "running"):
            with self.subTest(status=stored_status):
                PdfExtraction.objects.filter(record=self.record).delete()
                self._extraction(status_value=stored_status)

                response = self._get(self.owner)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["state"], "pending")
                self.assertEqual(
                    response.data["suggestions"], {"title": None, "abstract": None}
                )

    def test_a_failed_extraction_is_failed_with_no_suggestions(self):
        self._extraction(status_value="failed")

        response = self._get(self.owner)

        self.assertEqual(response.data["state"], "failed")
        self.assertEqual(response.data["suggestions"], {"title": None, "abstract": None})

    def test_a_draft_with_no_manuscript_extraction_is_unsupported(self):
        """Nothing was queued -- no manuscript yet, or one saved before
        manuscripts were extracted. There is nothing to read, which is not a
        failure (spec §4.5: `unsupported` shows the neutral line)."""
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "unsupported")
        self.assertEqual(response.data["suggestions"], {"title": None, "abstract": None})
        self.assertEqual(response.data["source"], "pdf_structure")

    def test_running_page_headers_and_footers_are_not_part_of_the_abstract(self):
        """An abstract that crosses a page break picks up the page's running
        head and folio. Those are furniture, not the author's text."""
        self._extraction(structure=_structure(
            "Solar-Powered Irrigation for Upland Farms",
            _heading("Abstract"),
            _paragraph("Upland farms lose most of their dry-season yield."),
            DocumentElement(kind=PAGE_FOOTER, text="iii"),
            DocumentElement(kind=PAGE_HEADER, text="CIT University"),
            _paragraph("We built a solar pump and measured it for a year."),
        ))

        response = self._get(self.owner)

        self.assertEqual(
            response.data["suggestions"]["abstract"],
            "Upland farms lose most of their dry-season yield.\n\n"
            "We built a solar pump and measured it for a year.",
        )


class MetadataSuggestionsAccessTests(APITestCase):
    """Owner-only, and a refusal reads like a missing record (IR-153).

    The suggestions are read from the manuscript itself, so anyone who may not
    download the manuscript must not get its title and abstract this way --
    including office staff and the Adviser, who may *read* the record but are
    not the one publishing it (spec Appendix D: "the owner through
    `visible_to()`, with a 404 otherwise").
    """

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        self.record = Record.objects.create(
            title="thesis", abstract="", record_type=self.record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.DRAFT,
            adviser=self.adviser,
        )
        Record.objects.filter(pk=self.record.pk).update(abstract_file="abstracts/thesis.pdf")
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        PdfExtraction.objects.create(
            record=self.record, kind=DocumentKind.MANUSCRIPT, status="done",
            structure=_structure("A Real Title", _heading("Abstract"), _paragraph("Text.")),
        )

    def _get(self, user=None):
        if user is not None:
            self.client.force_authenticate(user)
        return self.client.get(
            reverse("record-metadata-suggestions", args=[self.record.id])
        )

    def test_the_owner_gets_the_suggestions(self):
        response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["suggestions"]["title"], "A Real Title")

    def test_a_stranger_gets_404(self):
        response = self._get(make_user("stranger@cit.edu", "Student"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_readers_who_are_not_owners_get_404(self):
        """Each of these may read the record, so `visible_to()` alone would
        let them through."""
        Record.objects.filter(pk=self.record.pk).update(
            pipeline_status=PipelineStatus.PUBLISHED
        )
        readers = {
            "office staff": make_user("rdco@cit.edu", "RDCO"),
            "the assigned adviser": self.adviser,
            "any signed-in user, on a published record": make_user("reader@cit.edu", "Student"),
        }
        for who, user in readers.items():
            with self.subTest(who=who):
                response = self._get(user)

                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_anonymous_request_is_refused(self):
        response = self._get()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reading_suggestions_never_calls_docling(self):
        """No network call (spec §5, Seam 2): the endpoint reads the stored
        structure and never reaches the extractor, even when one is pending."""
        PdfExtraction.objects.filter(record=self.record).update(status="queued")

        with mock.patch(
            "apps.documents.tasks._build_extractor",
            side_effect=AssertionError("the extractor must not be called"),
        ):
            response = self._get(self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "pending")
