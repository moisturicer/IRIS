"""Which Extractor runs (IR-838).

``EXTRACTION_BACKEND`` and the ``DOCLING_*`` settings are read here and
nowhere else, so no caller learns which vendor reads its PDFs.
``use_extractor`` mirrors ``use_composition_root``: a test installs an
adapter for one block instead of monkeypatching a builder.
"""

from contextlib import contextmanager
from typing import Callable, Optional

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


BACKENDS: dict[str, Callable[[], StructuredExtractor]] = {"docling": _docling}

# A module global, not a contextvar: worker threads in tests must see it.
_installed: Optional[StructuredExtractor] = None


def verify_extraction_configuration() -> None:
    """Refuse to start on an unknown backend (the IR-379 posture)."""
    backend = settings.EXTRACTION_BACKEND
    if backend not in BACKENDS:
        raise ImproperlyConfigured(
            f"EXTRACTION_BACKEND={backend!r} is not one of: {', '.join(sorted(BACKENDS))} (IR-838)."
        )


def current_extractor() -> StructuredExtractor:
    if _installed is not None:
        return _installed
    verify_extraction_configuration()
    return BACKENDS[settings.EXTRACTION_BACKEND]()


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
