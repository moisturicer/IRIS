"""Shared, bounded PDF intake (ADR-053). No parser runs in the web worker."""
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Optional

from django.conf import settings

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024
PDF_SIGNATURE_WINDOW = 1024
LIMIT_NAMES = (
    "PDF_VALIDATION_WALL_SECONDS", "PDF_VALIDATION_MEMORY_MIB",
    "PDF_VALIDATION_MAX_PAGES", "PDF_VALIDATION_MAX_OBJECTS", "PDF_VALIDATION_MAX_DEPTH",
)
PROBLEMS = {
    2: "This file is not a readable PDF.",
    3: "Encrypted PDFs are not accepted.",
    4: "This PDF contains unsupported active content.",
    5: "This PDF exceeds the processing limits.",
    6: "PDF checking is temporarily unavailable. Please try again later.",
}


def validation_limits() -> tuple:
    values = tuple(getattr(settings, name, None) for name in LIMIT_NAMES)
    for index, value in enumerate(values):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0
                or (index > 0 and int(value) != value)):
            raise ValueError("PDF validation requires finite positive limits.")
    return values


def is_pdf_upload(file) -> bool:
    """General attachments retain their formats; PDF claims/bytes opt into checking."""
    file.seek(0)
    signature = file.read(PDF_SIGNATURE_WINDOW)
    file.seek(0)
    return (
        (getattr(file, "name", "") or "").lower().endswith(".pdf")
        or (getattr(file, "content_type", "") or "").lower() == "application/pdf"
        or b"%PDF-" in signature
    )


def pdf_upload_problem(file) -> Optional[str]:
    name = (getattr(file, "name", "") or "").lower()
    mime = (getattr(file, "content_type", "") or "").lower()
    if not name.endswith(".pdf") or mime not in {"application/pdf", "application/octet-stream", ""}:
        return "Only PDF files are accepted."
    if file.size > MAX_PDF_SIZE_BYTES:
        return f"File size {file.size / (1024 * 1024):.1f} MB exceeds the 50 MB limit."
    if not file.size:
        return PROBLEMS[2]
    try:
        limits = validation_limits()
    except ValueError:
        return PROBLEMS[6]
    if sys.platform != "linux":
        return PROBLEMS[6]
    digest = hashlib.sha256()
    try:
        with tempfile.TemporaryDirectory(prefix="iris-pdf-") as directory:
            path = Path(directory) / "source.pdf"
            total = 0
            file.seek(0)
            with path.open("wb") as target:
                for chunk in file.chunks():
                    total += len(chunk)
                    if total > MAX_PDF_SIZE_BYTES:
                        return "File size exceeds the 50 MB limit."
                    digest.update(chunk)
                    target.write(chunk)
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("pdf_inspection.py")),
                 str(path), *(str(value) for value in limits[1:])],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=limits[0], check=False,
                env={key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}},
            )
            if result.returncode:
                return PROBLEMS.get(result.returncode, PROBLEMS[5])
            file.source_sha256 = digest.hexdigest()
            return None
    except subprocess.TimeoutExpired:
        return PROBLEMS[5]
    except OSError:
        return PROBLEMS[6]
    finally:
        file.seek(0)
