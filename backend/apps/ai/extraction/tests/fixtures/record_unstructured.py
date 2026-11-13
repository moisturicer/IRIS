"""Record Unstructured Transform's output for the synthetic PDFs (IR-984, ADR-067).

Manual only, never CI: every run spends vendor pages. From ``backend/``::

    UNSTRUCTURED_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_unstructured

Writes ``unstructured/<fixture>/result.json`` and ``manifest.json`` per PDF.
``--pdf PATH --out DIR`` records any other PDF outside the repo, and
``--measure DIR...`` prints what the spike report counts. See
``unstructured/README.md``.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

from . import DIRECTORY, FIXTURES, pdf_bytes

RECORDINGS = DIRECTORY / "unstructured"

BASE_URL = "https://transform.unstructured.io"
PROFILE = "balanced"
INCLUDE = ("coordinates", "table_html")
OPTIONS = {"output": "elements", "profile": PROFILE, "include": list(INCLUDE)}

_DONE = {"completed", "completed_with_warnings"}
_TERMINAL = _DONE | {"failed", "cancelled"}
_POLL_SECONDS = 3.0
_JOB_TIMEOUT_SECONDS = 1800.0
_SECRET_HEADER_PARTS = ("cookie", "authorization", "key", "token", "signature")


class RecordingFailed(RuntimeError):
    pass


def record(
    name: str,
    pdf: bytes,
    out_dir: Path,
    *,
    api: httpx.Client,
    wait: Optional[int] = None,
    profile: str = PROFILE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Path:
    """Parse one PDF and write its recording under ``out_dir / name``.

    ``wait`` sends ``Prefer: wait=N``; omitted, Transform waits its default.
    """
    headers = {"Prefer": f"wait={wait}"} if wait is not None else {}
    options = {**OPTIONS, "profile": profile}
    started = clock()
    parsed = api.post(
        "/api/v2/parse",
        params=[("include", value) for value in options["include"]],
        files={"input": (f"{name}.pdf", pdf, "application/pdf")},
        data={"output": options["output"], "profile": options["profile"]},
        headers=headers,
    )
    _check(parsed, "parse")
    body = parsed.json()
    job_id = body.get("id")
    file_id = (body.get("source") or {}).get("file_id")
    location, polls, terminal = None, 0, False
    last_headers = parsed.headers
    try:
        if parsed.status_code == 202:
            location = parsed.headers.get("location") or body.get("poll_url")
            if not location:
                raise RecordingFailed("202 without a Location or poll_url")
            body, polls, last_headers = _wait(api, location, options, sleep)
        terminal = True
        latency = clock() - started
        file_id = file_id or (body.get("source") or {}).get("file_id")

        target = out_dir / name
        target.mkdir(parents=True, exist_ok=True)
        _write_json(target / "result.json", scrub(body))
        _write_json(
            target / "manifest.json",
            {
                "fixture": f"{name}.pdf",
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "endpoint": f"POST {api.base_url.copy_with(path='/api/v2/parse')}",
                "options": options,
                "prefer": headers.get("Prefer"),
                "http_status": parsed.status_code,
                "location": location,
                "polls": polls,
                "job_id": job_id,
                "status": body.get("status"),
                "profile": body.get("profile"),
                "format_version": body.get("format_version"),
                "latency_seconds": round(latency, 1),
                "response_headers": safe_headers(parsed.headers),
                "final_response_headers": safe_headers(last_headers),
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        return target
    except RecordingFailed:
        terminal = True
        raise
    finally:
        failing = sys.exc_info()[1] is not None
        if file_id:
            _delete(api, f"/api/v2/upload/{file_id}", failing=failing)
        if job_id and terminal:
            _delete(api, f"/api/v2/jobs/{job_id}", failing=failing)


def _wait(api: httpx.Client, location: str, options: dict, sleep: Callable[[float], None]):
    # The jobs endpoint defaults to markdown; it needs output and include again.
    params = [("output", options["output"])] + [("include", v) for v in options["include"]]
    polls, waited = 0, 0.0
    while True:
        polled = api.get(location, params=params)
        polls += 1
        _check(polled, "poll")
        job = polled.json()
        status = job.get("status")
        if status in _TERMINAL:
            if status not in _DONE:
                raise RecordingFailed(f"job ended {status}: {job.get('error')}")
            return job["result"], polls, polled.headers
        if waited >= _JOB_TIMEOUT_SECONDS:
            raise RecordingFailed(f"job still {status} after {waited:.0f}s")
        sleep(_POLL_SECONDS)
        waited += _POLL_SECONDS


def _delete(api: httpx.Client, path: str, *, failing: bool) -> None:
    """ADR-056 decision 7, carried by ADR-067; never hides an error already in flight."""
    try:
        _check(api.delete(path), f"delete {path}")
    except (httpx.HTTPError, RecordingFailed) as error:
        if not failing:
            raise RecordingFailed(f"{path} may remain: {error}") from error
        print(f"{path} may remain: {error}", file=sys.stderr)


def safe_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        k.lower(): v for k, v in headers.items()
        if not any(part in k.lower() for part in _SECRET_HEADER_PARTS)
    }


def scrub(value: Any) -> Any:
    """Signed URLs grant access while they live; never commit one."""
    if isinstance(value, dict):
        return {
            k: scrub(v) for k, v in value.items()
            if k != "presigned_url" and not _signed(v)
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def _signed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("http") and (
        "Signature=" in value or "X-Amz-" in value or "sig=" in value
    )


# -- what the spike report counts -----------------------------------------


def _boxes(coordinates: Any) -> list[dict]:
    if isinstance(coordinates, dict):
        return [coordinates]
    if isinstance(coordinates, list):
        return [c for c in coordinates if isinstance(c, dict)]
    return []


def _is_text(element: dict) -> bool:
    return element.get("type") != "Image" and bool((element.get("text") or "").strip())


def measure(result: dict) -> dict:
    elements = result.get("elements") or []
    text = [e for e in elements if _is_text(e)]
    systems: Counter = Counter()
    keys: set[str] = set()
    for element in elements:
        metadata = element.get("metadata") or {}
        keys.update(metadata)
        for box in _boxes(metadata.get("coordinates")):
            systems[str(box.get("system"))] += 1
    return {
        "page_count": (result.get("metadata") or {}).get("page_count"),
        "status": result.get("status"),
        "profile": result.get("profile"),
        "types": dict(Counter(e.get("type") for e in elements)),
        "text_elements": len(text),
        "text_elements_without_coordinates": sum(
            1 for e in text if not _boxes((e.get("metadata") or {}).get("coordinates"))
        ),
        "coordinate_systems": dict(systems),
        "tables_with_html": sum(
            1 for e in elements
            if e.get("type") == "Table" and (e.get("metadata") or {}).get("text_as_html")
        ),
        "metadata_keys": sorted(keys),
        "warnings": [w.get("code") for w in result.get("warnings") or []],
        "failed_pages": result.get("failed_pages") or [],
        "degraded_pages": result.get("degraded_pages") or [],
    }


def reading_order_holds(elements: Iterable[dict], phrases: Iterable[str]) -> bool:
    """Every phrase is found, each after the one before it."""
    joined = "\n".join(e.get("text") or "" for e in elements)
    at = 0
    for phrase in phrases:
        found = joined.find(phrase, at)
        if found < 0:
            return False
        at = found + len(phrase)
    return True


def _check(response: httpx.Response, step: str) -> None:
    if response.is_error:
        raise RecordingFailed(f"{step} returned {response.status_code}: {response.text[:500]}")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--profile", default=PROFILE, choices=("balanced", "best"))
    parser.add_argument("--wait", type=int, help="send Prefer: wait=N (default: none)")
    parser.add_argument("--pdf", type=Path, action="append", default=[], help="record this PDF instead")
    parser.add_argument("--out", type=Path, help="where --pdf recordings go (never the repo)")
    parser.add_argument("--measure", type=Path, nargs="+", help="print measurements of recorded folders")
    parser.add_argument("fixtures", nargs="*", help=f"any of {', '.join(FIXTURES)}; default all")
    args = parser.parse_args(argv)

    if args.measure:
        report = {}
        for folder in args.measure:
            result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            report[folder.name] = measure(result)
            if folder.name in FIXTURES:
                report[folder.name]["reading_order_holds"] = reading_order_holds(
                    result.get("elements") or [], FIXTURES[folder.name].reading_order
                )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    unknown = set(args.fixtures) - set(FIXTURES)
    if unknown:
        parser.error(f"unknown fixtures: {', '.join(sorted(unknown))}")
    if args.pdf and not args.out:
        parser.error("--pdf needs --out")

    key = os.environ.get("UNSTRUCTURED_API_KEY")
    if not key:
        print("UNSTRUCTURED_API_KEY is not set", file=sys.stderr)
        return 2

    jobs = [(p.stem, p.read_bytes(), args.out) for p in args.pdf] or [
        (name, pdf_bytes(FIXTURES[name]), RECORDINGS) for name in args.fixtures or FIXTURES
    ]
    timeout = httpx.Timeout(1000.0, connect=10.0)
    with httpx.Client(base_url=args.base_url, headers={"unstructured-api-key": key}, timeout=timeout) as api:
        for name, pdf, out in jobs:
            target = record(name, pdf, out, api=api, wait=args.wait, profile=args.profile)
            print(f"recorded {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
