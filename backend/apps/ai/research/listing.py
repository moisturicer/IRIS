"""Presence and listing: a bounded candidate list, shown early, then screened (IR-546).

The application owns every identity and every state. Retrieval ranks, at most
`CANDIDATE_LIMIT` distinct Records are selected, and the reader sees them at
once as `pending`. A model is then shown title-and-abstract (and, for a
paper it was unsure of, a few passages) and may only answer include, exclude
or uncertain for a handle it was issued. Whatever it cannot or does not
answer stays `unassessed`. A candidate is never replaced, so a retry cannot
widen the list, and none is ever described as a match until it is decided.

Access is read again before every send, before every update the reader sees
and before the final list. A paper that became unreadable disappears without
a trace; one whose text changed since it was sent loses its decision.
"""

from __future__ import annotations

import contextvars
import json
import logging
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import connections

from apps.ai.answers.events import (
    EXCLUDED, INCLUDED, PENDING, UNASSESSED, UNCERTAIN,
    CandidatesSelected, CandidatesUpdated,
)
from apps.ai.history import estimate_tokens
from apps.ai.inference import InferenceTask
from apps.ai.models.chunk import DocumentChunk
from apps.ai.providers.deadline import model_call_deadline, time_left
from apps.ai.research.budget import BudgetExhausted
from apps.ai.research.registry import ToolRun
from apps.ai.research.tools.common import QUERY, collect_record, disclosable, readable_records
from apps.ai.research.tools.records import _relevant, rank_record_candidates
from apps.ai.research.tools.screening import DECIDED, SYSTEM, validate_decisions

logger = logging.getLogger(__name__)

#: At most this many distinct Records are screened for one ordinary listing.
#: A constant on purpose: changing it needs measured screening recall, latency
#: and cost on human-labelled pilot data (IR-546), not an environment edit.
CANDIDATE_LIMIT = 20

#: Characters of one passage sent for an uncertain paper.
PASSAGE_CHARS = 1500

STATE_OF = {"include": INCLUDED, "exclude": EXCLUDED, "uncertain": UNCERTAIN, "unassessed": UNASSESSED}

LIST_WORDING = "These are matches found, not a complete list of the papers you can see."


# ---- selection ----------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    ids: tuple[int, ...]
    more_available: bool
    degraded: bool


def select_candidates(run: ToolRun, topic: str, *, limit: int = CANDIDATE_LIMIT) -> Selection:
    """The best `limit` distinct readable Records for ``topic``.

    One ranked list from the vector, word and passage signals already fused
    by Record, so a Record found three ways, or in many chunks, counts once.
    """
    fused, degraded, _ = rank_record_candidates(run, {"topic": topic})
    ids = tuple(dict.fromkeys(fused))
    return Selection(ids[:limit], len(ids) > limit, degraded)


# ---- the outcome --------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    record_id: int
    title: str
    state: str
    #: A verbatim quote that decided it, and where it came from.
    quote: str = ""
    source: Optional[dict] = None
    #: The Record is readable but its content may not go to a model. It counts
    #: as a candidate and as unassessed, and is not named: a paper that AI may
    #: not read is reported only as one that could not be assessed.
    withheld: bool = False

    def wire(self) -> dict:
        if self.withheld:
            return {"record_id": self.record_id, "state": UNASSESSED, "withheld": True}
        row = {"record_id": self.record_id, "title": self.title, "state": self.state}
        if self.quote:
            row.update(quote=self.quote, source=self.source)
        return row


@dataclass(frozen=True)
class Outcome:
    candidates: tuple[Candidate, ...]
    more_available: bool = False
    search_degraded: bool = False
    #: Access or content changed while the run was going.
    changed: bool = False
    limit: int = CANDIDATE_LIMIT

    def count(self, state: str) -> int:
        return sum(c.state == state for c in self.candidates)

    @property
    def decided(self) -> int:
        return self.count(INCLUDED) + self.count(EXCLUDED)

    @property
    def judged(self) -> int:
        return self.decided + self.count(UNCERTAIN)

    @property
    def completeness(self) -> str:
        """`inconclusive` only when nothing was assessed at all."""
        return "inconclusive" if self.candidates and not self.judged else "matches_found"

    @property
    def degraded(self) -> bool:
        return self.search_degraded or self.count(UNASSESSED) > 0

    def coverage(self) -> dict:
        return {
            "limit": self.limit, "selected": len(self.candidates),
            "included": self.count(INCLUDED), "excluded": self.count(EXCLUDED),
            "uncertain": self.count(UNCERTAIN), "unassessed": self.count(UNASSESSED),
            "more_available": self.more_available, "search_degraded": self.search_degraded,
            "changed": self.changed,
        }

    def wording(self) -> str:
        selected = len(self.candidates)
        if not selected:
            return ("No candidate papers were found among the papers you can see. "
                    "This is a search result, not proof that none exist.")
        notes = []
        if self.more_available:
            notes.append(f"More candidates were found than were screened (limit {self.limit}).")
        if self.search_degraded:
            notes.append("Meaning-based search was unavailable, so candidates came from word "
                         "matching only.")
        if self.changed:
            notes.append("The papers you can read changed while this ran; this covers the "
                         "papers still readable.")
        if self.completeness == "inconclusive":
            return " ".join([
                f"Inconclusive: none of the {selected} candidate papers could be assessed, "
                "so this does not show whether any match. Please try again.",
                "Other relevant papers may exist.", *notes])
        counts = (f"Screened {selected} candidate papers: {self.count(INCLUDED)} matched, "
                  f"{self.count(EXCLUDED)} did not match, {self.count(UNCERTAIN)} uncertain, "
                  f"{self.count(UNASSESSED)} could not be assessed.")
        lead = ("" if self.count(INCLUDED) else
                "No matches found among the assessed candidates; other relevant papers may exist. ")
        return " ".join([lead + counts, LIST_WORDING, *notes])

    def wire(self) -> dict:
        """The listing a reader receives, and what a Turn stores (ids only)."""
        return {
            "completeness": self.completeness,
            "wording": self.wording(),
            "records": [{"record_id": c.record_id, "title": c.title}
                        for c in self.candidates if c.state == INCLUDED],
            "candidates": [c.wire() for c in self.candidates],
            "coverage": self.coverage(),
        }


def verify_quote(quote: str, source: Optional[dict], record) -> bool:
    """Does ``quote`` still appear where it was found, in this Record as it is now?"""
    field = (source or {}).get("field")
    if field == "title":
        return quote in record.title
    if field == "abstract":
        return quote in record.abstract
    if field == "passage":
        return DocumentChunk.objects.filter(
            pk=source.get("chunk_id"), record_id=record.pk, deleted_at__isnull=True,
            content__contains=quote,
        ).exists()
    return False


def reader_view(stored: dict, visible: dict) -> dict:
    """A stored listing as the reader may see it now.

    ``visible`` maps Record id to the Record, for the Records the reader can
    see. A candidate that is not there is gone; one whose quote no longer
    holds is unassessed. The wording is rebuilt from what remains, so it
    never counts a paper the reader can no longer see.
    """
    coverage = stored.get("coverage") or {}
    candidates, changed = [], bool(coverage.get("changed"))
    for row in stored["candidates"]:
        record = visible.get(row["record_id"])
        if record is None:
            changed = True
            continue
        if row.get("withheld"):
            candidates.append(Candidate(record.pk, "", UNASSESSED, withheld=True))
            continue
        quote, source, state = row.get("quote", ""), row.get("source"), row["state"]
        if quote and not verify_quote(quote, source, record):
            quote, source, state, changed = "", None, UNASSESSED, True
        candidates.append(Candidate(record.pk, record.title, state, quote, source))
    return Outcome(
        tuple(candidates), bool(coverage.get("more_available")),
        bool(coverage.get("search_degraded")), changed, coverage.get("limit", CANDIDATE_LIMIT),
    ).wire()


# ---- screening ----------------------------------------------------------------


@dataclass(frozen=True)
class _Job:
    batch: tuple
    user: str
    #: handle -> ((page, text, chunk_id), ...) sent beside the abstract.
    passages: dict

    @property
    def ids(self) -> list[int]:
        return [e.record_id for e in self.batch]


@dataclass(frozen=True)
class _Verdict:
    state: str
    quote: str
    source: Optional[dict]
    #: The title and abstract the decision was made from.
    evidence: tuple[str, str]


def _locate(quote: str, item, passages) -> Optional[dict]:
    if quote in item.record_title:
        return {"field": "title"}
    if quote in item.text:
        return {"field": "abstract"}
    for page, text, chunk_id in passages:
        if quote in text:
            return {"field": "passage", "page": page, "chunk_id": chunk_id}
    return None


def _dispatch(jobs, call):
    """``call(job)`` for each job on at most `AI_SCREEN_CONCURRENCY` threads.

    Yields ``(job, future)`` as each finishes, and ``(job, None)`` for any job
    still running when the run's deadline arrives. Each job runs in a copy of
    this context, so it carries the run's deadline and admission scope.
    """
    if not jobs:
        return
    pool = ThreadPoolExecutor(
        max_workers=max(1, min(settings.AI_SCREEN_CONCURRENCY, len(jobs))),
        thread_name_prefix="listing-screen",
    )
    futures = {}
    try:
        for job in jobs:
            futures[pool.submit(contextvars.copy_context().run, call, job)] = job
        pending = set(futures)
        while pending:
            left = time_left()
            done, pending = wait(
                pending, timeout=None if left is None else max(0.0, left),
                return_when=FIRST_COMPLETED,
            )
            if not done:
                break
            for future in done:
                yield futures[future], future
        for future in pending:
            future.cancel()
            yield futures[future], None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


class _Screening:
    def __init__(self, run: ToolRun, criterion: str, ids: tuple[int, ...],
                 withheld: frozenset = frozenset()) -> None:
        self.run, self.criterion, self.ids, self.withheld = run, criterion, ids, withheld
        self.verdicts: dict[int, _Verdict] = {}
        self.announced = {pk: UNASSESSED if pk in withheld else PENDING for pk in ids}
        self.changed = False
        self.llm = None

    # -- one pass ----------------------------------------------------------

    def screen(self):
        self.llm = self._llm()
        size = max(1, settings.AI_SCREEN_BATCH_SIZE)
        jobs, never_sent = [], []
        sendable_ids = [pk for pk in self.ids if pk not in self.withheld]
        for start in range(0, len(sendable_ids), size):
            chunk = sendable_ids[start:start + size]
            allowed = disclosable(self.run.ctx, chunk)
            never_sent += [(pk, UNASSESSED) for pk in chunk if pk not in allowed]
            batch = tuple(collect_record(self.run.ledger, allowed[pk]) for pk in chunk if pk in allowed)
            if batch:
                jobs.append(self._job(batch))
        # A paper the gate refuses is never sent, and is said to be unassessed now.
        yield from self._announce(never_sent)

        sendable = []
        for job in jobs:
            try:
                if self.llm is None:
                    raise BudgetExhausted("unavailable")
                self._charge(job)
                sendable.append(job)
            except BudgetExhausted:
                yield from self._settle(job, None)
        for job, future in _dispatch(sendable, self._call):
            yield from self._settle(job, self._rows(job, future))
        yield from self._recheck()

    def _recheck(self):
        """Read a few passages for papers the model was unsure of, if limits allow.

        A failed recheck leaves the paper uncertain; only a decision moves it.
        """
        cap = settings.AI_SCREEN_RECHECK_MAX_RECORDS
        if self.llm is None or settings.AI_SCREEN_RECHECK_PASSAGES < 1 or cap < 1:
            return
        unsure = [pk for pk in self.ids if self.verdicts.get(pk) and self.verdicts[pk].state == UNCERTAIN]
        if not unsure:
            return
        needed = settings.AI_SCREEN_TIMEOUT_SECONDS
        left = time_left()
        if (left is not None and left < needed) or self.run.spend.remaining_seconds < needed:
            return
        allowed = disclosable(self.run.ctx, unsure[:cap])
        batch, passages = [], {}
        for pk in unsure[:cap]:
            record = allowed.get(pk)
            found = self._passages(record) if record is not None else ()
            if found:
                item = collect_record(self.run.ledger, record)
                batch.append(item)
                passages[item.handle] = found
        if not batch:
            return
        job = self._job(tuple(batch), passages)
        try:
            self._charge(job)
        except BudgetExhausted:
            return
        for sent, future in _dispatch([job], self._call):
            rows = self._rows(sent, future)
            if rows is not None:
                yield from self._settle(sent, rows, only_decisions=True)

    # -- pieces ------------------------------------------------------------

    def _llm(self):
        try:
            return self.run.root.llm_for(InferenceTask.SCREEN)
        except Exception as exc:
            logger.warning("listing screening unavailable",
                           extra={"run_id": self.run.ctx.run_id, "error": type(exc).__name__})
            return None

    def _job(self, batch, passages=None) -> _Job:
        passages = passages or {}
        records = []
        for item in batch:
            row = {"record": item.handle, "title": item.record_title, "abstract": item.text}
            if item.handle in passages:
                row["passages"] = [{"page": page, "text": text} for page, text, _ in passages[item.handle]]
            records.append(row)
        user = json.dumps({"criterion": self.criterion, "records": records}, ensure_ascii=False)
        return _Job(batch, user, passages)

    def _charge(self, job: _Job) -> None:
        """Main thread only: `Spend` is not safe to share with workers."""
        if self.run.spend.remaining_seconds <= 0:
            raise BudgetExhausted("wall_clock_seconds")
        self.run.spend.charge_prompt_tokens(estimate_tokens(SYSTEM + job.user))

    def _call(self, job: _Job) -> str:
        """One vendor call, on a worker. No database access but its own, closed after."""
        try:
            with model_call_deadline(settings.AI_SCREEN_TIMEOUT_SECONDS):
                if time_left() <= 0:
                    raise BudgetExhausted("wall_clock_seconds")
                reply = self.llm.generate(SYSTEM, job.user)
                if time_left() <= 0:
                    raise TimeoutError("late screening response")
                return reply
        finally:
            connections.close_all()

    def _rows(self, job: _Job, future) -> Optional[list]:
        """The validated decisions for ``job``, or ``None`` if there are none to trust."""
        if future is None or future.cancelled():
            return None
        error = future.exception()
        if error is not None:
            # A vendor can echo input in its message: keep the type only.
            logger.info("listing screening batch failed",
                        extra={"run_id": self.run.ctx.run_id, "error": type(error).__name__})
            return None
        try:
            return validate_decisions(future.result(), job.batch, job.passages)
        except Exception:
            return None

    def _passages(self, record) -> tuple:
        try:
            found = self.run.root.retriever(records=frozenset({record.pk})).retrieve(
                self.criterion, self.run.ctx.user, limit=settings.AI_SCREEN_RECHECK_PASSAGES,
            )
        except Exception:
            return ()
        return tuple(
            (p.source_page, p.content[:PASSAGE_CHARS], p.chunk_id)
            for p in _relevant(found) if p.record_id == record.pk
        )[:settings.AI_SCREEN_RECHECK_PASSAGES]

    def _settle(self, job: _Job, rows, *, only_decisions: bool = False):
        """Keep each decision whose paper is still readable, disclosable and unchanged."""
        readable = {r.pk: r for r in readable_records(self.run.ctx).filter(pk__in=job.ids)}
        settled = []
        rows = rows or [{"record": e.handle, "decision": "unassessed", "quote": ""} for e in job.batch]
        for item, row in zip(job.batch, rows):
            if only_decisions and row["decision"] not in DECIDED:
                continue
            record = readable.get(item.record_id)
            same = (record is not None and self.run.ctx.permits(record)
                    and (record.title, record.abstract) == (item.record_title, item.text))
            if not same:
                self.changed = True
            decision = row["decision"] if same else "unassessed"
            quote = row["quote"] if same and decision in DECIDED else ""
            source = _locate(quote, item, job.passages.get(item.handle, ())) if quote else None
            self.verdicts[item.record_id] = _Verdict(
                STATE_OF[decision], quote if source else "", source,
                (item.record_title, item.text),
            )
            settled.append((item.record_id, self.verdicts[item.record_id].state))
        yield from self._announce(settled)

    def _announce(self, rows):
        """Tell the reader the new states of papers they can still read."""
        readable = set(readable_records(self.run.ctx).filter(pk__in=[pk for pk, _ in rows])
                       .values_list("pk", flat=True))
        shown = [(pk, state) for pk, state in rows if pk in readable]
        if len(shown) != len(rows):
            self.changed = True
        fresh = [(pk, state) for pk, state in shown if self.announced.get(pk) != state]
        if fresh:
            self.announced.update(fresh)
            yield CandidatesUpdated(tuple({"record_id": pk, "state": state} for pk, state in fresh))

    # -- the result --------------------------------------------------------

    def finish(self, selection: Selection) -> Outcome:
        """Reconcile every candidate against the Records as they are now."""
        records = {r.pk: r for r in readable_records(self.run.ctx).filter(pk__in=self.ids)}
        candidates = []
        for pk in self.ids:
            record = records.get(pk)
            if record is None:
                self.changed = True
                continue
            if pk in self.withheld:
                candidates.append(Candidate(pk, "", UNASSESSED, withheld=True))
                continue
            verdict = self.verdicts.get(pk)
            kept = (verdict is not None and self.run.ctx.permits(record)
                    and verdict.evidence == (record.title, record.abstract)
                    and (not verdict.quote or verify_quote(verdict.quote, verdict.source, record)))
            if kept:
                candidates.append(Candidate(pk, record.title, verdict.state, verdict.quote, verdict.source))
                continue
            if verdict is not None and verdict.state != UNASSESSED:
                self.changed = True
            candidates.append(Candidate(pk, record.title, UNASSESSED))
        return Outcome(tuple(candidates), selection.more_available, selection.degraded, self.changed)


def screen_listing(run: ToolRun, question: str):
    """Yield the preview and every update; return the `Outcome`."""
    criterion = question.strip()[:QUERY["maxLength"]]
    selection = select_candidates(run, criterion)
    records = {r.pk: r for r in readable_records(run.ctx).filter(pk__in=selection.ids)}
    ids = tuple(pk for pk in selection.ids if pk in records)
    if not ids:
        return Outcome((), selection.more_available, selection.degraded)

    # Counted among the twenty, never sent, never named.
    allowed = disclosable(run.ctx, ids)
    withheld = frozenset(pk for pk in ids if pk not in allowed)
    yield CandidatesSelected(
        tuple({"record_id": pk, "state": UNASSESSED, "withheld": True} if pk in withheld else
              {"record_id": pk, "title": records[pk].title, "state": PENDING} for pk in ids),
        CANDIDATE_LIMIT, selection.more_available, selection.degraded,
    )
    screening = _Screening(run, criterion, ids, withheld)
    try:
        yield from screening.screen()
    except Exception as exc:
        # Keep what was decided; the rest stays unassessed, never excluded.
        logger.warning("listing screening stopped", extra={
            "run_id": run.ctx.run_id, "error": type(exc).__name__})
    outcome = screening.finish(selection)
    final = [(c.record_id, c.state) for c in outcome.candidates]
    yield from screening._announce(final)
    return outcome
