"""Trial chunk sets: measure a chunking variant beside the live one (IR-1051).

A trial set is a ChunkSet with ``trial_variant`` set. A database constraint
keeps it inactive, so no reader path (they all read ``is_active=True``) ever
sees it. Only ``CompositionRoot.for_trial`` retrieves from it, and only
``eval_retrieval --variant`` uses that.

A variant is ``<extractor>:<strategy>:<options>``. A blank extractor or
strategy means "what production uses". Options are comma-separated
``key=value`` pairs: the ChunkingOptions fields, plus ``trail=on|off|shuffled``
for the heading-trail test (Kuehlkamp et al. 2026, arXiv 2610.10170).

Trial sets are built from the stored extraction, so there is no vendor
re-read. A chunk whose text already has a vector for that record in the
space reuses it. Only new text is embedded, so a variant identical to the
active set costs nothing.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Optional

from apps.ai.chunking import ChunkingOptions, ChunkSet, chunk_text_hash
from apps.ai.chunking.hashing import chunkset_hash
from apps.ai.chunking.outline import PATH_SEPARATOR, TRAIL_JOIN, embedded_text
from apps.ai.chunking.registry import registered_strategies
from apps.ai.chunking.tokens import TOKENIZER_ID, count_tokens

TRAIL_MODES = ("on", "off", "shuffled")

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_INT_OPTIONS = ("max_tokens", "target_tokens", "min_tokens", "context_path_max_tokens")
_OPTION_KEYS = (*_INT_OPTIONS, "merge_short_siblings", "exclude_sections", "trail")


class VariantError(ValueError):
    """The variant cannot be built as asked."""


@dataclass(frozen=True)
class Variant:
    name: str
    extractor: str = ""
    strategy: str = ""
    options: tuple[tuple[str, str], ...] = ()

    @property
    def trail(self) -> str:
        return dict(self.options).get("trail", "on")

    @property
    def spec(self) -> str:
        """Canonical form, stored on every trial set of this variant."""
        opts = ",".join(f"{k}={v}" for k, v in self.options)
        return f"{self.extractor}:{self.strategy}:{opts}"

    def chunking_options(self, base: ChunkingOptions) -> ChunkingOptions:
        changes: dict = {}
        if self.strategy:
            changes["strategy"] = self.strategy
        for key, value in self.options:
            if key in _INT_OPTIONS:
                changes[key] = int(value)
            elif key == "merge_short_siblings":
                changes[key] = value == "true"
            elif key == "exclude_sections":
                changes[key] = tuple(s for s in value.split("|") if s)
        try:
            return replace(base, **changes)
        except ValueError as exc:
            raise VariantError(f"variant {self.name!r}: {exc}") from None


def parse_variant(text: str) -> Variant:
    """``name=<extractor>:<strategy>:<options>``."""
    name, sep, spec = text.partition("=")
    if not sep or not _NAME.match(name):
        raise VariantError(
            f"{text!r}: expected NAME=<extractor>:<strategy>:<options>, "
            f"NAME being letters, digits, - or _"
        )
    parts = spec.split(":", 2)
    if len(parts) != 3:
        raise VariantError(f"{text!r}: the spec needs three ':'-separated parts")
    extractor, strategy, raw = (p.strip() for p in parts)
    if strategy and strategy not in registered_strategies():
        raise VariantError(
            f"unknown strategy {strategy!r}; known: {', '.join(registered_strategies())}"
        )
    options: list[tuple[str, str]] = []
    for pair in (p.strip() for p in raw.split(",") if p.strip()):
        key, eq, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if not eq or key not in _OPTION_KEYS:
            raise VariantError(f"option {pair!r}: known keys are {', '.join(_OPTION_KEYS)}")
        if key in _INT_OPTIONS and not value.isdigit():
            raise VariantError(f"option {key} needs a whole number, not {value!r}")
        if key == "merge_short_siblings" and value not in ("true", "false"):
            raise VariantError("merge_short_siblings is true or false")
        if key == "trail" and value not in TRAIL_MODES:
            raise VariantError(f"trail is one of {', '.join(TRAIL_MODES)}")
        options.append((key, value))
    return Variant(name, extractor, strategy, tuple(sorted(options)))


# -- the heading trail -------------------------------------------------------


def _body(chunk) -> str:
    prefix = PATH_SEPARATOR.join(chunk.context_path)
    if prefix and chunk.text.startswith(prefix + TRAIL_JOIN):
        return chunk.text[len(prefix) + len(TRAIL_JOIN):]
    return chunk.text


def with_trail(chunk_set: ChunkSet, mode: str) -> ChunkSet:
    """``chunk_set`` with its heading trails kept, dropped, or shuffled.

    Shuffled is the placebo: every chunk keeps a real trail, just not its
    own, under a permutation seeded by the set's hash so a rebuild matches.
    A heading-only chunk keeps its text when the trail is dropped.
    """
    if mode == "on" or not chunk_set.chunks:
        return chunk_set
    trails = [c.context_path for c in chunk_set.chunks]
    if mode == "off":
        trails = [()] * len(trails)
    else:
        random.Random(chunk_set.content_hash).shuffle(trails)
    chunks = []
    for chunk, trail in zip(chunk_set.chunks, trails):
        body = _body(chunk)
        text = embedded_text(trail, body) if body else chunk.text
        chunks.append(replace(
            chunk, text=text, context_path=tuple(trail), token_count=count_tokens(text)
        ))
    chunks = tuple(chunks)
    return replace(chunk_set, chunks=chunks, content_hash=chunkset_hash(chunks))


# -- the plan ------------------------------------------------------------------


@dataclass
class RecordPlan:
    record_id: int
    chunk_set: Optional[ChunkSet] = None
    extraction_hash: str = ""
    active_hash: str = ""
    skipped: str = ""
    new_chunks: int = 0
    new_tokens: int = 0


@dataclass
class TrialPlan:
    variant: Variant
    space_id: int
    records: list[RecordPlan] = field(default_factory=list)

    @property
    def built(self) -> list[RecordPlan]:
        return [r for r in self.records if r.chunk_set is not None]

    @property
    def skipped(self) -> list[RecordPlan]:
        return [r for r in self.records if r.chunk_set is None]

    @property
    def chunk_count(self) -> int:
        return sum(len(r.chunk_set.chunks) for r in self.built)

    @property
    def new_chunks(self) -> int:
        return sum(r.new_chunks for r in self.built)

    @property
    def new_tokens(self) -> int:
        return sum(r.new_tokens for r in self.built)

    def estimated_cost(self, cost_per_million: float) -> float:
        return self.new_tokens * cost_per_million / 1_000_000

    def exceeds(self, ceiling: int) -> bool:
        return bool(ceiling) and self.new_tokens > ceiling


def _vectored_hashes(record_id: int, space_id: int, hashes) -> set[str]:
    from apps.ai.models.chunk import ChunkEmbedding

    return set(ChunkEmbedding.objects.filter(
        space_id=space_id, chunk__record_id=record_id, chunk__text_hash__in=list(hashes),
    ).values_list("chunk__text_hash", flat=True))


def _check_spec(variant: Variant) -> None:
    from apps.ai.models.chunk import ChunkSet as ChunkSetModel

    other = (ChunkSetModel.objects.filter(trial_variant=variant.name)
             .exclude(trial_spec=variant.spec).values_list("trial_spec", flat=True).first())
    if other is not None:
        raise VariantError(
            f"variant {variant.name!r} already exists as {other!r}. Remove it with "
            f"`manage.py cleanup_trial_chunk_sets --variant {variant.name}` or pick "
            f"another name."
        )


def plan_trial(variant: Variant, *, space_id: int,
               base: Optional[ChunkingOptions] = None) -> TrialPlan:
    """Chunk every record with an active set under ``variant``, in memory.

    Writes nothing and calls no vendor. A record whose stored extraction is
    missing, unreadable, or from another extractor is skipped and named.
    """
    from apps.ai.figure_descriptions import with_descriptions
    from apps.ai.ingestion.pipeline import _options_for_document, default_chunking_options
    from apps.ai.chunking import build_chunker, normalize
    from apps.ai.models.chunk import ChunkSet as ChunkSetModel
    from apps.ai.providers.batching import estimate_tokens
    from apps.documents.models import PdfExtraction

    _check_spec(variant)
    base = base or default_chunking_options()
    options = variant.chunking_options(base)
    plan = TrialPlan(variant=variant, space_id=space_id)
    actives = ChunkSetModel.objects.filter(is_active=True).order_by("record_id")
    for active in actives.values("record_id", "content_hash"):
        record_plan = RecordPlan(record_id=active["record_id"], active_hash=active["content_hash"])
        plan.records.append(record_plan)
        extraction = PdfExtraction.objects.filter(record_id=active["record_id"]).first()
        document = extraction.as_normalized_document() if extraction else None
        if document is None or not extraction.content_hash:
            record_plan.skipped = "no stored extraction to chunk"
            continue
        if variant.extractor and extraction.extractor != variant.extractor:
            record_plan.skipped = (
                f"stored extraction is {extraction.extractor or 'unnamed'}, "
                f"not {variant.extractor}"
            )
            continue
        document = with_descriptions(document, extraction)
        # A blank strategy behaves as production does; a named one wins.
        record_options = options if variant.strategy else _options_for_document(document, options)
        try:
            built = build_chunker(record_options).chunk(
                normalize(document, record_options), record_options
            )
        except Exception as exc:  # one bad paper should not sink the run
            record_plan.skipped = f"chunking failed: {exc}"
            continue
        built = with_trail(built, variant.trail)
        record_plan.chunk_set = built
        record_plan.extraction_hash = extraction.content_hash
        hashes = [chunk_text_hash(c) for c in built.chunks]
        have = _vectored_hashes(active["record_id"], space_id, hashes)
        owed = [c for c, h in zip(built.chunks, hashes) if h not in have]
        record_plan.new_chunks = len(owed)
        record_plan.new_tokens = sum(estimate_tokens(c.text) for c in owed)
    return plan


# -- writing and embedding --------------------------------------------------


@dataclass
class TrialBuild:
    written: int = 0
    reused_sets: int = 0
    carried: int = 0
    embedded: int = 0
    refused: dict[int, str] = field(default_factory=dict)


def _options_json(chunk_set: ChunkSet, trail: str) -> dict:
    from apps.ai.repositories import _serialize_options

    return {**_serialize_options(chunk_set.options), "trail": trail}


def _write_set(record_plan: RecordPlan, variant: Variant):
    """The trial row for this record, reused when its content is unchanged."""
    from django.db import transaction

    from apps.ai.models.chunk import ChunkSet as ChunkSetModel
    from apps.ai.models.chunk import DocumentChunk
    from apps.ai.repositories import _serialize_page_sizes, chunk_rows

    built = record_plan.chunk_set
    with transaction.atomic():
        existing = ChunkSetModel.objects.select_for_update().filter(
            record_id=record_plan.record_id, trial_variant=variant.name
        ).first()
        if existing is not None and existing.content_hash == built.content_hash:
            return existing, False
        if existing is not None:
            existing.delete()
        row = ChunkSetModel.objects.create(
            record_id=record_plan.record_id,
            extraction_hash=record_plan.extraction_hash,
            strategy_id=built.strategy_id,
            options=_options_json(built, variant.trail),
            content_hash=built.content_hash,
            page_sizes=_serialize_page_sizes(built.page_sizes),
            is_active=False,
            trial_variant=variant.name,
            trial_spec=variant.spec,
        )
        DocumentChunk.objects.bulk_create(chunk_rows(row, record_plan.record_id, built))
    return row, True


def _carry_over(row, space_id: int) -> int:
    """Copy this record's existing vectors onto trial chunks with the same text."""
    from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk

    missing = list(DocumentChunk.objects.filter(chunk_set=row)
                   .exclude(embeddings__space_id=space_id))
    if not missing:
        return 0
    vectors: dict[str, object] = {}
    for text_hash, vector in ChunkEmbedding.objects.filter(
        space_id=space_id, chunk__record_id=row.record_id,
        chunk__text_hash__in={c.text_hash for c in missing},
    ).values_list("chunk__text_hash", "embedding"):
        vectors.setdefault(text_hash, vector)
    rows = [ChunkEmbedding(chunk=c, space_id=space_id, embedding=vectors[c.text_hash])
            for c in missing if c.text_hash in vectors]
    ChunkEmbedding.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def _embed_rest(row, space, provider, active_hash: str) -> tuple[int, str]:
    """Embed the trial chunks still without a vector. Returns (count, refusal)."""
    from django.db import transaction

    from apps.ai.indexing import (
        SPACE_RETIRED,
        EmbeddingRefused,
        _hold_space,
        _require_disclosure,
        chunk_texts,
        default_permits,
    )
    from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
    from apps.ai.policy.outbound import Dependency, OutboundGuard, Withheld
    from apps.ai.providers.batching import window_for_embedding
    from apps.records.models import Record

    chunks = list(DocumentChunk.objects.filter(chunk_set=row)
                  .exclude(embeddings__space_id=space.pk).order_by("sequence"))
    if not chunks:
        return 0, ""
    try:
        _require_disclosure(Record.objects.get(pk=row.record_id))
    except EmbeddingRefused as exc:
        return 0, str(exc)
    # Fenced on the active set's version: a trial is derived from the same
    # source, so a change there stops the send here too.
    versions = {Dependency.passage(row.record_id, active_hash)}
    try:
        with OutboundGuard(principal=None, permits=default_permits).fence(lambda: versions):
            vectors = [
                vector
                for group in provider.embed_document_chunks(
                    window_for_embedding(chunk_texts(chunks)))
                for vector in group
            ]
    except Withheld:
        return 0, "disclosure refused before sending"
    if len(vectors) != len(chunks):
        raise ValueError(
            f"provider returned {len(vectors)} vectors for {len(chunks)} chunks"
        )
    with transaction.atomic():
        # Same write fence as indexing: no vectors into a space retired mid-run.
        Record.objects.select_for_update().get(pk=row.record_id)
        if not _hold_space(space):
            return 0, SPACE_RETIRED
        ChunkEmbedding.objects.bulk_create(
            (ChunkEmbedding(chunk=c, space=space, embedding=v)
             for c, v in zip(chunks, vectors)),
            ignore_conflicts=True,
        )
    return len(chunks), ""


def build_trial(plan: TrialPlan, *, provider=None) -> TrialBuild:
    """Persist the plan's trial sets and give every chunk a vector."""
    from apps.ai.admission.scope import workload
    from apps.ai.indexing import _checked_space, build_embedding_provider

    provider = provider or build_embedding_provider()
    space = _checked_space(provider, plan.space_id)
    outcome = TrialBuild()
    with workload("ingestion"):
        for record_plan in plan.built:
            row, written = _write_set(record_plan, plan.variant)
            if written:
                outcome.written += 1
            else:
                outcome.reused_sets += 1
            outcome.carried += _carry_over(row, space.pk)
            embedded, refused = _embed_rest(row, space, provider, record_plan.active_hash)
            outcome.embedded += embedded
            if refused:
                outcome.refused[record_plan.record_id] = refused
    return outcome


# -- cleanup and provenance -------------------------------------------------


def delete_trial_sets(variant: Optional[str] = None, *, dry_run: bool = False) -> dict:
    """Remove trial sets (one variant, or all), with their chunks and vectors."""
    from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
    from apps.ai.models.chunk import ChunkSet as ChunkSetModel

    sets = ChunkSetModel.objects.filter(trial_variant__isnull=False)
    if variant is not None:
        sets = sets.filter(trial_variant=variant)
    counts = {
        "sets": sets.count(),
        "chunks": DocumentChunk.objects.filter(chunk_set__in=sets).count(),
        "vectors": ChunkEmbedding.objects.filter(chunk__chunk_set__in=sets).count(),
    }
    if not dry_run:
        sets.delete()
    return counts


def trial_variants() -> dict[str, int]:
    """Each stored trial variant and how many records it covers."""
    from django.db.models import Count

    from apps.ai.models.chunk import ChunkSet as ChunkSetModel

    return dict(ChunkSetModel.objects.filter(trial_variant__isnull=False)
                .values_list("trial_variant").annotate(n=Count("pk")).order_by("trial_variant"))


def chunking_provenance(variant: Optional[Variant] = None) -> dict:
    """What produced the passages a run retrieved from, for its run file."""
    from apps.ai.models.chunk import ChunkSet as ChunkSetModel
    from apps.documents.models import PdfExtraction

    scope = {"trial_variant": variant.name} if variant else {"is_active": True}
    rows = list(ChunkSetModel.objects.filter(**scope)
                .values("extraction_hash", "strategy_id", "options"))
    extractors = dict(PdfExtraction.objects.filter(
        content_hash__in={r["extraction_hash"] for r in rows}
    ).values_list("content_hash", "extractor"))
    groups = Counter(
        (extractors.get(r["extraction_hash"], "unknown") or "unknown", r["strategy_id"],
         json.dumps(r["options"], sort_keys=True))
        for r in rows
    )
    return {
        "variant": variant.name if variant else None,
        "variant_spec": variant.spec if variant else None,
        "tokenizer": TOKENIZER_ID,
        "chunk_sets": [
            {"extractor": e, "strategy_id": s, "options": json.loads(o), "records": n}
            for (e, s, o), n in sorted(groups.items())
        ],
    }
