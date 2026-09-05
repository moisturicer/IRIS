"""
Grounded retrieval over the CIT-U record corpus.

ARCHITECTURE NOTE — deviation from ADR-007, recorded rather than reconciled:
ADR-007 selects pgvector for semantic retrieval. pgvector is **not implemented**
(`apps.ai` models are field-less stubs and there is no embedding column), so this
module retrieves with PostgreSQL full-text search over `Record.search_vector`,
which is maintained by `apps.records.signals` and works today. The public
interface here is deliberately shaped so a pgvector implementation can replace
the body of `search_records()` without changing any caller.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from functools import reduce

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q

from apps.records.models import Record

MAX_TOP_K = 20

#: Question scaffolding that carries no topical signal. Postgres strips English
#: stopwords itself; these are the interrogatives that survive stemming and would
#: otherwise match every abstract in the corpus.
_NOISE_TERMS = frozenset(
    """what which who whom whose when where why how does did done is are was were
    be been being do can could should would will shall may might must have has had
    the a an and or but not for from with about into over under this that these those
    there here any some all more most other such only own same than too very
    tell show find give list explain describe summarize summarise research study
    studies paper papers record records please""".split()
)


def _content_terms(text: str, limit: int = 8) -> list[str]:
    """Topical words only, de-duplicated, order preserved."""
    seen: set[str] = set()
    terms: list[str] = []
    for raw in text.lower().split():
        word = raw.strip(".,;:!?\"'()[]{}")
        if len(word) <= 2 or word in _NOISE_TERMS or word in seen:
            continue
        seen.add(word)
        terms.append(word)
        if len(terms) >= limit:
            break
    return terms


@dataclass(frozen=True)
class RetrievedSource:
    """One retrieved record, already reduced to what a citation needs."""

    id: int
    title: str
    abstract: str
    authors: str
    year: int | None
    classification: str | None
    score: float

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "classification": self.classification,
            "score": round(self.score, 4),
        }


def _to_source(record: Record, score: float) -> RetrievedSource:
    return RetrievedSource(
        id=record.id,
        title=record.title,
        abstract=(record.abstract or "").strip(),
        authors=", ".join(a.name for a in record.authors.all()) or "Institutional Author",
        year=record.year_accomplished,
        classification=record.classification.name if record.classification_id else None,
        score=score,
    )


def search_records(
    query: str, top_k: int = 5, exclude_id: int | None = None
) -> list[RetrievedSource]:
    """
    Rank readable records against `query`.

    Only records matching `Record.objects.publicly_visible()` are ever returned,
    so an answer can never cite something the asker cannot open.

    `exclude_id` drops one record before ranking. "Find records like this one"
    passes the record's own text as the query, which would otherwise match
    itself perfectly in the first tier and stop the search there.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    top_k = max(1, min(top_k, MAX_TOP_K))

    base = (
        Record.objects.publicly_visible()
        .select_related("classification")
        .prefetch_related("authors")
    )
    if exclude_id is not None:
        base = base.exclude(pk=exclude_id)

    def ranked(search_query) -> list[RetrievedSource]:
        rows = (
            base.filter(search_vector=search_query)
            .annotate(rank=SearchRank("search_vector", search_query))
            .filter(rank__gt=0)
            .order_by("-rank", "-access_count")[:top_k]
        )
        return [_to_source(r, float(r.rank)) for r in rows]

    # Tier 1 — websearch honours quoted phrases and -exclusions, but ANDs every
    # term, so it only fires for a question whose words all appear in one record.
    results = ranked(SearchQuery(cleaned, search_type="websearch"))
    if results:
        return results

    # Tier 2 — OR the individual terms. This is what answers a natural-language
    # question: Postgres drops stopwords itself, and SearchRank still orders by
    # how well each record matches, so relevance survives.
    terms = _content_terms(cleaned)
    if terms:
        or_query = reduce(operator.or_, (SearchQuery(t, config="english") for t in terms))
        results = ranked(or_query)
        if results:
            return results

    # Tier 3 — substring scan for terms the dictionary stems away entirely
    # (acronyms, product names). Ranked by how many distinct terms hit, so this
    # never degenerates into "every record contains the word research".
    if not terms:
        return []

    predicate = Q()
    for term in terms:
        predicate |= Q(title__icontains=term) | Q(abstract__icontains=term)

    scored: list[tuple[int, Record]] = []
    for record in base.filter(predicate)[: top_k * 5]:
        haystack = f"{record.title} {record.abstract or ''}".lower()
        hits = sum(1 for term in terms if term in haystack)
        if hits:
            scored.append((hits, record))

    scored.sort(key=lambda pair: (-pair[0], -pair[1].access_count))
    return [_to_source(r, 0.0) for _, r in scored[:top_k]]
