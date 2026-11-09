"""Which readings a comparison uses (IR-873, ADR-058 §3 as amended 2026-11-08).

Two readers split the same PDF differently, so a comparison only ever sets two
readings by **one reader** side by side. A Version whose text was read by an
earlier reader is read again from its own file, and that reading is **added**
beside the original, never in its place: the Version keeps pointing at the
reading made at submission, which its text view and its Threads go on using.

- `current_reader()`: the reader this deployment runs.
- `reading_for(version, reader)`: that reader's reading of the Version's file.
- `ensure_current(version)`: the current reader's reading, created and queued
  if there is none. Never re-reads a stored text.
- `prepare_earlier(record_id, number)`: called when Version `number` is
  submitted, so its earlier Versions are ready for the comparison with it.
- `pair(a, b)`: what to compare, or why there is nothing to compare yet.

Readers are never named to a reviewer; nothing here returns a message.
"""
from __future__ import annotations

from dataclasses import dataclass

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import RecordVersion, ReviewText, ReviewTextState
from . import deployed_reader

#: A text still `pending` this long after it was asked for lost its queued read
#: (a worker died, a broker message was dropped), so it is queued again.
STALE_PENDING = timedelta(hours=1)

#: The comparison is waiting for a reading still being made.
PREPARING = "preparing"
#: Both sides have a reading by one reader.
READY = "ready"
#: The current reader failed on a side and no reader is shared by both.
UNAVAILABLE = "unavailable"
#: A side has no text at all (a scan, no manuscript, or a file not kept).
NO_TEXT = "no_text"


def current_reader() -> str:
    # Looked up on each call, so a test can deploy a newer reader by patching
    # `deployed_reader.reader_version`.
    return deployed_reader.reader_version()


def _same_file(text):
    return ReviewText.objects.filter(
        record_id=text.record_id, source_file=text.source_file,
        manuscript_sha256=text.manuscript_sha256,
    )


def _made_by(text, reader) -> bool:
    """Is (or will) ``text`` be ``reader``'s reading? A text not read yet is the
    reader it was requested for; one requested before IR-873 named none, so it
    will be whichever reader reads it, which is the current one."""
    if text.reader:
        return text.reader == reader
    return text.requested_reader in ("", reader)


def reading_for(version, reader) -> ReviewText | None:
    """``reader``'s reading of the Version's manuscript, if there is one: its
    own text when that reader made it, else one a comparison added beside it."""
    original = version.review_text
    if original is None:
        return None
    if _made_by(original, reader):
        return original
    return next((t for t in _same_file(original).order_by("pk") if _made_by(t, reader)), None)


def ensure_current(version) -> ReviewText | None:
    """The current reader's reading of the Version's manuscript, adding one and
    queueing its read when there is none. None when the Version has no text a
    reader could add to: no manuscript, or an original with no text at all."""
    original = version.review_text
    if original is None:
        return None
    reader = current_reader()
    found = reading_for(version, reader)
    if found is not None:
        _requeue_if_lost(found)
        return found
    if original.state in (ReviewTextState.PENDING, ReviewTextState.UNAVAILABLE):
        # Not read yet, though asked for under an earlier reader: a read always
        # runs the reader deployed now, so this text will be the current one.
        _requeue_if_lost(original)
        return original
    if original.state != ReviewTextState.READ:
        # A scan or a missing file reads the same to any reader.
        return None
    try:
        with transaction.atomic():
            text = ReviewText.objects.create(
                record_id=original.record_id, source_file=original.source_file,
                manuscript_sha256=original.manuscript_sha256,
                requested_reader=reader, read_after_submission=True,
            )
    except IntegrityError:
        # Another request added it first (`review_text_one_reading_per_reader`).
        return reading_for(version, reader)
    _queue(text.pk)
    return text


def _queue(text_id):
    from ..tasks import read_review_text

    transaction.on_commit(lambda: read_review_text.delay(text_id))


def _requeue_if_lost(text):
    """A comparison asked again: retry a read that failed, or one whose queued
    task was lost. `read_text` reads only a text with nothing stored."""
    stale = timezone.now() - STALE_PENDING
    if text.state == ReviewTextState.UNAVAILABLE or (
        text.state == ReviewTextState.PENDING and text.created_at < stale
    ):
        _queue(text.pk)


def prepare_earlier(record_id, number) -> int:
    """Give every Version before ``number`` the current reader's reading, so
    the comparison with Version ``number`` opens with no wait. Returns how
    many readings it added."""
    added, reader = 0, current_reader()
    for version in (RecordVersion.objects.select_related("review_text")
                    .filter(record_id=record_id, number__lt=number)):
        if version.review_text is None or reading_for(version, reader) is not None:
            continue
        if ensure_current(version) is not None:
            added += 1
    return added


@dataclass
class Pair:
    state: str
    old: ReviewText | None = None
    new: ReviewText | None = None
    #: The Version with no text, when ``state`` is `NO_TEXT`.
    without_text: RecordVersion | None = None


def _readings_of(version):
    """Every stored reading of the Version's manuscript, by reader."""
    original = version.review_text
    if original is None:
        return {}
    return {t.reader: t for t in _same_file(original).filter(state=ReviewTextState.READ)}


def pair(old_version, new_version) -> Pair:
    """The two readings to compare, both by one reader (ADR-058 §3 as amended):

    1. both read by the current reader: compare them;
    2. a side's current reading is still being made: preparing;
    3. the current reader failed on a side: the newest reader both Versions
       already share, else unavailable (its read is retried next time);
    4. a side has no text at all: no text, whatever the reader.
    """
    for version in (old_version, new_version):
        original = version.review_text
        if original is None or original.state in (ReviewTextState.NO_TEXT, ReviewTextState.NOT_KEPT):
            return Pair(NO_TEXT, without_text=version)
    old, new = ensure_current(old_version), ensure_current(new_version)
    if old is None or new is None:
        return Pair(NO_TEXT, without_text=old_version if old is None else new_version)
    states = {old.state, new.state}
    if states == {ReviewTextState.READ} and old.reader == new.reader:
        return Pair(READY, old, new)
    if ReviewTextState.PENDING in states:
        return Pair(PREPARING)
    # The current reader failed on a side (unavailable, or no text in a file
    # an earlier reader could read). Fall back to a reader both already share;
    # no earlier reader is ever run again.
    older, newer = _readings_of(old_version), _readings_of(new_version)
    shared = older.keys() & newer.keys()
    if shared:
        reader = max(shared, key=lambda r: max(older[r].read_at, newer[r].read_at))
        return Pair(READY, older[reader], newer[reader])
    return Pair(UNAVAILABLE)
