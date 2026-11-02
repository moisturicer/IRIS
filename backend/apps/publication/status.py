"""Safe acknowledgement status; it never claims completed extraction."""
from django.db import connection, transaction, ProgrammingError
from .models import ManuscriptWork


def processing_status(record):
    work = ManuscriptWork.objects.filter(record=record, revoked_at=None).first()
    if work is None:
        return None
    acknowledged = False
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT iris_ai.manuscript_acknowledged(%s, %s)",
                           [str(work.pk), work.authority_generation])
            acknowledged = cursor.fetchone()[0]
    except ProgrammingError as exc:
        # AI migrations are additive and may not have been installed yet.
        if getattr(exc.__cause__, "pgcode", None) not in ("42883", "3F000"):
            raise
    return {"state": "acknowledged_pending" if acknowledged else "pending_processing",
            "revision": str(work.revision)}
