"""Planning a corpus-wide embedding run before paying for it (IR-282).

Indexing is metered per token, and IRIS's own token budget is known to
undercount real BPE tokens by roughly 44% (IR-243, deliberately not
recalibrated ahead of IR-133's evidence). A misconfigured chunk size therefore
turns one run into a large bill quietly, which is why the plan is a value
computed *before* anything is sent and not a log line emitted afterwards.

The plan is separated from the command that prints it for the usual reason:
the interesting decisions — what counts as pending, what a stub is, whether
the estimate clears the ceiling — are then testable without capturing stdout,
and the command is left with formatting.

**The estimate is an upper bound, not a quote.** It uses the same estimator
the batching rule uses, so the number an operator is shown and the number the
run actually batches against come from one place; both are ceilings, because
for a spend guard an overcount costs one extra request and an undercount
costs money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

#: Every stub upload in the development database is exactly these bytes. A
#: naive corpus run would put 4,910 of them through structured extraction —
#: 4,910 Docling conversions of a sixteen-byte file. They never produce a
#: chunk set, so they are already skipped by construction; this constant is
#: what lets the report *say so* instead of leaving an operator to wonder why
#: five thousand records were silently absent.
STUB_PDF_BYTES = b"%PDF-1.7 fake bytes"

#: A file at or under this many bytes cannot be a real submission. Sized off
#: the stub above with room to spare, and used only to *classify a skip* —
#: never to decide that something should be deleted or not embedded, so a
#: false positive here costs a mislabelled line in a report and nothing else.
STUB_SIZE_LIMIT = 256


@dataclass(frozen=True)
class RecordPlan:
    """What one record would cost, and why it might cost nothing."""

    record_id: int
    title: str
    pending_chunks: int
    total_chunks: int
    estimated_tokens: int
    #: Stage 1 of ADR-013's retrieval ranks *records* on `RecordEmbedding`
    #: before stage 2 ranks chunks within them, so a record whose chunks are
    #: all embedded but whose summary vector is missing is invisible to
    #: retrieval however complete its chunks are. Planning on pending chunks
    #: alone would never walk such a record again.
    needs_summary: bool = False
    reason: str = ""

    @property
    def has_work(self) -> bool:
        return self.pending_chunks > 0 or self.needs_summary


@dataclass(frozen=True)
class BackfillPlan:
    """The whole run, before a single vendor call.

    ``skipped`` is kept beside ``to_embed`` rather than filtered away: an
    operator who asked to index a corpus and is shown "42 records" needs to
    know whether the other 4,910 were already done, never chunked, or stubs,
    and those are three different problems.
    """

    records: tuple[RecordPlan, ...]
    space_id: Optional[int] = None
    space_model: str = ""
    stub_records: int = 0
    cost_per_million: float = 0.0

    @property
    def to_embed(self) -> tuple[RecordPlan, ...]:
        return tuple(plan for plan in self.records if plan.has_work)

    @property
    def skipped(self) -> tuple[RecordPlan, ...]:
        return tuple(plan for plan in self.records if not plan.has_work)

    @property
    def chunk_count(self) -> int:
        return sum(plan.pending_chunks for plan in self.to_embed)

    @property
    def summary_count(self) -> int:
        return sum(1 for plan in self.to_embed if plan.needs_summary)

    @property
    def estimated_tokens(self) -> int:
        return sum(plan.estimated_tokens for plan in self.to_embed)

    @property
    def estimated_cost(self) -> float:
        """Approximate, and labelled as such wherever it is printed. Vendor
        pricing is not in this repository's control and a figure that looks
        exact invites someone to treat it as a quote."""
        return self.estimated_tokens * self.cost_per_million / 1_000_000

    def exceeds(self, ceiling: int) -> bool:
        return ceiling > 0 and self.estimated_tokens > ceiling


def _is_stub(file_field) -> bool:
    """Is this a placeholder rather than a document?

    Reads the stored size rather than opening the file: the whole point is to
    classify thousands of rows cheaply, and a missing file answers "not a real
    document" just as well as a tiny one.
    """
    if not file_field:
        return False
    try:
        return file_field.size <= STUB_SIZE_LIMIT
    except (OSError, ValueError):
        # The row points at a file that is not there. Not a stub, but equally
        # not something to embed, and not this function's call to make.
        return False


def record_has_only_stub_documents(record) -> bool:
    """True when every document attached to ``record`` is a placeholder.

    A record with no documents at all is *not* a stub record — it is simply
    unsubmitted, and conflating the two would hide a real gap behind a label
    that says "expected".
    """
    files = [upload.file for upload in record.uploads.all()]
    if getattr(record, "abstract_file", None):
        files.append(record.abstract_file)
    files = [f for f in files if f]
    return bool(files) and all(_is_stub(f) for f in files)


def plan_records(
    records: Iterable,
    *,
    space_id: int,
    space_model: str = "",
    cost_per_million: float = 0.0,
    include_summaries: bool = True,
) -> BackfillPlan:
    """Cost every record in ``records`` against the embedding space ``space_id``.

    One query per record rather than a single clever aggregate, deliberately:
    ``pending_chunks`` is the *same* function the run itself calls, so the
    plan cannot disagree with what the run will do. A backfill is an
    occasional operator command, and a plan that is fast but lies about the
    bill is the wrong trade.

    ``include_summaries`` is off when filling a **pending** space, because
    that mode writes chunk vectors only — ``RecordEmbedding`` is one row per
    record with no space key, so a summary vector cannot exist in two spaces
    at once.
    """
    from apps.ai.indexing import active_chunks, estimate_pending_tokens, pending_chunks
    from apps.ai.models import RecordEmbedding

    plans: list[RecordPlan] = []
    stub_records = 0
    # One query for the whole run rather than one per record: this is the
    # only part of the plan that can be answered in bulk without the answer
    # drifting from what the run will do.
    summarised = (
        set(
            RecordEmbedding.objects.filter(model_name=space_model).values_list(
                "record_id", flat=True
            )
        )
        if include_summaries and space_model
        else set()
    )

    for record in records:
        chunks = pending_chunks(record.id, space_id)
        total = active_chunks(record.id).count()
        # Gated on the record having chunks at all. A record with no active
        # chunk set is not in the corpus — the 4,910 placeholders among
        # them least of all — and owing it a summary vector would walk every
        # one of them straight back into the run this skip exists to keep
        # them out of.
        needs_summary = (
            include_summaries
            and bool(space_model)
            and total > 0
            and record.id not in summarised
        )

        reason = ""
        if not chunks and not needs_summary:
            if total:
                reason = "already embedded in this space"
            elif record_has_only_stub_documents(record):
                reason = "placeholder upload, never extracted"
                stub_records += 1
            else:
                reason = "no active chunk set"

        plans.append(
            RecordPlan(
                record_id=record.id,
                title=record.title,
                pending_chunks=len(chunks),
                total_chunks=total,
                estimated_tokens=(
                    estimate_pending_tokens(record.id, space_id) if chunks else 0
                ),
                needs_summary=needs_summary,
                reason=reason,
            )
        )

    return BackfillPlan(
        records=tuple(plans),
        space_id=space_id,
        space_model=space_model,
        stub_records=stub_records,
        cost_per_million=cost_per_million,
    )


@dataclass
class RunReport:
    """What a run actually did, accumulated as it goes.

    Mutable and appended to per record, because the point of a resumable run
    is that it is still meaningful when it stops halfway — a frozen value
    assembled at the end would exist only on the path where nothing went
    wrong.
    """

    embedded_records: int = 0
    embedded_chunks: int = 0
    skipped_records: int = 0
    refused: list[tuple[int, str]] = field(default_factory=list)
    failed: list[tuple[int, str]] = field(default_factory=list)

    def record_outcome(self, outcome) -> None:
        if outcome.refused:
            self.refused.append((outcome.record_id, outcome.reason))
        elif outcome.embedded:
            self.embedded_records += 1
            self.embedded_chunks += outcome.embedded
        else:
            self.skipped_records += 1

    def record_failure(self, record_id: int, error: Exception) -> None:
        self.failed.append((record_id, str(error)))


def default_ceiling() -> int:
    from django.conf import settings

    return getattr(settings, "AI_EMBEDDING_TOKEN_CEILING", 0)


def cost_per_million() -> float:
    from django.conf import settings

    return getattr(settings, "AI_EMBEDDING_COST_PER_MILLION_TOKENS", 0.0)


def records_to_consider(record_ids: Optional[Sequence[int]] = None):
    """The records a run walks, oldest first.

    Deterministic ordering is what makes ``--limit`` mean something across
    two invocations: an unordered queryset would give a second run a
    different slice of the corpus and call it a resume.
    """
    from apps.records.models import Record

    queryset = Record.objects.all().order_by("pk")
    if record_ids:
        queryset = queryset.filter(pk__in=list(record_ids))
    return queryset
