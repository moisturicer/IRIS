"""The five rules a question's evidence requirement is detected by (IR-464).

ADR-035 §5: five rules emitting five reason codes, so an error is attributable
per rule rather than in aggregate. Four are lexical and leaky; `scope_record`
is structural and reliable.

**This is defense in depth, not a classifier.** It misses paraphrases and it
over-fires. A rule may add retrieval; it may never drive a refusal, which is
why nothing here can express one -- the only outcomes are "evidence required"
and "no requirement detected".

Pure: no Django, no settings, no database. The institution and Area terms are
passed in by `config.py`, which reads them at startup.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

#: The structural rule. A Conversation bound to a Record is Paper Chat, and
#: every question in it is about that document.
SCOPE_RECORD = "scope_record"

INSTITUTION_TERM = "institution_term"
DOCUMENT_REFERENCE = "document_reference"
SOURCING_DEMAND = "sourcing_demand"
AGGREGATE_SHAPE = "aggregate_shape"

#: Every reason code, in the order ADR-035 §5 lists them. A report iterates
#: this so a rule that never fires still appears with a zero.
REASON_CODES: tuple[str, ...] = (
    SCOPE_RECORD,
    INSTITUTION_TERM,
    DOCUMENT_REFERENCE,
    SOURCING_DEMAND,
    AGGREGATE_SHAPE,
)

#: Deliberately absent: a restricted-evidence rule. Restricted material is
#: protected by `Record.objects.visible_to(user)` and ADR-015's disclosure
#: gate, never by a word list (ADR-035 §5).
NO_RESTRICTED_RULE = True

# The generic English terms are in code; only institution and Area terms are
# deployment settings (ADR-035 §Per-instance).

DOCUMENT_REFERENCE_TERMS: tuple[str, ...] = (
    "abstract", "article", "articles", "author", "authors", "bibliography",
    "chapter", "citation", "citations", "cite", "cited", "conference",
    "dissertation", "dissertations", "doi", "et al", "figure", "findings",
    "journal", "manuscript", "manuscripts", "paper", "papers", "preprint",
    "preprints", "proceedings", "publication", "publications", "published",
    "section", "study", "studies", "table", "thesis", "theses",
    "this document", "this paper", "this record", "this study",
)

SOURCING_DEMAND_TERMS: tuple[str, ...] = (
    "according to", "back that up", "citation", "citations", "cite your",
    "evidence for", "evidence that", "give me the source",
    "on what basis", "page number", "quote", "quoted", "reference",
    "references", "show me where", "source", "sources", "verbatim",
    "what does it say", "where does it say", "which page", "who said",
    "with citations", "with sources",
)

AGGREGATE_SHAPE_TERMS: tuple[str, ...] = (
    "across the", "all of the papers", "all the papers", "any papers",
    "body of work", "common themes", "corpus", "gap", "gaps", "how many",
    "landscape", "list every", "list of", "list the", "literature",
    "most cited", "most common", "most studied", "number of",
    "overall trend", "overview of the", "research gap", "research gaps",
    "state of the art", "survey of", "trend", "trends",
    "under-researched", "what papers", "which papers", "which theses",
    "who has written", "whole collection",
)

_PUNCTUATION_TO_SPACE = {
    code: " "
    for code in range(0x110000)
    if not chr(code).isalnum() and not chr(code).isspace()
}


def normalize(text: str) -> str:
    """One normalization for the question and the terms alike.

    Unicode-folded, casefolded, every non-alphanumeric character turned into a
    space, whitespace collapsed, and padded with a space at each end -- so a
    term is matched as a whole phrase by plain containment, with no regex and
    no word-boundary edge cases. "CIT-U", "CIT U" and "cit–u" fold together.
    """
    folded = unicodedata.normalize("NFKC", str(text)).casefold()
    spaced = folded.translate(_PUNCTUATION_TO_SPACE)
    return f" {' '.join(spaced.split())} "


def _clean_terms(terms) -> tuple[str, ...]:
    """Deduplicated, normalized, sorted -- so the digest is stable."""
    seen = {normalize(term).strip() for term in terms or ()}
    return tuple(sorted(term for term in seen if term))


@dataclass(frozen=True)
class LexicalRule:
    """One lexical rule: a reason code and the phrases that raise it."""

    code: str
    terms: tuple[str, ...]
    note: str = ""

    def matches(self, normalized_question: str) -> tuple[str, ...]:
        return tuple(
            term for term in self.terms if f" {term} " in normalized_question
        )

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "kind": "lexical", "terms": list(self.terms)}


@dataclass(frozen=True)
class RuleSet:
    """The complete active rule set: four lexical rules plus `scope_record`.

    `digest` covers all of it, generic English terms included, so changing one
    word changes the digest a run records.
    """

    rules: tuple[LexicalRule, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return REASON_CODES

    @property
    def term_counts(self) -> dict[str, int]:
        return {rule.code: len(rule.terms) for rule in self.rules}

    def rule(self, code: str) -> Optional[LexicalRule]:
        for candidate in self.rules:
            if candidate.code == code:
                return candidate
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "codes": list(REASON_CODES),
            "rules": [
                {"code": SCOPE_RECORD, "kind": "structural", "terms": []},
                *(rule.as_dict() for rule in self.rules),
            ],
        }

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def summary(self) -> str:
        counts = ", ".join(
            f"{code}={count}" for code, count in sorted(self.term_counts.items())
        )
        return f"{len(REASON_CODES)} rules ({counts}) digest={self.digest[:12]}"


def build_rule_set(
    *, institution_terms=(), area_terms=()
) -> RuleSet:
    """The rule set for one deployment's institution and Area terms.

    Pure, so a test can build one without touching settings.
    """
    return RuleSet(
        rules=(
            LexicalRule(
                code=INSTITUTION_TERM,
                terms=_clean_terms((*institution_terms, *area_terms)),
                note="names the institution, the repository, or an Area",
            ),
            LexicalRule(
                code=DOCUMENT_REFERENCE,
                terms=_clean_terms(DOCUMENT_REFERENCE_TERMS),
                note="refers to a paper, thesis, author or publication",
            ),
            LexicalRule(
                code=SOURCING_DEMAND,
                terms=_clean_terms(SOURCING_DEMAND_TERMS),
                note="demands sources or citations",
            ),
            LexicalRule(
                code=AGGREGATE_SHAPE,
                terms=_clean_terms(AGGREGATE_SHAPE_TERMS),
                note="asks about the collection — gaps, trends, counts, "
                "'which papers'",
            ),
        )
    )
