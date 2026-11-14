"""Unstructured's Platform API as a ``StructuredExtractor`` (IR-985, ADR-067).

The one module that knows the partition endpoint's HTTP contract. ADR-067's
2026-11-14 amendment pins ``strategy=hi_res`` on the Platform API, not
Transform. The call is synchronous: each attempt has a timeout that grows
with the page count, and a timed-out attempt is retried once (amendment §5).

The endpoint keeps no upload and no job, so there is nothing to delete
afterwards (ADR-056 decision 7). ``shape`` (IR-986) turns the raw result into
IRIS's document. Whether a paper may be sent is decided around this adapter
(IR-850), never here.
"""

import time
from io import BytesIO
from typing import Any, Callable, Mapping, Optional

import httpx

from apps.ai.chunking.document import NormalizedDocument

from .ports import (
    DocumentRejected,
    EmptyExtraction,
    ExtractedDocument,
    ExtractorUnavailable,
    Provenance,
    Usage,
)

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
ATTEMPTS = 2
_RETRY_PAUSE_SECONDS = 5.0
_CONNECT_SECONDS = 10.0
# Sending the PDF and reading the answer, on top of every attempt.
TRANSFER_SLACK_SECONDS = 60

# A key, quota or rate fault is the deployment's, never the document's.
_NOT_THE_DOCUMENT = {401, 402, 403, 408, 429}
_NOT_CONTENT = {"PageBreak"}

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
        api: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._shape = shape
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
        return (ATTEMPTS * self._attempt_seconds(self._max_pages)
                + (ATTEMPTS - 1) * _RETRY_PAUSE_SECONDS + TRANSFER_SLACK_SECONDS)

    def _attempt_seconds(self, pages: int) -> float:
        return float(self._base_seconds + self._per_page_seconds * pages)

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        pages = _page_count(pdf_bytes)
        attempt_seconds = self._attempt_seconds(pages)
        if self._api is not None:
            response = self._partition(self._api, pdf_bytes, filename, attempt_seconds)
        else:
            with httpx.Client(base_url=self._base_url,
                              headers={"unstructured-api-key": self._api_key}) as api:
                response = self._partition(api, pdf_bytes, filename, attempt_seconds)

        elements = _elements(response)
        if not any(e.get("type") not in _NOT_CONTENT and (e.get("text") or "").strip()
                   for e in elements):
            raise EmptyExtraction(f"Unstructured found no content in {filename!r}")
        raw = {"elements": _without_signed_urls(elements)}
        document = self._shape(raw)
        if not document.elements:
            raise EmptyExtraction(f"no extractable content for {filename!r}")
        options = {**REQUEST_OPTIONS, "call": {
            "mode": "synchronous", "attempts": ATTEMPTS, "attempt_timeout_seconds": attempt_seconds,
        }}
        return ExtractedDocument(
            document=document,
            provenance=Provenance(name=EXTRACTOR_NAME, version=VERSION, options=options),
            usage=Usage(pages=_billed_pages(response) or pages),
            raw=raw,
        )

    def _partition(self, api: httpx.Client, pdf_bytes: bytes, filename: str,
                   attempt_seconds: float) -> httpx.Response:
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
            return response
        raise AssertionError("unreachable")


def _check(response: httpx.Response) -> None:
    status = response.status_code
    if status in _NOT_THE_DOCUMENT or status >= 500:
        raise ExtractorUnavailable(f"Unstructured partition returned {status}")
    if status >= 400:
        raise DocumentRejected(f"Unstructured partition returned {status}: {_detail(response)}")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
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
    return isinstance(value, str) and value.startswith("http") and (
        "Signature=" in value or "X-Amz-" in value or "sig=" in value
    )


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    try:
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception as exc:
        raise DocumentRejected("the PDF could not be opened to count its pages") from exc
