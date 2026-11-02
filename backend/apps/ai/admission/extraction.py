"""Admission around an Extractor that leaves campus (IR-850, ADR-041, ADR-056 §6).

One read is one attempt: refused unless admission enforces, reserved at pages x
the dearest per-page credits, gated again just before sending, and settled to
the credits reported or kept at the reservation.
"""

from __future__ import annotations

import io
import logging
from typing import Callable, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.ai.extraction import gate
from apps.ai.extraction.ports import ExtractedDocument

from . import errors, scope
from .ledger import Request, provider_attempt
from .limits import NotConfigured, enforcing, read_extraction_price

logger = logging.getLogger(__name__)

LANE = "extraction"


def pdf_pages(pdf_bytes: bytes) -> Optional[int]:
    """The page count, or ``None``. Runs in the worker, on bytes intake bounded (IR-830)."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(pdf_bytes), strict=False).pages) or None
    except Exception:
        return None


def _refuse(reason: str) -> errors.AdmissionDenied:
    scope.note_denial(reason)
    logger.info("extraction admission refused: %s", reason)
    return errors.AdmissionDenied(reason)


class AdmittedExtractor:
    leaves_campus = True

    def __init__(self, adapter, *, count_pages: Callable[[bytes], Optional[int]] = pdf_pages) -> None:
        self._adapter = adapter
        self._count_pages = count_pages

    @property
    def model(self) -> str:
        return self._adapter.model

    @property
    def timeout_seconds(self) -> float:
        return self._adapter.timeout_seconds

    def _pages(self, pdf_bytes: bytes) -> int:
        # An unreadable count reserves the most intake accepts: worst case first.
        pages = self._count_pages(pdf_bytes) or getattr(settings, "PDF_VALIDATION_MAX_PAGES", None)
        if not pages:
            raise _refuse(errors.NOT_CONFIGURED)
        return int(pages)

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        if not enforcing():
            raise _refuse(errors.ADMISSION_OFF)
        try:
            price = read_extraction_price()
        except (NotConfigured, ImproperlyConfigured):
            raise _refuse(errors.NOT_CONFIGURED) from None
        adapter = self._adapter
        request = Request(
            operation="extraction",
            default_lane=LANE,
            account=adapter.account,
            models=(adapter.model,),
            input_tokens=0,
            output_tokens=0,
            timeout_seconds=float(self.timeout_seconds),
            cost_micros=price.reserve_micros(self._pages(pdf_bytes)),
        )
        with provider_attempt(lambda: request):
            gate.require_disclosure()
            scope.mark_sent(model=adapter.model)
            extracted = adapter.extract(pdf_bytes, filename=filename)
            usage = extracted.usage
            if usage is not None and usage.credits is not None:
                scope.report_usage(
                    input_tokens=0, output_tokens=0, model=adapter.model,
                    cost_usd=price.micros(usage.credits) / 1_000_000,
                )
            return extracted
