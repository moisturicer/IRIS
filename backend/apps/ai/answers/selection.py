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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from apps.ai.retrieval.ports import RetrievedChunk
from apps.records.models import Record


def permits_nothing_unknown(record: Record) -> bool:
    """The default gate: the real disclosure predicate."""
    from apps.ai.retrieval.reranking import disclosure_permits

    return disclosure_permits(record)


@dataclass(frozen=True)
class SourceSelection:
    """The passages a model may be shown, out of what retrieval returned."""

    permits: Callable[[Record], bool] = permits_nothing_unknown
    policy_enabled: bool = True
    max_sources: int = 8

    def disclosable(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        if not self.policy_enabled:
            return list(chunks)
        records = Record.objects.filter(pk__in={c.record_id for c in chunks}).in_bulk()
        allowed = {rid for rid, rec in records.items() if self.permits(rec)}
        return [c for c in chunks if c.record_id in allowed]

    def apply(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        return self.disclosable(chunks)[: self.max_sources]
