"""The chunk keyword index is the database's job, not ours (IR-393).

Every assertion reads the column back out of the database, since what ADR-033
§2 bought is that a write path nobody has written yet is still indexed.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from io import StringIO

from apps.ai.keyword_index import (
    CONFIG,
    backfill_chunk_keyword_index,
    chunks_awaiting_backfill,
)
from apps.ai.models.chunk import ChunkSet, DocumentChunk
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture
def chunk_set(db):
    record = Record.objects.create(title="Pond Thesis")
    return ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash="c", is_active=True,
    )


def make_chunk(chunk_set, content, sequence=0):
    return DocumentChunk.objects.create(
        chunk_set=chunk_set, record=chunk_set.record, sequence=sequence,
        max_sequence=0, text=content, content=content, context_path=[],
        token_count=len(content.split()), text_hash=f"h{sequence}",
        source_page=1, element_kinds=["paragraph"], bboxes=[],
    )


def stored_vector(chunk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT search_vector::text FROM ai_documentchunk WHERE id = %s",
            [chunk.pk],
        )
        return cursor.fetchone()[0]


def clear_vector(chunk):
    """Undo the trigger's work without touching `content`, which is how a row
    that predates the trigger looks."""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE ai_documentchunk SET search_vector = NULL WHERE id = %s",
            [chunk.pk],
        )


class TheDatabaseMaintainsTheColumnTests:
    def test_an_inserted_chunk_is_indexed_without_any_code_doing_so(self, chunk_set):
        chunk = make_chunk(chunk_set, "weekly pond sampling procedure")

        assert "sampl" in stored_vector(chunk)

    def test_an_edited_chunk_is_reindexed(self, chunk_set):
        chunk = make_chunk(chunk_set, "weekly pond sampling procedure")

        chunk.content = "monthly reservoir titration"
        chunk.save()

        stored = stored_vector(chunk)
        assert "titrat" in stored
        assert "sampl" not in stored

    def test_a_bulk_written_chunk_set_is_indexed_too(self, chunk_set):
        """The path `repositories.save` uses: no `save()`, no signal."""
        DocumentChunk.objects.bulk_create([
            DocumentChunk(
                chunk_set=chunk_set, record=chunk_set.record, sequence=i,
                max_sequence=1, text=text, content=text, context_path=[],
                token_count=2, text_hash=f"b{i}", source_page=1,
                element_kinds=["paragraph"], bboxes=[],
            )
            for i, text in enumerate(["aeration schedule", "harvest yield"])
        ])

        indexed = DocumentChunk.objects.filter(
            chunk_set=chunk_set, search_vector__isnull=False
        ).count()
        assert indexed == 2

    def test_the_query_and_the_column_agree_about_what_a_word_is(self, chunk_set):
        """`english` stems `sampling` to `sampl`; `simple` would not."""
        chunk = make_chunk(chunk_set, "weekly pond sampling")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT search_vector @@ plainto_tsquery(%s, 'sample') "
                "FROM ai_documentchunk WHERE id = %s",
                [CONFIG, chunk.pk],
            )
            assert cursor.fetchone()[0] is True

    def test_the_configuration_matches_the_record_index(self):
        """`Record.search_vector` is built with no `config=`, so it takes the
        server's `default_text_search_config`. This column names `english`
        outright, which agrees only while that default is `english` -- so the
        agreement is asserted rather than assumed."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_tsvector(%s, 'weekly pond sampling') "
                "= to_tsvector('weekly pond sampling')",
                [CONFIG],
            )
            assert cursor.fetchone()[0] is True


class BackfillTests:
    def test_it_fills_a_chunk_that_predates_the_trigger(self, chunk_set):
        chunk = make_chunk(chunk_set, "weekly pond sampling")
        clear_vector(chunk)
        assert chunks_awaiting_backfill() == 1

        assert backfill_chunk_keyword_index() == 1
        assert "sampl" in stored_vector(chunk)

    def test_running_it_again_writes_nothing(self, chunk_set):
        chunk = make_chunk(chunk_set, "weekly pond sampling")
        clear_vector(chunk)
        backfill_chunk_keyword_index()

        assert backfill_chunk_keyword_index() == 0

    def test_an_interrupted_run_resumes_where_it_stopped(self, chunk_set):
        """No state is carried between the two calls; it recomputes."""
        for i, text in enumerate(["aeration", "harvest", "titration"]):
            clear_vector(make_chunk(chunk_set, text, sequence=i))

        assert backfill_chunk_keyword_index(batch_size=1, limit=1) == 1
        assert chunks_awaiting_backfill() == 2
        assert backfill_chunk_keyword_index(batch_size=1) == 2
        assert chunks_awaiting_backfill() == 0

    def test_the_command_reports_an_empty_backlog_without_writing(self, chunk_set):
        make_chunk(chunk_set, "weekly pond sampling")
        out = StringIO()

        call_command("backfill_chunk_keyword_index", stdout=out)

        assert "nothing to do" in out.getvalue()

    def test_the_command_dry_run_writes_nothing(self, chunk_set):
        chunk = make_chunk(chunk_set, "weekly pond sampling")
        clear_vector(chunk)
        out = StringIO()

        call_command("backfill_chunk_keyword_index", "--dry-run", stdout=out)

        assert chunks_awaiting_backfill() == 1
        assert stored_vector(chunk) is None
