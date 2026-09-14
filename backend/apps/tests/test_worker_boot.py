"""Every routed queue has a worker, and every worker reports whether it is alive (IR-225).

`iris-celery-extraction-1` crash-looped for nine hours on
``ModuleNotFoundError: No module named 'debug_toolbar'`` while `docker ps`
showed only ``Restarting``. `extract_pdf_text` routes to the `extraction`
queue, so nothing consumed it and the whole document pipeline was silent --
0 uploads, 0 extractions, 0 chunks, 0 embeddings.

**Be honest about what a test can catch here.** The cause was a *stale image*:
the three worker services share an identical build spec but were running three
different image SHAs, one built before `django-debug-toolbar` was declared. No
test running inside the `backend` container can observe what is installed
inside the `celery-extraction` container -- they are separate images. Detecting
that at runtime is the healthcheck's job, and `test_every_worker_declares_a_healthcheck`
below exists to stop the healthcheck being dropped again, not to detect a stale
image itself.

What these tests *do* catch is the neighbouring defect, which is the one that
made the outage invisible for so long: a queue that nothing consumes. IR-164
fixed exactly that (tasks routed to queues no worker subscribed to) by editing
two files that had no reason to agree with each other -- `CELERY_TASK_ROUTES`
in settings, and the `-Q` flags in `docker-compose.yml`. Nothing kept them in
step. This does.

Static analysis of the compose file, deliberately: reading the YAML is what
makes the check work in CI, where no stack is running.

**Where this runs.** The `backend` container mounts only `./backend` at `/app`,
so `docker-compose.yml` is not reachable from inside it and these tests skip
there. They run in CI, which checks out the whole repo and runs pytest from
`backend/`, and on any full local checkout. Following `testing.harness`: that
skip becomes a *failure* under ``IRIS_REQUIRE_DB``, so the one environment that
gates merges cannot report green having checked nothing.
"""

import os
import re
from pathlib import Path

import pytest

from testing.harness import strict_mode_requested

#: Repo root -- `backend/` is BASE_DIR, so the compose file is one level up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE = _REPO_ROOT / "docker-compose.yml"

#: A celery worker service's command names its queues after `-Q`.
_QUEUE_FLAG = re.compile(r"celery\b[^\n]*?\s-Q\s+([A-Za-z0-9_,\-]+)")


def _compose_text() -> str:
    """The compose file's text, or a skip -- unless skipping is forbidden here.

    Deliberately not `pytest.skip` unconditionally. A test that silently opts
    out wherever it happens to be inconvenient is the "green but toothless"
    failure this module was written about; `strict_mode_requested` is how the
    rest of this suite already distinguishes a developer's laptop from the
    gate.
    """
    if not _COMPOSE.is_file():
        message = (
            f"docker-compose.yml not found at {_COMPOSE} -- this suite needs a "
            "full repo checkout, not the backend/ mount inside the container"
        )
        if strict_mode_requested(os.environ):
            pytest.fail(message)
        pytest.skip(message)
    return _COMPOSE.read_text(encoding="utf-8")


def _worker_blocks() -> dict[str, str]:
    """
    Map each top-level service that runs a celery *worker* to its YAML block.

    Split on two-space-indented service keys, which is how every service in
    this file is written. `celery-beat` is deliberately included in the split
    and then filtered out by the `-Q` match: beat schedules tasks, it does not
    consume a queue, so it has no `-Q` and never reaches the assertions below.
    """
    text = _compose_text()
    # Service keys sit at exactly two spaces of indentation under `services:`.
    starts = [m for m in re.finditer(r"^  ([a-z0-9][a-z0-9_-]*):$", text, re.MULTILINE)]
    blocks: dict[str, str] = {}
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[match.start():end]
        if _QUEUE_FLAG.search(body):
            blocks[match.group(1)] = body
    return blocks


def _consumed_queues() -> set[str]:
    consumed: set[str] = set()
    for body in _worker_blocks().values():
        for match in _QUEUE_FLAG.finditer(body):
            consumed.update(q.strip() for q in match.group(1).split(",") if q.strip())
    return consumed


def test_compose_declares_at_least_one_celery_worker():
    """A guard on the parsing itself.

    Every assertion below is of the form "everything in set A is in set B".
    If the regex stopped matching -- someone reformats the compose file, or
    switches to list-form commands -- `_consumed_queues()` would return the
    empty set and the interesting tests would start passing vacuously while
    detecting nothing. This is the test that fails first in that case.
    """
    workers = _worker_blocks()
    assert workers, (
        "parsed no celery worker services out of docker-compose.yml -- the "
        "queue assertions in this module would now pass vacuously"
    )


@pytest.mark.django_required
def test_every_routed_queue_has_a_worker_consuming_it():
    """`CELERY_TASK_ROUTES` and the `-Q` flags must agree.

    This is IR-164's defect as a test. A task routed to a queue nothing
    subscribes to is accepted by the broker and then sits there forever: the
    dispatch succeeds, the caller sees no error, and the work silently never
    happens. Failing here is the only cheap way to notice.
    """
    from django.conf import settings

    consumed = _consumed_queues()

    routed = {
        route["queue"]
        for route in settings.CELERY_TASK_ROUTES.values()
        if isinstance(route, dict) and "queue" in route
    }
    default = getattr(settings, "CELERY_TASK_DEFAULT_QUEUE", None)
    if default:
        routed.add(default)

    orphaned = routed - consumed
    assert not orphaned, (
        f"queue(s) {sorted(orphaned)} are routed to in settings but no worker "
        f"in docker-compose.yml consumes them (consumed: {sorted(consumed)}). "
        "Tasks sent there are accepted by the broker and never executed."
    )


def test_every_worker_declares_a_healthcheck():
    """A crash-looping worker must report `unhealthy`, not `Restarting`.

    With `restart: unless-stopped` and no healthcheck, a permanently broken
    worker is indistinguishable at a glance from one that happened to bounce.
    That is what let IR-225 run for nine hours unnoticed. A healthcheck makes
    the difference visible to `docker ps`, to `depends_on: service_healthy`,
    and to anything watching the stack.
    """
    missing = [
        name for name, body in _worker_blocks().items()
        if "healthcheck:" not in body
    ]
    assert not missing, (
        f"celery worker service(s) {sorted(missing)} declare no healthcheck, so "
        "a crash-loop there shows only as 'Restarting' and is easy to miss"
    )
