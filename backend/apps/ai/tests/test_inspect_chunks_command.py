"""The chunk inspection command (IR-116 H).

Light coverage on purpose: the command exists to put chunks in front of a
person, and no test can do that part. What is worth asserting is that the
numbers it reports are the ones the ticket asks to have recorded — a wrong
median region count would be written into the findings and believed.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.chunking import ChunkingOptions
from apps.ai.chunking.document import BoundingBox
from apps.ai.chunking.values import Chunk, ChunkSet
from apps.ai.chunking.hashing import chunkset_hash
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _chunk(sequence: int, regions: int) -> Chunk:
    return Chunk(
        text=f"Thesis > 3 Methodology\n\nPassage {sequence}",
        content=f"Passage {sequence}",
        context_path=("Thesis", "3 Methodology"),
        sequence=sequence,
        token_count=10 + sequence,
        source_page=12,
        element_kinds=frozenset({"paragraph"}),
        bboxes=tuple(
            BoundingBox(page=12, left=72.0, top=100.0 + i, right=540.0, bottom=140.0 + i)
            for i in range(regions)
        ),
    )


@pytest.fixture
def record(db):
    record = Record.objects.create(title="Inspected thesis")
    chunks = (_chunk(0, regions=1), _chunk(1, regions=3), _chunk(2, regions=5))
    DjangoChunkRepository().save(
        record_id=record.id,
        extraction_hash="e" * 64,
        chunk_set=ChunkSet(
            chunks=chunks,
            strategy_id="structural-markdown-v1",
            options=ChunkingOptions(max_tokens=512),
            content_hash=chunkset_hash(chunks),
        ),
    )
    return record


def test_it_reports_the_measurements_the_ticket_asks_to_record(record, capsys):
    call_command("inspect_chunks", record.id, "--json")

    stats = json.loads(capsys.readouterr().out)
    assert stats["chunk_count"] == 3
    assert stats["regions"]["median"] == 3
    assert stats["tokens"]["median"] == 11
    assert stats["without_page"] == 0


def test_it_prints_the_chunks_a_person_is_meant_to_read(record, capsys):
    call_command("inspect_chunks", record.id, "--limit", "2")

    out = capsys.readouterr().out
    assert "Passage 0" in out and "Passage 1" in out
    assert "Passage 2" not in out
    assert "3 Methodology" in out


def test_a_record_with_no_chunk_set_says_so(db, capsys):
    record = Record.objects.create(title="Never chunked")

    with pytest.raises(CommandError, match="no active chunk set"):
        call_command("inspect_chunks", record.id)
