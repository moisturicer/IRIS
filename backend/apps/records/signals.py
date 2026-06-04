from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Record


@receiver(post_save, sender=Record)
def on_record_saved(sender, instance, **kwargs):
    """
    Rebuild the PostgreSQL FTS search_vector whenever a Record is saved.
    Triggered automatically on every save (create or update).

    Skips the update when called from update_search_vector() itself to
    avoid an infinite loop (that function uses QuerySet.update which does
    NOT fire post_save, so re-entrancy is not actually a risk — but the
    guard is kept for clarity).
    """
    from .services import update_search_vector
    update_search_vector(instance)
