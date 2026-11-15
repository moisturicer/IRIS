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
    #: Percent of the budget one paper may fill outside Paper Chat, mates included; 0 is unlimited.
    #: Off by default: every share below 75 lost recall in IR-1150's replay.
    paper_share: int = 0
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


#: How far from a hit a section-mate may sit, in chunks (IR-1055, provisional).
MATE_RADIUS = 2


def select(ranked, limit: int, policy: Policy, *, scoped: bool = False, neighbours=()) -> list[Placed]:
    """Hits by rank under the cap and budget, then section-mates from `neighbours` while the budget holds."""
    kept = choose(ranked, limit, policy, scoped=scoped)
    mates = []
    if policy.section_mates:
        # Each paper's share first; then budget nobody else could use goes to whoever is left.
        mates = _mates(kept, neighbours, limit, policy, scoped)
        mates += _mates(kept, neighbours, limit, policy, True, mates)
    return _arrange(kept + mates, {m.id for m in mates}, policy.join)


def neighbour_positions(kept) -> set[tuple[int, int]]:
    """(chunk set, sequence) pairs a section-mate of `kept` could occupy."""
    return {(h.chunk_set_id, h.sequence + d) for h in kept
            for d in range(-MATE_RADIUS, MATE_RADIUS + 1) if d} - {(h.chunk_set_id, h.sequence) for h in kept}


def _share(limit: int, policy: Policy, scoped: bool) -> float:
    """Tokens one paper may fill; 0 when unlimited."""
    if scoped or not policy.paper_share:
        return 0
    return limit * policy.tokens_per_passage * policy.paper_share / 100


def _mates(kept, neighbours, limit: int, policy: Policy, scoped: bool, already=()) -> list[Hit]:
    """Nearest first, every hit taking its turn at each distance; never across a section or past a share."""
    budget, share = limit * policy.tokens_per_passage, _share(limit, policy, scoped)
    spent = sum(h.tokens for h in (*kept, *already))
    by_paper: dict[int, int] = {}
    for h in (*kept, *already):
        by_paper[h.record_id] = by_paper.get(h.record_id, 0) + h.tokens
    at = {(n.chunk_set_id, n.sequence): n for n in (*neighbours, *kept)}
    taken = {(h.chunk_set_id, h.sequence) for h in (*kept, *already)}
    added = []
    for distance in range(1, MATE_RADIUS + 1):
        for h in kept:
            if not h.section_key:
                continue
            for step in (distance, -distance):
                between = (h.chunk_set_id, h.sequence + step - (1 if step > 0 else -1))
                position = (h.chunk_set_id, h.sequence + step)
                mate = at.get(position)
                if (mate is None or position in taken or mate.section_key != h.section_key
                        or between not in taken or at[between].section_key != h.section_key):
                    continue
                if budget and spent + mate.tokens > budget:
                    continue
                if share and by_paper[mate.record_id] + mate.tokens > share:
                    continue
                taken.add(position)
                added.append(mate)
                spent += mate.tokens
                by_paper[mate.record_id] += mate.tokens
    return added


def choose(ranked, limit: int, policy: Policy, *, scoped: bool = False) -> list[Hit]:
    """The retrieved hits kept, in rank order: each paper within its share, then any budget left to the rest."""
    budget, share = limit * policy.tokens_per_passage, _share(limit, policy, scoped)
    kept, by_paper, spent = [], {}, 0
    for bounded in ((True, False) if share else (False,)):
        for hit in ranked:
            if len(kept) == limit:
                break
            if hit in kept or (budget and kept and spent + hit.tokens > budget):
                continue
            # A paper's first hit always enters; its share bounds the rest until the second pass.
            if bounded and hit.record_id in by_paper and by_paper[hit.record_id] + hit.tokens > share:
                continue
            by_paper[hit.record_id] = by_paper.get(hit.record_id, 0) + hit.tokens
            kept.append(hit)
            spent += hit.tokens
    order = {h.id: n for n, h in enumerate(ranked)}
    return sorted(kept, key=lambda h: order[h.id])


def _arrange(items, mates: set[int], join: bool) -> list[Placed]:
    """Rank order, except that contiguous chunks of one source run together.

    Two retrieved hits join only with `join`; a section-mate always sits with its hit.
    """
    rank = {h.id: n for n, h in enumerate(items)}
    by_position = {(h.chunk_set_id, h.sequence): h for h in items}

    def linked(a, b):
        # A mate sits only with its own section.
        return join or ((a.id in mates or b.id in mates) and a.section_key == b.section_key)

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
