"""Read a record's chunks (IR-116 H).

IR-116's exit criterion is not a test: it is a person reading fifty chunks
from a real submission and deciding the token ceiling from what they see.
This command is what makes that possible without a database client, and it
measures the three things the ticket asks to have written down — the token
distribution, the median region count per chunk, and what the front matter
and bibliography actually chunk to.

It only reads. Re-chunking with a different ceiling is a configuration
change (``AI_CHUNK_MAX_TOKENS``) followed by re-running the ingestion task
with ``force=True``, which is the same path production takes.
"""

import json
from collections import Counter
from statistics import median

from django.core.management.base import BaseCommand, CommandError

from apps.ai.repositories import deserialize_regions

# The design doc's own threshold: a chunk assembled from a heading and four
# paragraphs carries five regions, and if the median is around twenty the
# citation overlay needs logic to merge adjacent rectangles. Knowing that
# before the overlay is built is one of the reasons this command exists.
REGION_MERGE_THRESHOLD = 20


class Command(BaseCommand):
    help = "Print the active chunk set for a record, with the statistics IR-116 asks for."

    def add_arguments(self, parser):
        parser.add_argument("record_id", type=int)
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="How many chunks to print in full (default: 50, the number the "
            "ticket asks a person to read). 0 prints none.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the statistics as JSON instead of a report, for pasting "
            "into the written findings.",
        )

    def handle(self, *args, **options):
        from apps.ai.models.chunk import ChunkSet, DocumentChunk
        from apps.records.models import Record

        record_id = options["record_id"]
        record = Record.objects.filter(pk=record_id).first()
        if record is None:
            raise CommandError(f"No record with id {record_id}.")

        chunk_set = ChunkSet.objects.filter(record_id=record_id, is_active=True).first()
        if chunk_set is None:
            raise CommandError(
                f"Record {record_id} has no active chunk set. Has extraction "
                f"finished, and did the chunking task run?"
            )

        chunks = list(
            DocumentChunk.objects.filter(
                chunk_set=chunk_set, deleted_at__isnull=True
            ).order_by("sequence")
        )
        stats = _statistics(chunks, chunk_set)

        if options["json"]:
            self.stdout.write(json.dumps(stats, indent=2))
            return

        self._write_header(record, chunk_set)
        self._write_stats(stats)
        self._write_chunks(chunks[: options["limit"]])

    # -- output ----------------------------------------------------------

    def _write_header(self, record, chunk_set):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nRecord {record.pk}: {record.title}"))
        self.stdout.write(f"  chunk set      {chunk_set.pk}  (created {chunk_set.created_at:%Y-%m-%d %H:%M})")
        self.stdout.write(f"  strategy       {chunk_set.strategy_id}")
        self.stdout.write(f"  content hash   {chunk_set.content_hash[:16]}…")
        self.stdout.write(f"  extraction     {chunk_set.extraction_hash[:16]}…")
        self.stdout.write(f"  options        {json.dumps(chunk_set.options)}")

    def _write_stats(self, stats):
        self.stdout.write(self.style.MIGRATE_HEADING("\nStatistics"))
        self.stdout.write(f"  chunks              {stats['chunk_count']}")
        self.stdout.write(
            f"  tokens              min {stats['tokens']['min']} · "
            f"median {stats['tokens']['median']} · max {stats['tokens']['max']}"
        )
        self.stdout.write(
            f"  at the ceiling      {stats['tokens']['at_ceiling']} chunk(s) within 5% "
            f"of max_tokens={stats['max_tokens']}"
        )
        self.stdout.write(
            f"  regions per chunk   min {stats['regions']['min']} · "
            f"median {stats['regions']['median']} · max {stats['regions']['max']}"
        )
        if stats["regions"]["median"] >= REGION_MERGE_THRESHOLD:
            self.stdout.write(
                self.style.WARNING(
                    "  → a median around twenty is the threshold the design doc "
                    "names: the citation overlay will need logic to merge "
                    "adjacent rectangles."
                )
            )
        self.stdout.write(f"  degenerate rects    {stats['regions']['degenerate']}")
        self.stdout.write(f"  chunks with none    {stats['regions']['without_any']}")
        self.stdout.write(f"  chunks with no page {stats['without_page']}")
        self.stdout.write(f"  spanning >1 page    {stats['spanning_pages']}")
        self.stdout.write(f"  pages covered       {stats['pages_covered']}")
        kinds = ", ".join(f"{kind} {count}" for kind, count in stats["element_kinds"].items())
        self.stdout.write(f"  element kinds       {kinds or '(none recorded)'}")

    def _write_chunks(self, chunks):
        if not chunks:
            return
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nChunks (showing {len(chunks)})"))
        for chunk in chunks:
            self.stdout.write("")
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"[{chunk.sequence}/{chunk.max_sequence}] "
                    f"page {chunk.source_page} · {chunk.token_count} tokens · "
                    f"{len(chunk.bboxes)} region(s) · {', '.join(chunk.element_kinds)}"
                )
            )
            self.stdout.write(f"  path: {' > '.join(chunk.context_path)}")
            for line in chunk.content.splitlines() or [""]:
                self.stdout.write(f"  {line}")


def _statistics(chunks, chunk_set) -> dict:
    """The numbers IR-116 asks to have measured and written down."""
    # Read back through the repository's own deserializer rather than by
    # indexing the stored JSON here: the region wire format has one owner,
    # and a second reader of it is a second thing to change when it moves.
    pages_by_chunk = [
        {box.page for box in deserialize_regions(c.bboxes)} for c in chunks
    ]
    tokens = [c.token_count for c in chunks] or [0]
    regions = [len(c.bboxes) for c in chunks] or [0]
    max_tokens = chunk_set.options.get("max_tokens", 0)
    kinds: Counter = Counter()
    for chunk in chunks:
        kinds.update(chunk.element_kinds)

    return {
        "chunk_count": len(chunks),
        "max_tokens": max_tokens,
        "tokens": {
            "min": min(tokens),
            "median": int(median(tokens)),
            "max": max(tokens),
            # Within 5% of the ceiling: how often the cascade is actually
            # cutting rather than emitting a natural unit. A high count is
            # the signal that the ceiling, not the document, is deciding
            # where chunks end.
            "at_ceiling": sum(1 for t in tokens if max_tokens and t >= max_tokens * 0.95),
        },
        "regions": {
            "min": min(regions),
            "median": int(median(regions)),
            "max": max(regions),
            "without_any": sum(1 for c in chunks if not c.bboxes),
            "degenerate": sum(
                1
                for c in chunks
                for box in deserialize_regions(c.bboxes)
                if box.is_degenerate
            ),
        },
        "without_page": sum(1 for c in chunks if c.source_page is None),
        "spanning_pages": sum(1 for pages in pages_by_chunk if len(pages) > 1),
        "pages_covered": len(set().union(*pages_by_chunk) if pages_by_chunk else set()),
        "element_kinds": dict(kinds.most_common()),
    }
