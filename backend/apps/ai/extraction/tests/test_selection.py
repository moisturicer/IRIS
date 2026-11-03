"""Which Extractor runs, and how a test replaces it (IR-838)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    DoclingExtractor,
    InMemoryExtractor,
    current_extractor,
    use_extractor,
    verify_extraction_configuration,
)

pytestmark = [pytest.mark.django_required]

DOCUMENT = NormalizedDocument(
    title="A paper",
    elements=(DocumentElement(kind=PARAGRAPH, text="One passage.", page=1),),
    page_sizes={1: (612.0, 792.0)},
)


def test_docling_is_the_configured_backend_until_ir_842(settings):
    settings.EXTRACTION_BACKEND = "docling"

    assert isinstance(current_extractor(), DoclingExtractor)


def test_the_docling_adapter_is_built_from_the_docling_settings(settings):
    settings.EXTRACTION_BACKEND = "docling"
    settings.DOCLING_API_URL = "http://docling.test:5001/"

    assert current_extractor()._base_url == "http://docling.test:5001"


def test_an_unknown_backend_refuses_to_start(settings):
    settings.EXTRACTION_BACKEND = "pymupdf"

    with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
        verify_extraction_configuration()


def test_a_known_backend_starts(settings):
    settings.EXTRACTION_BACKEND = "docling"

    verify_extraction_configuration()


def test_use_extractor_replaces_the_extractor_inside_the_block_only():
    adapter = InMemoryExtractor(DOCUMENT)

    with use_extractor(adapter):
        assert current_extractor() is adapter
    assert isinstance(current_extractor(), DoclingExtractor)


def test_an_error_inside_the_block_cannot_leave_the_override_installed():
    with pytest.raises(RuntimeError):
        with use_extractor(InMemoryExtractor(DOCUMENT)):
            raise RuntimeError("boom")

    assert isinstance(current_extractor(), DoclingExtractor)


def test_startup_refuses_an_unknown_backend(settings):
    from django.apps import apps

    settings.EXTRACTION_BACKEND = "pymupdf"

    with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
        apps.get_app_config("ai").ready()


def test_extraction_settings_are_read_only_inside_the_extraction_module():
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[4]
    package = backend / "apps" / "ai" / "extraction"
    reader = re.compile(r"""settings\.(DOCLING_|EXTRACTION_BACKEND)|getattr\(\s*settings,\s*["'](DOCLING_|EXTRACTION_BACKEND)""")
    readers = [
        str(path.relative_to(backend))
        for path in (backend / "apps").rglob("*.py")
        if package not in path.parents and reader.search(path.read_text(encoding="utf-8"))
    ]

    assert readers == []


def test_an_extractor_that_leaves_campus_comes_admitted():
    from apps.ai.admission.extraction import AdmittedExtractor

    with use_extractor(InMemoryExtractor(DOCUMENT, leaves_campus=True)):
        assert isinstance(current_extractor(), AdmittedExtractor)


def test_an_extractor_that_does_not_say_is_treated_as_leaving():
    from apps.ai.admission.extraction import AdmittedExtractor

    class Undeclared:
        def extract(self, pdf_bytes, *, filename):
            raise AssertionError("never called here")

    with use_extractor(Undeclared()):
        assert isinstance(current_extractor(), AdmittedExtractor)
