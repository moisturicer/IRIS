"""Drawing a manuscript's first page in the IR-830 sandbox (IR-1241).

`render` is called directly where pypdfium2 runs; the real child needs Linux
(RLIMIT_AS), so those tests skip elsewhere and run on CI.
"""
import io
import sys

import pytest
from django.test import override_settings
from PIL import Image

from apps.documents.pdf_evidence import first_page as child
from apps.documents.pdf_evidence.tests.thesis import thesis_pdf
from apps.records import first_page

pytestmark = pytest.mark.django_required
linux = pytest.mark.skipif(sys.platform != "linux", reason="the sandbox needs Linux RLIMIT_AS")

LIMITS = {"PDF_EVIDENCE_WALL_SECONDS": 60, "PDF_EVIDENCE_MEMORY_MIB": 1024, "PDF_VALIDATION_MAX_PAGES": 1000}


def test_page_one_is_drawn_as_a_small_webp():
    image = child.render(thesis_pdf(), max_pages=1000)

    assert first_page.is_webp(image)
    assert len(image) < first_page.MAX_IMAGE_BYTES
    drawn = Image.open(io.BytesIO(image))
    assert drawn.format == "WEBP" and drawn.width == child.WIDTH
    assert drawn.height > drawn.width  # a portrait page, not a crop


def test_more_pages_than_the_limit_are_not_drawn():
    with pytest.raises(child.OverBudget):
        child.render(thesis_pdf(), max_pages=2)


def test_a_malformed_pdf_is_not_drawn():
    with pytest.raises(Exception):
        child.render(b"%PDF-1.7 not really a pdf", max_pages=1000)


@pytest.mark.parametrize("unset", ["PDF_EVIDENCE_WALL_SECONDS", "PDF_EVIDENCE_MEMORY_MIB",
                                   "PDF_VALIDATION_MAX_PAGES"])
def test_an_unset_limit_draws_nothing(unset):
    with override_settings(**{**LIMITS, unset: None}):
        assert first_page.render(thesis_pdf()) == (None, "limits_unset")


@override_settings(**LIMITS)
def test_a_file_over_the_upload_size_is_not_drawn(monkeypatch):
    from apps.documents.pdf_evidence import sandbox

    monkeypatch.setattr(sandbox, "MAX_SOURCE_BYTES", 10)
    assert first_page.render(thesis_pdf()) == (None, "over_limits")


@override_settings(**LIMITS)
def test_outside_linux_the_sandbox_refuses_rather_than_drawing_unconfined(monkeypatch):
    monkeypatch.setattr(first_page.sys, "platform", "win32")
    assert first_page.render(thesis_pdf()) == (None, "sandbox_unsupported")


@linux
@override_settings(**LIMITS)
def test_the_child_draws_a_thesis():
    image, error = first_page.render(thesis_pdf())

    assert error == ""
    assert Image.open(io.BytesIO(image)).width == child.WIDTH


@linux
@override_settings(**LIMITS)
def test_a_malformed_pdf_records_unreadable():
    assert first_page.render(b"%PDF-1.7 not really a pdf") == (None, "unreadable")


@linux
@override_settings(**{**LIMITS, "PDF_VALIDATION_MAX_PAGES": 2})
def test_more_pages_than_the_limit_records_over_limits():
    assert first_page.render(thesis_pdf()) == (None, "over_limits")


@linux
@override_settings(**{**LIMITS, "PDF_EVIDENCE_MEMORY_MIB": 1})
def test_a_child_over_its_memory_records_over_limits():
    assert first_page.render(thesis_pdf()) == (None, "over_limits")
