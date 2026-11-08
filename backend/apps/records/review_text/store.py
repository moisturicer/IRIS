"""Each Version's review text: attached, read, reported (ADR-058 §1 as amended, IR-871).

- **Attached at submission.** `write_version`, the one writer of Versions,
  calls `attach()`. A Version that changes the manuscript gets a new
  `pending` text and a read is queued after commit; a metadata-only Version
  points at the previous Version's text and reads nothing again.
- **No gate.** Nothing here asks the extraction gate (ADR-052) or AI consent
  (ADR-054): the reader runs on campus, in the IR-830 sandbox, and calls no
  model. Review text never reaches chunking, embedding or retrieval, and the AI
  never reads it (`test_review_text_isolation.py`).
- **Never re-read in place.** `read_text()` reads only a `pending` or
  `unavailable` text, and writes under the row's lock, so a reading that is
  stored stays the one reviewers commented on.
- **Earlier Versions.** `backfill()` gives a Version from before IR-871 the
  text of its own manuscript file, read as at submission, or `not_kept` when
  that file is gone.
"""
from __future__ import annotations

import logging

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from ..models import RecordVersion, ReviewText, ReviewTextSection, ReviewTextState
from . import readings, sandbox
from .readings import STALE_PENDING

logger = logging.getLogger(__name__)

#: Texts `read_text` may read: nothing stored yet.
READABLE_STATES = (ReviewTextState.PENDING, ReviewTextState.UNAVAILABLE)


def _same_manuscript(version, previous) -> bool:
    """Is ``version``'s manuscript the very file ``previous`` named? By name,
    and by content hash wherever both recorded one, so a name reused for new
    bytes is never taken for the same manuscript."""
    if previous is None or (version.manuscript.name or None) != (previous.manuscript.name or None):
        return False
    return not (version.manuscript_sha256 and previous.manuscript_sha256) or (
        version.manuscript_sha256 == previous.manuscript_sha256
    )


def attach(version, previous) -> None:
    """Give ``version`` its review text, inside ``write_version``'s transaction."""
    if not version.manuscript:
        return
    if _same_manuscript(version, previous):
        version.review_text_id = previous.review_text_id
        version.save(update_fields=["review_text"])
        return
    wanted = readings.current_reader()
    # The same file already read for this reader (a manuscript restored to an
    # earlier Version's) is the same text, so it isn't read twice.
    text, created = ReviewText.objects.get_or_create(
        record_id=version.record_id, source_file=version.manuscript.name,
        manuscript_sha256=version.manuscript_sha256, requested_reader=wanted,
    )
    version.review_text = text
    version.save(update_fields=["review_text"])
    from ..tasks import read_review_text

    if created:
        transaction.on_commit(lambda: read_review_text.delay(text.pk))
    # Earlier Versions get the same reader now, so the comparison with this
    # one is ready when it is opened (ADR-058 §3 as amended, point 4).
    record_id, number = version.record_id, version.number
    transaction.on_commit(lambda: readings.prepare_earlier(record_id, number))


def read_text(text_id) -> str | None:
    """Read one text if nothing is stored for it yet. Returns its state, or None."""
    text = ReviewText.objects.filter(pk=text_id).first()
    if text is None or text.state not in READABLE_STATES:
        return text and text.state
    # No lock is held while the sandbox runs; the write below rechecks.
    try:
        source = default_storage.open(text.source_file, "rb")
    except (FileNotFoundError, OSError):
        outcome = sandbox.Outcome(sandbox.NO_TEXT, "file_missing")
    else:
        with source:
            outcome = sandbox.read_in_sandbox(source)
        if text.manuscript_sha256 and outcome.sha256 and outcome.sha256 != text.manuscript_sha256:
            # Not the file the reviewers were served, so nothing it says is stored.
            outcome = sandbox.Outcome(sandbox.NO_TEXT, "file_changed")
    return _write(text.pk, outcome)


@transaction.atomic
def _write(text_id, outcome) -> str:
    text = ReviewText.objects.select_for_update().get(pk=text_id)
    if text.state not in READABLE_STATES:
        return text.state   # another worker stored it first
    now = timezone.now()
    if outcome.reason in ("file_missing", "file_changed"):
        # The file this Version names is gone or isn't the one submitted. For
        # a Version read later from its own file that is "text not kept"
        # (ADR-058 §1 point 4); at submission it is "No text for vN".
        text.state = (ReviewTextState.NOT_KEPT if text.read_after_submission
                      else ReviewTextState.NO_TEXT)
        text.reason = outcome.reason
    elif outcome.state == sandbox.UNAVAILABLE:
        text.state, text.reason = ReviewTextState.UNAVAILABLE, outcome.reason
        logger.warning("review text %s not read: %s", text.pk, outcome.reason)
    else:
        reading = outcome.reading
        text.reader = reading.get("reader", "")
        text.page_count = reading.get("page_count")
        text.read_at = now
        if outcome.state == sandbox.READ:
            text.state, text.reason, text.warnings = ReviewTextState.READ, "", reading["warnings"]
            ReviewTextSection.objects.bulk_create(
                ReviewTextSection(
                    text=text, ordinal=index, key=s["key"], heading=s["heading"],
                    page=s["page"], text_hash=s["text_hash"], passages=s["passages"],
                )
                for index, s in enumerate(reading["sections"], start=1)
            )
        else:
            text.state, text.reason = ReviewTextState.NO_TEXT, outcome.reason
    text.save()
    return text.state


# --- what a reader is told ------------------------------------------------------

def message(version, text) -> str | None:
    """What a Version's text state reads as. None when there is text."""
    n = f"v{version.number}"
    if text is None:
        return f"{n}'s text hasn't been read yet."
    return {
        ReviewTextState.PENDING: f"{n}'s text is being read.",
        ReviewTextState.UNAVAILABLE: f"{n}'s text hasn't been read yet.",
        ReviewTextState.NO_TEXT: f"No text for {n}, so it can't be compared.",
        ReviewTextState.NOT_KEPT: f"{n}'s text was not kept.",
    }.get(text.state)


def status(version) -> dict | None:
    """The Version's review text state, as `versions_payload` carries it. None with no manuscript."""
    if not version.manuscript:
        return None
    text = version.review_text
    return {
        "state": text.state if text else "not_read",
        "message": message(version, text),
        "warnings": text.warnings if text else [],
        "url": (f"/api/v1/records/{version.record_id}/versions/{version.number}/text/"
                if text and text.state == ReviewTextState.READ else None),
    }


def payload(version) -> dict:
    """The Version's whole review text, for `GET .../versions/<n>/text/`."""
    text = version.review_text
    body = status(version) or {"state": "no_manuscript", "message": None, "warnings": []}
    body.pop("url", None)
    # The reader is never named to a reviewer (ADR-058 §3 as amended, point 5).
    body.update({"version": version.number,
                 "page_count": text.page_count if text else None, "sections": []})
    if text and text.state == ReviewTextState.READ:
        body["sections"] = sections(text)
    return body


def sections(text) -> list:
    """A read text's sections, as the text view and the comparison use them."""
    return [
        {"key": s.key, "heading": s.heading, "page": s.page,
         "text_hash": s.text_hash, "passages": s.passages}
        for s in text.sections.all()
    ]


# --- Versions from before IR-871 ------------------------------------------------

def backfill_plan(record_id=None) -> list:
    """What `backfill` would do: (version, action, previous Version) triples,
    oldest first per record. Retries texts left `unavailable`, and `pending`
    ones older than `STALE_PENDING`; a text two Versions share is retried once."""
    stale, retried = timezone.now() - STALE_PENDING, set()
    versions = RecordVersion.objects.select_related("review_text").order_by("record_id", "number")
    if record_id is not None:
        versions = versions.filter(record_id=record_id)
    plan, previous = [], None
    for v in versions:
        if previous is not None and previous.record_id != v.record_id:
            previous = None
        if v.review_text_id is None and v.manuscript:
            if _same_manuscript(v, previous):
                plan.append((v, "share", previous))
            elif default_storage.exists(v.manuscript.name):
                plan.append((v, "read", previous))
            else:
                plan.append((v, "not_kept", previous))
        elif v.review_text is not None and v.review_text_id not in retried and (
            v.review_text.state == ReviewTextState.UNAVAILABLE
            or (v.review_text.state == ReviewTextState.PENDING and v.review_text.created_at < stale)
        ):
            retried.add(v.review_text_id)
            plan.append((v, "retry", previous))
        previous = v
    return plan


def backfill(record_id=None) -> dict:
    """Give every Version without review text one, reading in this process's
    sandbox; retry texts left `unavailable`. Idempotent: a re-run finds nothing."""
    counts = {"share": 0, "read": 0, "not_kept": 0, "retry": 0}
    for v, action, previous in backfill_plan(record_id):
        v.refresh_from_db()
        counts[action] += 1
        if action == "retry":
            read_text(v.review_text_id)
            continue
        with transaction.atomic():
            v = RecordVersion.objects.select_for_update().get(pk=v.pk)
            if v.review_text_id is not None:
                continue
            if action == "share":
                previous.refresh_from_db(fields=["review_text"])   # given its text earlier in this run
                v.review_text_id = previous.review_text_id
                v.save(update_fields=["review_text"])
                continue
            text = ReviewText.objects.create(
                record_id=v.record_id, source_file=v.manuscript.name,
                manuscript_sha256=v.manuscript_sha256, read_after_submission=True,
                **({"state": ReviewTextState.NOT_KEPT, "reason": "file_missing"}
                   if action == "not_kept" else {}),
            )
            v.review_text = text
            v.save(update_fields=["review_text"])
        if action == "read":
            read_text(text.pk)
    return counts
