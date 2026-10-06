"""Detecting whether a question requires corpus evidence (IR-464).

ADR-035 §5. The detector runs on the **raw question and on the stored Resolved
question, combined by OR**: a rewrite must never be able to weaken an evidence
requirement, and the Resolved question is untrusted input -- it came from a
resolver that reads prior assistant answers, which are retrieval-derived and
may carry text injected into a Passage. Where the two disagree, the
requirement stands.

Three things this cannot do, by construction:

- It cannot express a refusal. The outcomes are "evidence required" and "no
  requirement detected"; the second is not a claim that nothing exists.
- It cannot read a Record, a user or the disclosure gate. Visibility and
  disclosure are the application's, applied inside retrieval (ADR-035 §6).
- It cannot answer. Nothing consumes a `Verdict` yet.

Pure apart from the rule set it is given: no Django, no database, no model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .rules import REASON_CODES, SCOPE_RECORD, RuleSet, normalize

#: Which text a hit came from. `scope` is the structural rule, which has no
#: text behind it.
SOURCE_SCOPE = "scope"
SOURCE_RAW = "raw"
SOURCE_RESOLVED = "resolved"
SOURCES = (SOURCE_SCOPE, SOURCE_RAW, SOURCE_RESOLVED)


@dataclass(frozen=True)
class RuleHit:
    """One rule firing on one source, and the phrases that raised it."""

    code: str
    source: str
    matched: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "source": self.source, "matched": list(self.matched)}


@dataclass(frozen=True)
class Verdict:
    """Whether this question requires corpus evidence, and why.

    `undetermined` is the fail-safe: unreadable question text yields a
    requirement with no rule code, because the cheap error is a pointless
    retrieval and the expensive one is answering without passages that were
    needed (ADR-035 §3).

    There is deliberately no field a consumer could read as "refuse".
    """

    evidence_required: bool
    hits: tuple[RuleHit, ...] = ()
    rule_set_digest: str = ""
    undetermined: bool = False

    @property
    def codes(self) -> tuple[str, ...]:
        """The reason codes that fired, in ADR-035 §5's order."""
        fired = {hit.code for hit in self.hits}
        return tuple(code for code in REASON_CODES if code in fired)

    def codes_from(self, source: str) -> tuple[str, ...]:
        fired = {hit.code for hit in self.hits if hit.source == source}
        return tuple(code for code in REASON_CODES if code in fired)

    def fired(self, code: str) -> bool:
        return code in self.codes

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_required": self.evidence_required,
            "codes": list(self.codes),
            "undetermined": self.undetermined,
            "rule_set_digest": self.rule_set_digest,
            "hits": [hit.as_dict() for hit in self.hits],
        }


def _lexical_hits(rule_set: RuleSet, text: str, source: str) -> tuple[RuleHit, ...]:
    normalized = normalize(text)
    return tuple(
        RuleHit(code=rule.code, source=source, matched=matched)
        for rule in rule_set.rules
        if (matched := rule.matches(normalized))
    )


def _readable(text: Optional[str]) -> bool:
    """Whether there is anything here for a rule to match.

    Judged on the normalized form, not the raw string: "???" carries no word,
    so the detector has nothing to go on and the unclear case must fail safe
    to a requirement rather than read as "no requirement detected".
    """
    return bool(text) and bool(normalize(str(text)).strip())


class EvidenceDetector:
    """The deterministic half of the evidence decision.

    Built from one `RuleSet`, which `config.active_rule_set()` reads at
    startup. Stateless and reusable.
    """

    def __init__(self, rule_set: RuleSet) -> None:
        self._rules = rule_set

    @property
    def rule_set(self) -> RuleSet:
        return self._rules

    def detect(
        self,
        question: Optional[str],
        *,
        resolved_question: Optional[str] = None,
        record_scoped: bool = False,
    ) -> Verdict:
        """The requirement for one question, raw and Resolved combined by OR.

        `record_scoped` is the Conversation's own binding to a Record, taken
        from the request and never from anything a model emitted.
        """
        hits: list[RuleHit] = []
        if record_scoped:
            hits.append(RuleHit(code=SCOPE_RECORD, source=SOURCE_SCOPE))

        if _readable(question):
            hits.extend(_lexical_hits(self._rules, str(question), SOURCE_RAW))
        if _readable(resolved_question):
            hits.extend(
                _lexical_hits(self._rules, str(resolved_question), SOURCE_RESOLVED)
            )

        undetermined = (
            not record_scoped
            and not _readable(question)
            and not _readable(resolved_question)
        )
        return Verdict(
            evidence_required=bool(hits) or undetermined,
            hits=tuple(hits),
            rule_set_digest=self._rules.digest,
            undetermined=undetermined,
        )

    def detect_lane(
        self, question: Optional[str], *, source: str, record_scoped: bool = False
    ) -> Verdict:
        """One lane on its own, for a report that keeps raw and Resolved apart.

        The combined verdict is what a route would read; these two exist so an
        over-fire or a miss can be attributed to the text it came from.
        """
        if source == SOURCE_RAW:
            return self.detect(question, record_scoped=record_scoped)
        if source == SOURCE_RESOLVED:
            return self.detect(None, resolved_question=question, record_scoped=record_scoped)
        raise ValueError(f"a lane is {SOURCE_RAW} or {SOURCE_RESOLVED}, not {source!r}")
