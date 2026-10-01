"""Is vector search finding what it should (IR-442)?

A question naming a paper almost word for word was answered "the sources do
not contain this": the approximate scan never reached that paper's passages,
and nothing noticed, because a retrieval miss arrives as a fluent refusal.

Two measurements, because neither replaces the other. `measure_index_recall`
compares the index against an exact scan using stored vectors as probes, and
calls no vendor. `probe_titles` asks the real stack about each paper by name,
and costs one query embedding per record -- but a stored vector is an easier
question than a real query vector, which lands elsewhere in the space.
"""

from __future__ import annotations

import random
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from django.db import connection, transaction
from pgvector.django import CosineDistance

from apps.ai.retrieval.scan_depth import configured_depth, scan_depth

DEFAULT_PROBES = 60

#: Ten, so a number here is comparable with `eval_retrieval`'s recall@10.
DEFAULT_K = 10

DEFAULT_MIN_RECALL = 0.99


def recall_at_k(exact: Sequence[int], approximate: Sequence[int]) -> float:
    """Fraction of the true neighbours the index returned.

    Set overlap, not rank agreement: everything downstream reranks or reads
    them as a set. No exact neighbours scores 1.0 -- nothing to miss.
    """
    if not exact:
        return 1.0
    return len(set(exact) & set(approximate)) / len(exact)


def overview_question(title: str) -> str:
    """The phrasing that failed. Pinned so an edit cannot quietly change what
    was measured."""
    return f"Can you give me the overview of {title}"


@dataclass(frozen=True)
class TitleMiss:
    record_id: int
    title: str
    #: What won instead -- naming it is what made the original miss diagnosable.
    returned: tuple[int, ...]


def probe_titles(
    records: Iterable[tuple[int, str]],
    retrieve: Callable[[str, int], Sequence[int]],
    limit: int = DEFAULT_K,
) -> tuple[TitleMiss, ...]:
    """Ask the stack about each record by name; report the misses.

    ``retrieve`` is injected so this is testable without a vendor account.
    """
    misses: list[TitleMiss] = []
    for record_id, title in records:
        returned = tuple(retrieve(overview_question(title), limit))
        if record_id not in returned:
            misses.append(TitleMiss(record_id, title, returned))
    return tuple(misses)


@dataclass(frozen=True)
class ProbeRecall:
    probe_id: int
    recall: float


@dataclass(frozen=True)
class IndexRecall:
    label: str
    probes: int
    k: int
    #: Part of the result, not context a caller must remember: recall read
    #: without its depth is how IR-440's cap survived a whole eval baseline.
    depth: int
    recall: float
    #: False means the planner chose a sequential scan, so the figure says
    #: nothing about the index. Small tables do this.
    used_index: bool
    worst: tuple[ProbeRecall, ...]
    probe_ids: tuple[int, ...]


def _restore(cursor, settings: Sequence[tuple[str, str]]) -> None:
    for name, value in settings:
        # `set_config`, because a GUC value cannot be a query parameter in SET.
        cursor.execute("SELECT set_config(%s, %s, true)", [name, value])


@contextmanager
def _planner(**flags: str):
    """Hold planner flags for one transaction, then put them back.

    `SET LOCAL` outside a transaction is silently a no-op, so this opens one.
    But inside an outer transaction -- every `django_db` test -- `atomic()` is
    only a savepoint and the flags outlive the block. A leaked
    `enable_indexscan = off` makes the approximate measurement run exactly
    too, scoring 1.0 whatever the index does, so they are restored by hand.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            prior = []
            for name, value in flags.items():
                cursor.execute(f"SHOW {name}")
                prior.append((name, cursor.fetchone()[0]))
                cursor.execute(f"SET LOCAL {name} = {value}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                _restore(cursor, prior)


def exact_scan():
    """The truth: no index at all. `enable_indexscan` alone is not enough,
    because a bitmap scan reaches the index too."""
    return _planner(enable_indexscan="off", enable_bitmapscan="off")


def index_scan():
    """Force the planner onto the HNSW index.

    Without this a small table is scanned sequentially and compared against
    itself, which is perfect recall by construction (IR-440's own test needs
    the same two flags).
    """
    return _planner(enable_seqscan="off", enable_sort="off")


def _queryset(model, space_id: Optional[int]):
    queryset = model.objects.all()
    return queryset if space_id is None else queryset.filter(space_id=space_id)


def _neighbours(model, vector, k: int, space_id: Optional[int]) -> list[int]:
    return list(
        _queryset(model, space_id)
        .annotate(_distance=CosineDistance("embedding", vector))
        .order_by("_distance")
        .values_list("id", flat=True)[:k]
    )


def _uses_hnsw(model, vector, k: int, space_id: Optional[int]) -> bool:
    """Whether the plan actually reads the HNSW index."""
    query = (
        _queryset(model, space_id)
        .annotate(_distance=CosineDistance("embedding", vector))
        .order_by("_distance")
        .values_list("id", flat=True)[:k]
    )
    sql, params = query.query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN " + sql, params)
        plan = "\n".join(row[0] for row in cursor.fetchall())
    return "hnsw" in plan.lower()


def measure_index_recall(
    model,
    *,
    space_id: Optional[int] = None,
    k: int = DEFAULT_K,
    probes: int = DEFAULT_PROBES,
    seed: int = 0,
    label: Optional[str] = None,
) -> IndexRecall:
    """Compare the index against an exact scan, using stored vectors as probes.

    A stored vector is its own nearest neighbour, so every probe has a known
    answer and no vendor call is needed. Seeded, so runs are comparable.
    """
    ids = sorted(_queryset(model, space_id).values_list("id", flat=True))
    chosen = sorted(random.Random(seed).sample(ids, min(probes, len(ids))))
    depth = configured_depth()
    name = label or model.__name__

    if not chosen:
        return IndexRecall(name, 0, k, depth, 1.0, False, (), ())

    vectors = model.objects.in_bulk(chosen)
    # Inside the same context the measurement uses, or it reports the plan for
    # a query nobody ran.
    with index_scan(), scan_depth():
        used_index = _uses_hnsw(model, vectors[chosen[0]].embedding, k, space_id)

    scores: list[ProbeRecall] = []
    for probe_id in chosen:
        vector = vectors[probe_id].embedding
        with exact_scan():
            truth = _neighbours(model, vector, k, space_id)
        with index_scan(), scan_depth():
            found = _neighbours(model, vector, k, space_id)
        scores.append(ProbeRecall(probe_id, recall_at_k(truth, found)))

    return IndexRecall(
        label=name,
        probes=len(scores),
        k=k,
        depth=depth,
        recall=sum(s.recall for s in scores) / len(scores),
        used_index=used_index,
        worst=tuple(sorted((s for s in scores if s.recall < 1.0), key=lambda s: s.recall)),
        probe_ids=tuple(chosen),
    )
