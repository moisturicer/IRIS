"""
IR-665: an upload is accepted only if its content is a PDF.

`pdf_upload_problem` trusted the file name and the declared content type, both
of which the client chooses, so `payload.exe` renamed to `paper.pdf` was stored
and sent to extraction. It now reads the bytes.

**Seam: the validator every upload path shares**, plus one upload through the
API to show a refusal stores nothing.
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from pypdf import PdfWriter

from apps.documents.testing import pdf_upload, real_pdf_bytes
from apps.documents.validators import MAX_PDF_SIZE_BYTES, pdf_upload_problem

NOT_A_PDF = "This file is not a readable PDF."


def upload(content, name="paper.pdf", content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class PdfContentTests(SimpleTestCase):

    def test_a_real_pdf_is_accepted(self):
        self.assertIsNone(pdf_upload_problem(upload(real_pdf_bytes())))

    def test_a_multi_page_pdf_is_accepted(self):
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=200)
        buffer = BytesIO()
        writer.write(buffer)
        self.assertIsNone(pdf_upload_problem(upload(buffer.getvalue())))

    def test_bytes_before_the_signature_are_tolerated_as_readers_do(self):
        self.assertIsNone(pdf_upload_problem(upload(b"\n\n" + real_pdf_bytes())))

    def test_a_renamed_program_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b"MZ\x90\x00" + b"\x00" * 2048)), NOT_A_PDF)

    def test_html_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b"<html><script>x</script></html>")), NOT_A_PDF)

    def test_an_empty_file_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b"")), NOT_A_PDF)

    def test_a_signature_with_nothing_behind_it_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b"%PDF-1.7 fake bytes")), NOT_A_PDF)

    def test_garbage_behind_a_signature_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b"%PDF-1.7\n" + b"\x8f" * 4096)), NOT_A_PDF)

    def test_a_signature_too_far_in_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(b" " * 2048 + real_pdf_bytes())), NOT_A_PDF)

    def test_a_truncated_pdf_with_no_pages_left_is_refused(self):
        self.assertEqual(pdf_upload_problem(upload(real_pdf_bytes()[:60])), NOT_A_PDF)

    def test_the_name_and_type_are_still_checked(self):
        self.assertEqual(
            pdf_upload_problem(upload(real_pdf_bytes(), name="paper.exe")), "Only PDF files are accepted.",
        )
        self.assertEqual(
            pdf_upload_problem(upload(real_pdf_bytes(), content_type="text/plain")),
            "Only PDF files are accepted.",
        )

    def test_the_size_limit_still_applies_and_is_checked_before_parsing(self):
        oversized = upload(b"not read")
        oversized.size = MAX_PDF_SIZE_BYTES + 1
        self.assertIn("exceeds", pdf_upload_problem(oversized))

    def test_the_file_can_still_be_read_from_the_start_afterwards(self):
        content = real_pdf_bytes()
        file = upload(content)

        pdf_upload_problem(file)

        self.assertEqual(file.read(), content)

    def test_the_shared_helper_is_named_like_an_upload(self):
        file = pdf_upload("thesis.pdf")
        self.assertEqual((file.name, file.content_type), ("thesis.pdf", "application/pdf"))
        self.assertIsNone(pdf_upload_problem(file))
