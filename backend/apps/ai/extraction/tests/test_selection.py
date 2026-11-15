"""Which Extractor runs, and how a test replaces it (IR-838)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    InMemoryExtractor,
    current_extractor,
    use_extractor,
    verify_extraction_configuration,
)
from apps.ai.extraction.selection import UnconfiguredExtractor

pytestmark = [pytest.mark.django_required]

DOCUMENT = NormalizedDocument(
    title="A paper",
    elements=(DocumentElement(kind=PARAGRAPH, text="One passage.", page=1),),
    page_sizes={1: (612.0, 792.0)},
)


def test_an_unknown_backend_refuses_to_start(settings):
    settings.EXTRACTION_BACKEND = "docling"

    with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
        verify_extraction_configuration()


def test_unstructured_is_the_only_backend():
    from apps.ai.extraction.selection import BACKENDS

    assert set(BACKENDS) == {"unstructured"}


def test_llamaparse_is_no_longer_a_backend(settings):
    settings.EXTRACTION_BACKEND = "llamaparse"

    with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
        verify_extraction_configuration()


def test_development_starts_without_an_unstructured_key(settings):
    settings.EXTRACTION_BACKEND = "unstructured"
    settings.UNSTRUCTURED_PLATFORM_API_KEY = ""
    settings.DEBUG = True

    verify_extraction_configuration()


def test_production_refuses_to_start_without_an_unstructured_key(settings):
    settings.EXTRACTION_BACKEND = "unstructured"
    settings.UNSTRUCTURED_PLATFORM_API_KEY = ""
    settings.DEBUG = False

    with pytest.raises(ImproperlyConfigured, match="UNSTRUCTURED_PLATFORM_API_KEY"):
        verify_extraction_configuration()


def test_production_starts_with_an_unstructured_key(settings):
    settings.EXTRACTION_BACKEND = "unstructured"
    settings.UNSTRUCTURED_PLATFORM_API_KEY = "uns-test"
    settings.UNSTRUCTURED_BASE_URL = "https://api.unstructuredapp.io"
    settings.DEBUG = False

    verify_extraction_configuration()


def test_an_unconfigured_extractor_fails_the_read_as_unavailable(settings):
    from apps.ai.extraction import ExtractorUnavailable

    settings.EXTRACTION_BACKEND = "unstructured"
    settings.UNSTRUCTURED_PLATFORM_API_KEY = ""

    extractor = current_extractor()

    assert isinstance(extractor, UnconfiguredExtractor)
    assert extractor.timeout_seconds > 0
    with pytest.raises(ExtractorUnavailable, match="UNSTRUCTURED_PLATFORM_API_KEY"):
        extractor.extract(b"%PDF-1.7", filename="paper.pdf")


def test_use_extractor_replaces_the_extractor_inside_the_block_only(settings):
    settings.UNSTRUCTURED_PLATFORM_API_KEY = ""
    adapter = InMemoryExtractor(DOCUMENT)

    with use_extractor(adapter):
        assert current_extractor() is adapter
    assert isinstance(current_extractor(), UnconfiguredExtractor)


def test_an_error_inside_the_block_cannot_leave_the_override_installed(settings):
    settings.UNSTRUCTURED_PLATFORM_API_KEY = ""
    adapter = InMemoryExtractor(DOCUMENT)
    with pytest.raises(RuntimeError):
        with use_extractor(adapter):
            raise RuntimeError("boom")

    assert isinstance(current_extractor(), UnconfiguredExtractor)


def test_startup_refuses_an_unknown_backend(settings):
    from django.apps import apps

    settings.EXTRACTION_BACKEND = "docling"

    with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
        apps.get_app_config("ai").ready()


def test_extraction_settings_are_read_only_inside_the_extraction_module():
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[4]
    package = backend / "apps" / "ai" / "extraction"
    reader = re.compile(r"""settings\.(UNSTRUCTURED_|EXTRACTION_BACKEND)|getattr\(\s*settings,\s*["'](UNSTRUCTURED_|EXTRACTION_BACKEND)""")
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


def test_the_configured_backend_is_the_admitted_unstructured_adapter(settings):
    from apps.ai.admission.extraction import AdmittedExtractor
    from apps.ai.extraction.unstructured_client import UnstructuredExtractor

    settings.EXTRACTION_BACKEND = "unstructured"
    settings.UNSTRUCTURED_PLATFORM_API_KEY = "uns-test"
    settings.UNSTRUCTURED_BASE_URL = "https://api.unstructuredapp.io"

    extractor = current_extractor()

    assert isinstance(extractor, AdmittedExtractor)
    assert isinstance(extractor._adapter, UnstructuredExtractor)
    assert extractor.extractor_name == "unstructured"


def test_no_production_code_names_llamaparse_or_llamaextract():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[4]
    names = ("llamaparse_client", "llamaextract_client", "shape_llamaparse", "LLAMAPARSE_", "LLAMAEXTRACT_")
    found = [
        f"{path.relative_to(backend)}: {name}"
        for path in (backend / "apps").rglob("*.py")
        if not ({"tests", "migrations"} & set(path.parts)) and not path.name.startswith("test_")
        for name in names if name in path.read_text(encoding="utf-8")
    ]
    found += [f"config: {name}" for path in (backend / "config").rglob("*.py")
              for name in names if name in path.read_text(encoding="utf-8")]

    assert found == []
