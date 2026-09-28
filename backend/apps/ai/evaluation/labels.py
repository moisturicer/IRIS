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


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected: tuple[Label, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "corpus": self.corpus,
            "tier": self.tier,
            "questions": len(self.questions),
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

        raw_expected = raw.get("expected")
        if not isinstance(raw_expected, list) or not raw_expected:
            if drop_incomplete:
                skipped.append(qid)
                continue
            raise QuestionSetError(f"{where}: needs at least one expected passage")

        if drop_incomplete and _is_unlabelled(raw_expected):
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

        questions.append(Question(id=qid, question=text, expected=tuple(labels)))

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
