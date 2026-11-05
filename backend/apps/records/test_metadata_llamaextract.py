"""Publish suggestions sourced from LlamaExtract (IR-846, ADR-056 §15).

At IR-833's owner-only REST seam. The parse is IR-849's recorded
``two_columns`` LlamaParse result; the LlamaExtract reading is AUTHORED from
the vendor's documented response format (no recording exists yet), with its
citations pointing at text that is in that parse. No vendor is called.
"""

import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.ai.extraction.tests.llamaextract_vendor import two_columns_reading
from apps.ai.extraction.tests.llamaparse_fixtures import recorded, result_with
from apps.documents.models import DocumentKind, ManuscriptMetadata, PdfExtraction
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus


def _vendor_result(**changes):
    """The stored reading: LlamaExtract's values and citations, per field."""
    vendor = two_columns_reading()
    values = vendor["extract_result"]
    metadata = vendor["extract_metadata"]["field_metadata"]["document_metadata"]
    for field, change in changes.items():
        if change is None:
            values.pop(field, None)
            metadata.pop(field, None)
        else:
            value, meta = change
            values[field] = value
            metadata[field] = meta
    return {"values": values, "field_metadata": metadata}


class LlamaExtractSuggestionTests(APITestCase):
    def setUp(self):
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        self.record = Record.objects.create(
            title="two_columns.pdf", abstract="", record_type=record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.DRAFT,
            abstract_file=SimpleUploadedFile("two_columns.pdf", b"%PDF-1.7 fake", content_type="application/pdf"),
            manuscript_revision=uuid.uuid4(),
            is_embargoed=False, embargo_released_at=timezone.now(), dpa_accepted_at=timezone.now(),
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        self.extraction = PdfExtraction.objects.create(
            record=self.record, kind=DocumentKind.MANUSCRIPT, status="done", phase="ready",
            source_revision=self.record.manuscript_revision, extractor="llamaparse",
            raw_result=recorded("two_columns"),
        )

    def _reading(self, status=ManuscriptMetadata.DONE, result=None, revision=None):
        return ManuscriptMetadata.objects.create(
            extraction=self.extraction, source_revision=revision or self.record.manuscript_revision,
            status=status, result=_vendor_result() if result is None else result,
        )

    def _get(self, user=None):
        self.client.force_authenticate(user or self.owner)
        return self.client.get(reverse("record-metadata-suggestions", args=[self.record.id]))

    def _data(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        return response.data

    # ── Provenance ───────────────────────────────────────────────────────

    def test_each_value_says_where_llamaextract_found_it(self):
        self._reading()

        data = self._data()

        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["source"], "llamaextract")
        title = data["fields"]["title"]
        self.assertEqual(title["value"], "Two column study")
        self.assertEqual(title["source"], "llamaextract")
        self.assertEqual(title["page"], 1)
        self.assertEqual(title["matching_text"], "Two column study")
        self.assertEqual(title["confidence"], 0.97)
        # The heading's line box in the parse's grounding.
        region = title["region"]
        self.assertEqual(region["page"], 1)
        self.assertAlmostEqual(region["left"], 72.2)
        self.assertAlmostEqual(region["top"], 73.95)
        self.assertEqual(data["fields"]["authors"]["value"], ["Ana Cruz", "Ben Reyes"])
        self.assertEqual(data["fields"]["keywords"]["value"], ["columns", "reading order"])
        self.assertEqual(data["fields"]["publication_year"]["value"], 2026)
        # The legacy projection stays.
        self.assertEqual(data["suggestions"]["title"], "Two column study")
        self.assertEqual(data["suggestions"]["abstract"], "Left column one opens. Right column one resumes.")

    def test_matching_text_across_two_columns_is_located_by_its_lines(self):
        self._reading()

        region = self._data()["fields"]["abstract"]["region"]

        # Both line boxes: the left column's start to the right column's end.
        self.assertAlmostEqual(region["left"], 72.76, places=0)
        self.assertGreater(region["right"], 440)

    def test_a_value_with_no_citation_has_no_page_region_or_text(self):
        self._reading()

        keywords = self._data()["fields"]["keywords"]

        self.assertIsNone(keywords["page"])
        self.assertIsNone(keywords["region"])
        self.assertIsNone(keywords["matching_text"])

    def test_cited_text_not_in_the_parse_has_a_page_but_no_region(self):
        self._reading()

        authors = self._data()["fields"]["authors"]

        self.assertEqual(authors["page"], 1)
        self.assertEqual(authors["matching_text"], "Ana Cruz and Ben Reyes")
        self.assertIsNone(authors["region"])

    def test_an_unreported_confidence_is_absent_never_guessed(self):
        self._reading()

        self.assertIsNone(self._data()["fields"]["publication_year"]["confidence"])

    # ── Auto-apply ───────────────────────────────────────────────────────

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=None)
    def test_with_no_threshold_nothing_is_filled_in_unasked(self):
        self._reading()

        fields = self._data()["fields"]

        self.assertFalse(any(entry["auto_apply"] for entry in fields.values() if entry))
        self.assertFalse(any(entry["low_confidence"] for entry in fields.values() if entry))

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.9)
    def test_a_confident_found_title_and_abstract_may_be_filled_in(self):
        self._reading()

        fields = self._data()["fields"]

        self.assertTrue(fields["title"]["auto_apply"])
        self.assertTrue(fields["abstract"]["auto_apply"])
        for field in ("authors", "keywords", "publication_year"):
            self.assertFalse(fields[field]["auto_apply"], field)

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.95)
    def test_a_value_below_the_threshold_is_offered_and_marked_for_checking(self):
        self._reading()

        fields = self._data()["fields"]

        self.assertTrue(fields["title"]["auto_apply"])
        self.assertFalse(fields["title"]["low_confidence"])
        self.assertFalse(fields["abstract"]["auto_apply"])
        self.assertTrue(fields["abstract"]["low_confidence"])
        self.assertTrue(fields["authors"]["low_confidence"])

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.5)
    def test_a_confident_title_with_no_citation_is_not_filled_in(self):
        self._reading(result=_vendor_result(title=("Two column study", {"citation": [], "confidence": 0.99})))

        self.assertFalse(self._data()["fields"]["title"]["auto_apply"])

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.5)
    def test_a_confident_title_whose_text_is_not_in_the_parse_is_not_filled_in(self):
        cited = {"citation": [{"page": 1, "matching_text": "A Study Nobody Printed"}], "confidence": 0.99}
        self._reading(result=_vendor_result(title=("A Study Nobody Printed", cited)))

        title = self._data()["fields"]["title"]

        self.assertIsNone(title["region"])
        self.assertFalse(title["auto_apply"])

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.5)
    def test_a_confident_title_cited_to_other_text_is_not_filled_in(self):
        cited = {"citation": [{"page": 1, "matching_text": "Two column study"}], "confidence": 0.99}
        self._reading(result=_vendor_result(title=("A Study Nobody Printed", cited)))

        title = self._data()["fields"]["title"]

        self.assertIsNotNone(title["region"])
        self.assertFalse(title["auto_apply"])

    @override_settings(PUBLISH_AUTOFILL_MIN_CONFIDENCE=0.5)
    def test_an_overlong_title_is_offered_whole_and_never_filled_in(self):
        long_title = "Two column study " * 40
        cited = {"citation": [{"page": 1, "matching_text": "Two column study"}], "confidence": 0.99}
        self._reading(result=_vendor_result(title=(long_title, cited)))

        title = self._data()["fields"]["title"]

        self.assertEqual(title["value"], long_title.strip())
        self.assertTrue(title["exceeds_limit"])
        self.assertFalse(title["auto_apply"])

    # ── What is never read ───────────────────────────────────────────────

    def test_malformed_values_offer_nothing(self):
        self._reading(result=_vendor_result(
            authors=(["", "  "], {}), keywords=("not a list", {}), publication_year=("next year", {}),
        ))

        fields = self._data()["fields"]

        self.assertIsNone(fields["authors"])
        self.assertIsNone(fields["keywords"])
        self.assertIsNone(fields["publication_year"])

    def test_nothing_but_the_five_fields_is_offered(self):
        self._reading(result={
            **_vendor_result(),
            "values": {**_vendor_result()["values"], "adviser": "Dr. Santos", "completion_year": 2025},
        })

        self.assertEqual(
            set(self._data()["fields"]), {"title", "abstract", "authors", "keywords", "publication_year"},
        )

    def test_no_vendor_payload_job_id_or_storage_path_is_exposed(self):
        self._reading()

        text = str(self._data())

        for leak in ("pjb-", "ext-", "extract_metadata", "field_metadata", "grounded_items",
                     "two_columns.pdf", "credits"):
            self.assertNotIn(leak, text)

    # ── State and fallback ───────────────────────────────────────────────

    def test_while_llamaextract_reads_the_suggestions_are_pending(self):
        self._reading(status=ManuscriptMetadata.RUNNING, result={})

        self.assertEqual(self._data()["state"], "pending")

    def test_a_reading_left_running_past_its_budget_falls_back(self):
        reading = self._reading(status=ManuscriptMetadata.RUNNING, result={})
        ManuscriptMetadata.objects.filter(pk=reading.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=3),
            started_at=timezone.now() - timezone.timedelta(hours=2),
        )

        data = self._data()

        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["source"], "pdf_structure")

    def test_a_reading_that_waited_in_the_queue_gets_its_whole_budget_once_claimed(self):
        reading = self._reading(status=ManuscriptMetadata.RUNNING, result={})
        ManuscriptMetadata.objects.filter(pk=reading.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=2), started_at=timezone.now(),
        )

        self.assertEqual(self._data()["state"], "pending")

    def test_a_reading_never_claimed_past_its_budget_falls_back(self):
        reading = self._reading(status=ManuscriptMetadata.QUEUED, result={})
        ManuscriptMetadata.objects.filter(pk=reading.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=2),
        )

        data = self._data()

        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["source"], "pdf_structure")

    def _fallback_parse(self):
        items = [
            {"type": "heading", "level": 1, "value": "Solar Irrigation for Upland Farms",
             "bbox": [{"x": 72, "y": 70, "w": 300, "h": 18}]},
            {"type": "heading", "level": 2, "value": "Abstract", "bbox": [{"x": 72, "y": 100, "w": 60, "h": 12}]},
            {"type": "text", "value": "We pumped water with sunlight.", "bbox": [{"x": 72, "y": 120, "w": 200, "h": 10}]},
            {"type": "text", "value": "Keywords: solar, irrigation", "bbox": [{"x": 72, "y": 140, "w": 200, "h": 10}]},
            {"type": "heading", "level": 2, "value": "1 Introduction", "bbox": [{"x": 72, "y": 160, "w": 90, "h": 12}]},
        ]
        PdfExtraction.objects.filter(pk=self.extraction.pk).update(raw_result=result_with(items))

    def test_a_failed_reading_falls_back_to_the_shaped_documents_title_and_abstract(self):
        self._fallback_parse()
        self._reading(status=ManuscriptMetadata.FAILED, result={})

        data = self._data()

        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["source"], "pdf_structure")
        self.assertEqual(data["fields"]["title"]["value"], "Solar Irrigation for Upland Farms")
        self.assertEqual(data["fields"]["abstract"]["value"], "We pumped water with sunlight.")
        # LlamaParse papers are not read for labelled front matter.
        self.assertIsNone(data["fields"]["keywords"])

    def test_a_reading_that_found_nothing_falls_back_to_the_shaped_document(self):
        self._fallback_parse()
        self._reading(result={"values": {}, "field_metadata": {}})

        data = self._data()

        self.assertEqual(data["source"], "pdf_structure")
        self.assertEqual(data["fields"]["title"]["value"], "Solar Irrigation for Upland Farms")

    def test_with_no_reading_at_all_the_shaped_document_is_read(self):
        self._fallback_parse()

        data = self._data()

        self.assertEqual(data["source"], "pdf_structure")
        self.assertEqual(data["fields"]["title"]["value"], "Solar Irrigation for Upland Farms")

    def test_a_previous_revisions_reading_is_never_shown(self):
        self._fallback_parse()
        self._reading(revision=uuid.uuid4())

        data = self._data()

        self.assertEqual(data["source"], "pdf_structure")
        self.assertNotEqual(data["fields"]["title"]["value"], "Two column study")

    def test_a_paper_the_gate_now_refuses_reports_unsupported(self):
        self._reading()
        Record.objects.filter(pk=self.record.pk).update(dpa_accepted_at=None)

        data = self._data()

        self.assertEqual(data["state"], "unsupported")
        self.assertTrue(all(entry is None for entry in data["fields"].values()))

    # ── Who may see it ───────────────────────────────────────────────────

    def test_a_non_owner_gets_the_same_404_as_a_missing_record(self):
        self._reading()
        stranger = make_user("stranger@cit.edu", "Student")

        self.assertEqual(self._get(stranger).status_code, 404)

