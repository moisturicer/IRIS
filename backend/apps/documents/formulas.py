"""A Manuscript's display formulas, cropped from its PDF (IR-1102, ADR-067 §Amendment).

``hi_res`` locates each ``Formula``; its OCR text is never the formula. The box
is rendered from the stored PDF in the sandbox (``pdf_evidence/crops.py``) and
kept as an ``ExtractionFormula`` for the formula transcription model.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DocumentKind, ExtractionFormula

logger = logging.getLogger(__name__)

#: Formulas cropped per Manuscript; past it the rest are logged and not kept.
MAX_FORMULAS = 500
PNG = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class FormulaTarget:
    """One shaped Formula element: its name, page and box in page points."""

    name: str
    page: int
    left: float
    top: float
    right: float
    bottom: float

    @property
    def bbox(self) -> dict:
        return {"x": self.left, "y": self.top, "w": self.right - self.left, "h": self.bottom - self.top}

    def fractions(self, size) -> dict:
        width, height = size
        return {"page": self.page, "box": [self.left / width, self.top / height,
                                           self.right / width, self.bottom / height]}


def targets(document) -> list[FormulaTarget]:
    """Each Formula the Extractor located and shaping left as a crop."""
    found = []
    for element in document.elements:
        if element.source_label != "Formula" or element.kind != "image" or not element.figure:
            continue
        boxes = [b for b in element.bboxes if b.page == element.page]
        if not boxes or element.page not in document.page_sizes:
            continue
        found.append(FormulaTarget(
            name=element.figure, page=element.page,
            left=min(b.left for b in boxes), top=min(b.top for b in boxes),
            right=max(b.right for b in boxes), bottom=max(b.bottom for b in boxes),
        ))
    if len(found) > MAX_FORMULAS:
        logger.warning("%s formulas; only the first %s are cropped", len(found), MAX_FORMULAS)
    return found[:MAX_FORMULAS]


def crop(pdf_bytes: bytes, document) -> list[tuple[FormulaTarget, bytes]]:
    """Each target with its PNG crop. Empty when nothing can be cropped here."""
    found = targets(document)
    if not found:
        return []
    crops = _render(pdf_bytes, [t.fractions(document.page_sizes[t.page]) for t in found])
    return [(target, data) for target, data in zip(found, crops) if data]


def _render(pdf_bytes: bytes, boxes: list) -> list:
    """The sandbox child's crops, or none at all if it could not run."""
    from .pdf_evidence import sandbox

    try:
        wall, memory_mib, max_pages = sandbox.limits()
    except ValueError:
        return []
    if sys.platform != "linux" or len(pdf_bytes) > sandbox.MAX_SOURCE_BYTES:
        return []
    try:
        with tempfile.TemporaryDirectory(prefix="iris-formula-crops-") as directory:
            pdf, listed, out = (Path(directory) / name for name in ("source.pdf", "boxes.json", "crops.json"))
            pdf.write_bytes(pdf_bytes)
            listed.write_text(json.dumps(boxes), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("pdf_evidence") / "crops.py"),
                 str(pdf), str(listed), str(out), str(int(memory_mib)), str(int(max_pages))],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=wall, check=False, cwd=directory,
                env={key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}},
            )
            if result.returncode or not out.is_file() or out.stat().st_size > sandbox.MAX_OUTPUT_BYTES:
                logger.warning("formula crops were not rendered (exit %s)", result.returncode)
                return []
            return _read(out.read_text(encoding="utf-8"), len(boxes))
    except (subprocess.TimeoutExpired, OSError):
        logger.warning("formula crops were not rendered: the sandbox did not finish")
        return []


def _read(output: str, expected: int) -> list:
    try:
        crops = json.loads(output)["crops"]
    except (ValueError, KeyError, TypeError):
        return []
    if not isinstance(crops, list) or len(crops) != expected:
        return []
    decoded = []
    for item in crops:
        data = None
        if isinstance(item, str):
            try:
                data = base64.b64decode(item, validate=True)
            except ValueError:
                data = None
        decoded.append(data if data and data.startswith(PNG) else None)
    return decoded


def replace_formulas(extraction, cropped) -> None:
    """Make ``cropped`` the Extraction's whole formula set, for its current revision.
    Called under the Extraction's lock, with the read it belongs to."""
    if extraction.kind != DocumentKind.MANUSCRIPT:
        return
    extraction.formulas.all().delete()
    for target, data in cropped:
        stored = ExtractionFormula(
            extraction=extraction, source_revision=extraction.source_revision,
            name=target.name[:255], page=target.page, bbox=target.bbox,
        )
        stored.image.save("formula.png", ContentFile(data), save=False)
        stored.save()


@receiver(post_delete, sender=ExtractionFormula)
def _remove_image(sender, instance, **kwargs):
    """The crop goes with its row, once the deletion has committed."""
    image = instance.image
    if image.name:
        transaction.on_commit(lambda: image.delete(save=False))
