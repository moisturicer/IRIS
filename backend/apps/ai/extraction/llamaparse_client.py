"""LlamaParse as a ``StructuredExtractor`` (IR-841, ADR-056).

The one module that knows LlamaParse's v2 HTTP contract. ``extract`` uploads
the PDF, starts a job, polls it, fetches the result, the word/line/cell boxes
and the figure crops, then deletes the uploaded file in a ``finally``.

``shape`` (IR-840) turns the raw result into IRIS's document. Whether a paper
may be sent is decided around this adapter (IR-850), never here.
"""

import hashlib
import json
import logging
import re
import time
from contextlib import ExitStack
from decimal import Decimal
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Callable, Iterator, Mapping, Optional
from urllib.parse import urlparse

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

EXTRACTOR_NAME = "llamaparse"
BASE_URLS = {
    "na": "https://api.cloud.llamaindex.ai",
    "eu": "https://api.cloud.eu.llamaindex.ai",
}
EXPAND = ("items", "markdown", "metadata", "job_metadata", "usage", "images_content_metadata")

DEFAULT_TIMEOUT_BASE_SECONDS = 300
DEFAULT_TIMEOUT_PER_PAGE_SECONDS = 30
# Upload, fetch and download time on top of the vendor's own job budget.
TRANSFER_SLACK_SECONDS = 120

_POLL_SECONDS = 2.0
# The vendor enforces the same budget; ours fires only if it does not.
POLL_GRACE_SECONDS = 60
_USAGE_ATTEMPTS = 3
_REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_TIMEOUT_MEMORY_SECONDS = 24 * 60 * 60

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_REJECTED = {
    "DOCUMENT_TOO_LARGE", "PROCESSING_SIZE_LIMIT_EXCEEDED", "CONTENT_POLICY_REFUSAL",
    "TOO_MANY_PAGES", "PDF_IS_PROTECTED", "PDF_IS_BROKEN", "FILE_IS_CORRUPT",
    "UNSUPPORTED_FILE_TYPE", "INVALID_PAGE_RANGE",
}
_EMPTY = {"FILE_IS_EMPTY", "NO_DATA_FOUND_IN_FILE"}
_TIMED_OUT = {"TIMEOUT", "JOB_EXPIRE"}
# A key, credit or download fault is the deployment's, never the document's.
_NOT_THE_DOCUMENT = {401, 402, 403, 429}
_CODE = re.compile(r"\b[A-Z][A-Z_]*[A-Z]\b")

Shape = Callable[[Mapping[str, Any]], NormalizedDocument]


def request_options(
    tier: str, version: str, *, base_seconds: int, per_page_seconds: int,
) -> dict[str, Any]:
    """ADR-056 decision 3: everything LlamaParse can return for a paper."""
    return {
        "tier": tier,
        "version": version,
        "disable_cache": True,
        "processing_options": {
            "cost_optimizer": {"enable": True},
            "confidence_score_effort": "high",
            "specialized_chart_parsing": "agentic",
        },
        "output_options": {
            "granular_bboxes": ["word", "line", "cell"],
            "extract_printed_page_number": True,
            "markdown": {"tables": {"merge_continued_tables": True}},
            "images_to_save": ["layout"],
        },
        "processing_control": {
            "timeouts": {
                "base_in_seconds": base_seconds,
                "extra_time_per_page_in_seconds": per_page_seconds,
            },
        },
    }


def _first_timeout(key: str) -> bool:
    """True the first time this PDF times out; a second is the document's fault."""
    from django.core.cache import cache

    try:
        return cache.add(f"llamaparse:timeout:{key}", True, _TIMEOUT_MEMORY_SECONDS)
    except Exception:
        logger.warning("LlamaParse timeout memory unavailable; treating the timeout as transient")
        return True


class LlamaParseExtractor:
    leaves_campus = True

    def __init__(
        self,
        *,
        shape: Shape,
        version: str,
        api_key: str = "",
        base_url: str = BASE_URLS["na"],
        tier: str = "agentic",
        timeout_base_seconds: int = DEFAULT_TIMEOUT_BASE_SECONDS,
        timeout_per_page_seconds: int = DEFAULT_TIMEOUT_PER_PAGE_SECONDS,
        max_pages: int = 1000,
        api: Optional[httpx.Client] = None,
        downloads: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        remember_timeout: Callable[[str], bool] = _first_timeout,
    ):
        self._shape = shape
        self._version = version
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._tier = tier
        self._base_seconds = timeout_base_seconds
        self._per_page_seconds = timeout_per_page_seconds
        self._max_pages = max_pages
        self._api = api
        self._downloads = downloads
        self._sleep = sleep
        self._clock = clock
        self._remember_timeout = remember_timeout
        self._options = request_options(
            tier, version, base_seconds=timeout_base_seconds, per_page_seconds=timeout_per_page_seconds,
        )

    @property
    def timeout_seconds(self) -> float:
        return self._job_seconds(self._max_pages) + POLL_GRACE_SECONDS + TRANSFER_SLACK_SECONDS

    def _job_seconds(self, pages: int) -> float:
        return self._base_seconds + self._per_page_seconds * pages

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        pages = _page_count(pdf_bytes)
        with ExitStack() as stack:
            api = self._api or stack.enter_context(httpx.Client(
                base_url=self._base_url, headers={"Authorization": f"Bearer {self._api_key}"},
            ))
            # Presigned URLs need no key, so the key never reaches the storage host.
            downloads = self._downloads or stack.enter_context(httpx.Client())
            raw, figures = self._read(api, downloads, pdf_bytes, filename, pages)

        failed = _failed_pages(raw)
        if not any(page.get("items") for page in _pages(raw, "items")):
            raise EmptyExtraction(f"LlamaParse found no content in {filename!r}")
        document = self._shape(raw)
        if not document.elements:
            raise EmptyExtraction(f"no extractable content for {filename!r}")
        return ExtractedDocument(
            document=document,
            provenance=Provenance(name=EXTRACTOR_NAME, version=self._version, options=self._options),
            failed_pages=failed,
            usage=Usage(pages=len(_pages(raw, "metadata")) or pages, credits=_credits(raw)),
            figures=figures,
            raw=raw,
        )

    # -- the job ------------------------------------------------------------

    def _read(self, api, downloads, pdf_bytes, filename, pages):
        uploaded = _send(api, "POST", "/api/v1/beta/files", "upload",
                         files={"file": (filename, pdf_bytes, "application/pdf")},
                         data={"purpose": "parse"})
        file_id = uploaded.json()["id"]
        try:
            created = _send(api, "POST", "/api/v2/parse", "create job",
                            json={"file_id": file_id, **self._options})
            job_id = created.json()["id"]
            self._wait(api, job_id, pdf_bytes, pages)
            result = self._result(api, job_id)
            grounded = _grounded_items(downloads, result)
            figures = tuple(_figures(downloads, result))
            raw = {**_without_presigned_urls(result), "grounded_items": grounded}
            return raw, figures
        finally:
            _delete(api, file_id)

    def _wait(self, api, job_id: str, pdf_bytes: bytes, pages: int) -> None:
        started = self._clock()
        deadline = started + self._job_seconds(pages) + POLL_GRACE_SECONDS
        while True:
            job = _send(api, "GET", f"/api/v2/parse/{job_id}", "poll").json()["job"]
            if job["status"] in _TERMINAL:
                if job["status"] != "COMPLETED":
                    self._job_failed(job, pdf_bytes)
                return
            now = self._clock()
            if now >= deadline:
                raise ExtractorUnavailable(
                    f"LlamaParse job {job_id} still {job['status']} after {now - started:.0f}s"
                )
            self._sleep(_POLL_SECONDS)

    def _job_failed(self, job: Mapping[str, Any], pdf_bytes: bytes) -> None:
        message = job.get("error_message") or ""
        codes = set(_CODE.findall(message))
        summary = f"LlamaParse job {job.get('id')} ended {job['status']}: {message[:300]}"
        if job["status"] == "CANCELLED" or "JOB_CANCELLED" in codes:
            raise ExtractorUnavailable(summary)
        if codes & _TIMED_OUT:
            if self._remember_timeout(hashlib.sha256(pdf_bytes).hexdigest()):
                raise ExtractorUnavailable(summary)
            raise DocumentRejected(f"{summary} (timed out twice)")
        if codes & _EMPTY:
            raise EmptyExtraction(summary)
        if codes & _REJECTED:
            raise DocumentRejected(summary)
        raise ExtractionError(summary)

    def _result(self, api, job_id: str) -> dict:
        # Billing can record credits shortly after the job completes.
        for attempt in range(1, _USAGE_ATTEMPTS + 1):
            result = _send(api, "GET", f"/api/v2/parse/{job_id}", "fetch result",
                           params={"expand": ",".join(EXPAND)}).json()
            if _credits(result) is not None or attempt == _USAGE_ATTEMPTS:
                return result
            self._sleep(_POLL_SECONDS)


# -- HTTP ---------------------------------------------------------------------


def _send(client: httpx.Client, method: str, url: str, step: str, **kwargs) -> httpx.Response:
    try:
        response = client.request(method, url, timeout=_REQUEST_TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise ExtractorUnavailable(f"LlamaParse {step} failed: {type(exc).__name__}") from exc
    status = response.status_code
    if status in _NOT_THE_DOCUMENT or status >= 500 or (step == "download" and status >= 400):
        raise ExtractorUnavailable(f"LlamaParse {step} returned {status}")
    if status >= 400:
        raise DocumentRejected(f"LlamaParse {step} returned {status}: {response.text[:300]}")
    return response


def _delete(api: httpx.Client, file_id: str) -> None:
    """ADR-056 decision 7. Never masks an error already in flight."""
    try:
        _send(api, "DELETE", f"/api/v1/beta/files/{file_id}", "delete file")
    except ExtractionError as error:
        logger.error("LlamaParse uploaded file %s may remain: %s", file_id, error)


def _download(downloads: httpx.Client, url: str) -> bytes:
    return _send(downloads, "GET", url, "download").content


def _grounded_items(downloads: httpx.Client, result: Mapping[str, Any]) -> list:
    meta = ((result.get("result_content_metadata") or {}).get("grounded_items") or {})
    if not meta.get("presigned_url"):
        return []
    text = _download(downloads, meta["presigned_url"]).decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _figures(downloads: httpx.Client, result: Mapping[str, Any]) -> Iterator[FigureImage]:
    items = {name: (page, item) for page, item in _image_items(result) for name in [_basename(item.get("url"))] if name}
    for image in (result.get("images_content_metadata") or {}).get("images", []):
        if image.get("category") != "layout" or not image.get("presigned_url"):
            continue
        found = items.get(image["filename"])
        if found is None:
            # Its metadata stays in ``raw``; only the page is unknown.
            logger.warning("LlamaParse figure %s matches no image item; not kept", image["filename"])
            continue
        page, item = found
        yield FigureImage(
            page=page, bbox=image.get("bbox") or {}, data=_download(downloads, image["presigned_url"]),
            media_type=image.get("content_type") or "application/octet-stream",
            caption=item.get("caption"),
        )


def _image_items(result: Mapping[str, Any]) -> Iterator[tuple[int, Mapping[str, Any]]]:
    def walk(items):
        for item in items or ():
            if item.get("type") == "image":
                yield item
            yield from walk(item.get("items"))

    for page in _pages(result, "items"):
        for item in walk(page.get("items")):
            yield page["page_number"], item


# -- reading the result -------------------------------------------------------


def _pages(result: Mapping[str, Any], key: str) -> list:
    return list(((result.get(key) or {}).get("pages")) or [])


def _failed_pages(result: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(sorted({
        page["page_number"]
        for key in ("items", "markdown") for page in _pages(result, key)
        if page.get("success") is False
    }))


def _credits(result: Mapping[str, Any]) -> Optional[Decimal]:
    value = ((result.get("job") or {}).get("usage") or {}).get("credits")
    return None if value is None else Decimal(str(value))


def _basename(url: Optional[str]) -> str:
    return PurePosixPath(urlparse(url).path).name if url else ""


def _without_presigned_urls(value: Any) -> Any:
    """Signed URLs grant access while they live; never stored."""
    if isinstance(value, dict):
        return {k: _without_presigned_urls(v) for k, v in value.items() if k != "presigned_url"}
    if isinstance(value, list):
        return [_without_presigned_urls(v) for v in value]
    return value


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    try:
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception as exc:
        raise DocumentRejected("the PDF could not be opened to count its pages") from exc
