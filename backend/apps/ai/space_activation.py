"""Activating a verified Embedding Space, and returning to the one before (IR-739).

ADR-049 §23: a model upgrade is built beside the live index (IR-752), checked,
and only then promoted, atomically, without mixing vectors or mutating the
active index. The previous revision is kept for a deliberate rollback, subject
to current access, deletion and disclosure.

**What activation is.** One row flipping. Record summary vectors and Passage
vectors both carry a space identity (``RecordSpaceEmbedding`` and
``ChunkEmbedding``), and every reader names the one space it resolved at the
start of its request, so retiring the old active space and activating the new
one in a single transaction moves both levels together. No vector is written,
copied or deleted by a promotion or a rollback.

**What it refuses.** Verification runs before the flip and again inside the
transaction, under a row lock on every space, so a writer that finishes just
before the lock is counted and one that arrives after waits for it:

- the space is not in a state the move allows (promotion takes a pending space;
  rollback takes the one the last activation replaced);
- its width is not the columns' or its metric is not cosine, or a stored
  vector's width is not its own;
- the provider that would embed queries for it does not name its model or
  width (ADR-015 rule 3: a query must be embedded by the model the documents
  were);
- a Record that readers can use has no summary vector, a stale one (its title
  or abstract changed), or, for a promotion, an unverified one;
- a Passage of a current chunk set has no vector, or the chunk set is not the
  Record's current Manuscript revision;
- the space's vector indexes do not find what an exact scan does.

"Records that readers can use" excludes Records that are deleted or that the
disclosure gate refuses (ADR-052): they are never embedded and no reader can
return them, so requiring a vector for them would make every corpus holding one
unpromotable.

**Rollback cannot resurrect anything.** It reactivates a space; it reads no
more than the space already held. Readers still apply ``visible_to``, the
active chunk set and tombstones to every row they return, whichever space
serves them, so a source revoked, deleted or embargoed after the promotion is
as unreachable through the old space as through the new one. A rollback target
that fell behind (Records added since it retired exist only in the newer space)
is refused naming the shortfall, and ``reopen_rollback_target`` returns it to
``pending`` so IR-752's build can catch it up before a second attempt.

**Not here.** Building a space and the schema expansion are IR-752. Executing
an upgrade against production is a deliberate operational act this module does
not perform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from django.db import DatabaseError, connection, transaction

from apps.ai.promotion import PromotionRefused

__all__ = [
    "ActivationRefused",
    "ActivationResult",
    "Refusal",
    "Verdict",
    "activate_space",
    "check_activation",
    "reader_probe",
    "reopen_rollback_target",
    "rollback_target",
]

#: A promotion waits this long for a writer's row lock, then refuses and changes
#: nothing; an operator retries. Not a reader limit: readers take no lock.
LOCK_TIMEOUT_MS = 10_000

_UNSET = object()


class ActivationRefused(PromotionRefused):
    """Activation was refused; ``verdict`` says every reason, and nothing changed."""

    def __init__(self, verdict: "Verdict") -> None:
        self.verdict = verdict
        super().__init__(verdict.message())


@dataclass(frozen=True)
class Refusal:
    code: str
    detail: str


@dataclass
class Verdict:
    """What verification found. ``ok`` is the only thing a caller needs to act on."""

    space_id: int
    kind: str
    current_active_id: Optional[int]
    refusals: list = field(default_factory=list)
    #: Plain numbers an operator can read; never a record title or a vector.
    checks: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def message(self) -> str:
        return " ".join(r.detail for r in self.refusals) or "ready"

    def as_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "kind": self.kind,
            "current_active_id": self.current_active_id,
            "ok": self.ok,
            "refusals": [{"code": r.code, "detail": r.detail} for r in self.refusals],
            "checks": dict(self.checks),
        }


@dataclass
class ActivationResult:
    verdict: Verdict
    activated: bool = False
    dry_run: bool = False
    activation_id: Optional[int] = None
    previous_space_id: Optional[int] = None

    def as_dict(self) -> dict:
        return {
            "activated": self.activated,
            "dry_run": self.dry_run,
            "activation_id": self.activation_id,
            "previous_space_id": self.previous_space_id,
            "verdict": self.verdict.as_dict(),
        }


# -- history -------------------------------------------------------------------


def _latest_activation():
    from apps.ai.models import EmbeddingSpaceActivation

    return EmbeddingSpaceActivation.objects.order_by("-id").first()


def rollback_target():
    """The compatible previous revision a deliberate rollback returns to, or ``None``.

    The space the newest activation replaced, and only while that activation is
    still what is live: if the active space was changed some other way the
    history no longer describes it and nothing is offered.
    """
    from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

    last = _latest_activation()
    active = EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).first()
    if last is None or active is None or last.space_id != active.pk or last.previous_space_id is None:
        return None
    return EmbeddingSpace.objects.filter(pk=last.previous_space_id).first()


def reopen_rollback_target() -> "object":
    """Return the rollback target to ``pending`` so a build can catch it up.

    A retired space is read by nothing and is not built into (IR-752 refuses
    it), so a target that fell behind could never become complete. Reopening is
    the one deliberate way back to a buildable state: it changes a state and
    deletes nothing, and the space still has to pass verification to go live.
    """
    from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

    with transaction.atomic():
        target = rollback_target()
        if target is None:
            raise PromotionRefused("There is no previous revision recorded to reopen.")
        locked = EmbeddingSpace.objects.select_for_update().get(pk=target.pk)
        if locked.state != EmbeddingSpaceState.RETIRED:
            raise PromotionRefused(
                f"Space {locked.pk} is {locked.state}; only a retired rollback target is reopened."
            )
        EmbeddingSpace.objects.filter(pk=locked.pk).update(state=EmbeddingSpaceState.PENDING)
        locked.refresh_from_db()
    return locked


# -- verification --------------------------------------------------------------


def _default_provider_factory(model_id: str):
    from apps.ai import indexing

    return indexing.build_embedding_provider(model=model_id)


def _owed_records():
    """Records readers can use that have active chunks: the coverage denominator."""
    from apps.ai.models.chunk import DocumentChunk
    from apps.ai.policy import decision_for_record
    from apps.records.models import Record

    with_chunks = DocumentChunk.objects.filter(
        chunk_set__is_active=True, deleted_at__isnull=True
    ).values("record_id")
    records = Record.objects.filter(pk__in=with_chunks, is_deleted=False).order_by("pk")
    return [r for r in records if decision_for_record(r).allowed]


def _stale_revisions(owed) -> list:
    """Records whose active chunk set is not their current Manuscript revision."""
    from apps.ai.models.chunk import ChunkSet
    from apps.documents.models import PdfExtraction

    current = dict(
        PdfExtraction.objects.filter(
            record_id__in=[r.pk for r in owed], source_revision__isnull=False
        ).values_list("record_id", "source_revision")
    )
    stale = []
    for record_id, chunk_revision in ChunkSet.objects.filter(
        record_id__in=list(current), is_active=True
    ).values_list("record_id", "source_revision"):
        if chunk_revision != current[record_id]:
            stale.append(record_id)
    return sorted(stale)


def _coverage(space, kind: str, verdict: Verdict) -> None:
    from apps.ai.models.embedding import RecordSpaceEmbedding
    from apps.ai.promotion import records_missing_vectors
    from apps.ai.indexing import record_source_hash

    owed = _owed_records()
    owed_ids = {r.pk for r in owed}
    stored = dict(
        RecordSpaceEmbedding.objects.filter(space_id=space.pk).values_list("record_id", "source_hash")
    )
    missing = stale = unverified = 0
    for record in owed:
        if record.pk not in stored:
            missing += 1
        elif stored[record.pk] == "":
            unverified += 1
        elif stored[record.pk] != record_source_hash(record):
            stale += 1
    shortfalls = [s for s in records_missing_vectors(space.pk) if s.record_id in owed_ids]
    revisions = _stale_revisions(owed)
    # An unverified vector has no recorded text to compare. A rollback restores
    # what was serving readers, so it is let through and counted; a promotion
    # rests on a build that records its hash, so a missing one is a defect.
    refuse_unverified = kind != "rollback"

    verdict.checks.update(
        records_owed=len(owed), summaries_missing=missing, summaries_stale=stale,
        summaries_unverified=unverified, passage_shortfall_records=len(shortfalls),
        passages_missing=sum(s.missing for s in shortfalls), stale_revision_records=len(revisions),
    )
    if missing or stale or (unverified and refuse_unverified):
        verdict.refusals.append(Refusal(
            "summary_coverage",
            f"Record summary vectors in space {space.pk}: {missing} missing, {stale} stale"
            + (f", {unverified} unverified" if refuse_unverified else "") + ".",
        ))
    if shortfalls:
        verdict.refusals.append(Refusal(
            "passage_coverage",
            f"{len(shortfalls)} record(s) have active chunks with no vector in space "
            f"{space.pk} ({space.model_id}). A space promoted half-indexed answers "
            f"confidently from the half it holds.",
        ))
    if revisions:
        verdict.refusals.append(Refusal(
            "stale_revision",
            f"{len(revisions)} record(s) have an active chunk set that is not their current "
            f"Manuscript revision (first: record {revisions[0]}).",
        ))


def _structure(space, kind: str, verdict: Verdict, current) -> None:
    from apps.ai.models import VECTOR_COLUMN_DIMENSIONS, EmbeddingSpaceState
    from apps.ai.space_build import stored_dimension_mismatches

    if space.state == EmbeddingSpaceState.ACTIVE:
        verdict.refusals.append(Refusal("already_active", f"Space {space.pk} is already active."))
    elif kind == "promote" and space.state == EmbeddingSpaceState.RETIRED:
        verdict.refusals.append(Refusal(
            "retired",
            f"Space {space.pk} is retired. Promoting one the project has already retired makes "
            f"live what it decided against; create a new space instead, or roll back to the "
            f"previous revision.",
        ))
    elif kind == "rollback" and space.state not in (EmbeddingSpaceState.RETIRED, EmbeddingSpaceState.PENDING):
        verdict.refusals.append(Refusal("state", f"Space {space.pk} is {space.state}."))

    if space.dimensions != VECTOR_COLUMN_DIMENSIONS:
        verdict.refusals.append(Refusal(
            "dimensions",
            f"Space {space.pk} is {space.dimensions} dimensions but the vector columns hold "
            f"{VECTOR_COLUMN_DIMENSIONS}. Queries against it would compare vectors of "
            f"different widths.",
        ))
    if space.metric != "cosine":
        verdict.refusals.append(Refusal(
            "metric", f"Space {space.pk} uses the {space.metric!r} metric; the vector indexes are cosine."))
    mismatches = stored_dimension_mismatches(space)
    verdict.checks["dimension_mismatches"] = mismatches
    if mismatches and space.dimensions == VECTOR_COLUMN_DIMENSIONS:
        verdict.refusals.append(Refusal(
            "stored_dimensions", f"{mismatches} stored vector(s) are not {space.dimensions} wide."))


def _query_semantics(space, factory: Callable, verdict: Verdict) -> None:
    try:
        provider = factory(space.model_id)
    except Exception as exc:  # noqa: BLE001 - any failure to build is a refusal, not a crash
        verdict.refusals.append(Refusal(
            "query_semantics", f"No query provider can be built for model {space.model_id!r}: {exc}"))
        return
    if provider.model_id is None or provider.model_id != space.model_id:
        verdict.refusals.append(Refusal(
            "query_semantics",
            f"The query provider names model {provider.model_id!r} but space {space.pk} is "
            f"{space.model_id!r}. A query embedded by another model finds nothing real.",
        ))
    elif provider.dimensions != space.dimensions:
        verdict.refusals.append(Refusal(
            "query_semantics",
            f"The query provider emits {provider.dimensions} dimensions but space {space.pk} "
            f"is {space.dimensions}.",
        ))
    verdict.checks["query_provider_model"] = provider.model_id


def _index_health(space, verdict: Verdict, *, min_recall: float, probes: int) -> None:
    from apps.ai.index_health import measure_index_recall
    from apps.ai.models.chunk import ChunkEmbedding
    from apps.ai.models.embedding import RecordSpaceEmbedding

    for model, label in ((ChunkEmbedding, "chunk"), (RecordSpaceEmbedding, "record")):
        result = measure_index_recall(model, space_id=space.pk, probes=probes, label=label)
        verdict.checks[f"{label}_index_recall"] = round(result.recall, 4)
        verdict.checks[f"{label}_index_probes"] = result.probes
        if result.probes and result.recall < min_recall:
            verdict.refusals.append(Refusal(
                "retrieval_check",
                f"The {label} vector index in space {space.pk} found {result.recall:.3f} of what an "
                f"exact scan finds (minimum {min_recall}).",
            ))


def check_activation(
    space,
    *,
    kind: str = "promote",
    provider_factory: Optional[Callable] = None,
    verify_index: bool = True,
    min_recall: Optional[float] = None,
    probes: Optional[int] = None,
) -> Verdict:
    """Everything that must hold for ``space`` to go live. Read-only, calls no vendor."""
    from apps.ai.index_health import DEFAULT_MIN_RECALL, DEFAULT_PROBES
    from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

    current = EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).first()
    verdict = Verdict(space_id=space.pk, kind=kind, current_active_id=current.pk if current else None)
    _structure(space, kind, verdict, current)
    _query_semantics(space, provider_factory or _default_provider_factory, verdict)
    _coverage(space, kind, verdict)
    if verify_index:
        _index_health(
            space, verdict,
            min_recall=DEFAULT_MIN_RECALL if min_recall is None else min_recall,
            probes=DEFAULT_PROBES if probes is None else probes,
        )
    return verdict


# -- the flip --------------------------------------------------------------------


def _record_activation(kind: str, space, previous, actor: str, report: dict):
    from apps.ai.models import EmbeddingSpaceActivation

    return EmbeddingSpaceActivation.objects.create(
        kind=kind, space_id=space.pk, previous_space_id=previous.pk if previous else None,
        actor=actor[:254], report=report,
    )


def activate_space(
    space_id: int,
    *,
    kind: str = "promote",
    actor: str = "",
    dry_run: bool = False,
    expect_active=_UNSET,
    provider_factory: Optional[Callable] = None,
    verify_index: bool = True,
    min_recall: Optional[float] = None,
    probes: Optional[int] = None,
    lock_timeout_ms: int = LOCK_TIMEOUT_MS,
) -> ActivationResult:
    """Verify ``space_id`` and, unless ``dry_run``, make it the active space.

    ``kind="rollback"`` takes the space the newest activation replaced and no
    other. ``expect_active`` is the active space id the caller looked at; if the
    live one differs by the time the lock is held the move is refused, so two
    operators acting on the same picture cannot both land.

    Atomic: the previous active space is retired, the target activated and the
    history row written in one transaction. Any failure rolls all of it back and
    the previous space stays active and untouched.
    """
    from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

    space = EmbeddingSpace.objects.filter(pk=space_id).first()
    if space is None:
        raise PromotionRefused(f"No EmbeddingSpace with id {space_id}.")
    if kind == "rollback":
        target = rollback_target()
        if target is None or target.pk != space.pk:
            raise PromotionRefused(
                f"Space {space.pk} is not the previous revision of the active space; "
                f"a rollback returns only to the space the last activation replaced."
            )

    verdict = check_activation(
        space, kind=kind, provider_factory=provider_factory,
        verify_index=verify_index, min_recall=min_recall, probes=probes,
    )
    if dry_run:
        return ActivationResult(verdict=verdict, dry_run=True, previous_space_id=verdict.current_active_id)
    if not verdict.ok:
        raise ActivationRefused(verdict)

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = %s", [f"{int(lock_timeout_ms)}ms"])
            # Every space row, in a fixed order: concurrent activations serialize
            # here, and a writer holding a share lock on one finishes first.
            locked = {s.pk: s for s in EmbeddingSpace.objects.select_for_update().order_by("pk")}
            target = locked.get(space.pk)
            current = next((s for s in locked.values() if s.state == EmbeddingSpaceState.ACTIVE), None)
            if expect_active is not _UNSET and (current.pk if current else None) != expect_active:
                raise ActivationRefused(_refused(verdict, "active_changed", (
                    f"The active space changed from {expect_active} to "
                    f"{current.pk if current else None} since this move was checked.")))
            if target is None or (kind == "rollback" and (rollback_target() or target).pk != target.pk):
                raise ActivationRefused(_refused(verdict, "target_changed", "The target space changed."))
            recheck = check_activation(
                target, kind=kind, provider_factory=provider_factory, verify_index=False)
            if not recheck.ok:
                recheck.checks.update(verdict.checks)
                raise ActivationRefused(recheck)

            if current is not None:
                EmbeddingSpace.objects.filter(pk=current.pk).update(state=EmbeddingSpaceState.RETIRED)
            EmbeddingSpace.objects.filter(pk=target.pk).update(state=EmbeddingSpaceState.ACTIVE)
            row = _record_activation(kind, target, current, actor, recheck.checks | verdict.checks)
    except DatabaseError as exc:
        if getattr(exc.__cause__, "pgcode", None) == "55P03":  # lock_not_available
            raise ActivationRefused(_refused(verdict, "busy", (
                "A writer held the space long enough to time out the lock; nothing changed. "
                "Retry when indexing is quiet."))) from exc
        raise
    return ActivationResult(
        verdict=verdict, activated=True, activation_id=row.pk,
        previous_space_id=current.pk if current else None,
    )


def _refused(verdict: Verdict, code: str, detail: str) -> Verdict:
    refused = Verdict(verdict.space_id, verdict.kind, verdict.current_active_id, checks=dict(verdict.checks))
    refused.refusals.append(Refusal(code, detail))
    return refused


# -- the reader's search and citation, before and after ----------------------------


class _StoredVectorQuery:
    """A query embedder that returns one stored vector, so a probe calls no vendor."""

    def __init__(self, vector, model_id: str, dimensions: int) -> None:
        self._vector, self.model_id, self.dimensions = vector, model_id, dimensions

    def embed_query(self, text: str):
        return list(self._vector)


def reader_probe(space, user, *, samples: int = 5, limit: int = 5) -> dict:
    """Search as ``user`` in ``space`` and check every citation is a current, readable one.

    Each probe uses a chunk vector already stored in the space as the query, so
    it costs nothing and is deterministic. A returned passage passes only if it
    belongs to the space asked, to the Record's active chunk set (current
    version, not a tombstone), and to a Record the reader may research (``research_records``, the one read entry point). ``found``
    counts probes whose own chunk came back; it is reported, not required.
    """
    from apps.ai.grants.reads import research_records
    from apps.ai.models.chunk import ChunkEmbedding
    from apps.ai.retrieval.two_stage import TwoStageRetriever

    rows = list(
        ChunkEmbedding.objects.filter(
            space_id=space.pk, chunk__chunk_set__is_active=True, chunk__deleted_at__isnull=True,
            chunk__record__in=research_records(user).values("pk"),
        ).select_related("chunk").order_by("chunk_id")[:samples]
    )
    failures: list = []
    returned = found = 0
    for row in rows:
        embedder = _StoredVectorQuery(row.embedding, space.model_id, space.dimensions)
        result = TwoStageRetriever(embedder, space=space).retrieve("probe", user, limit=limit)
        if result.embedding_space_id not in (None, space.pk):
            failures.append(f"probe {row.chunk_id}: answered from space {result.embedding_space_id}")
        for passage in result.passages:
            returned += 1
            current = ChunkEmbedding.objects.filter(
                chunk_id=passage.chunk_id, space_id=space.pk,
                chunk__chunk_set__is_active=True, chunk__deleted_at__isnull=True,
                chunk__record__in=research_records(user).values("pk"),
            ).exists()
            if not current:
                failures.append(
                    f"probe {row.chunk_id}: cited chunk {passage.chunk_id} is not a current, readable passage of space {space.pk}")
        found += any(p.chunk_id == row.chunk_id for p in result.passages)
    return {
        "space_id": space.pk, "probes": len(rows), "passages_returned": returned,
        "own_chunk_found": found, "failures": failures, "ok": not failures,
    }
