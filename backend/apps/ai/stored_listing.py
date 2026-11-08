"""Listings and topic counts as a stored Turn shows them (IR-546, IR-547).

The research lane that screened them is retired (IR-957); a Turn it wrote
still reads through `reader_view`, which rebuilds the wording from the
candidates this reader may see now, so it never counts a paper not visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.ai.answers.events import EXCLUDED, INCLUDED, UNASSESSED, UNCERTAIN
from apps.ai.models.chunk import DocumentChunk

#: At most this many distinct Records are screened for one ordinary listing.
#: A constant on purpose: changing it needs measured screening recall, latency
#: and cost on human-labelled pilot data (IR-546), not an environment edit.
CANDIDATE_LIMIT = 20

LIST_WORDING = "These are matches found, not a complete list of the papers you can see."

#: What a Turn keeps of a count: the run's identity. Every figure is rebuilt from the candidates.
TOPIC_PROVENANCE = ("criterion", "method", "version")

#: What a topic count counts, said once so a reader never takes it for the other kinds.
COUNT_BASIS = "topic_classification_of_selected_candidates"
COUNT_SCOPE = (
    "This counts topic classifications among the selected candidates only. It is not a "
    "catalogue metadata count and not a count of every paper you can see. "
    "Other relevant papers may exist beyond the selected candidates."
)
OBSERVED_NOTE = (
    "Observed for this run only. A run that reused earlier verdicts does not show how a "
    "fresh model call performs or what capacity exists."
)


@dataclass(frozen=True)
class Candidate:
    record_id: int
    title: str
    state: str
    #: A verbatim quote that decided it, and where it came from.
    quote: str = ""
    source: Optional[dict] = None
    #: The Record is readable but its content may not go to a model. It counts
    #: as a candidate and as unassessed, and is not named: a paper that AI may
    #: not read is reported only as one that could not be assessed.
    restricted: bool = False

    def wire(self) -> dict:
        if self.restricted:
            return {"record_id": self.record_id, "state": UNASSESSED, "restricted": True}
        row = {"record_id": self.record_id, "title": self.title, "state": self.state}
        if self.quote:
            row.update(quote=self.quote, source=self.source)
        return row


@dataclass(frozen=True)
class Outcome:
    candidates: tuple[Candidate, ...]
    more_available: bool = False
    search_degraded: bool = False
    #: Access or content changed while the run was going.
    changed: bool = False
    limit: int = CANDIDATE_LIMIT
    #: Set for a topic count: the criterion, method and version it was made under.
    topic: Optional[dict] = None
    #: Cache use, stage timings and usage of the run that produced this, if known.
    observed: Optional[dict] = None

    def count(self, state: str) -> int:
        return sum(c.state == state for c in self.candidates)

    @property
    def decided(self) -> int:
        return self.count(INCLUDED) + self.count(EXCLUDED)

    @property
    def judged(self) -> int:
        return self.decided + self.count(UNCERTAIN)

    @property
    def completeness(self) -> str:
        """`inconclusive` only when nothing was assessed at all."""
        return "inconclusive" if self.candidates and not self.judged else "matches_found"

    @property
    def degraded(self) -> bool:
        return self.search_degraded or self.count(UNASSESSED) > 0

    def coverage(self) -> dict:
        return {
            "limit": self.limit, "selected": len(self.candidates),
            "included": self.count(INCLUDED), "excluded": self.count(EXCLUDED),
            "uncertain": self.count(UNCERTAIN), "unassessed": self.count(UNASSESSED),
            "more_available": self.more_available, "search_degraded": self.search_degraded,
            "changed": self.changed,
        }

    def wording(self) -> str:
        selected = len(self.candidates)
        notes = []
        if self.more_available:
            notes.append(f"More candidates were found than were screened (limit {self.limit}).")
        if self.search_degraded:
            notes.append("Meaning-based search was unavailable, so candidates came from word "
                         "matching only.")
        if not selected:
            return " ".join(["No candidate papers were found among the papers you can see. "
                             "This is a search result, not proof that none exist.", *notes])
        if self.changed:
            notes.append("The papers you can read changed while this ran; this covers the "
                         "papers still readable.")
        if self.completeness == "inconclusive":
            return " ".join([
                f"Inconclusive: none of the {selected} candidate papers could be assessed, "
                "so this does not show whether any match. Please try again.",
                "Other relevant papers may exist.", *notes])
        if self.topic:
            return self._count_wording(notes)
        counts = (f"Screened {selected} candidate papers: {self.count(INCLUDED)} matched, "
                  f"{self.count(EXCLUDED)} did not match, {self.count(UNCERTAIN)} uncertain, "
                  f"{self.count(UNASSESSED)} could not be assessed.")
        lead = ("" if self.count(INCLUDED) else
                "No matches found among the assessed candidates; other relevant papers may exist. ")
        return " ".join([lead + counts, LIST_WORDING, *notes])

    def _count_wording(self, notes: list) -> str:
        selected, matches, uncertain = len(self.candidates), self.count(INCLUDED), self.count(UNCERTAIN)
        counted = (
            f"{matches} {'match' if matches == 1 else 'matches'} among {self.judged} assessed of "
            f"{selected} selected candidate {'paper' if selected == 1 else 'papers'}"
            + (f", {uncertain} of them uncertain" if uncertain else "")
            + f", with {self.count(UNASSESSED)} not assessed."
        )
        provenance = (f'Criterion: "{self.topic["criterion"]}" '
                      f"({self.topic['method'].replace('_', ' ')}, {self.topic['version']}).")
        return " ".join([counted, provenance, COUNT_SCOPE, *notes])

    def topic_count(self) -> dict:
        """The count's figures and provenance, always derived from the candidates."""
        return {
            **self.topic, "basis": COUNT_BASIS,
            "matches": self.count(INCLUDED), "assessed": self.judged,
            "excluded": self.count(EXCLUDED), "uncertain": self.count(UNCERTAIN),
            "unassessed": self.count(UNASSESSED), "selected": len(self.candidates),
            "limit": self.limit, "more_available": self.more_available,
        }

    def wire(self) -> dict:
        """The listing a reader receives, and what a Turn stores (ids only)."""
        wire = {
            "completeness": self.completeness,
            "wording": self.wording(),
            "records": [{"record_id": c.record_id, "title": c.title}
                        for c in self.candidates if c.state == INCLUDED],
            "candidates": [c.wire() for c in self.candidates],
            "coverage": self.coverage(),
        }
        if self.topic:
            wire["topic_count"] = self.topic_count()
        if self.observed:
            wire["observed"] = self.observed
        return wire


def verify_quote(quote: str, source: Optional[dict], record) -> bool:
    """Does ``quote`` still appear where it was found, in this Record as it is now?"""
    field = (source or {}).get("field")
    if field == "title":
        return quote in record.title
    if field == "abstract":
        return quote in record.abstract
    if field == "passage":
        return DocumentChunk.objects.filter(
            pk=source.get("chunk_id"), record_id=record.pk, deleted_at__isnull=True,
            content__contains=quote,
        ).exists()
    return False


def reader_view(stored: dict, visible: dict) -> dict:
    """A stored listing as this reader may see it now (``visible``: id to Record).

    Unseen candidates are gone and a quote that no longer holds reads as
    unassessed; the wording is rebuilt, so it never counts a paper not visible.
    """
    coverage = stored.get("coverage") or {}
    candidates, changed = [], bool(coverage.get("changed"))
    for row in stored["candidates"]:
        record = visible.get(row["record_id"])
        if record is None:
            changed = True
            continue
        if row.get("restricted"):
            candidates.append(Candidate(record.pk, "", UNASSESSED, restricted=True))
            continue
        quote, source, state = row.get("quote", ""), row.get("source"), row["state"]
        if quote and not verify_quote(quote, source, record):
            quote, source, state, changed = "", None, UNASSESSED, True
        candidates.append(Candidate(record.pk, record.title, state, quote, source))
    topic = stored.get("topic_count")
    return Outcome(
        tuple(candidates), bool(coverage.get("more_available")),
        bool(coverage.get("search_degraded")), changed, coverage.get("limit", CANDIDATE_LIMIT),
        # Provenance is what ran; every figure is rebuilt from the candidates read just now.
        {key: topic[key] for key in TOPIC_PROVENANCE} if topic else None,
        stored.get("observed"),
    ).wire()
