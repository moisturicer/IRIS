"""Unstructured's Platform API, ``hi_res``, as a ``StructuredExtractor`` (IR-985, ADR-067).

Synchronous: each attempt's timeout grows with the page count and one timeout
is retried. The endpoint returns no upload or job id, so there is nothing to
delete; what it retains is ADR-067 open condition 1.
"""

import base64
import logging
import re
import time
from io import BytesIO
from typing import Any, Callable, Mapping, Optional

import httpx

from apps.ai.chunking.document import NormalizedDocument

from .ports import (
    DocumentRejected,
    EmptyExtraction,
    ExtractedDocument,
    ExtractionError,
    ExtractorUnavailable,
    FigureImage,
    Provenance,
    Usage,
)

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "unstructured"
BASE_URL = "https://api.unstructuredapp.io"
PATH = "/general/v0/general"
STRATEGY = "hi_res"
VERSION = f"general/v0:{STRATEGY}"

# ADR-067 amendment §1.
REQUEST_OPTIONS = {
    "strategy": STRATEGY,
    "coordinates": "true",
    "pdf_infer_table_structure": "true",
    "include_page_breaks": "true",
    "extract_image_block_types": '["Image", "Table"]',
}

DEFAULT_TIMEOUT_BASE_SECONDS = 120
DEFAULT_TIMEOUT_PER_PAGE_SECONDS = 10
DEFAULT_MAX_FIGURES = 200
# A whole A3 page at hi_res's 250 dpi is about 12 Mpx.
DEFAULT_MAX_FIGURE_PIXELS = 16_000_000
ATTEMPTS = 2
_RETRY_PAUSE_SECONDS = 5.0
_CONNECT_SECONDS = 10.0
# Sending the PDF and reading the answer, on top of every attempt.
TRANSFER_SLACK_SECONDS = 60

# A key, quota or rate fault is the deployment's, never the document's.
_NOT_THE_DOCUMENT = {401, 402, 403, 408, 429}
_NOT_CONTENT = {"PageBreak"}
_SIGNED = re.compile(r"[?&](X-Amz-[A-Za-z]+|Signature|sig)=")

Shape = Callable[[Mapping[str, Any]], NormalizedDocument]


class UnstructuredExtractor:
    leaves_campus = True

    def __init__(
        self,
        *,
        shape: Shape,
        api_key: str = "",
        base_url: str = BASE_URL,
        timeout_base_seconds: int = DEFAULT_TIMEOUT_BASE_SECONDS,
        timeout_per_page_seconds: int = DEFAULT_TIMEOUT_PER_PAGE_SECONDS,
        max_pages: int = 1000,
        max_figures: int = DEFAULT_MAX_FIGURES,
        max_figure_pixels: int = DEFAULT_MAX_FIGURE_PIXELS,
        api: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._shape = shape
        self._max_figures = max_figures
        self._max_figure_pixels = max_figure_pixels
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._base_seconds = timeout_base_seconds
        self._per_page_seconds = timeout_per_page_seconds
        self._max_pages = max_pages
        self._api = api
        self._sleep = sleep

    @property
    def model(self) -> str:
        return f"{EXTRACTOR_NAME}-{STRATEGY}"

    @property
    def account(self) -> str:
        """Admission's per-account fence (IR-850); never the key itself."""
        from apps.ai.admission.ledger import account_for

        return account_for(self._api_key)

    @property
    def timeout_seconds(self) -> float:
        return (ATTEMPTS * (self._attempt_seconds(self._max_pages) + TRANSFER_SLACK_SECONDS)
                + (ATTEMPTS - 1) * _RETRY_PAUSE_SECONDS)

    def _attempt_seconds(self, pages: int) -> float:
        return float(self._base_seconds + self._per_page_seconds * pages)

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        pages = _page_count(pdf_bytes)
        attempt_seconds = self._attempt_seconds(pages)
        if self._api is not None:
            response, made = self._partition(self._api, pdf_bytes, filename, attempt_seconds)
        else:
            with httpx.Client(base_url=self._base_url,
                              headers={"unstructured-api-key": self._api_key}) as api:
                response, made = self._partition(api, pdf_bytes, filename, attempt_seconds)

        elements = _elements(response)
        if not any(e.get("type") not in _NOT_CONTENT and (e.get("text") or "").strip()
                   for e in elements):
            raise EmptyExtraction(f"Unstructured found no content in {filename!r}")
        raw = {"elements": _without_signed_urls(elements)}
        document = self._shape(raw)
        if not document.elements:
            raise EmptyExtraction(f"no extractable content for {filename!r}")
        figures = _figures(elements, document, self._max_figures, self._max_figure_pixels)
        options = {**REQUEST_OPTIONS, "call": {
            "mode": "synchronous", "attempts": ATTEMPTS, "attempts_made": made,
            "attempt_timeout_seconds": attempt_seconds,
        }}
        return ExtractedDocument(
            document=document,
            provenance=Provenance(name=EXTRACTOR_NAME, version=VERSION, options=options),
            usage=Usage(pages=_billed_pages(response) or pages),
            figures=figures,
            raw=raw,
        )

    def _partition(self, api: httpx.Client, pdf_bytes: bytes, filename: str,
                   attempt_seconds: float) -> tuple[httpx.Response, int]:
        timeout = httpx.Timeout(attempt_seconds, connect=_CONNECT_SECONDS)
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = api.post(
                    PATH, timeout=timeout, data=REQUEST_OPTIONS,
                    files={"files": (filename, pdf_bytes, "application/pdf")},
                )
            except httpx.TimeoutException as exc:
                # A hung hi_res call answered on retry in the spike (amendment §5).
                if attempt < ATTEMPTS:
                    self._sleep(_RETRY_PAUSE_SECONDS)
                    continue
                raise ExtractorUnavailable(
                    f"Unstructured partition timed out {ATTEMPTS} times at {attempt_seconds:.0f}s"
                ) from exc
            except httpx.HTTPError as exc:
                raise ExtractorUnavailable(f"Unstructured partition failed: {type(exc).__name__}") from exc
            _check(response)
            return response, attempt
        raise AssertionError("unreachable")


def _check(response: httpx.Response) -> None:
    status = response.status_code
    if status in _NOT_THE_DOCUMENT or status >= 500:
        raise ExtractorUnavailable(f"Unstructured partition returned {status}")
    if status < 400:
        return
    body = _body(response)
    # FastAPI lists field errors: our request was wrong, not the document.
    if isinstance(body, dict) and isinstance(body.get("detail"), list):
        raise ExtractionError(f"Unstructured refused the request ({status}): {str(body['detail'])[:300]}")
    raise DocumentRejected(f"Unstructured partition returned {status}: {_detail(body)}")


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _detail(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("user_message") or body.get("detail") or body)[:300]
    return str(body)[:300]


def _elements(response: httpx.Response) -> list:
    try:
        body = response.json()
    except ValueError as exc:
        raise ExtractorUnavailable("Unstructured partition answered with no JSON") from exc
    if not isinstance(body, list):
        raise ExtractorUnavailable("Unstructured partition answered with no element list")
    return body


def _billed_pages(response: httpx.Response) -> Optional[int]:
    try:
        return int(response.headers["x-num-pages"])
    except (KeyError, ValueError):
        return None


def _without_signed_urls(value: Any) -> Any:
    """Signed URLs grant access while they live; never stored."""
    if isinstance(value, dict):
        return {k: _without_signed_urls(v) for k, v in value.items()
                if k != "presigned_url" and not _signed(v)}
    if isinstance(value, list):
        return [_without_signed_urls(v) for v in value]
    return value


def _signed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("http") and bool(_SIGNED.search(value))


def _figures(elements: list, document: NormalizedDocument, max_figures: int,
             max_pixels: int) -> tuple[FigureImage, ...]:
    """Each shaped Image's ``image_base64`` as a Figure (IR-987, ADR-067 decision 10).
    Page and caption come from shaping, so a Figure joins its element by name."""
    shaped = {e.figure: e for e in document.elements if e.kind == "image" and e.figure}
    figures: list[FigureImage] = []
    for item in elements:
        metadata = item.get("metadata") or {}
        element = shaped.get(str(item.get("element_id") or ""))
        if item.get("type") != "Image" or element is None or not metadata.get("image_base64"):
            continue
        if len(figures) == max_figures:
            logger.warning("more than %s figures; the rest are not kept", max_figures)
            break
        media_type = str(metadata.get("image_mime_type") or "")
        data = _image_bytes(metadata["image_base64"], media_type, max_pixels, element.figure)
        if data is None:
            continue
        figures.append(FigureImage(
            page=element.page, bbox=_box(metadata, element.page),
            media_type=media_type, data=data,
            caption=element.text or None, name=element.figure,
        ))
    return tuple(figures)


def _image_bytes(encoded: str, media_type: str, max_pixels: int, name: str) -> Optional[bytes]:
    """Decoded bytes, or ``None`` for an unreadable, mislabelled or oversized image.
    Only the header is read, so an oversized image is never decoded."""
    from PIL import Image

    try:
        data = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            actual = Image.MIME.get(image.format or "")
    except Exception:
        logger.warning("figure %s is not a readable image; not kept", name)
        return None
    if actual != media_type:
        logger.warning("figure %s is %s, not the %s it claims; not kept", name, actual, media_type)
        return None
    if width * height > max_pixels:
        logger.warning("figure %s is %sx%s, over %s pixels; not kept", name, width, height, max_pixels)
        return None
    return data


def _box(metadata: Mapping[str, Any], page: int) -> dict:
    """The union of the element's boxes, in the ``x/y/w/h`` page points stored Figures use."""
    from .shaping_unstructured import element_boxes

    boxes = element_boxes(metadata, page)
    if not boxes:
        return {}
    left, top = min(b.left for b in boxes), min(b.top for b in boxes)
    return {"x": left, "y": top, "w": max(b.right for b in boxes) - left,
            "h": max(b.bottom for b in boxes) - top}


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    try:
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception as exc:
        raise DocumentRejected("the PDF could not be opened to count its pages") from exc
