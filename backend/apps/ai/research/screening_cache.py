"""A reader's remembered screening verdicts (IR-547).

Reuse is an optimisation and never a grant. The cache is consulted only for
Records already selected as candidates, readable and disclosable now; a hit
supplies a verdict and nothing else, and the caller still re-checks access,
content and the verbatim quote before the verdict reaches the reader.

Scope is one reader. Another reader's verdict is never read: a cross-reader
count is an inference channel (ADR-027 §3, ADR-038 §Counts) and nobody has
approved one. Content is a digest inside the key, never a column.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from django.db import transaction

from apps.ai.models.chunk import ChunkSet
from apps.ai.models.screening import ScreeningJudgment
from apps.ai.research.tools import screening

#: The reply shape the prompt asks for. Bump it when `validate_decisions` changes
#: what it accepts, so verdicts read under the old rules are never reused.
SCHEMA = "decisions-v1"
METHOD = "title_and_abstract_screening"
#: Only these are worth remembering: `unassessed` records a failure, not a view.
REMEMBERED = ("included", "excluded", "uncertain")


def version() -> str:
    """Names the prompt and reply schema a verdict was made under."""
    digest = hashlib.sha256(f"{SCHEMA}\0{screening.SYSTEM}".encode()).hexdigest()
    return f"screen-{digest[:8]}"


@dataclass(frozen=True)
class Verdict:
    state: str
    quote: str
    source: Optional[dict]


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


class ScreeningCache:
    """Verdicts for one reader, one criterion, one model and one approval policy."""

    def __init__(self, user, *, criterion: str, model: str, policy: str) -> None:
        self.user = user
        # Whitespace alone never makes a different criterion.
        self._scope = json.dumps([" ".join(criterion.split()), model, policy, version(), METHOD])
        self._versions: dict[int, str] = {}

    # -- keys ------------------------------------------------------------------

    def _load_versions(self, ids: Iterable[int]) -> None:
        """The extraction behind each Record's chunks, read once per Record."""
        missing = [pk for pk in set(ids) if pk not in self._versions]
        if not missing:
            return
        active = {
            row["record_id"]: _digest(row["strategy_id"], row["extraction_hash"], row["content_hash"])
            for row in ChunkSet.objects.filter(record_id__in=missing, is_active=True)
            .values("record_id", "strategy_id", "extraction_hash", "content_hash")
        }
        for pk in missing:
            self._versions[pk] = active.get(pk, "no-extraction")

    def _key(self, pk: int, title: str, abstract: str) -> str:
        return _digest(self._scope, str(pk), self._versions[pk], _digest(title), _digest(abstract))

    # -- use -------------------------------------------------------------------

    def recall(self, records: Mapping[int, "object"]) -> dict[int, Verdict]:
        """Remembered verdicts for ``records`` (id to Record) as they are now."""
        if not records:
            return {}
        self._load_versions(records)
        keys = {self._key(pk, r.title, r.abstract): pk for pk, r in records.items()}
        found = ScreeningJudgment.objects.filter(user=self.user, key__in=list(keys))
        return {
            keys[row.key]: Verdict(row.state, row.quote, row.source)
            for row in found if row.state in REMEMBERED
        }

    def remember(self, verdicts: Mapping[int, Verdict], evidence: Mapping[int, tuple[str, str]]) -> None:
        """Keep each decision against the content it was made from.

        Safe to race: a concurrent writer of the same key either updates the row
        first or loses the insert, and the row that exists then is a decision
        about the same content, so either is correct to keep.
        """
        kept = {pk: v for pk, v in verdicts.items() if v.state in REMEMBERED and pk in evidence}
        if not kept:
            return
        self._load_versions(kept)
        with transaction.atomic():
            for pk, verdict in kept.items():
                key = self._key(pk, *evidence[pk])
                changed = ScreeningJudgment.objects.filter(user=self.user, key=key).update(
                    state=verdict.state, quote=verdict.quote, source=verdict.source)
                if not changed:
                    ScreeningJudgment.objects.bulk_create(
                        [ScreeningJudgment(user=self.user, record_id=pk, key=key, state=verdict.state,
                                           quote=verdict.quote, source=verdict.source)],
                        ignore_conflicts=True,
                    )
