"""A paper's first page, as the small image beside a Discover row (IR-1241).

Before this, each row downloaded the whole manuscript to draw page 1 in the
browser, and every download wrote a `DOWNLOAD` audit event. Now:

- **Same access as the paper.** The caller resolves the record through
  `visible_to` (`get_object()`); the file is `versions.served_manuscript`,
  the one this reader is shown. No new rule.
- **Never parsed in a web request.** The view only reads the cache. A missing
  image is drawn by `tasks.draw_first_page` on the `extraction` queue, inside
  the IR-830 sandbox (`documents/pdf_evidence/first_page.py`), under that
  sandbox's existing limits.
- **Keyed by the served file's SHA-256**, so a new manuscript version gets a
  new image and readers served the same bytes share one. Stored in the Redis
  cache: it is derived data, re-drawn if lost.
- **Queued once.** `cache.add` sets a pending marker atomically, so only one
  of many simultaneous requests queues the drawing. A failed drawing is
  remembered for a day, so a broken PDF is not re-sandboxed on every visit.
- **No audit event.** A thumbnail is decoration; opening the paper still
  writes `DOWNLOAD`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Bump when the drawing changes (size, format), so old images are not served.
VERSION = "v1"
IMAGE_SECONDS = 30 * 24 * 60 * 60
PENDING_SECONDS = 10 * 60
FAILED_SECONDS = 24 * 60 * 60
#: A WebP of one page at 192 px is ~10-25 KB; anything far larger is refused.
MAX_IMAGE_BYTES = 512 * 1024

READY = "ready"
PENDING = "pending"
NO_MANUSCRIPT = "no_manuscript"
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Lookup:
    state: str
    image: bytes | None = None


def key(kind: str, sha256: str) -> str:
    return f"first-page:{VERSION}:{kind}:{sha256}"


def is_webp(data: bytes) -> bool:
    return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def lookup(record, user) -> Lookup:
    """What `user` is shown for ``record``'s first page, queuing the drawing
    if nobody has asked yet. Reads no PDF."""
    from .versions import served_manuscript, served_manuscript_identity

    if not served_manuscript(record, user):
        return Lookup(NO_MANUSCRIPT)
    _revision, sha256 = served_manuscript_identity(record, user)
    if not sha256:
        # Not fingerprinted yet (backfill_manuscript_fingerprints): there is
        # nothing to key an image by, and hashing it here would read the file.
        return Lookup(UNAVAILABLE)
    image = cache.get(key("image", sha256))
    if image:
        return Lookup(READY, image)
    if cache.get(key("failed", sha256)):
        return Lookup(UNAVAILABLE)
    if cache.add(key("pending", sha256), True, PENDING_SECONDS):
        from .tasks import draw_first_page

        try:
            draw_first_page.delay(record.pk, user.pk, sha256)
        except Exception:
            # The broker is down: let the next request try again.
            cache.delete(key("pending", sha256))
            logger.warning("first page of record %s was not queued", record.pk, exc_info=True)
    return Lookup(PENDING)


def draw(record_id: int, user_id: int, sha256: str) -> str:
    """The task's body: draw the first page of the file ``user`` is served,
    if it is still the one with ``sha256``. Returns what happened."""
    from django.contrib.auth import get_user_model

    from apps.documents.pdf_evidence import sandbox

    from .models import Record
    from .versions import served_manuscript

    try:
        record = Record.objects.get(pk=record_id)
        user = get_user_model().objects.get(pk=user_id)
        served = served_manuscript(record, user)
        if not served:
            return "gone"
        try:
            with served.open("rb") as handle:
                data = handle.read(sandbox.MAX_SOURCE_BYTES + 1)
        except OSError:
            # Named in the database but not on disk: a day before asking again.
            cache.set(key("failed", sha256), "missing_file", FAILED_SECONDS)
            return "missing_file"
        if hashlib.sha256(data).hexdigest() != sha256:
            # Replaced since it was asked for; the new file has its own key.
            return "changed"
        image, error = render(data)
        if image:
            cache.set(key("image", sha256), image, IMAGE_SECONDS)
            return READY
        cache.set(key("failed", sha256), error, FAILED_SECONDS)
        return error
    except (Record.DoesNotExist, get_user_model().DoesNotExist):
        return "gone"
    finally:
        cache.delete(key("pending", sha256))


def render(pdf_bytes: bytes) -> tuple[bytes | None, str]:
    """``(webp, "")`` from the sandbox child, or ``(None, reason)``."""
    from apps.documents.pdf_evidence import sandbox

    try:
        wall, memory_mib, max_pages = sandbox.limits()
    except ValueError:
        return None, "limits_unset"
    if len(pdf_bytes) > sandbox.MAX_SOURCE_BYTES:
        return None, "over_limits"
    if sys.platform != "linux":
        return None, "sandbox_unsupported"
    child = Path(sandbox.__file__).with_name("first_page.py")
    try:
        with tempfile.TemporaryDirectory(prefix="iris-first-page-") as directory:
            pdf, out = Path(directory) / "source.pdf", Path(directory) / "page.webp"
            pdf.write_bytes(pdf_bytes)
            result = subprocess.run(
                [sys.executable, "-I", str(child), str(pdf), str(out), str(int(memory_mib)), str(int(max_pages))],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=wall, check=False, cwd=directory,
                env={name: value for name, value in os.environ.items() if name in {"PATH", "LANG"}},
            )
            if result.returncode < 0:
                return None, "over_limits"
            if result.returncode:
                return None, sandbox.EXIT_REASONS.get(result.returncode, "unreadable")
            if not out.is_file() or out.stat().st_size > MAX_IMAGE_BYTES:
                return None, "over_limits"
            image = out.read_bytes()
    except subprocess.TimeoutExpired:
        return None, "over_limits"
    except OSError:
        return None, "sandbox_failed"
    return (image, "") if is_webp(image) else (None, "invalid_output")
