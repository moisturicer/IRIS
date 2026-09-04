"""Docling-serve as a ``StructuredExtractor``.

The only module in this package that does I/O, and the only one that knows
Docling-serve's HTTP contract. Everything it learns from the wire is handed
straight to ``docling_mapping``, which is pure — so the untestable part of
extraction is one POST and a status check.

**Why the service and not the library.** Docling as a Python package would
put a multi-gigabyte dependency into the Django image and into every Celery
worker. As a service it is one container, already declared in both Compose
files, and extraction throughput scales by replica count rather than by
growing every worker (ADR-016).

**Why ``httpx`` and not ``requests``.** IR-107 asked for ``requests``; the
tree already declares ``httpx`` and already calls the AI gateway with it. A
second HTTP stack for one more call is a dependency, a failure mode and an
exception hierarchy to learn, in exchange for nothing.

**On-premise, and that is load-bearing.** PDF bytes leave the Django process
but never the deployment. That is why this work carries none of the
third-party-transmission exposure that gates the Voyage integration, and it
is a property to check before anyone swaps in a hosted extractor.
"""

import json
from typing import Any, Mapping, Optional

import httpx

from .docling_mapping import normalized_document_from_docling
from .ports import (
    EmptyExtraction,
    ExtractedDocument,
    ExtractionError,
    ExtractorUnavailable,
)

EXTRACTOR_NAME = "docling"

_CONVERT_PATH = "/v1/convert/file"

# OCR is on because a meaningful share of the corpus is scanned submissions,
# and Docling's own OCR is the reason ADR-016 could drop a separate OCR
# fallback library. Accurate table structure is on because theses are full of
# tables and a table read as prose retrieves as noise. Images are off: the
# citation overlay draws regions over the real PDF, so a rendered picture
# would be megabytes of derived asset nothing reads.
_CONVERT_OPTIONS: dict[str, Any] = {
    "to_formats": ["json"],
    "do_ocr": "true",
    "do_table_structure": "true",
    "table_mode": "accurate",
    "include_images": "false",
}

# Statuses docling-serve can report on a conversion it nonetheless returned
# a 200 for. Anything not listed here is treated as usable — "partial_success"
# included, since a document that lost one page is still worth indexing.
_FAILED_STATUSES = {"failure", "skipped", "error"}

# Connecting is either instant or the container is not there. Only the *read*
# deserves the long budget — a scanned thesis through OCR is minutes of work.
# One timeout value for both would make an unreachable host hang for ten
# minutes on a connection that was never going to open.
_CONNECT_TIMEOUT_SECONDS = 10.0

# The standalone default. Deployments override it through
# ``DOCLING_TIMEOUT_SECONDS``; both Compose files set 900 on the extraction
# worker. Defined here so the number has one home in the code.
DEFAULT_TIMEOUT_SECONDS = 600.0


class DoclingExtractor:
    """Extracts through a Docling-serve instance over HTTP.

    ``client`` is injectable so the contract can be tested against a
    transport rather than a container; when it is not supplied one is created
    per call and closed with it.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: Optional[httpx.Client] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        payload = self._convert(pdf_bytes, filename=filename)
        document = normalized_document_from_docling(payload, fallback_title=filename)

        if not document.elements:
            raise EmptyExtraction(
                f"Docling-serve returned no extractable content for {filename!r}. "
                "The PDF may be empty, corrupt, or an image-only scan OCR could not read."
            )
        return ExtractedDocument(document=document, extractor=EXTRACTOR_NAME)

    # -- HTTP ---------------------------------------------------------------

    def _convert(self, pdf_bytes: bytes, *, filename: str) -> Mapping[str, Any]:
        url = f"{self._base_url}{_CONVERT_PATH}"
        files = {"files": (filename, pdf_bytes, "application/pdf")}

        # The timeout rides on the request, not on the client, so an injected
        # client gets the same budget as one built here rather than silently
        # using its own.
        try:
            if self._client is not None:
                response = self._post(self._client, url, files)
            else:
                with httpx.Client() as client:
                    response = self._post(client, url, files)
        except httpx.TimeoutException as exc:
            raise ExtractorUnavailable(
                f"Docling-serve did not respond within {self._timeout:.0f}s at {url}"
            ) from exc
        except httpx.HTTPError as exc:
            # ConnectError, ReadError, protocol violations — all of them say
            # something about the container and nothing about the PDF.
            raise ExtractorUnavailable(f"Docling-serve unreachable at {url}: {exc}") from exc

        return _parse_conversion(response, url=url)

    def _post(self, client: httpx.Client, url: str, files: dict) -> httpx.Response:
        return client.post(
            url, files=files, data=_CONVERT_OPTIONS, timeout=self._timeouts()
        )

    def _timeouts(self) -> httpx.Timeout:
        return httpx.Timeout(self._timeout, connect=_CONNECT_TIMEOUT_SECONDS)


def _parse_conversion(response: httpx.Response, *, url: str) -> Mapping[str, Any]:
    """Turn one docling-serve conversion envelope into its ``DoclingDocument``.

    A 5xx is the service failing; a 4xx is the service rejecting *this*
    document — a page-count or size limit, an unreadable file. Both retry
    under the Celery policy, but only the first is a reason to go and look at
    the container, so they do not share an exception type.
    """
    if response.status_code >= 500:
        raise ExtractorUnavailable(
            f"Docling-serve returned {response.status_code} at {url}: {_excerpt(response)}"
        )
    if response.status_code >= 400:
        raise ExtractionError(
            f"Docling-serve rejected the document ({response.status_code}) at {url}: "
            f"{_excerpt(response)}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ExtractionError(f"Docling-serve returned a non-JSON body at {url}") from exc
    if not isinstance(body, Mapping):
        raise ExtractionError(f"Docling-serve returned an unexpected body shape at {url}")

    status = str(body.get("status") or "").lower()
    if status in _FAILED_STATUSES:
        raise ExtractionError(
            f"Docling-serve reported status {status!r}: {_errors(body)}"
        )

    document = body.get("document")
    content = document.get("json_content") if isinstance(document, Mapping) else None
    if isinstance(content, str):
        # docling-serve has returned json_content both as an object and as an
        # embedded JSON string across versions. Accept either.
        try:
            content = json.loads(content)
        except ValueError as exc:
            raise ExtractionError(
                f"Docling-serve returned an unparseable json_content at {url}"
            ) from exc

    if not isinstance(content, Mapping):
        raise ExtractionError(
            f"Docling-serve returned no structured content at {url}. "
            "Structure is the point of this call — a markdown-only response is not usable."
        )
    return content


def _excerpt(response: httpx.Response, limit: int = 300) -> str:
    try:
        return response.text[:limit]
    except Exception:  # pragma: no cover - a body that cannot be decoded at all
        return "<unreadable body>"


def _errors(body: Mapping[str, Any]) -> str:
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(e) for e in errors)
    return "no detail reported"
