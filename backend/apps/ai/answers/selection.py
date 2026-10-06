"""Which retrieved passages the model is given (IR-133 / IR-394).

Split out of `GroundedAnswerService` so the eval harness can measure the final
set **without calling a model**. Before this, the only way to learn what the
model received was to ask for an answer, which needs a configured vendor and
spends generation credits on a retrieval measurement.

That makes this the place ADR-033 §3–§4's relevance cut-off, per-paper cap and
token budget belong when they land (IR-396, IR-397): put them here and the
harness measures them for free, because the second measure is defined as
"whatever this returns".

Today it is the disclosure gate and the source cap. The gate is the same
predicate `RerankingRetriever` applies to candidates -- applied again, because
a passage reaching a prompt leaves the deployment exactly as a passage reaching
a reranker does.

**This is also where a retrieval is classified** (IR-459). The outcome is
computed over this stage alone, because this gate is the one that runs on
every path, degraded included -- so the counts feeding the decision are always
observable. The recall stage's counts ride along as diagnostics and take no
part in it; `apps/ai/retrieval/diagnostics.py` says why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from apps.ai.retrieval.diagnostics import (
    ChunkBuckets,
    RetrievalConfiguration,
    RetrievalDiagnostics,
    StageDiagnostics,
    chunk_ids,
    classify,
)
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk
from apps.records.models import Record


def permits_nothing_unknown(record: Record) -> bool:
    """The default gate: the real disclosure predicate."""
    from apps.ai.retrieval.reranking import disclosure_permits

    return disclosure_permits(record)


@dataclass(frozen=True)
class Selection:
    """The passages a model may be shown, and why those and no others."""

    passages: tuple[RetrievedChunk, ...]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class SourceSelection:
    """The passages a model may be shown, out of what retrieval returned."""

    permits: Callable[[Record], bool] = permits_nothing_unknown
    policy_enabled: bool = True
    max_sources: int = 8

    def disclosable(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        # Accepted unknown, not a solved problem (IR-460): the response is the
        # same whether this gate removed nothing or everything, but the time
        # taken is not -- gate work scales with what was withheld. Timing is
        # not mitigated here, and nor is repeated probing at a non-zero
        # temperature. See ADR-034 §Security Impact.
        if not self.policy_enabled:
            return list(chunks)
        records = Record.objects.filter(pk__in={c.record_id for c in chunks}).in_bulk()
        allowed = {rid for rid, rec in records.items() if self.permits(rec)}
        return [c for c in chunks if c.record_id in allowed]

    def apply(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        return self.disclosable(chunks)[: self.max_sources]

    def select(self, result: RetrievalResult) -> Selection:
        """What the model may be shown, plus the classified outcome (IR-459).

        `apply` stays the plain answer for the eval harness, which measures the
        final set and has no use for a classification; this is the same gate
        and the same cap, reporting what it did on the way through.
        """
        presented = tuple(result.passages)
        survivors = self.disclosable(presented)
        kept = survivors[: self.max_sources]
        buckets = ChunkBuckets(
            withheld=chunk_ids(presented) - chunk_ids(survivors),
            # Absent, not zero: there is no relevance floor to fall below
            # until IR-396 builds one, so nothing here measured anything.
            below_floor=None,
            kept=chunk_ids(kept),
            not_selected=chunk_ids(survivors) - chunk_ids(kept),
            # Empty when the gate is switched off -- it evaluated nothing,
            # which is observed, and is not an absent count.
            gate_evaluated=chunk_ids(presented) if self.policy_enabled else frozenset(),
        )

        return Selection(
            passages=tuple(kept),
            diagnostics=RetrievalDiagnostics(
                # No relevance signal exists yet, so surviving evidence is
                # unassessed rather than relevant, and never irrelevant.
                outcome=classify(chunk_ids(presented), buckets, relevance_assessed=False),
                selection=StageDiagnostics(
                    buckets=buckets, configuration=self._configuration(result)
                ),
                recall=result.diagnostics,
                degraded=result.degraded,
            ),
        )

    def _configuration(self, result: RetrievalResult) -> RetrievalConfiguration:
        return RetrievalConfiguration(
            mode=result.mode,
            degraded=result.degraded,
            embedding_space_id=result.embedding_space_id,
            disclosure_gate=self.policy_enabled,
            max_sources=self.max_sources,
        )
