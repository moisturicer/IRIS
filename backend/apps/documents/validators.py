"""Shared, bounded PDF intake (IR-830). No parser runs in the web worker."""
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Optional
import zipfile

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
    # What to do, not only what is wrong: no retry of the same file can pass (IR-1048)
    4: (
        "This PDF contains unsupported active content, such as attached files or scripts. "
        "Save a copy without them (for example, with Print to PDF) and upload that."
    ),
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


SUPPLEMENTARY_TYPES_PROBLEM = "Only PDF, Word, PNG or JPG files are accepted."
# What each accepted extension's first bytes begin with (IR-1220, ADR-032 §10
# as amended 2026-11-18). A PDF may carry a few bytes before its header, so its
# header is looked for anywhere in the first PDF_SIGNATURE_WINDOW bytes.
_LEADING_BYTES = {
    "doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # Word 97-2003: an OLE2 compound file
    "docx": b"PK\x03\x04",  # Office Open XML: a zip, opened below
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
}


def _docx_problem(file) -> bool:
    """True unless the zip is a Word document with no macros in it.

    Only the zip's directory is read; nothing is decompressed. A plain ZIP
    renamed `.docx` has no `word/document.xml`, and a macro-carrying document
    saved as `.docx` keeps its macros in `word/vbaProject.bin`.
    """
    file.seek(0)
    try:
        with zipfile.ZipFile(file) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, ValueError, OSError):
        return True
    finally:
        file.seek(0)
    return "word/document.xml" not in names or "word/vbaProject.bin" in names


def supplementary_file_problem(file) -> Optional[str]:
    """Why an office's supplementary file is refused, or None (IR-1220).

    PDF, Word (.doc, .docx), PNG and JPG only, the types every other upload in
    IRIS keeps to, judged by the extension and by the file's first bytes, so a
    renamed file (an SVG called `.png`, a PNG called `.pdf`) is refused. A PDF
    then has the same safety check as every other PDF upload.
    """
    name = (getattr(file, "name", "") or "").lower()
    extension = name.rsplit(".", 1)[-1] if "." in name else ""
    if not file.size:
        return SUPPLEMENTARY_TYPES_PROBLEM
    file.seek(0)
    head = file.read(PDF_SIGNATURE_WINDOW)
    file.seek(0)
    if extension == "pdf":
        return pdf_upload_problem(file) if b"%PDF-" in head else SUPPLEMENTARY_TYPES_PROBLEM
    leading = _LEADING_BYTES.get(extension)
    if leading is None or not head.startswith(leading):
        return SUPPLEMENTARY_TYPES_PROBLEM
    if extension == "docx" and _docx_problem(file):
        return SUPPLEMENTARY_TYPES_PROBLEM
    return None


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
