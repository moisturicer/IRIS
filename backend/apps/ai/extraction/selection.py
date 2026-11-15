"""Which Extractor runs (IR-838).

``EXTRACTION_BACKEND`` and ``LLAMAPARSE_*`` are read here and
nowhere else, so no caller learns which vendor reads its PDFs.
``use_extractor`` mirrors ``use_composition_root``: a test installs an
adapter for one block instead of monkeypatching a builder.
"""

import importlib.util
from contextlib import contextmanager
from typing import Callable, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .ports import ExtractorUnavailable, StructuredExtractor


def _llamaparse_shape():
    """IR-840's shaping of a LlamaParse result, once it exists."""
    if importlib.util.find_spec(f"{__package__}.shaping") is None:
        return None
    from .shaping import shape_llamaparse

    return shape_llamaparse


def _llamaparse() -> StructuredExtractor:
    from .llamaparse_client import LlamaParseExtractor

    return LlamaParseExtractor(
        shape=_llamaparse_shape(),
        api_key=settings.LLAMAPARSE_API_KEY,
        base_url=settings.LLAMAPARSE_BASE_URL,
        tier=settings.LLAMAPARSE_TIER,
        version=settings.LLAMAPARSE_VERSION,
        timeout_base_seconds=settings.LLAMAPARSE_TIMEOUT_BASE_SECONDS,
        timeout_per_page_seconds=settings.LLAMAPARSE_TIMEOUT_PER_PAGE_SECONDS,
        max_pages=settings.PDF_VALIDATION_MAX_PAGES or settings.LLAMAPARSE_MAX_PAGES,
    )


def _verify_llamaparse() -> None:
    from .llamaparse_client import BASE_URLS

    for name in ("LLAMAPARSE_API_KEY", "LLAMAPARSE_VERSION", "LLAMAPARSE_TIER"):
        if not getattr(settings, name):
            raise ImproperlyConfigured(f"{name} is required when EXTRACTION_BACKEND=llamaparse (IR-841).")
    if settings.LLAMAPARSE_VERSION == "latest" and not settings.DEBUG:
        raise ImproperlyConfigured(
            "LLAMAPARSE_VERSION=latest is refused outside development; pin a dated version (ADR-056)."
        )
    hosts = {urlparse(url).netloc for url in BASE_URLS.values()}
    if urlparse(settings.LLAMAPARSE_BASE_URL).netloc not in hosts:
        raise ImproperlyConfigured(
            f"LLAMAPARSE_BASE_URL must be one of: {', '.join(sorted(BASE_URLS.values()))} (IR-841)."
        )
    if _llamaparse_shape() is None:
        raise ImproperlyConfigured(
            "EXTRACTION_BACKEND=llamaparse needs IR-840's shaping, which is not built yet."
        )


def _verify_llamaextract() -> None:
    """LlamaExtract reads the parse with LlamaParse's own account (IR-846)."""
    from .llamaparse_client import BASE_URLS

    for name in ("LLAMAPARSE_API_KEY", "LLAMAEXTRACT_TIER"):
        if not getattr(settings, name):
            raise ImproperlyConfigured(f"{name} is required when LLAMAEXTRACT_VERSION is set (IR-846).")
    if settings.LLAMAEXTRACT_VERSION == "latest" and not settings.DEBUG:
        raise ImproperlyConfigured(
            "LLAMAEXTRACT_VERSION=latest is refused outside development; pin a version (ADR-056)."
        )
    hosts = {urlparse(url).netloc for url in BASE_URLS.values()}
    if urlparse(settings.LLAMAPARSE_BASE_URL).netloc not in hosts:
        raise ImproperlyConfigured(
            f"LLAMAPARSE_BASE_URL must be one of: {', '.join(sorted(BASE_URLS.values()))} (IR-846)."
        )


def _verify_unstructured() -> None:
    from .unstructured_client import BASE_URL

    if not settings.UNSTRUCTURED_PLATFORM_API_KEY:
        raise ImproperlyConfigured("UNSTRUCTURED_PLATFORM_API_KEY is required to read with Unstructured (IR-985).")
    if urlparse(settings.UNSTRUCTURED_BASE_URL).netloc != urlparse(BASE_URL).netloc:
        raise ImproperlyConfigured(f"UNSTRUCTURED_BASE_URL must be {BASE_URL} (ADR-067).")


def unstructured_extractor() -> StructuredExtractor:
    """The Unstructured adapter, unadmitted. Not a selectable backend until
    IR-988's cutover (ADR-067 decision 1); refuses a bad configuration."""
    from .shaping_unstructured import shape_unstructured
    from .unstructured_client import UnstructuredExtractor

    _verify_unstructured()
    return UnstructuredExtractor(
        shape=shape_unstructured,
        api_key=settings.UNSTRUCTURED_PLATFORM_API_KEY,
        base_url=settings.UNSTRUCTURED_BASE_URL,
        timeout_base_seconds=settings.UNSTRUCTURED_TIMEOUT_BASE_SECONDS,
        timeout_per_page_seconds=settings.UNSTRUCTURED_TIMEOUT_PER_PAGE_SECONDS,
        max_pages=settings.PDF_VALIDATION_MAX_PAGES or settings.UNSTRUCTURED_MAX_PAGES,
        max_figures=settings.UNSTRUCTURED_MAX_FIGURES,
        max_figure_pixels=settings.UNSTRUCTURED_MAX_FIGURE_PIXELS,
    )


BACKENDS: dict[str, Callable[[], StructuredExtractor]] = {"llamaparse": _llamaparse}

# A module global, not a contextvar: worker threads in tests must see it.
_installed: Optional[StructuredExtractor] = None
# A LlamaExtractReader, or a test's stand-in with the same read().
_installed_reader: Optional[object] = None


class UnconfiguredExtractor:
    """Stands in, in development only, until LlamaParse is configured (IR-843)."""

    leaves_campus = False
    timeout_seconds = 60

    def __init__(self, reason: str):
        self.reason = reason

    def extract(self, pdf_bytes: bytes, *, filename: str):
        raise ExtractorUnavailable(self.reason)


def _verify_backend() -> None:
    backend = settings.EXTRACTION_BACKEND
    if backend not in BACKENDS:
        raise ImproperlyConfigured(
            f"EXTRACTION_BACKEND={backend!r} is not one of: {', '.join(sorted(BACKENDS))} (IR-843)."
        )


def verify_extraction_configuration() -> None:
    """Refuse to start on a bad configuration (the IR-379 posture).

    Development starts without a LlamaParse account (IR-843); its reads then
    fail as unavailable.
    """
    _verify_backend()
    if not settings.DEBUG:
        _verify_llamaparse()
    if settings.LLAMAEXTRACT_VERSION:
        _verify_llamaextract()


def current_extractor() -> StructuredExtractor:
    """The configured Extractor; one that leaves campus comes admitted (IR-850)."""
    from apps.ai.admission.extraction import AdmittedExtractor

    from .gate import leaves_campus

    if _installed is not None:
        adapter = _installed
    else:
        try:
            _verify_backend()
            _verify_llamaparse()
            adapter = BACKENDS[settings.EXTRACTION_BACKEND]()
        except ImproperlyConfigured as error:
            # Reachable only where startup allowed it: nothing is sent.
            adapter = UnconfiguredExtractor(str(error))
    if leaves_campus(adapter) and not isinstance(adapter, AdmittedExtractor):
        return AdmittedExtractor(adapter)
    return adapter


@contextmanager
def use_extractor(adapter: StructuredExtractor):
    """Install ``adapter`` for the duration of the block."""
    global _installed
    previous = _installed
    _installed = adapter
    try:
        yield adapter
    finally:
        _installed = previous


def metadata_reader_configured() -> bool:
    """Whether a LlamaParse read is followed by a LlamaExtract reading (IR-846)."""
    return _installed_reader is not None or bool(settings.LLAMAEXTRACT_VERSION)


def current_metadata_reader():
    """The LlamaExtract reader, admitted (IR-846). Call only when configured."""
    from apps.ai.admission.extraction import AdmittedMetadataReader

    if _installed_reader is not None:
        adapter = _installed_reader
    else:
        from .llamaextract_client import LlamaExtractReader

        _verify_llamaextract()
        adapter = LlamaExtractReader(
            api_key=settings.LLAMAPARSE_API_KEY,
            base_url=settings.LLAMAPARSE_BASE_URL,
            tier=settings.LLAMAEXTRACT_TIER,
            version=settings.LLAMAEXTRACT_VERSION,
            timeout_seconds=settings.LLAMAEXTRACT_TIMEOUT_SECONDS,
        )
    return adapter if isinstance(adapter, AdmittedMetadataReader) else AdmittedMetadataReader(adapter)


@contextmanager
def use_metadata_reader(adapter):
    """Install ``adapter`` as the LlamaExtract reader for the block."""
    global _installed_reader
    previous = _installed_reader
    _installed_reader = adapter
    try:
        yield adapter
    finally:
        _installed_reader = previous
