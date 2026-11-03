"""IR-830: accepted PDF content, through the shared intake boundary."""
from io import BytesIO

import pytest
from django.test import override_settings
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from apps.documents.testing import pdf_upload
from apps.documents.validators import pdf_upload_problem


def encoded(writer):
    stream = BytesIO()
    writer.write(stream)
    file = pdf_upload()
    file.file = BytesIO(stream.getvalue())
    file.size = len(stream.getvalue())
    return file


def test_a_structurally_parseable_pdf_with_zero_pages_is_refused():
    assert pdf_upload_problem(encoded(PdfWriter())) == "This file is not a readable PDF."


@pytest.mark.parametrize("password", ["", "secret"])
def test_encryption_is_refused_even_when_no_password_is_needed(password):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    assert pdf_upload_problem(encoded(writer)) == "Encrypted PDFs are not accepted."


@pytest.mark.parametrize("action", ["/JavaScript", "/Launch", "/SubmitForm"])
def test_parsed_actions_are_refused(action):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.root_object[NameObject("/OpenAction")] = DictionaryObject({
        NameObject("/S"): NameObject(action),
        NameObject("/JS"): TextStringObject("app.alert('hello')"),
    })
    assert pdf_upload_problem(encoded(writer)) == "This PDF contains unsupported active content."


def test_embedded_files_are_refused():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_attachment("readme.txt", b"attachment")
    assert pdf_upload_problem(encoded(writer)) == "This PDF contains unsupported active content."


def test_indirect_action_names_cannot_hide_launch_actions():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.root_object[NameObject("/Action")] = DictionaryObject({
        NameObject("/S"): writer._add_object(NameObject("/Launch")),
        NameObject("/F"): TextStringObject("program.exe"),
    })
    assert pdf_upload_problem(encoded(writer)) == "This PDF contains unsupported active content."


def test_extra_dictionary_type_cannot_hide_an_automatic_action():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.root_object[NameObject("/AA")] = DictionaryObject({
        NameObject("/Type"): NameObject("/Anything"),
        NameObject("/WC"): DictionaryObject({NameObject("/S"): NameObject("/Named"), NameObject("/N"): NameObject("/Print")}),
    })
    assert pdf_upload_problem(encoded(writer)) == "This PDF contains unsupported active content."


@pytest.mark.parametrize("uri", ["https://example.org/paper", "www.sdss.org", "ftp://example.org/paper"])
def test_ordinary_hyperlinks_and_innocent_keyword_text_remain_valid(uri):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_uri(0, uri, [0, 0, 100, 100])
    writer.add_metadata({"/Title": "/JavaScript and /EmbeddedFiles are discussed here"})
    assert pdf_upload_problem(encoded(writer)) is None


def test_opening_at_a_page_is_navigation_not_executable_content():
    from pypdf.generic import ArrayObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    writer.root_object[NameObject("/OpenAction")] = ArrayObject([page.indirect_reference, NameObject("/Fit")])
    assert pdf_upload_problem(encoded(writer)) is None


def test_a_non_action_dictionary_may_use_s_for_an_image_stream():
    from pypdf.generic import DecodedStreamObject
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    stream = DecodedStreamObject()
    stream.set_data(b"scientific image data")
    writer.root_object[NameObject("/AppData")] = DictionaryObject({
        NameObject("/S"): writer._add_object(stream.flate_encode()),
    })
    assert pdf_upload_problem(encoded(writer)) is None


@pytest.mark.parametrize("mime", ["application/octet-stream", "", None])
def test_structurally_valid_pdf_with_generic_mime_is_accepted(mime):
    file = pdf_upload()
    file.content_type = mime
    assert pdf_upload_problem(file) is None


def test_actual_child_hits_page_limit():
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    with override_settings(PDF_VALIDATION_MAX_PAGES=2):
        assert pdf_upload_problem(encoded(writer)) == "This PDF exceeds the processing limits."


def test_actual_child_hits_traversal_limit():
    with override_settings(PDF_VALIDATION_MAX_OBJECTS=2):
        assert pdf_upload_problem(pdf_upload()) == "This PDF exceeds the processing limits."


def test_actual_child_hits_memory_limit():
    with override_settings(PDF_VALIDATION_MEMORY_MIB=1):
        assert pdf_upload_problem(pdf_upload()) == "This PDF exceeds the processing limits."


def test_child_memory_budget_uses_its_current_footprint_after_exec(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from apps.documents import validators

    source = tmp_path / "source.pdf"
    source.write_bytes(pdf_upload().read())
    inspector = Path(validators.__file__).with_name("pdf_inspection.py")
    result = subprocess.run([
        sys.executable, "-c",
        "import os, sys; allocation = bytearray(300 * 1024 * 1024); "
        "del allocation; os.execv(sys.executable, [sys.executable, '-I', *sys.argv[1:]])",
        str(inspector), str(source), "256", "1000", "200000", "100",
    ], capture_output=True, timeout=15, check=False)
    assert result.returncode == 0


def test_actual_child_hits_wall_limit():
    with override_settings(PDF_VALIDATION_WALL_SECONDS=0.001):
        assert pdf_upload_problem(pdf_upload()) == "This PDF exceeds the processing limits."


def test_missing_limit_refuses_processing():
    with override_settings(PDF_VALIDATION_MAX_PAGES=None):
        assert pdf_upload_problem(pdf_upload()) == "PDF checking is temporarily unavailable. Please try again later."
