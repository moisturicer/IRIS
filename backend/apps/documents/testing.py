"""Real PDF bytes for tests that upload through the API (IR-665).

The upload validator opens what it is given, so a test that posts a file needs
one it can open. `content` is kept in the file as a comment, for the tests that
tell uploads apart by their bytes.
"""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from pypdf import PdfWriter


def real_pdf_bytes(content: bytes = b"") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue() + (b"\n%" + content + b"\n" if content else b"")


def pdf_upload(name: str = "paper.pdf", content: bytes = b"") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, real_pdf_bytes(content), content_type="application/pdf")


def send_drafted_requests(test, record, user, party):
    """
    Send `user`'s draft document requests as `party`, as their *Finish review*
    does (ADR-022 Amendment 9, IR-1325), for a test that needs a request out
    and is not about finishing a review. Notices run as on commit.
    """
    from django.db import transaction

    from .requests import send_drafts

    with test.captureOnCommitCallbacks(execute=True), transaction.atomic():
        send_drafts(record, user, str(party))
