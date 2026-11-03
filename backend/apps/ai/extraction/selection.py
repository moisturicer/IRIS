"""Which Extractor runs (IR-838).

``EXTRACTION_BACKEND``, ``DOCLING_*`` and ``LLAMAPARSE_*`` are read here and
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

from .ports import StructuredExtractor


def _docling() -> StructuredExtractor:
    from .docling_client import DoclingExtractor

    return DoclingExtractor(
        settings.DOCLING_API_URL,
        timeout=settings.DOCLING_TIMEOUT_SECONDS,
        do_ocr=settings.DOCLING_DO_OCR,
        do_formula_enrichment=settings.DOCLING_DO_FORMULA_ENRICHMENT,
        do_code_enrichment=settings.DOCLING_DO_CODE_ENRICHMENT,
        do_picture_classification=settings.DOCLING_DO_PICTURE_CLASSIFICATION,
    )


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


BACKENDS: dict[str, Callable[[], StructuredExtractor]] = {"docling": _docling, "llamaparse": _llamaparse}

# A module global, not a contextvar: worker threads in tests must see it.
_installed: Optional[StructuredExtractor] = None
# A LlamaExtractReader, or a test's stand-in with the same read().
_installed_reader: Optional[object] = None


def configured_backend() -> str:
    """The name of the configured backend, for a caller that must refuse another."""
    return settings.EXTRACTION_BACKEND


def verify_extraction_configuration() -> None:
    """Refuse to start on an unknown backend (the IR-379 posture)."""
    backend = settings.EXTRACTION_BACKEND
    if backend not in BACKENDS:
        raise ImproperlyConfigured(
            f"EXTRACTION_BACKEND={backend!r} is not one of: {', '.join(sorted(BACKENDS))} (IR-838)."
        )
    if backend == "llamaparse":
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
        verify_extraction_configuration()
        adapter = BACKENDS[settings.EXTRACTION_BACKEND]()
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
