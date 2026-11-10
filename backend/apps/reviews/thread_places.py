"""
Each later Version finds an open anchored thread's passage again (ADR-032 §7,
*Outdated threads*; IR-876, decided 2026-11-09).

**A thread follows its passage.** Version N is searched for the thread's text
in Version N-1: the quote while it has only been found, the edited passage
once it has changed. Each Version adds one `ThreadPlace`; the thread's own
anchor never changes, so an Outdated thread still shows the Version it was
written on.

**Outdated stays Outdated.** The first *changed* or *removed* place makes the
thread Outdated from that Version on, and only resolving it ends that. A
removed passage leaves nothing to follow, so no later Version is searched.
Nothing here resolves, reopens or answers a thread.

**When.** A Version's text is read in the background (ADR-058 §1), so this
runs after each read (`apps.records.tasks.read_review_text`) and after a
Version is submitted, and does nothing until both readings exist. The two
readings are the comparison's own pair (`readings.pair`), so one reader
reads both and a thread never disagrees with the Changes tab.
"""
from __future__ import annotations

from django.db import transaction

from apps.records.models import RecordVersion
from apps.records.review_text import readings
from core.enums import ThreadPlaceOutcome, ThreadState

from . import comparison, placement
from .models import ReviewComment, ThreadPlace
from .version_comparison import as_reading

#: Places a later Version can still follow.
FOLLOWED = (ThreadPlaceOutcome.FOUND, ThreadPlaceOutcome.CHANGED)


def place_threads(record) -> int:
    """Place every open anchored thread of ``record`` in each Version it
    hasn't been placed in yet, oldest first. Returns how many places it wrote."""
    versions = list(RecordVersion.objects.filter(record=record).order_by("number"))
    return sum(_place_in(record, previous, version)
               for previous, version in zip(versions, versions[1:]))


def _place_in(record, previous, version) -> int:
    texts = _followable(record, previous, version)
    if not texts:
        return 0
    pair = readings.pair(previous, version)
    if pair.state != readings.READY:
        return 0
    old, new = as_reading(pair.old), as_reading(pair.new)
    rows = []
    for thread, text in texts:
        place = placement.place(old, new, text)
        rows.append(ThreadPlace(
            thread=thread, version=version, outcome=place.outcome, page=place.page,
            text=place.text, regions=place.regions,
            suggestion_page=_suggestion_page(new, thread.suggestion),
        ))
    with transaction.atomic():
        written = ThreadPlace.objects.bulk_create(rows, ignore_conflicts=True)
    return len(written)


def _followable(record, previous, version) -> list:
    """The open anchored threads with a text to look for in ``version``:
    anchored on ``previous``, or placed there and still followed."""
    done = ThreadPlace.objects.filter(version=version).values("thread_id")
    threads = (ReviewComment.objects
               .filter(record=record, reply_to__isnull=True, state=ThreadState.OPEN)
               .exclude(anchor_version__isnull=True).exclude(anchor_quote="")
               .exclude(pk__in=done))
    out = []
    for thread in threads.filter(anchor_version=previous):
        out.append((thread, thread.anchor_quote))
    places = ThreadPlace.objects.filter(version=previous, outcome__in=FOLLOWED, thread__in=threads)
    for place in places.select_related("thread"):
        out.append((place.thread, place.text))
    return out


def _suggestion_page(reading, suggestion: str):
    """The page a suggested wording appears on in ``reading``, or None."""
    if not suggestion:
        return None
    found = comparison.appears_in(reading, suggestion)
    return found[0][0]["page"] if found else None


def outdated_since(thread):
    """The Version number from which ``thread`` is Outdated, or None."""
    first = (thread.places.exclude(outcome=ThreadPlaceOutcome.FOUND)
             .select_related("version").order_by("version__number").first())
    return first.version.number if first else None
