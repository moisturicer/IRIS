"""LlamaExtract reading a completed LlamaParse job (IR-846, ADR-056 §15).

The one module that knows LlamaExtract's v2 HTTP contract. ``read`` names the
parse job IR-841 already ran (``pjb-…``) as the input, so the Manuscript is
not uploaded or parsed a second time. One fixed schema; citations and
confidence on. Whether a paper may be read is decided around this adapter
(IR-850), never here.

The contract is written from LlamaIndex's documentation
(``/llamaparse/extract/api``, ``/llamaparse/extract/guides/response-format``,
read 2026-11-03). No response has been recorded yet; the tests use authored
payloads.
"""

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional

import httpx

from .ports import DocumentRejected, ExtractionError, ExtractorUnavailable

logger = logging.getLogger(__name__)

READER_NAME = "llamaextract"

#: The one schema every Manuscript is read with. Never built per paper.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "The paper's title, as printed on its title page."},
        "authors": {
            "type": "array", "items": {"type": "string"},
            "description": "The paper's authors' names, in the order printed. Not advisers or panel members.",
        },
        "abstract": {"type": "string", "description": "The full text of the paper's abstract, without its heading."},
        "keywords": {
            "type": "array", "items": {"type": "string"},
            "description": "The keywords or index terms the paper lists.",
        },
        "publication_year": {"type": "integer", "description": "The year the paper was published, if printed."},
    },
}

DEFAULT_TIMEOUT_SECONDS = 600
_POLL_SECONDS = 2.0
_USAGE_ATTEMPTS = 3
_REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
# A key, credit or rate fault is the deployment's, never the document's.
_NOT_THE_DOCUMENT = {401, 402, 403, 429}


@dataclass(frozen=True)
class MetadataReading:
    """What LlamaExtract returned: values, per-field citations, and its charge.

    ``values`` and ``field_metadata`` are the vendor's, unvalidated. The
    Publish suggestions read them; nothing else does.
    """

    values: Mapping[str, Any]
    field_metadata: Mapping[str, Any]
    credits: Optional[Decimal]

    def as_json(self) -> dict:
        return {"values": dict(self.values), "field_metadata": dict(self.field_metadata)}


class LlamaExtractReader:
    leaves_campus = True

    def __init__(
        self,
        *,
        version: str,
        api_key: str = "",
        base_url: str = "https://api.cloud.llamaindex.ai",
        tier: str = "agentic",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        api: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._version = version
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._tier = tier
        self._timeout = timeout_seconds
        self._api = api
        self._sleep = sleep
        self._clock = clock

    @property
    def model(self) -> str:
        return f"{READER_NAME}-{self._tier}"

    @property
    def account(self) -> str:
        """Admission's per-account fence (IR-850); never the key itself."""
        from apps.ai.admission.ledger import account_for

        return account_for(self._api_key)

    @property
    def timeout_seconds(self) -> float:
        return float(self._timeout)

    @property
    def configuration(self) -> dict:
        return {
            "tier": self._tier,
            "version": self._version,
            "extraction_target": "per_doc",
            "data_schema": SCHEMA,
            "cite_sources": True,
            "confidence_scores": True,
        }

    def read(self, parse_job_id: str) -> MetadataReading:
        if self._api is not None:
            return self._read(self._api, parse_job_id)
        with httpx.Client(base_url=self._base_url, headers={"Authorization": f"Bearer {self._api_key}"}) as api:
            return self._read(api, parse_job_id)

    def _read(self, api: httpx.Client, parse_job_id: str) -> MetadataReading:
        created = _send(api, "POST", "/api/v2/extract", "create job",
                        json={"file_input": parse_job_id, "configuration": self.configuration})
        job_id = created.json()["id"]
        self._wait(api, job_id)
        result = self._result(api, job_id)
        metadata = (result.get("extract_metadata") or {}).get("field_metadata") or {}
        return MetadataReading(
            values=result.get("extract_result") or {},
            field_metadata=metadata.get("document_metadata") or {},
            credits=_credits(result),
        )

    def _wait(self, api: httpx.Client, job_id: str) -> None:
        started = self._clock()
        while True:
            job = _send(api, "GET", f"/api/v2/extract/{job_id}", "poll").json()
            status = job.get("status")
            if status in _TERMINAL:
                if status != "COMPLETED":
                    # The vendor's message is logged, never shown or stored.
                    logger.warning("LlamaExtract job %s ended %s: %s", job_id, status,
                                   str(job.get("error_message") or "")[:300])
                    raise ExtractionError(f"LlamaExtract job {job_id} ended {status}")
                return
            if self._clock() - started >= self._timeout:
                raise ExtractorUnavailable(f"LlamaExtract job {job_id} still {status} after {self._timeout}s")
            self._sleep(_POLL_SECONDS)

    def _result(self, api: httpx.Client, job_id: str) -> dict:
        # Billing can record credits shortly after the job completes.
        for attempt in range(1, _USAGE_ATTEMPTS + 1):
            result = _send(api, "GET", f"/api/v2/extract/{job_id}", "fetch result",
                           params=[("expand", "extract_metadata"), ("expand", "usage")]).json()
            if _credits(result) is not None or attempt == _USAGE_ATTEMPTS:
                return result
            self._sleep(_POLL_SECONDS)
        raise AssertionError("unreachable")


def _send(client: httpx.Client, method: str, url: str, step: str, **kwargs) -> httpx.Response:
    try:
        response = client.request(method, url, timeout=_REQUEST_TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise ExtractorUnavailable(f"LlamaExtract {step} failed: {type(exc).__name__}") from exc
    status = response.status_code
    if status in _NOT_THE_DOCUMENT or status >= 500:
        raise ExtractorUnavailable(f"LlamaExtract {step} returned {status}")
    if status >= 400:
        raise DocumentRejected(f"LlamaExtract {step} returned {status}")
    return response


def _credits(result: Mapping[str, Any]) -> Optional[Decimal]:
    usage = result.get("usage") or {}
    # Only what LlamaExtract itself charged: the parse was charged by IR-841.
    value = usage.get("extract_credits", usage.get("credits"))
    return None if value is None else Decimal(str(value))
