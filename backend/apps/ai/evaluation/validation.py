"""Does every label point at something that exists? (IR-133 / IR-394)

The labelling loop is a person reading PDFs and typing quotes, and the three
ways that goes wrong are all silent: a title that does not match a `Record`, a
quote Docling extracted differently than it reads on the page, and a quote that
straddles a chunk boundary. Each one shows up as a question that scores zero,
indistinguishable from retrieval failing.

So this checks the labels against the corpus **without embedding anything** —
pure SQL over the active chunk sets. It is what `--dry-run` runs, and it costs
no vendor credits, which is why a labeller can run it after every few
questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.ai.models.chunk import DocumentChunk
from apps.records.models import Record

from .labels import Label, QuestionSet, normalize


@dataclass(frozen=True)
class LabelCheck:
    question_id: str
    label: Label
    record_id: Optional[int] = None
    problem: Optional[str] = None
    found_on_pages: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.problem is None


def _resolve_record(label: Label) -> tuple[Optional[Record], Optional[str]]:
    if isinstance(label.record, int):
        record = Record.objects.filter(pk=label.record).first()
        return record, None if record else f"no record with id {label.record}"

    matches = list(Record.objects.filter(title__iexact=str(label.record).strip())[:2])
    if not matches:
        return None, f"no record titled {str(label.record)[:60]!r}"
    if len(matches) > 1:
        return None, f"{str(label.record)[:60]!r} matches more than one record"
    return matches[0], None


def check_label(question_id: str, label: Label) -> LabelCheck:
    record, problem = _resolve_record(label)
    if record is None:
        return LabelCheck(question_id, label, problem=problem)

    chunks = DocumentChunk.objects.filter(
        record=record, chunk_set__is_active=True
    ).values_list("content", "source_page")
    if not chunks:
        return LabelCheck(
            question_id,
            label,
            record_id=record.pk,
            problem="record has no active chunk set — it has not been extracted "
            "and chunked yet",
        )

    quote = label.normalized_quote
    pages = tuple(
        sorted(
            {
                page
                for content, page in chunks
                if page is not None and quote in normalize(content or "")
            }
        )
    )
    if not any(quote in normalize(content or "") for content, _ in chunks):
        return LabelCheck(
            question_id,
            label,
            record_id=record.pk,
            problem="quote is in no chunk of this record — check the wording "
            "against `manage.py inspect_chunks`, or shorten it: a quote that "
            "crosses a chunk boundary is in neither chunk",
        )

    if label.page is not None and pages and label.page not in pages:
        return LabelCheck(
            question_id,
            label,
            record_id=record.pk,
            found_on_pages=pages,
            problem=f"quote found, but on page {pages[0]}, not the labelled "
            f"page {label.page} — correct the page",
        )

    return LabelCheck(question_id, label, record_id=record.pk, found_on_pages=pages)


def check_question_set(question_set: QuestionSet) -> list[LabelCheck]:
    return [
        check_label(question.id, label)
        for question in question_set.questions
        for label in question.expected
    ]


def render_checks(checks: list[LabelCheck]) -> str:
    good = [c for c in checks if c.ok]
    bad = [c for c in checks if not c.ok]
    lines = [f"{len(good)}/{len(checks)} labels resolve against this database.", ""]
    for check in bad:
        lines.append(f"  x {check.question_id}: {check.problem}")
        lines.append(f"      quote: {check.label.quote[:70]}")
        lines.append(f"      record: {str(check.label.record)[:70]}")
    if bad:
        lines.append("")
        lines.append(
            "A label that does not resolve scores zero for a reason that has "
            "nothing to do with retrieval. Fix these before spending a run."
        )
    return "\n".join(lines)
