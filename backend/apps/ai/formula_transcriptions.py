"""Formulas as exact LaTeX (IR-1102, ADR-067 §Amendment).

Each stored Formula crop is read by the formula transcription model, which
returns LaTeX and a one-line description. A refused, unreadable or unavailable
call leaves the formula as its crop: the Extractor's OCR text is never used.
With ``AI_FORMULA_TEXT_INDEXED`` on, chunking places both at the formula.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Raised whenever SYSTEM or the reply's reading changes; stored with each request.
PROMPT_VERSION = 1
SYSTEM = (
    "You transcribe one display equation from a research paper, shown as an image. "
    'Reply with a JSON object only: {"latex": "...", "description": "..."}. '
    "latex is the equation exactly as typeset, with no $ or \\[ delimiters. Keep a "
    "printed equation number as \\tag{n}. Ignore partial prose lines cut off at the "
    "edges. description is one plain-language sentence saying what the equation "
    'states. If the image holds no equation, reply {"latex": "", "description": ""}.'
)
USER = "Transcribe this equation."
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_DELIMITERS = re.compile(r"^(?:\$\$|\\\[)\s*(?P<body>.*?)\s*(?:\$\$|\\\])$", re.DOTALL)
_TAG = re.compile(r"\\tag\*?\{([^{}]{1,32})\}")
MAX_DESCRIPTION = 300


class TranscriptionsOwed(Exception):
    """A formula was left untranscribed by a failure worth retrying."""


def read_reply(reply: str) -> tuple[str, str]:
    """``(latex, description)`` from the model's reply; ``("", "")`` when it gave none."""
    try:
        value = json.loads(_FENCE.sub("", reply.strip()))
    except ValueError:
        return "", ""
    if not isinstance(value, dict):
        return "", ""
    latex, description = value.get("latex"), value.get("description")
    if not isinstance(latex, str) or not latex.strip():
        return "", ""
    latex = latex.strip()
    delimited = _DELIMITERS.fullmatch(latex)
    if delimited:
        latex = delimited.group("body").strip()
    lines = description.strip().splitlines() if isinstance(description, str) else []
    return latex, (lines[0].strip()[:MAX_DESCRIPTION] if lines else "")


def equation_number(latex: str) -> str:
    found = _TAG.search(latex)
    return found.group(1).strip() if found else ""


def transcribe_formulas(extraction_id: int, source_revision) -> int:
    """Transcribe each untried Formula of the current read; returns how many got LaTeX.
    Nothing is sent while the Profile is unset or the gate refuses the Record.
    Raises ``TranscriptionsOwed`` after the rest are written if a send failed."""
    from apps.ai.admission.errors import AdmissionDenied
    from apps.ai.composition import composition_root
    from apps.ai.providers.openai_compatible import LLMUnavailable
    from apps.documents.models import ExtractionFormula, PdfExtraction
    from apps.records.models import Record

    extraction = PdfExtraction.objects.filter(pk=extraction_id, record__isnull=False).first()
    if extraction is None or str(extraction.source_revision) != str(source_revision):
        return 0
    root = composition_root()
    transcriber = root.formula_transcriber()
    if transcriber is None:
        return 0
    request = {"prompt_version": PROMPT_VERSION, "dpi": ExtractionFormula.CROP_DPI,
               "models": list(root.formula_transcriber_models())}
    written = 0
    owed = False
    pending = ExtractionFormula.objects.filter(
        extraction=extraction, source_revision=extraction.source_revision, transcribed_at__isnull=True,
    )
    for formula in pending:
        # Read fresh before each send: a withdrawn consent stops the rest.
        record = Record.objects.filter(pk=extraction.record_id, is_deleted=False).first()
        if record is None or record.manuscript_revision != formula.source_revision \
                or not root.vendor_permits()(record):
            break
        with formula.image.open("rb") as image:
            data = image.read()
        try:
            reply = transcriber.describe_image(SYSTEM, USER, data, formula.media_type)
        except (LLMUnavailable, AdmissionDenied) as error:
            logger.warning("Formula %s was not transcribed: %s", formula.pk, type(error).__name__)
            owed = True
            if isinstance(error, AdmissionDenied):
                break  # every later send would be refused too
            continue
        latex, description = read_reply(reply)
        # A refusal is recorded so it is not paid for again; the crop stays.
        updated = ExtractionFormula.objects.filter(
            pk=formula.pk, source_revision=formula.source_revision, transcribed_at__isnull=True,
        ).update(
            latex=latex, description=description if latex else "",
            equation_number=equation_number(latex), model=_answered_by(transcriber, request),
            request=request, transcribed_at=timezone.now(),
        )
        written += updated if latex else 0
    if written and settings.AI_FORMULA_TEXT_INDEXED:
        _queue_rechunk(extraction.pk, str(extraction.source_revision))
    if owed:
        raise TranscriptionsOwed(f"extraction {extraction.pk} has formulas left to transcribe")
    return written


def _answered_by(transcriber, request) -> str:
    """The model that replied, a fallback included; else the first one asked."""
    used = getattr(transcriber, "last_model_used", None)
    return used if isinstance(used, str) and used else next(iter(request["models"]), "")


def _queue_rechunk(extraction_id: int, source_revision: str) -> None:
    from apps.ai.tasks import chunk_extraction

    transaction.on_commit(lambda: chunk_extraction.delay(extraction_id, source_revision, force=True))


def with_formulas(document, extraction):
    """``document`` with each transcribed Formula as LaTeX, when formulas are indexed.
    Off, the document is returned unchanged, so chunks are exactly as before."""
    from apps.ai.chunking.document import FORMULA
    from apps.documents.models import ExtractionFormula

    if not settings.AI_FORMULA_TEXT_INDEXED:
        return document
    transcribed = {
        name: (latex, description)
        for name, latex, description in ExtractionFormula.objects.filter(
            extraction_id=extraction.pk, source_revision=extraction.source_revision,
        ).exclude(latex="").values_list("name", "latex", "description")
    }
    if not transcribed:
        return document
    return replace(document, elements=tuple(
        replace(e, kind=FORMULA, text=transcribed[e.figure][0], description=transcribed[e.figure][1], figure="")
        if e.source_label == "Formula" and e.kind == "image" and e.figure in transcribed else e
        for e in document.elements
    ))
