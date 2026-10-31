"""
IR-676: every copy saved through the download route is marked, or not served.

The footer names the downloader on every page, a grey "CIT-U" lies beneath the
content, and the PDF's metadata says the same (ADR-048, decisions 10 and 11).

**Seam: the API.** Pages are read back out of the response with pypdf.
"""

from io import BytesIO
from unittest import mock

from django.core.files.base import ContentFile
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.records.test_download_grant import Fixtures, _user
from core.enums import RequestStatus


def _text_pdf(pages=3, size=(612, 792)) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=size)
    for number in range(1, pages + 1):
        pdf.drawString(72, 400, f"Body of page {number}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _rewritten(source: bytes, change) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(source)))
    change(writer)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _opaque_scan_pdf() -> bytes:
    """One page that is nothing but an opaque image, as a scanner produces."""
    from PIL import Image

    image = BytesIO()
    Image.new("RGB", (612, 792), "white").save(image, format="PNG")
    image.seek(0)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    pdf.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class WatermarkFixtures(Fixtures):

    def use_manuscript(self, content: bytes):
        self.record.abstract_file.save("thesis.pdf", ContentFile(content), save=True)

    def copy(self, user=None) -> PdfReader:
        response = self.get(user)
        self.assertEqual(response.status_code, status.HTTP_200_OK, getattr(response, "data", ""))
        return PdfReader(BytesIO(b"".join(response.streaming_content)))


class MarkedCopyTests(WatermarkFixtures):

    def test_every_page_names_the_holder_of_the_grant(self):
        self.use_manuscript(_text_pdf(pages=3))
        grant = self.request_by()
        today = timezone.localdate().isoformat()

        pages = self.copy().pages

        self.assertEqual(len(pages), 3)
        for number, page in enumerate(pages, start=1):
            with self.subTest(page=number):
                text = " ".join(page.extract_text().split())
                self.assertIn(f"Body of page {number}", text)
                self.assertIn(
                    f"Downloaded by Test User (grant-reader@cit.edu) on {today} "
                    f"via CIT-U IRIS · request #{grant.pk}",
                    text,
                )

    def test_every_page_carries_the_diagonal_beneath_the_content(self):
        self.use_manuscript(_text_pdf(pages=2))
        self.request_by()

        for page in self.copy().pages:
            content = page.get_contents().get_data().decode("latin-1")
            # The diagonal is drawn first, so the page's own content covers it,
            # and the footer last, so nothing covers it.
            self.assertLess(content.index("(CIT"), content.index("(Body of page"))
            self.assertLess(content.index("(Body of page"), content.index("(Downloaded by"))

    def test_an_exempt_copy_says_why_in_place_of_a_request(self):
        self.use_manuscript(_text_pdf(pages=1))

        text = " ".join(self.copy(self.adviser).pages[0].extract_text().split())

        self.assertIn("via CIT-U IRIS · record adviser", text)
        self.assertNotIn("request #", text)

    def test_metadata_carries_the_same_identity_date_and_request(self):
        self.use_manuscript(_text_pdf(pages=1))
        grant = self.request_by()

        metadata = self.copy().metadata

        self.assertEqual(metadata["/DownloadedBy"], "Test User (grant-reader@cit.edu)")
        self.assertEqual(metadata["/DownloadedOn"], timezone.localdate().isoformat())
        self.assertEqual(metadata["/DownloadBasis"], f"request #{grant.pk}")

    def test_an_exempt_copys_metadata_gives_the_reason(self):
        self.use_manuscript(_text_pdf(pages=1))
        self.assertEqual(self.copy(self.owner).metadata["/DownloadBasis"], "record owner")

    def test_the_stored_file_is_unchanged(self):
        original = _text_pdf(pages=2)
        self.use_manuscript(original)
        self.request_by()

        self.copy()

        self.record.refresh_from_db()
        with self.record.abstract_file.open("rb") as stored:
            self.assertEqual(stored.read(), original)

    def test_a_copy_is_never_cached_for_someone_else(self):
        self.use_manuscript(_text_pdf(pages=1))
        self.request_by()
        self.assertEqual(self.get()["Cache-Control"], "private, no-store")

    def test_a_marked_copy_is_audited_as_served(self):
        self.use_manuscript(_text_pdf(pages=1))
        grant = self.request_by()

        self.copy()

        event = AuditEvent.objects.get(record=self.record, event_type="DOWNLOAD")
        self.assertEqual(event.metadata["source"], "grant")
        self.assertEqual(event.metadata["request"], grant.pk)
        self.assertNotIn("outcome", event.metadata)


class PageShapeTests(WatermarkFixtures):
    """Each footer has to land on the part of the page a reader can see."""

    def _footer_position(self, page):
        """The (x, y) the footer's text is drawn at, in page coordinates."""
        found = []

        def visit(text, _cm, tm, _font, _size):
            if "Downloaded by" in text:
                found.append((_cm[4] + tm[4], _cm[5] + tm[5]))

        page.extract_text(visitor_text=visit)
        self.assertTrue(found, "no footer on the page")
        return found[0]

    def test_a_cropped_page_keeps_its_footer_inside_the_crop(self):
        def crop(writer):
            for page in writer.pages:
                page.cropbox.lower_left = (100, 200)
                page.cropbox.upper_right = (500, 700)

        self.use_manuscript(_rewritten(_text_pdf(pages=1), crop))
        self.request_by()

        x, y = self._footer_position(self.copy().pages[0])

        self.assertTrue(100 <= x <= 500 and 200 <= y <= 700, (x, y))

    def test_a_rotated_page_keeps_its_footer(self):
        def rotate(writer):
            writer.pages[0].rotate(90)

        self.use_manuscript(_rewritten(_text_pdf(pages=1), rotate))
        self.request_by()

        page = self.copy().pages[0]

        self.assertIn("Downloaded by", page.extract_text())
        self.assertIn("Body of page 1", page.extract_text())
        # Upright once the copy is opened, so the footer reads along the bottom.
        self.assertEqual(page.rotation, 0)

    def test_a_scanned_page_still_shows_the_footer(self):
        self.use_manuscript(_opaque_scan_pdf())
        self.request_by()

        content = self.copy().pages[0].get_contents().get_data().decode("latin-1")

        self.assertLess(content.index(" Do"), content.index("(Downloaded by"))

    def test_a_long_identity_still_fits_on_a_narrow_page(self):
        self.use_manuscript(_text_pdf(pages=1, size=(300, 400)))
        reader = _user(f"{'very-long-address-' * 3}@cit.edu")
        self.record_request = self.request_by(reader)

        page = self.copy(reader).pages[0]

        content = page.get_contents().get_data().decode("latin-1")
        size = float(content.rsplit(" Tf", 1)[0].rsplit(" ", 1)[1])
        self.assertLess(size, 8)
        self.assertIn(reader.email, " ".join(page.extract_text().split()))

    def test_a_page_too_narrow_for_a_legible_footer_is_refused(self):
        self.use_manuscript(_text_pdf(pages=1, size=(100, 100)))
        self.request_by()
        self.assertEqual(self.get().status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_a_name_outside_the_built_in_font_is_refused_rather_than_lost(self):
        """A footer that cannot spell the holder's name does not identify the copy."""
        self.use_manuscript(_text_pdf(pages=1))
        reader = _user("grant-unicode@cit.edu")
        reader.first_name = "李"
        reader.save(update_fields=["first_name"])
        self.request_by(reader)

        response = self.get(reader)

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_a_filipino_name_prints_as_written(self):
        self.use_manuscript(_text_pdf(pages=1))
        reader = _user("grant-enye@cit.edu")
        reader.first_name = "Niño"
        reader.save(update_fields=["first_name"])
        self.request_by(reader)

        self.assertIn("Niño User", self.copy(reader).pages[0].extract_text())


class FailClosedTests(WatermarkFixtures):

    def assert_refused_and_audited(self, reason):
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY, reason)
        self.assertEqual(response.data["code"], "watermark_failed")
        self.assertIn("RDCO", response.data["detail"])
        event = AuditEvent.objects.get(record=self.record, event_type="DOWNLOAD", user=self.reader)
        self.assertEqual(event.metadata["outcome"], "watermark_failed")
        self.assertEqual(event.metadata["source"], "grant")

    def test_an_encrypted_manuscript_is_refused_and_audited(self):
        self.use_manuscript(_rewritten(_text_pdf(pages=1), lambda w: w.encrypt("secret")))
        self.request_by()
        self.assert_refused_and_audited("encrypted")

    def test_one_with_an_empty_password_is_refused_too(self):
        self.use_manuscript(_rewritten(_text_pdf(pages=1), lambda w: w.encrypt("")))
        self.request_by()
        self.assert_refused_and_audited("encrypted, empty password")

    def test_a_malformed_manuscript_is_refused_and_audited(self):
        self.use_manuscript(b"%PDF-1.7 this is not really a PDF")
        self.request_by()
        self.assert_refused_and_audited("malformed")

    def test_a_library_error_is_refused_and_audited(self):
        self.use_manuscript(_text_pdf(pages=1))
        self.request_by()
        with mock.patch("apps.records.watermark.PdfWriter", side_effect=RuntimeError("boom")):
            self.assert_refused_and_audited("library error")

    def test_a_refusal_for_access_writes_no_failure(self):
        self.use_manuscript(b"not a pdf")
        self.request_by(state=RequestStatus.DECLINED, expires_in=None)

        response = self.get()

        self.assertEqual(response.data["code"], "request_declined")
        self.assertFalse(AuditEvent.objects.filter(record=self.record, event_type="DOWNLOAD").exists())


class NoStoredCopyTests(WatermarkFixtures):

    def test_a_download_writes_nothing_to_storage(self):
        self.use_manuscript(_text_pdf(pages=1))
        self.request_by()

        with mock.patch("django.core.files.storage.base.Storage.save", side_effect=AssertionError("stored a copy")):
            self.copy()
