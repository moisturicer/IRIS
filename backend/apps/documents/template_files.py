"""
What a Template may be, and how it is served (ADR-063 decision 8, IR-971).

A Template is a file people download and follow: PDF, Word, spreadsheet or
image, up to 50 MB. It is **never opened inside IRIS**, so no parser runs on
it; the check is the extension *and* the file's first bytes, so a program
renamed `form.pdf` is refused. Everything else is refused, including slides,
plain text, `.csv`, archives, video, programs, scripts and web pages.

`.docx`, `.xlsx`, `.odt` and `.ods` are ZIP containers, so their signature is
ZIP's; `.doc` and `.xls` share the OLE compound-file signature. A ZIP with a
`.docx` name is accepted as a `.docx`: the browser only ever saves it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from django.http import FileResponse

MAX_TEMPLATE_BYTES = 50 * 1024 * 1024

_PDF = (b"%PDF-",)
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
_ZIP = (b"PK\x03\x04",)
_PNG = (b"\x89PNG\r\n\x1a\n",)
_JPEG = (b"\xff\xd8\xff",)

#: extension -> (accepted leading bytes, the content type it is served as)
ACCEPTED = {
    ".pdf":  (_PDF, "application/pdf"),
    ".doc":  (_OLE, "application/msword"),
    ".docx": (_ZIP, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".odt":  (_ZIP, "application/vnd.oasis.opendocument.text"),
    ".xls":  (_OLE, "application/vnd.ms-excel"),
    ".xlsx": (_ZIP, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".ods":  (_ZIP, "application/vnd.oasis.opendocument.spreadsheet"),
    ".png":  (_PNG, "image/png"),
    ".jpg":  (_JPEG, "image/jpeg"),
    ".jpeg": (_JPEG, "image/jpeg"),
}

REFUSED_TYPE = (
    "Templates must be a PDF, Word (.doc, .docx, .odt), spreadsheet "
    "(.xls, .xlsx, .ods) or image (.png, .jpg) file."
)


def _extension(name: str) -> str:
    return Path(name or "").suffix.lower()


def template_problem(file) -> Optional[str]:
    """Why `file` can't be a Template, or None when it can."""
    if file is None:
        return "Choose a file."
    accepted = ACCEPTED.get(_extension(getattr(file, "name", "")))
    if accepted is None:
        return REFUSED_TYPE
    size = getattr(file, "size", 0) or 0
    if size > MAX_TEMPLATE_BYTES:
        return f"File size {size / (1024 * 1024):.1f} MB exceeds the 50 MB limit."
    if not size:
        return "This file is empty."
    file.seek(0)
    head = file.read(16)
    file.seek(0)
    signatures, _ = accepted
    if not any(head.startswith(sig) for sig in signatures):
        return "This file's contents don't match its type."
    return None


def display_name(name: str) -> str:
    """The name a Template downloads under: the uploader's file name, without any path."""
    return Path((name or "").replace("\\", "/")).name[:255] or "template"


def template_response(field_file, filename: str) -> FileResponse:
    """Serve a Template as a download, never inline (decision 8)."""
    _, content_type = ACCEPTED.get(_extension(filename), (None, "application/octet-stream"))
    response = FileResponse(
        field_file.open("rb"), as_attachment=True, filename=filename, content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
