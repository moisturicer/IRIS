"""Record LlamaParse's output for the synthetic PDFs (IR-849, ADR-056).

Manual only, never CI: every run is a paid vendor call. From ``backend/``::

    LLAMAPARSE_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_llamaparse

Writes ``llamaparse/<fixture>/`` per PDF: ``result.json``,
``grounded_items.jsonl``, ``images/`` and ``manifest.json``. See
``llamaparse/README.md``.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from . import DIRECTORY, FIXTURES, pdf_bytes

RECORDINGS = DIRECTORY / "llamaparse"

BASE_URL = "https://api.cloud.llamaindex.ai"
TIER = "agentic"
# A published dated release; ADR-056 decision 2 forbids "latest".
VERSION = "2026-09-28"

EXPAND = ("items", "markdown", "metadata", "job_metadata", "usage", "images_content_metadata")

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_POLL_SECONDS = 2.0
_JOB_TIMEOUT_SECONDS = 600.0
# Billing records credits shortly after completion.
_USAGE_ATTEMPTS = 10


class RecordingFailed(RuntimeError):
    pass


def configuration(version: str) -> dict[str, Any]:
    """ADR-056 decision 3, without high-effort confidence (IR-851 amendment)."""
    return {
        "tier": TIER,
        "version": version,
        "disable_cache": True,
        "processing_options": {
            "cost_optimizer": {"enable": True},
            "specialized_chart_parsing": "agentic",
        },
        "output_options": {
            "granular_bboxes": ["word", "line", "cell"],
            "extract_printed_page_number": True,
            "markdown": {"tables": {"merge_continued_tables": True}},
            "images_to_save": ["layout"],
        },
    }


def record(
    name: str,
    pdf: bytes,
    out_dir: Path,
    *,
    api: httpx.Client,
    downloads: httpx.Client,
    version: str = VERSION,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Parse one PDF and write its recording under ``out_dir / name``.

    ``api`` carries the key; ``downloads`` fetches presigned URLs and must not.
    """
    if version == "latest":
        raise RecordingFailed("pin a dated version, never 'latest' (ADR-056 decision 2)")
    request = configuration(version)

    uploaded = api.post(
        "/api/v1/beta/files",
        files={"file": (f"{name}.pdf", pdf, "application/pdf")},
        data={"purpose": "parse"},
    )
    _check(uploaded, "upload")
    file_id = uploaded.json()["id"]
    try:
        created = api.post("/api/v2/parse", json={"file_id": file_id, **request})
        _check(created, "create job")
        job_id = created.json()["id"]
        _wait(api, job_id, sleep)
        result = _result_with_credits(api, job_id, sleep)

        target = out_dir / name
        images = target / "images"
        images.mkdir(parents=True, exist_ok=True)
        for image in (result.get("images_content_metadata") or {}).get("images", []):
            (images / Path(image["filename"]).name).write_bytes(_download(downloads, image["presigned_url"]))
        grounded = ((result.get("result_content_metadata") or {}).get("grounded_items") or {})
        if grounded.get("presigned_url"):
            (target / "grounded_items.jsonl").write_bytes(
                _download(downloads, grounded["presigned_url"])
            )

        _write_json(target / "result.json", _without_presigned_urls(result))
        _write_json(
            target / "manifest.json",
            {
                "fixture": f"{name}.pdf",
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "tier": TIER,
                "version": version,
                "request": request,
                "expand": list(EXPAND),
                "job_id": job_id,
                "credits": _credits(result),
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        return target
    finally:
        _delete(api, file_id, failing=sys.exc_info()[1] is not None)


def _delete(api: httpx.Client, file_id: str, *, failing: bool) -> None:
    """ADR-056 decision 7; never hides the error that is already in flight."""
    try:
        deleted = api.delete(f"/api/v1/beta/files/{file_id}")
        _check(deleted, f"delete file {file_id}")
    except (httpx.HTTPError, RecordingFailed) as error:
        if not failing:
            raise RecordingFailed(f"uploaded file {file_id} may remain: {error}") from error
        print(f"uploaded file {file_id} may remain: {error}", file=sys.stderr)


def _wait(api: httpx.Client, job_id: str, sleep: Callable[[float], None]) -> None:
    waited = 0.0
    while True:
        polled = api.get(f"/api/v2/parse/{job_id}")
        _check(polled, "poll")
        job = polled.json()["job"]
        if job["status"] in _TERMINAL:
            if job["status"] != "COMPLETED":
                raise RecordingFailed(f"job {job_id} ended {job['status']}: {job.get('error_message')}")
            return
        if waited >= _JOB_TIMEOUT_SECONDS:
            raise RecordingFailed(f"job {job_id} still {job['status']} after {waited:.0f}s")
        sleep(_POLL_SECONDS)
        waited += _POLL_SECONDS


def _result_with_credits(api: httpx.Client, job_id: str, sleep: Callable[[float], None]) -> dict:
    for _ in range(_USAGE_ATTEMPTS):
        fetched = api.get(f"/api/v2/parse/{job_id}", params={"expand": ",".join(EXPAND)})
        _check(fetched, "fetch result")
        result = fetched.json()
        if _credits(result) is not None:
            return result
        sleep(_POLL_SECONDS)
    return result


def _credits(result: dict) -> float | None:
    return (result["job"].get("usage") or {}).get("credits")


def _download(downloads: httpx.Client, url: str) -> bytes:
    response = downloads.get(url)
    _check(response, "download")
    return response.content


def _without_presigned_urls(value: Any) -> Any:
    """Signed URLs expire and grant access while they live; never commit them."""
    if isinstance(value, dict):
        return {k: _without_presigned_urls(v) for k, v in value.items() if k != "presigned_url"}
    if isinstance(value, list):
        return [_without_presigned_urls(v) for v in value]
    return value


def _check(response: httpx.Response, step: str) -> None:
    if response.is_error:
        raise RecordingFailed(f"{step} returned {response.status_code}: {response.text[:500]}")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default=VERSION, help=f"dated tier version (default {VERSION})")
    parser.add_argument("--base-url", default=BASE_URL, help="regional API host")
    parser.add_argument("fixtures", nargs="*", help=f"any of {', '.join(FIXTURES)}; default all")
    args = parser.parse_args(argv)
    unknown = set(args.fixtures) - set(FIXTURES)
    if unknown:
        parser.error(f"unknown fixtures: {', '.join(sorted(unknown))}")

    key = os.environ.get("LLAMAPARSE_API_KEY")
    if not key:
        print("LLAMAPARSE_API_KEY is not set", file=sys.stderr)
        return 2

    names = args.fixtures or list(FIXTURES)
    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(
        base_url=args.base_url, headers={"Authorization": f"Bearer {key}"}, timeout=timeout
    ) as api, httpx.Client(timeout=timeout) as downloads:
        for name in names:
            target = record(
                name, pdf_bytes(FIXTURES[name]), RECORDINGS,
                api=api, downloads=downloads, version=args.version,
            )
            print(f"recorded {target.relative_to(DIRECTORY)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
