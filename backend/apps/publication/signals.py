from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.records.models import Record
from .dispatch import reconcile


@receiver(post_save, sender=Record, dispatch_uid="publication.committed_manuscript")
def committed_manuscript(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(lambda record_id=instance.pk: reconcile(limit=1, record_id=record_id), robust=True)
