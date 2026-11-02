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
    reader = re.compile(r"""settings\.(DOCLING_|LLAMAPARSE_|EXTRACTION_BACKEND)|getattr\(\s*settings,\s*["'](DOCLING_|LLAMAPARSE_|EXTRACTION_BACKEND)""")
    readers = [
        str(path.relative_to(backend))
        for path in (backend / "apps").rglob("*.py")
        if package not in path.parents and reader.search(path.read_text(encoding="utf-8"))
    ]

    assert readers == []


def _llamaparse(settings, **values):
    settings.EXTRACTION_BACKEND = "llamaparse"
    settings.LLAMAPARSE_API_KEY = "llx-test"
    settings.LLAMAPARSE_TIER = "agentic"
    settings.LLAMAPARSE_VERSION = "2026-09-28"
    settings.LLAMAPARSE_BASE_URL = "https://api.cloud.eu.llamaindex.ai"
    for name, value in values.items():
        setattr(settings, name, value)


@pytest.fixture
def shaping(monkeypatch):
    from apps.ai.extraction import selection

    monkeypatch.setattr(selection, "_llamaparse_shape", lambda: (lambda raw: DOCUMENT))


@pytest.mark.parametrize("missing", ["LLAMAPARSE_API_KEY", "LLAMAPARSE_VERSION"])
def test_llamaparse_refuses_to_start_without_a_key_or_a_pinned_version(settings, shaping, missing):
    _llamaparse(settings, **{missing: ""})

    with pytest.raises(ImproperlyConfigured, match=missing):
        verify_extraction_configuration()


def test_llamaparse_refuses_latest_outside_development(settings, shaping):
    _llamaparse(settings, LLAMAPARSE_VERSION="latest", DEBUG=False)

    with pytest.raises(ImproperlyConfigured, match="latest"):
        verify_extraction_configuration()


def test_llamaparse_allows_latest_in_development(settings, shaping):
    _llamaparse(settings, LLAMAPARSE_VERSION="latest", DEBUG=True)

    verify_extraction_configuration()


def test_llamaparse_refuses_a_region_it_does_not_know(settings, shaping):
    _llamaparse(settings, LLAMAPARSE_BASE_URL="https://llamaparse.example.com")

    with pytest.raises(ImproperlyConfigured, match="LLAMAPARSE_BASE_URL"):
        verify_extraction_configuration()


def test_llamaparse_refuses_to_start_until_its_result_can_be_shaped(settings, monkeypatch):
    from apps.ai.extraction import selection

    _llamaparse(settings)
    monkeypatch.setattr(selection, "_llamaparse_shape", lambda: None)

    with pytest.raises(ImproperlyConfigured, match="IR-840"):
        verify_extraction_configuration()


def test_the_llamaparse_adapter_is_built_from_the_llamaparse_settings(settings, shaping):
    from apps.ai.extraction.llamaparse_client import LlamaParseExtractor

    _llamaparse(settings)

    adapter = current_extractor()

    assert isinstance(adapter, LlamaParseExtractor)
    assert adapter.leaves_campus is True
    assert adapter._base_url == "https://api.cloud.eu.llamaindex.ai"
    assert adapter._options["tier"] == "agentic"
    assert adapter._options["version"] == "2026-09-28"
