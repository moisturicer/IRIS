"""Publishers and consumers agree on queue names (IR-164).

Before this fix, every task published to Celery's own implicit "celery"
queue while docker-compose.yml's three workers consumed only "default",
"extraction" and "embedding" -- so nothing dispatched was ever picked up.
No database and no broker container is needed to catch that regression:
the first tests below inspect the router's own resolution, and the last
dispatches a real task against Celery's in-process "memory://" transport
and lets an actual worker thread consume it, so a route that looks right
but that no worker is subscribed to still fails.
"""

import pytest
from celery.contrib.testing.worker import start_worker
from django.conf import settings

from config.celery import app as celery_app

# Derived from settings rather than restated, so a queue renamed in
# CELERY_TASK_ROUTES/CELERY_TASK_DEFAULT_QUEUE can't drift from this test
# silently. docker-compose.yml's `-Q` flags are the one thing this can't see
# from here -- a queue added there with no route pointing at it is a worker
# with nothing to do, not a bug this test can catch.
WORKER_QUEUES = {settings.CELERY_TASK_DEFAULT_QUEUE} | {
    route["queue"] for route in settings.CELERY_TASK_ROUTES.values()
}


def _resolved_queue(task_name: str) -> str:
    return celery_app.amqp.router.route({}, task_name)["queue"].name


def test_the_extraction_task_routes_to_the_worker_with_docling_access():
    assert _resolved_queue("apps.documents.tasks.extract_pdf_text") == "extraction"


def test_the_embedding_task_routes_to_the_worker_with_vendor_access():
    assert _resolved_queue("apps.ai.tasks.embed_record") == "embedding"


def test_a_task_with_no_special_dependency_routes_to_the_default_worker():
    """Covers every task that isn't explicitly routed -- present
    (``chunk_record_document``, the accounts email tasks) and future -- so
    adding a task without a route can never reproduce this bug silently."""
    assert _resolved_queue("apps.ai.tasks.chunk_record_document") == "default"
    assert _resolved_queue("apps.accounts.tasks.send_email_task") == "default"


def test_every_routed_queue_has_a_worker_subscribed_to_it():
    for task_name in (
        "apps.documents.tasks.extract_pdf_text",
        "apps.ai.tasks.embed_record",
        "apps.ai.tasks.chunk_record_document",
    ):
        assert _resolved_queue(task_name) in WORKER_QUEUES


@pytest.mark.db_required
@pytest.mark.django_db
def test_a_dispatched_task_is_consumed_by_a_worker_listening_on_its_queue():
    """Not configuration inspection: an in-process worker on Celery's own
    memory transport actually receives and runs a task published by name,
    the same way `.delay()` publishes in production -- just without Redis.

    Dispatches ``chunk_record_document`` itself -- one of the two tasks this
    ticket's routing table actually concerns -- rather than an unrelated
    task, so this is evidence about the routing this diff adds, not just
    about Celery's own plumbing. A non-existent upload id is deliberate: the
    task's own "upload deleted before the task ran" branch returns cleanly,
    so this stays a routing/consumption check and never touches real data.
    """
    from apps.ai.tasks import chunk_record_document

    original = {
        "broker_url": celery_app.conf.broker_url,
        "result_backend": celery_app.conf.result_backend,
        "task_always_eager": celery_app.conf.task_always_eager,
    }
    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=False,
    )
    try:
        with start_worker(celery_app, queues=["default"], perform_ping_check=False):
            result = chunk_record_document.delay(999_999)
            assert result.get(timeout=10) is None  # ran to completion, not left queued
    finally:
        celery_app.conf.update(**original)
