"""Runs the PDF evidence reader in the IR-830 sandbox (IR-1053, ADR-067 decision 4).

Shaped like the review text sandbox (``apps/records/review_text/sandbox.py``):
the reader parses an untrusted PDF, so it runs in a fresh ``python -I``
interpreter with only ``PATH`` and ``LANG``, under a wall-time limit, an
address-space cap and a page cap, and confines itself before parsing so it
can open no further file. Only a clean exit's JSON is read back, after a size
cap and a shape check.

**Never raises for a bad PDF.** Every refusal is the empty document with its
reason in ``error``, so extraction still completes without evidence.

Limits: the upload's page cap (``PDF_VALIDATION_MAX_PAGES``) and size cap, plus
its own wall and memory (``PDF_EVIDENCE_*``), because a layout read does far
more work than the upload check. All are required; unset, nothing is read.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings

from apps.documents.validators import MAX_PDF_SIZE_BYTES

from .reader import READER

LIMIT_NAMES = ("PDF_EVIDENCE_WALL_SECONDS", "PDF_EVIDENCE_MEMORY_MIB", "PDF_VALIDATION_MAX_PAGES")
MAX_SOURCE_BYTES = MAX_PDF_SIZE_BYTES
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
#: The child's exit codes (``reader.main``), as a stored error.
EXIT_REASONS = {2: "unreadable", 3: "encrypted", 5: "over_limits"}
KEYS = {"reader", "error", "page_count", "pages", "bookmarks", "page_labels", "contents"}


def empty(error: str) -> dict:
    return {"reader": READER, "error": error, "page_count": 0, "pages": [],
            "bookmarks": [], "page_labels": None, "contents": []}


def limits() -> tuple:
    values = tuple(getattr(settings, name, None) for name in LIMIT_NAMES)
    for index, value in enumerate(values):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0
                or (index > 0 and int(value) != value)):
            raise ValueError("PDF evidence requires every limit.")
    return values


def read_pdf_evidence(pdf_bytes: bytes) -> dict:
    """The evidence of ``pdf_bytes``, or the empty document with its error."""
    try:
        wall, memory_mib, max_pages = limits()
    except ValueError:
        return empty("limits_unset")
    if len(pdf_bytes) > MAX_SOURCE_BYTES:
        return empty("over_limits")
    if sys.platform != "linux":
        return empty("sandbox_unsupported")
    try:
        with tempfile.TemporaryDirectory(prefix="iris-pdf-evidence-") as directory:
            pdf, out = Path(directory) / "source.pdf", Path(directory) / "evidence.json"
            pdf.write_bytes(pdf_bytes)
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("reader.py")),
                 str(pdf), str(out), str(int(memory_mib)), str(int(max_pages))],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=wall, check=False, cwd=directory,
                env={key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}},
            )
            if result.returncode < 0:
                return empty("over_limits")
            if result.returncode:
                return empty(EXIT_REASONS.get(result.returncode, "unreadable"))
            if not out.is_file() or out.stat().st_size > MAX_OUTPUT_BYTES:
                return empty("over_limits")
            try:
                evidence = json.loads(out.read_text(encoding="utf-8"))
            except ValueError:
                return empty("invalid_output")
    except subprocess.TimeoutExpired:
        return empty("over_limits")
    except OSError:
        return empty("sandbox_failed")
    return evidence if valid(evidence) else empty("invalid_output")


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _word(word):
    return (isinstance(word, list) and len(word) == 5 and isinstance(word[0], str)
            and all(map(_num, word[1:])))


def _line(line):
    return (isinstance(line, dict) and set(line) == {"box", "size", "bold", "words"}
            and isinstance(line["box"], list) and len(line["box"]) == 4 and all(map(_num, line["box"]))
            and _num(line["size"]) and isinstance(line["bold"], bool)
            and isinstance(line["words"], list) and all(map(_word, line["words"])))


def _page(page):
    if not (isinstance(page, dict) and _int(page.get("page")) and page["page"] >= 1
            and _num(page.get("width")) and _num(page.get("height"))
            and isinstance(page.get("has_text_layer"), bool)):
        return False
    if not page["has_text_layer"]:
        return set(page) == {"page", "width", "height", "has_text_layer"}
    return (set(page) == {"page", "width", "height", "has_text_layer", "lines"}
            and isinstance(page["lines"], list) and all(map(_line, page["lines"])))


def _bookmark(item):
    return (isinstance(item, dict) and set(item) == {"title", "level", "page"}
            and isinstance(item["title"], str) and _int(item["level"]) and item["level"] >= 1
            and (item["page"] is None or (_int(item["page"]) and item["page"] >= 1)))


def _entry(item):
    return (isinstance(item, dict) and set(item) == {"page", "number", "title", "indent", "page_label"}
            and _int(item["page"]) and item["page"] >= 1 and _num(item["indent"])
            and all(isinstance(item[key], str) for key in ("number", "title", "page_label")))


def valid(evidence) -> bool:
    """Exactly the shape ``reader.read`` writes, and nothing else."""
    if not (isinstance(evidence, dict) and set(evidence) == KEYS and evidence["reader"] == READER
            and evidence["error"] == "" and _int(evidence["page_count"])):
        return False
    labels = evidence["page_labels"]
    return (isinstance(evidence["pages"], list) and len(evidence["pages"]) == evidence["page_count"]
            and all(map(_page, evidence["pages"]))
            and isinstance(evidence["bookmarks"], list) and all(map(_bookmark, evidence["bookmarks"]))
            and (labels is None or (isinstance(labels, list) and all(isinstance(x, str) for x in labels)))
            and isinstance(evidence["contents"], list) and all(map(_entry, evidence["contents"])))
