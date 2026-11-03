"""A Manuscript's Figures: stored when it is read, removed when superseded (IR-845).

ADR-056 §9: the image LlamaParse cropped is downloaded right after the read
and stored with the Manuscript, in storage nothing serves directly.
"""

import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DocumentKind, ExtractionFigure

logger = logging.getLogger(__name__)

#: The file suffix each stored media type gets.
_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


def _media_type(data: bytes):
    """The image type ``data`` starts with, or ``None``."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def replace_figures(extraction, figures) -> None:
    """Make ``figures`` the Extraction's whole set, for its current revision.
    Called under the Extraction's lock, with the result it belongs to."""
    if extraction.kind != DocumentKind.MANUSCRIPT:
        return
    extraction.figures.all().delete()
    for figure in figures:
        # The media type is the vendor's word; a file is served as what its
        # bytes are, so one that is not the image it claims is dropped.
        if _media_type(figure.data) != figure.media_type:
            logger.warning("Figure on page %s of extraction %s is not a %s; not kept",
                           figure.page, extraction.pk, figure.media_type)
            continue
        stored = ExtractionFigure(
            extraction=extraction, source_revision=extraction.source_revision,
            page=figure.page, bbox=dict(figure.bbox), caption=figure.caption or "",
            media_type=figure.media_type,
        )
        stored.image.save(f"figure{_SUFFIX[figure.media_type]}", ContentFile(figure.data), save=False)
        stored.save()


def remove_superseded(extraction) -> None:
    """Drop Figures cropped from any revision but the Extraction's current one."""
    extraction.figures.exclude(source_revision=extraction.source_revision).delete()


@receiver(post_delete, sender=ExtractionFigure)
def _remove_image(sender, instance, **kwargs):
    """Every way a Figure row goes, cascades included, takes its image --
    once the deletion has committed, so a rollback leaves both."""
    image = instance.image
    if image.name:
        transaction.on_commit(lambda: image.delete(save=False))
