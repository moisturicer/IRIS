"""Why retrieval returned what it returned (IR-459).

"Nothing was found", "everything was withheld by the disclosure gate" and
"retrieval raised" used to collapse into one empty list and one `no_sources`
answer, so a refusal could not be diagnosed. ADR-034 §2 already needs that
distinction and could not make it.

**The outcome is computed over the selection stage only.** Let ``S`` be the set
presented to final selection -- what the retriever returned. The recall-stage
counts are diagnostics and take no part in classification: tying the two
together left a reachable state with no applicable outcome, because with the
no-op reranker a hundred candidates are recalled, only the trimmed handful
reaches the gate, and if all of those are withheld then the withheld count is
nowhere near the candidate count and every outcome value is false.

**Where a count cannot be observed it is absent, not zero.** A stage that did
not run on this path reports ``None`` for every bucket -- the degraded path has
no reranker and so no recall stage at all. A gate that ran and removed nothing
reports an empty set, which is a different fact.

**A chunk is never counted as withheld because it *would* have been removed.**
Records the visibility predicate removed are never candidates and are never
exposed, internally or otherwise -- `TwoStageRetriever` narrows by
``visible_to(user)`` before anything is scored, so they never reach a bucket.

No reader-visible change and no API change: nothing here is serialized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterable, Optional

#: The six outcomes, in precedence order. Strings rather than an enum, the
#: same call `ports.VECTOR` makes: these end up in a log line, where a name is
#: what is wanted.
FAILED = "failed"
EMPTY = "empty"
WITHHELD_ALL = "withheld_all"
NONE_RELEVANT = "none_relevant"
FOUND_RELEVANT = "found_relevant"
FOUND_UNASSESSED = "found_unassessed"

#: Precedence order, which is also the order `classify` tests them in.
OUTCOMES: tuple[str, ...] = (
    FAILED,
    EMPTY,
    WITHHELD_ALL,
    NONE_RELEVANT,
    FOUND_RELEVANT,
    FOUND_UNASSESSED,
)


def _ids(value: Optional[Iterable[int]]) -> Optional[frozenset[int]]:
    return None if value is None else frozenset(value)


def chunk_ids(chunks: Iterable) -> frozenset[int]:
    """The chunk ids of some passages, which is what a bucket holds."""
    return frozenset(chunk.chunk_id for chunk in chunks)


@dataclass(frozen=True)
class ChunkBuckets:
    """Sets of chunk ids, never events, over one stage of retrieval.

    The first four are **terminal and mutually exclusive**: a chunk the stage
    observed landed in exactly one of them. ``gate_evaluated`` is not one of
    them -- it is the set the disclosure gate actually ran on, which overlaps
    ``withheld`` by definition.

    Sets rather than integers because disjointness is then a property a test
    can assert directly instead of inferring from four numbers that happen to
    add up. ``counts`` is what a log line wants.

    ``None`` means *not observable on this path*. ``below_floor`` is ``None``
    everywhere today: no relevance floor exists until IR-396, so there is no
    stage that could have measured one.
    """

    withheld: Optional[frozenset[int]] = None
    below_floor: Optional[frozenset[int]] = None
    kept: Optional[frozenset[int]] = None
    not_selected: Optional[frozenset[int]] = None
    gate_evaluated: Optional[frozenset[int]] = None

    #: The buckets that partition. Named rather than described so a bucket
    #: added later has to be classified as terminal or not.
    TERMINAL: ClassVar[tuple[str, ...]] = (
        "withheld",
        "below_floor",
        "kept",
        "not_selected",
    )

    def __post_init__(self) -> None:
        for name in (*self.TERMINAL, "gate_evaluated"):
            object.__setattr__(self, name, _ids(getattr(self, name)))

    @property
    def counts(self) -> dict[str, Optional[int]]:
        """Each bucket's size, or ``None`` where it was not observable."""
        names = (*self.TERMINAL, "gate_evaluated")
        return {
            name: (None if getattr(self, name) is None else len(getattr(self, name)))
            for name in names
        }

    @property
    def observed(self) -> frozenset[int]:
        """Every chunk this stage could place -- the union of the terminal
        buckets it observed. Absent buckets contribute nothing, which is what
        makes exhaustiveness a claim about what the implementation can see
        rather than about the whole corpus.
        """
        seen: frozenset[int] = frozenset()
        for name in self.TERMINAL:
            bucket = getattr(self, name)
            if bucket is not None:
                seen |= bucket
        return seen

    @property
    def overlaps(self) -> dict[tuple[str, str], frozenset[int]]:
        """Any chunk in two terminal buckets at once. Empty is the invariant."""
        found: dict[tuple[str, str], frozenset[int]] = {}
        names = [n for n in self.TERMINAL if getattr(self, n) is not None]
        for position, left in enumerate(names):
            for right in names[position + 1:]:
                shared = getattr(self, left) & getattr(self, right)
                if shared:
                    found[(left, right)] = shared
        return found


@dataclass(frozen=True)
class RetrievalConfiguration:
    """What the counts mean depends on how retrieval was configured.

    Recorded beside them rather than reconstructed later: ``withheld`` of 8 out
    of 8 means one thing under a recall limit of 100 and a transmitting
    reranker and another under a no-op one, and a reader of a log line has no
    way to tell which run they are looking at.

    Every field is optional because each stage fills in what it knows: the
    selection stage has a source cap and no recall limit, and the degraded
    path has neither a reranker nor a space.
    """

    mode: Optional[str] = None
    degraded: Optional[bool] = None
    embedding_space_id: Optional[int] = None
    recall_limit: Optional[int] = None
    requested_limit: Optional[int] = None
    reranker: Optional[str] = None
    reranker_transmits: Optional[bool] = None
    disclosure_gate: Optional[bool] = None
    max_sources: Optional[int] = None

    @property
    def summary(self) -> dict[str, object]:
        """Only what this stage actually knows, so a log line does not read as
        a configuration of nulls."""
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if getattr(self, name) is not None
        }


@dataclass(frozen=True)
class StageDiagnostics:
    """One stage's buckets and the configuration that gives them meaning.

    The default is every bucket absent, which is the honest report from a path
    where the stage does not exist.
    """

    buckets: ChunkBuckets = ChunkBuckets()
    configuration: RetrievalConfiguration = RetrievalConfiguration()

    @property
    def observed_anything(self) -> bool:
        return any(value is not None for value in self.buckets.counts.values())

    @property
    def summary(self) -> dict[str, object]:
        return {"counts": self.buckets.counts, "config": self.configuration.summary}


def classify(
    presented: Optional[Iterable[int]],
    buckets: ChunkBuckets,
    *,
    relevance_assessed: bool = False,
) -> str:
    """The one outcome for this retrieval. Total and mutually exclusive.

    ``presented`` is ``S``, the chunk ids handed to final selection, or
    ``None`` when retrieval raised and there is no ``S`` to speak of.

    The chain is the precedence in `OUTCOMES`, and every branch returns, so
    there is no combination of inputs with no outcome and none with two.

    ``relevance_assessed`` says whether a relevance signal was available at
    all. It is ``False`` everywhere today, so evidence that survived the gate
    is ``found_unassessed`` -- **unassessed, never irrelevant**. That makes
    ``none_relevant`` unreachable until IR-396 builds the floor, which is why
    this does not wait for that ticket.
    """
    if presented is None:
        return FAILED

    presented_ids = frozenset(presented)
    if not presented_ids:
        return EMPTY

    if not (presented_ids - (buckets.withheld or frozenset())):
        return WITHHELD_ALL

    if not (buckets.kept or frozenset()):
        # Survivors existed and none was kept. Only a relevance floor can do
        # that, so this is where the floor's outcome lands when one exists.
        return NONE_RELEVANT

    return FOUND_RELEVANT if relevance_assessed else FOUND_UNASSESSED


@dataclass(frozen=True)
class RetrievalDiagnostics:
    """The whole retrieval, classified.

    ``outcome`` is computed over ``selection`` alone. ``recall`` rides along as
    a diagnostic and never enters the classification -- see this module's
    docstring for the reachable state that tying them together produced.

    ``degraded`` is kept as its own field rather than derived: nothing in the
    counts says the vendor was out.
    """

    outcome: str
    selection: StageDiagnostics = StageDiagnostics()
    recall: StageDiagnostics = StageDiagnostics()
    degraded: bool = False

    @classmethod
    def failed(cls) -> "RetrievalDiagnostics":
        """Retrieval raised, so there is no ``S`` and no bucket was filled."""
        return cls(outcome=FAILED)

    @property
    def summary(self) -> dict[str, object]:
        """The shape a log line carries: the outcome, then each stage."""
        return {
            "outcome": self.outcome,
            "degraded": self.degraded,
            "selection": self.selection.summary,
            "recall": self.recall.summary,
        }
