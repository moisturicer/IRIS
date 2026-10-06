"""What a question's expected answer is labelled as (IR-133 / IR-394).

A label is **a record, a page and a short quote** — never a chunk id.
`apps/ai/repositories.py` replaces a `ChunkSet` wholesale when a document is
re-chunked, so chunk-id labels would stop matching the moment the token
ceiling or the strategy changed, which are exactly the things the harness
exists to evaluate. A quote survives re-chunking, and is also what a human
labeller can read off a PDF (ADR-023 §Amendment).

**A hit is record identity plus quote containment.** The page is recorded and
reported, never scored: a chunk can span a page boundary and re-chunking moves
page attribution around, so requiring it would fail labels that are correct.

Pure: no Django, no database, no vendor. A label can be matched against any
text, which is what lets the re-chunking test run without either.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

#: A quote shorter than this is rejected by the loader. A two-word quote
#: matches half the corpus, and the resulting recall number would be noise
#: dressed as a measurement.
MIN_QUOTE_WORDS = 4
MIN_QUOTE_CHARS = 20

#: Longer than this and the quote is likely to straddle a chunk boundary,
#: which makes the label fail for a reason that is not about retrieval.
MAX_QUOTE_WORDS = 30

_WHITESPACE = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


class QuestionSetError(ValueError):
    """The question set is malformed, and says where."""


def normalize(text: str) -> str:
    """The one normalization both sides of a match go through.

    Unicode-folded, lowercased, curly quotes straightened, soft hyphens
    dropped and every whitespace run collapsed — so a quote typed from a PDF
    still matches text a line break fell inside of. Deliberately no further
    than that: stripping punctuation or stemming would start matching passages
    that do not contain the quote.
    """
    folded = unicodedata.normalize("NFKC", text).replace("­", "")
    return _WHITESPACE.sub(" ", folded.translate(_QUOTES).casefold()).strip()


@dataclass(frozen=True)
class Label:
    """One passage a question should retrieve.

    ``record`` is a title or a record id. A title is what a committed question
    set should carry: ids differ between one developer's database and the
    next, and `load_corpus` is idempotent by title, so the title is the part
    that travels.
    """

    record: str | int
    quote: str
    page: Optional[int] = None

    @property
    def normalized_quote(self) -> str:
        return normalize(self.quote)

    def identifies(self, record_id: int, record_title: str) -> bool:
        if isinstance(self.record, int):
            return self.record == record_id
        return normalize(self.record) == normalize(record_title)

    def found_in(self, text: str) -> bool:
        return self.normalized_quote in normalize(text)

    def matches(self, passage) -> bool:
        """Whether ``passage`` (anything with the `RetrievedChunk` fields) is
        this label's passage."""
        return self.identifies(
            passage.record_id, passage.record_title
        ) and self.found_in(passage.content)

    def as_dict(self) -> dict[str, Any]:
        return {"record": self.record, "page": self.page, "quote": self.quote}


#: Does answering this need the corpus at all? (IR-463)
EVIDENCE_REQUIRED = ("none", "corpus", "corpus_multi")

#: What the reader should get. Separate from `evidence_required` so that
#: "decline" is never mistaken for a retrieval route.
EXPECTED_OUTCOMES = ("answer", "clarify", "decline-no-evidence", "decline-restricted")
_DECLINES = ("decline-no-evidence", "decline-restricted")


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected: tuple[Label, ...]
    kind: Optional[str] = None
    evidence_required: Optional[str] = None
    expected_outcome: Optional[str] = None
    institutional: Optional[bool] = None

    @property
    def deliberately_empty(self) -> bool:
        """No expected passages, *on purpose* -- the question declared what it
        needs and what should happen, so an empty list is a label, not a gap."""
        return not self.expected and self.evidence_required is not None

    @property
    def expects_decline(self) -> bool:
        return self.expected_outcome in _DECLINES

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "kind": self.kind,
            "evidence_required": self.evidence_required,
            "expected_outcome": self.expected_outcome,
            "institutional": self.institutional,
            "expected": [label.as_dict() for label in self.expected],
        }


@dataclass(frozen=True)
class QuestionSet:
    name: str
    questions: tuple[Question, ...]
    source: Optional[str] = None
    corpus: Optional[str] = None
    tier: str = "proxy"
    #: Questions left unlabelled and dropped, when a caller asked for that.
    #: Carried into the report so a number is never read without knowing how
    #: much of the set produced it.
    skipped: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.questions)

    @property
    def label_count(self) -> int:
        return sum(len(q.expected) for q in self.questions)

    @property
    def scored(self) -> tuple[Question, ...]:
        """The questions a recall measure can score. One with no expected
        passage has nothing to recall, and averaging it in as 0.0 would pull
        every recall figure down for a reason that is not retrieval."""
        return tuple(q for q in self.questions if q.expected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "corpus": self.corpus,
            "tier": self.tier,
            "questions": len(self.questions),
            "without_passages": len(self.questions) - len(self.scored),
            "labels": self.label_count,
            "skipped_questions": list(self.skipped),
        }


#: A question whose text is this is an unfilled slot in a template, not a
#: question. Named so a half-labelled set fails loudly instead of scoring 0.
PLACEHOLDER = "TODO"


def _validate_quote(quote: str, where: str) -> None:
    words = quote.split()
    if len(words) < MIN_QUOTE_WORDS or len(quote.strip()) < MIN_QUOTE_CHARS:
        raise QuestionSetError(
            f"{where}: quote is too short to identify a passage "
            f"({len(words)} words, {len(quote.strip())} chars; "
            f"need {MIN_QUOTE_WORDS} words and {MIN_QUOTE_CHARS} chars)"
        )
    if len(words) > MAX_QUOTE_WORDS:
        raise QuestionSetError(
            f"{where}: quote is {len(words)} words; keep it under "
            f"{MAX_QUOTE_WORDS} so it cannot straddle a chunk boundary"
        )


def parse_question_set(
    data: dict[str, Any],
    *,
    source: Optional[str] = None,
    drop_incomplete: bool = False,
) -> QuestionSet:
    """Build a `QuestionSet` from the JSON shape, refusing a bad one.

    Validation is strict on purpose: every defect it catches — an empty
    question, a one-word quote, an unfilled template slot — would otherwise
    surface as a recall number that looks like a retrieval result.

    ``drop_incomplete`` is for labelling in progress: a question still holding
    a ``TODO`` is dropped and named rather than refused, so twelve labelled
    questions out of twenty can be measured today. A *malformed* question —
    a quote too short, a duplicate id — is still refused, because that is a
    mistake rather than unfinished work.
    """
    if not isinstance(data, dict):
        raise QuestionSetError("a question set is a JSON object")

    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise QuestionSetError("'questions' must be a non-empty list")

    questions: list[Question] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_questions):
        where = f"question {index + 1}"
        if not isinstance(raw, dict):
            raise QuestionSetError(f"{where}: must be an object")

        qid = str(raw.get("id") or f"q{index + 1}")
        if qid in seen:
            raise QuestionSetError(f"{where}: duplicate id {qid!r}")
        seen.add(qid)
        where = f"question {qid}"

        text = str(raw.get("question") or "").strip()
        if not text or text == PLACEHOLDER:
            if drop_incomplete:
                skipped.append(qid)
                continue
            raise QuestionSetError(f"{where}: has no question text yet")

        kind, evidence, outcome, institutional = _read_evidence_fields(raw, where)

        raw_expected = raw.get("expected")
        deliberate = (
            evidence is not None
            and isinstance(raw_expected, list)
            and not raw_expected
        )
        if deliberate:
            raw_expected = []
        elif not isinstance(raw_expected, list) or not raw_expected:
            if drop_incomplete:
                skipped.append(qid)
                continue
            raise QuestionSetError(f"{where}: needs at least one expected passage")

        if drop_incomplete and raw_expected and _is_unlabelled(raw_expected):
            skipped.append(qid)
            continue

        labels: list[Label] = []
        for label_index, raw_label in enumerate(raw_expected):
            label_where = f"{where}, expected {label_index + 1}"
            if not isinstance(raw_label, dict):
                raise QuestionSetError(f"{label_where}: must be an object")
            record = raw_label.get("record")
            if isinstance(record, str):
                record = record.strip()
            if not record or record == PLACEHOLDER:
                raise QuestionSetError(f"{label_where}: names no record")
            quote = str(raw_label.get("quote") or "")
            if quote.strip() == PLACEHOLDER:
                raise QuestionSetError(f"{label_where}: has no quote yet")
            _validate_quote(quote, label_where)
            page = raw_label.get("page")
            labels.append(
                Label(
                    record=record,
                    quote=quote,
                    page=int(page) if page not in (None, "") else None,
                )
            )

        _check_declaration(where, evidence, outcome, has_passages=bool(labels))
        questions.append(
            Question(
                id=qid,
                question=text,
                expected=tuple(labels),
                kind=kind,
                evidence_required=evidence,
                expected_outcome=outcome,
                institutional=institutional,
            )
        )

    if not questions:
        raise QuestionSetError(
            "no labelled question survived: every question is still a template "
            "slot. Fill at least one question and one quote."
        )

    return QuestionSet(
        name=str(data.get("name") or "unnamed"),
        questions=tuple(questions),
        source=source,
        corpus=data.get("corpus"),
        tier=str(data.get("tier") or "proxy"),
        skipped=tuple(skipped),
    )


def _read_evidence_fields(raw: dict, where: str):
    """`kind`, `evidence_required`, `expected_outcome`, `institutional`.

    The first and last are free-standing; the middle two are declared together
    or not at all, because one without the other leaves a question that says
    what it needs but not what should happen (or the reverse).
    """
    kind = raw.get("kind")
    if kind is not None and (not isinstance(kind, str) or not kind.strip()):
        raise QuestionSetError(f"{where}: kind must be a non-empty string")

    evidence = raw.get("evidence_required")
    outcome = raw.get("expected_outcome")
    if (evidence is None) != (outcome is None):
        raise QuestionSetError(
            f"{where}: evidence_required and expected_outcome are declared "
            f"together or not at all"
        )
    if evidence is not None and evidence not in EVIDENCE_REQUIRED:
        raise QuestionSetError(
            f"{where}: evidence_required {evidence!r} is not one of "
            f"{', '.join(EVIDENCE_REQUIRED)}"
        )
    if outcome is not None and outcome not in EXPECTED_OUTCOMES:
        raise QuestionSetError(
            f"{where}: expected_outcome {outcome!r} is not one of "
            f"{', '.join(EXPECTED_OUTCOMES)}"
        )

    institutional = raw.get("institutional")
    if institutional is not None and not isinstance(institutional, bool):
        raise QuestionSetError(f"{where}: institutional must be true or false")
    return kind, evidence, outcome, institutional


def _check_declaration(where, evidence, outcome, *, has_passages: bool) -> None:
    """Refuse a declaration that contradicts the passages it sits beside."""
    if evidence is None:
        return
    if evidence == "none" and has_passages:
        raise QuestionSetError(
            f"{where}: needs no evidence (evidence_required: none) but lists "
            f"expected passages"
        )
    if outcome == "decline-no-evidence" and has_passages:
        raise QuestionSetError(
            f"{where}: declines for want of evidence but lists expected passages"
        )
    if evidence != "none" and outcome == "answer" and not has_passages:
        raise QuestionSetError(
            f"{where}: needs corpus evidence and should be answered, so it "
            f"needs at least one expected passage"
        )


def _is_unlabelled(raw_expected: list) -> bool:
    """Whether every expected passage is still a template slot."""
    return all(
        not isinstance(raw, dict)
        or raw.get("record") in (None, "", PLACEHOLDER)
        or str(raw.get("quote") or "").strip() in ("", PLACEHOLDER)
        for raw in raw_expected
    )


def load_question_set(path: str | Path, *, drop_incomplete: bool = False) -> QuestionSet:
    file_path = Path(path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuestionSetError(f"no question set at {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise QuestionSetError(f"{file_path}: invalid JSON — {exc}") from exc
    return parse_question_set(
        data, source=str(file_path), drop_incomplete=drop_incomplete
    )


def labelled_records(question_set: QuestionSet) -> list[str | int]:
    """Every distinct record the set refers to, in first-seen order."""
    seen: list[str | int] = []
    for question in question_set.questions:
        for label in question.expected:
            if label.record not in seen:
                seen.append(label.record)
    return seen


def hits(labels: Iterable[Label], passages: Sequence) -> list[Label]:
    """The labels some passage in ``passages`` satisfies."""
    return [label for label in labels if any(label.matches(p) for p in passages)]
