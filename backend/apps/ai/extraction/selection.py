"""Which Extractor runs (IR-838).

``EXTRACTION_BACKEND`` and ``UNSTRUCTURED_*`` are read here and
nowhere else, so no caller learns which vendor reads its PDFs.
Unstructured is the only Extractor (ADR-067, IR-988).
``use_extractor`` mirrors ``use_composition_root``: a test installs an
adapter for one block instead of monkeypatching a builder.
"""

from contextlib import contextmanager
from typing import Callable, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .ports import ExtractorUnavailable, StructuredExtractor


def _verify_unstructured() -> None:
    from .unstructured_client import BASE_URL

    if not settings.UNSTRUCTURED_PLATFORM_API_KEY:
        raise ImproperlyConfigured("UNSTRUCTURED_PLATFORM_API_KEY is required to read with Unstructured (IR-985).")
    if urlparse(settings.UNSTRUCTURED_BASE_URL).netloc != urlparse(BASE_URL).netloc:
        raise ImproperlyConfigured(f"UNSTRUCTURED_BASE_URL must be {BASE_URL} (ADR-067).")


def unstructured_extractor() -> StructuredExtractor:
    """The Unstructured adapter, unadmitted; refuses a bad configuration."""
    from .shaping_unstructured import shape_unstructured
    from .unstructured_client import UnstructuredExtractor

    _verify_unstructured()
    max_figures, max_figure_pixels = figure_limits()
    return UnstructuredExtractor(
        shape=shape_unstructured,
        api_key=settings.UNSTRUCTURED_PLATFORM_API_KEY,
        base_url=settings.UNSTRUCTURED_BASE_URL,
        timeout_base_seconds=settings.UNSTRUCTURED_TIMEOUT_BASE_SECONDS,
        timeout_per_page_seconds=settings.UNSTRUCTURED_TIMEOUT_PER_PAGE_SECONDS,
        max_pages=settings.PDF_VALIDATION_MAX_PAGES or settings.UNSTRUCTURED_MAX_PAGES,
        max_figures=max_figures,
        max_figure_pixels=max_figure_pixels,
    )


def figure_limits() -> tuple[int, int]:
    """Figures kept per read, and pixels per Figure (IR-987)."""
    return settings.UNSTRUCTURED_MAX_FIGURES, settings.UNSTRUCTURED_MAX_FIGURE_PIXELS


BACKENDS: dict[str, Callable[[], StructuredExtractor]] = {"unstructured": unstructured_extractor}

# A module global, not a contextvar: worker threads in tests must see it.
_installed: Optional[StructuredExtractor] = None


class UnconfiguredExtractor:
    """Stands in, in development only, until Unstructured is configured (IR-843)."""

    leaves_campus = False
    timeout_seconds = 60

    def __init__(self, reason: str):
        self.reason = reason

    def extract(self, pdf_bytes: bytes, *, filename: str):
        raise ExtractorUnavailable(self.reason)


def selected_backend() -> str:
    """The configured backend's name, for admission's price (IR-983)."""
    return str(settings.EXTRACTION_BACKEND or "").strip().lower()


def _verify_backend() -> None:
    backend = settings.EXTRACTION_BACKEND
    if backend not in BACKENDS:
        raise ImproperlyConfigured(
            f"EXTRACTION_BACKEND={backend!r} is not one of: {', '.join(sorted(BACKENDS))} (IR-843)."
        )


def verify_extraction_configuration() -> None:
    """Refuse to start on a bad configuration (the IR-379 posture).

    Development starts without an Unstructured account (IR-843); its reads
    then fail as unavailable.
    """
    _verify_backend()
    if not settings.DEBUG:
        _verify_unstructured()


def current_extractor() -> StructuredExtractor:
    """The configured Extractor; one that leaves campus comes admitted (IR-850)."""
    from apps.ai.admission.extraction import AdmittedExtractor

    from .gate import leaves_campus

    if _installed is not None:
        adapter = _installed
    else:
        try:
            _verify_backend()
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
