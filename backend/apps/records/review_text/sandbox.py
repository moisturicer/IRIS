"""Runs the review text reader in the IR-830 sandbox (ADR-058 §1 as amended, IR-871).

The reader parses an untrusted PDF, so it never runs in this process: it runs
in a fresh, isolated interpreter (``python -I``) with no environment beyond
``PATH`` and ``LANG``, under a wall-time limit, an address-space cap and a page
cap, the same way upload checks run (``apps/documents/validators.py``). Its
exit code says what happened, and only a clean exit's JSON is read back, after
a size cap and a shape check.

**A sandbox that returns data** (IR-871 review; PDF_INTAKE.md §Review
text). Upload checks return only an exit code; this child must return text. So
it opens its input and output first and then confines itself (`reader.confine`):
it can open no further file, socket or pipe, so a parser taken over by a crafted
PDF has nothing to read and smuggle into the text, neither the worker's
environment under /proc nor another paper. It runs as the worker's user, so this
narrows the risk rather than removing it; a separate OS user would close it.

The limits are its own (``REVIEW_TEXT_*``), because a layout read does much
more work than the upload check. They are required: with any of them unset,
nothing is read and the text waits, ``unavailable``, for
``read_review_texts`` once they are set.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

LIMIT_NAMES = ("REVIEW_TEXT_WALL_SECONDS", "REVIEW_TEXT_MEMORY_MIB", "REVIEW_TEXT_MAX_PAGES")
#: The largest manuscript file the reader is handed, as at upload.
MAX_SOURCE_BYTES = 50 * 1024 * 1024
#: The largest reading read back. A 300-page thesis is a few megabytes.
MAX_OUTPUT_BYTES = 32 * 1024 * 1024

READ = "read"
NO_TEXT = "no_text"
UNAVAILABLE = "unavailable"

#: The child's exit codes (``reader.main``), as a stored reason.
EXIT_REASONS = {2: "unreadable", 3: "encrypted", 5: "over_limits"}


@dataclass
class Outcome:
    state: str
    reason: str = ""
    reading: dict = field(default_factory=dict)
    #: SHA-256 of the bytes handed to the reader, so the caller can check they
    #: are the file the Version names.
    sha256: str = ""


def limits() -> tuple:
    """The configured limits, or ValueError when any is unset or not finite and positive."""
    values = tuple(getattr(settings, name, None) for name in LIMIT_NAMES)
    for index, value in enumerate(values):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0
                or (index > 0 and int(value) != value)):
            raise ValueError("Review text reading requires every REVIEW_TEXT_* limit.")
    return values


def read_in_sandbox(source) -> Outcome:
    """Read ``source``, an open binary file, in the sandbox."""
    try:
        wall, memory_mib, max_pages = limits()
    except ValueError:
        return Outcome(UNAVAILABLE, "limits_unset")
    if sys.platform != "linux":
        return Outcome(UNAVAILABLE, "sandbox_unsupported")
    try:
        with tempfile.TemporaryDirectory(prefix="iris-review-text-") as directory:
            pdf, out = Path(directory) / "source.pdf", Path(directory) / "reading.json"
            total, digest = 0, hashlib.sha256()
            with pdf.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES:
                        return Outcome(NO_TEXT, "over_limits")
                    digest.update(chunk)
                    target.write(chunk)
            sha256 = digest.hexdigest()
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("reader.py")),
                 str(pdf), str(out), str(int(memory_mib)), str(int(max_pages))],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=wall, check=False, cwd=directory,
                env={key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}},
            )
            if result.returncode < 0:
                return Outcome(NO_TEXT, "over_limits", sha256=sha256)   # killed, as by the cap
            if result.returncode:
                return Outcome(NO_TEXT, EXIT_REASONS.get(result.returncode, "unreadable"), sha256=sha256)
            if not out.is_file() or out.stat().st_size > MAX_OUTPUT_BYTES:
                return Outcome(NO_TEXT, "over_limits", sha256=sha256)
            try:
                reading = json.loads(out.read_text(encoding="utf-8"))
            except ValueError:
                # The same file gives the same output, so retrying can't help.
                return Outcome(NO_TEXT, "invalid_output", sha256=sha256)
    except subprocess.TimeoutExpired:
        return Outcome(NO_TEXT, "over_limits")
    except OSError:
        return Outcome(UNAVAILABLE, "sandbox_failed")
    outcome = outcome_of(reading)
    outcome.sha256 = sha256
    return outcome


def outcome_of(reading) -> Outcome:
    """A reading as stored: checked for shape, and ``no_text`` when it holds none.
    A reading of the wrong shape is ``no_text`` too: the same file would give
    the same output, so it is never retried."""
    if not valid(reading):
        return Outcome(NO_TEXT, "invalid_output")
    if not reading["sections"]:
        return Outcome(NO_TEXT, "no_text_layer", reading)
    return Outcome(READ, "", reading)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _region_ok(r):
    return (isinstance(r, dict) and _is_int(r.get("page"))
            and all(isinstance(r.get(k), (int, float)) and 0 <= r[k] <= 1
                    for k in ("left", "top", "right", "bottom")))


def valid(reading) -> bool:
    """Exactly the shape ``reader.read`` writes, and nothing else."""
    if not isinstance(reading, dict) or not isinstance(reading.get("reader"), str):
        return False
    if not _is_int(reading.get("page_count")) or not isinstance(reading.get("warnings"), list):
        return False
    sections = reading.get("sections")
    if not isinstance(sections, list):
        return False
    for s in sections:
        # Within the columns they are stored in: `key` 255, `text_hash` 64, pages from 1.
        if not (isinstance(s, dict) and isinstance(s.get("key"), str) and 0 < len(s["key"]) <= 255
                and isinstance(s.get("heading"), str) and _is_int(s.get("page")) and s["page"] >= 1
                and isinstance(s.get("text_hash"), str) and len(s["text_hash"]) == 64
                and isinstance(s.get("passages"), list)):
            return False
        for p in s["passages"]:
            if not (isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"]
                    and _is_int(p.get("page")) and p["page"] >= 1
                    and _is_int(p.get("paragraph")) and p["paragraph"] >= 1
                    and p.get("kind") in ("sentence", "row")
                    and isinstance(p.get("regions"), list) and all(map(_region_ok, p["regions"]))):
                return False
    return len({s["key"] for s in sections}) == len(sections)
