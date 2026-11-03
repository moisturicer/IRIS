"""Recover durable work, then optionally wake isolated ingestion workers."""
import logging
import os
from django.db.models import Q
from django.utils import timezone
from apps.ai.grants.config import GrantsUnavailable
from .authority import WorkRefused, issue_grant
from .models import ManuscriptWork

log = logging.getLogger(__name__)
WAKEUP_KEY = "iris_ai:ingestion:wakeup"


def wakeup():
    url = os.environ.get("INGESTION_REDIS_URL", "")
    if not url:
        return
    try:
        from redis import Redis
        with Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1) as client:
            with client.pipeline() as pipe:
                pipe.lpush(WAKEUP_KEY, "1").ltrim(WAKEUP_KEY, 0, 63).execute()
    except Exception:
        log.warning("ingestion wakeup lost; committed work remains recoverable")


def reconcile(*, limit: int, record_id=None) -> int:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    work = ManuscriptWork.objects.filter(revoked_at=None).filter(
        Q(grant_expires_at=None) | Q(grant_expires_at__lte=timezone.now()))
    if record_id is not None:
        work = work.filter(record_id=record_id)
    ids = list(work.order_by("created_at", "pk").values_list("pk", flat=True)[:limit])
    published = 0
    for work_id in ids:
        try:
            issue_grant(work_id)
        except WorkRefused:
            continue
        except GrantsUnavailable:
            break  # pending is durable even before grants are enabled
        published += 1
    if published:
        wakeup()
    return published
