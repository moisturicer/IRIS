"""The outbound guard: rechecked before every physical provider attempt (IR-720).

Reading permission is not transmission permission. Each attempt rechecks the
reader's current access, scope, the source revision read, disclosure and the
recipient's provider policy. Content already sent cannot be recalled.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TypeVar

from apps.ai.admission import scope
from apps.ai.admission.errors import AdmissionDenied

T = TypeVar("T")


PASSAGE = "passage"
ABSTRACT = "abstract"
METADATA = "metadata"
#: The only reader-facing trace of a withheld source.
LIMITATION = "source_unavailable"


def _digest(title: str, abstract: str) -> str:
    return hashlib.sha256(f"{title}\0{abstract}".encode()).hexdigest()


@dataclass(frozen=True)
class Dependency:
    """A source an outgoing payload was built from, at the revision read."""

    record_id: int
    kind: str = METADATA
    version: Optional[str] = None

    @classmethod
    def passage(cls, record_id: int, chunk_set_hash: str) -> "Dependency":
        return cls(record_id, PASSAGE, chunk_set_hash)

    @classmethod
    def abstract(cls, record_id: int, title: str, abstract: str) -> "Dependency":
        return cls(record_id, ABSTRACT, _digest(title, abstract))

    @classmethod
    def metadata(cls, record_id: int) -> "Dependency":
        return cls(record_id)


def configured_provider_permits(model: Optional[str]) -> bool:
    """Only a model IRIS's configuration names, under a no-training policy."""
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    from apps.ai.inference import DataPolicy, InferenceTask, profile_for

    if not model:
        return False
    known = {getattr(settings, "VOYAGE_EMBED_MODEL", ""), getattr(settings, "VOYAGE_RERANK_MODEL", "")}
    for task in InferenceTask:
        try:
            profile = profile_for(task)
        except (ImproperlyConfigured, ValueError):
            continue
        if profile.data_policy is DataPolicy.NO_TRAINING:
            known.update(profile.models)
    return model in known - {""}


def disclosure_permits(record) -> bool:
    from .records import decision_for_record

    return decision_for_record(record).allowed


@dataclass(frozen=True)
class Authorization:
    permitted: frozenset
    withheld: frozenset = frozenset()
    provider_refused: bool = False

    @property
    def allowed(self) -> bool:
        return not self.withheld and not self.provider_refused

    def __bool__(self) -> bool:
        return self.allowed

    def retain(self, items: Iterable[T], dependencies_of: Callable[[T], Iterable[Dependency]]) -> tuple[T, ...]:
        """Items derived only from permitted sources; anything else is dropped."""
        return tuple(item for item in items if set(dependencies_of(item)) <= self.permitted)

    @property
    def limitation(self) -> Optional[str]:
        """One neutral code: no identity, title or count of what was withheld."""
        return None if self.allowed else LIMITATION


@dataclass(frozen=True)
class OutboundGuard:
    #: The reader; ``None`` is system work such as indexing.
    principal: object
    permits: Callable = disclosure_permits
    scope_record_id: Optional[int] = None
    provider_permits: Callable[[Optional[str]], bool] = configured_provider_permits

    def authorize(self, dependencies: Iterable[Dependency], *, model: Optional[str] = None) -> Authorization:
        wanted = frozenset(dependencies)
        if not self.provider_permits(model):
            return Authorization(frozenset(), wanted, provider_refused=True)
        records = self._readable().in_bulk({d.record_id for d in wanted})
        allowed = {pk: record for pk, record in records.items() if self.permits(record)}
        indexed = _active_versions(allowed) if any(d.kind == PASSAGE for d in wanted) else {}
        permitted = frozenset(
            d for d in wanted if d.record_id in allowed
            and _current(d, allowed[d.record_id], indexed))
        return Authorization(permitted, wanted - permitted)

    @contextmanager
    def fence(self, dependencies: Callable[[], Iterable[Dependency]]):
        """Authorize ``dependencies()`` before every physical attempt inside.

        A callable, so a caller that rebuilds its payload after a refusal is
        checked against what it sends next. Raises `Withheld` before sending.
        """
        def check(model):
            result = self.authorize(dependencies(), model=model)
            if not result:
                raise Withheld(result)

        with scope.before_send(check):
            yield

    def _readable(self):
        """The principal's research visibility; system work (no principal) reads all."""
        from apps.ai.grants.reads import research_records
        from apps.records.models import Record

        if self.principal is None:
            records = Record.objects.all()
            if self.scope_record_id is not None:
                records = records.filter(pk=self.scope_record_id)
            return records
        return research_records(self.principal, scope_record_id=self.scope_record_id)


def _current(dependency: Dependency, record, indexed: dict) -> bool:
    if dependency.kind == PASSAGE:
        return indexed.get(record.pk) == dependency.version
    if dependency.kind == ABSTRACT:
        return _digest(record.title, record.abstract) == dependency.version
    return True


def _active_versions(records: dict) -> dict:
    from apps.ai.models import ChunkSet

    return dict(ChunkSet.objects.filter(record_id__in=records, is_active=True)
                .values_list("record_id", "content_hash"))


class Withheld(AdmissionDenied):
    """Nothing was sent: a dependency lost its permission before the attempt.

    An `AdmissionDenied`, so it is never retried, never fails over and never
    counts against a circuit, and an answer path that does not handle it
    degrades to its unavailable state. ``authorization`` says what remains.
    """

    def __init__(self, authorization: Authorization) -> None:
        super().__init__(LIMITATION)
        self.authorization = authorization
