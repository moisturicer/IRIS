"""Which passages a search hands the agent (IR-397, IR-1055, ADR-033 §4).

Pure: ranked hits in, ordered passages out. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    id: int
    record_id: int
    chunk_set_id: int
    sequence: int
    #: Heading path from IR-1050; None or empty means the section is unknown.
    section_key: tuple | None
    tokens: int


@dataclass(frozen=True)
class Policy:
    #: Hits one paper may contribute outside Paper Chat; 0 is uncapped.
    per_paper: int = 3
    #: Adjacent chunks of one source arrive together, linked.
    join: bool = True
    #: Budget per requested passage, in chunker tokens; 0 is unbudgeted.
    tokens_per_passage: int = 700
    #: Add unretrieved neighbours from a hit's own section (IR-1055).
    section_mates: bool = True


@dataclass(frozen=True)
class Placed:
    hit: Hit
    #: Chunk id of the passage this one continues, when joined.
    continues: int | None = None
    #: Added for context from the hit's section, not retrieved.
    section_mate: bool = False


def select(ranked, limit: int, policy: Policy, *, scoped: bool = False) -> list[Placed]:
    budget = limit * policy.tokens_per_passage
    kept, per_paper, spent = [], {}, 0
    for hit in ranked:
        if len(kept) == limit:
            break
        if policy.per_paper and not scoped and per_paper.get(hit.record_id, 0) >= policy.per_paper:
            continue
        if budget and kept and spent + hit.tokens > budget:
            continue
        per_paper[hit.record_id] = per_paper.get(hit.record_id, 0) + 1
        kept.append(hit)
        spent += hit.tokens
    return _arrange(kept, set(), policy.join)


def _arrange(items, mates: set[int], join: bool) -> list[Placed]:
    """Rank order, except that contiguous chunks of one source run together.

    Two retrieved hits join only with `join`; a section-mate always sits with its hit.
    """
    rank = {h.id: n for n, h in enumerate(items)}
    by_position = {(h.chunk_set_id, h.sequence): h for h in items}

    def linked(a, b):
        return join or a.id in mates or b.id in mates

    runs, placed = [], set()
    for h in items:
        if h.id in placed:
            continue
        first = h
        while (prev := by_position.get((first.chunk_set_id, first.sequence - 1))) and linked(prev, first):
            first = prev
        run = [first]
        while (nxt := by_position.get((run[-1].chunk_set_id, run[-1].sequence + 1))) and linked(run[-1], nxt):
            run.append(nxt)
        placed.update(x.id for x in run)
        runs.append(run)
    runs.sort(key=lambda run: min(rank[x.id] for x in run))
    return [Placed(x, run[n - 1].id if n else None, x.id in mates)
            for run in runs for n, x in enumerate(run)]
