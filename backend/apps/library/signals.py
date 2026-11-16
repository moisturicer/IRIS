"""
The library's answers to changes it does not make itself.

When a Record's Manuscript is replaced or removed, or a new Version is
submitted, the places readers kept on bytes no one is served any more are
deleted (IR-573, ADR-044 §Amendment 2026-11-16, resume). The library listens;
`apps/records` never imports it, so a reader's private reading stays out of
the institutional workflow.

A path that writes a new identity with `.update()` sends no signal. Its stale
places are deleted when their reader next opens the paper
(`positions.current`) and are never given back before then.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.records.models import Record, RecordVersion

from . import positions

#: The Record fields that are its Manuscript's identity.
_IDENTITY = {"manuscript_revision", "manuscript_sha256"}


@receiver(post_save, sender=Record, dispatch_uid="library.positions.record")
def _record_saved(sender, instance, created, update_fields=None, **kwargs):
    if created or (update_fields is not None and not _IDENTITY & set(update_fields)):
        return
    positions.forget_replaced(instance)


@receiver(post_save, sender=RecordVersion, dispatch_uid="library.positions.version")
def _version_saved(sender, instance, **kwargs):
    positions.forget_replaced(instance.record)
