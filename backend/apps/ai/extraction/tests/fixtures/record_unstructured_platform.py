"""Record Unstructured's Platform partition output for the synthetic PDFs (IR-985).

ADR-067's 2026-11-14 amendment moved the Extractor to the Platform API's
``hi_res`` strategy; the Transform recordings beside this stay as IR-984's
spike evidence. Manual only, never CI: every run spends vendor pages. From
``backend/``::

    UNSTRUCTURED_PLATFORM_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_unstructured_platform

Writes ``unstructured_platform/<name>/result.json`` and ``manifest.json`` for
the four layout fixtures, ``blank`` and ``rejected`` (bytes that are not a PDF).
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from apps.ai.extraction.unstructured_client import BASE_URL, PATH
from apps.ai.extraction.unstructured_client import REQUEST_OPTIONS as OPTIONS

from . import DIRECTORY, FIXTURES, blank_pdf, pdf_bytes
from .record_unstructured import safe_headers, scrub

RECORDINGS = DIRECTORY / "unstructured_platform"
NOT_A_PDF = b"this is not a PDF\n"


def record(name: str, pdf: bytes, api: httpx.Client, out_dir: Path = RECORDINGS) -> Path:
    started = time.monotonic()
    response = api.post(PATH, files={"files": (f"{name}.pdf", pdf, "application/pdf")}, data=OPTIONS)
    latency = time.monotonic() - started
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text[:2000]}
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    _write_json(target / "result.json", scrub(body))
    _write_json(target / "manifest.json", {
        "fixture": f"{name}.pdf",
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "endpoint": f"POST {BASE_URL}{PATH}",
        "options": OPTIONS,
        "http_status": response.status_code,
        "latency_seconds": round(latency, 1),
        "response_headers": safe_headers(response.headers),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return target


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="fixture names, blank or rejected; default all")
    args = parser.parse_args(argv)
    key = os.environ.get("UNSTRUCTURED_PLATFORM_API_KEY")
    if not key:
        print("UNSTRUCTURED_PLATFORM_API_KEY is not set", file=sys.stderr)
        return 2
    jobs = {name: pdf_bytes(fixture) for name, fixture in FIXTURES.items()}
    jobs.update(blank=blank_pdf(), rejected=NOT_A_PDF)
    names = args.names or list(jobs)
    timeout = httpx.Timeout(600.0, connect=10.0)
    with httpx.Client(base_url=BASE_URL, headers={"unstructured-api-key": key}, timeout=timeout) as api:
        for name in names:
            print(f"recorded {record(name, jobs[name], api)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
