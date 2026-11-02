"""Chunks from authoritative labels, observed through the ingestion boundary."""

from dataclasses import replace

from apps.ai.chunking.values import ChunkingOptions
from apps.ai.extraction.shaping import shape_llamaparse
from apps.ai.extraction.tests.test_shaping import recorded, result_with
from apps.ai.ingestion.pipeline import build_chunk_set
from apps.ai.chunking.tokens import count_tokens


def test_recorded_formula_is_displayed_but_never_embedded():
    chunks = build_chunk_set(shape_llamaparse(recorded("figures")), ChunkingOptions()).chunks
    assert "a^2 + b^2 = c^2" in "\n".join(c.content for c in chunks)
    assert "a^2 + b^2 = c^2" not in "\n".join(c.text for c in chunks)
    assert "$$" in "\n".join(c.content for c in chunks)
    assert "IRIS contract fixture" not in "\n".join(c.text for c in chunks)


def test_heading_paths_use_declared_levels_and_text_has_no_legacy_repairs():
    raw = result_with([
        {"type": "heading", "value": "Paper", "level": 1},
        {"type": "heading", "value": "9.8.7 Methods", "level": 2},
        {"type": "text", "value": "123"},
        {"type": "text", "value": "inter-"},
        {"type": "text", "value": "national"},
        {"type": "heading", "value": "Peer", "level": 2},
        {"type": "text", "value": "Another body."},
    ])
    chunks = build_chunk_set(shape_llamaparse(raw), ChunkingOptions()).chunks
    peer = next(c for c in chunks if "Another body." in c.content)
    assert peer.context_path == ("Paper", "Peer")
    method = next(c for c in chunks if "national" in c.content)
    assert method.context_path == ("Paper", "9.8.7 Methods")
    assert "123" in method.text and "inter-" in method.text and "national" in method.text
    assert "international" not in method.text


def test_recorded_merged_table_splits_only_between_rows_and_repeats_its_header():
    chunk_set = build_chunk_set(shape_llamaparse(recorded("table_across_pages")), ChunkingOptions(max_tokens=80))
    tables = [c for c in chunk_set.chunks if "table" in c.element_kinds]
    assert len(tables) > 1
    assert all("Sample | Mass" in c.text for c in tables)
    assert all("<table>" in c.content and "<th>Sample</th>" in c.content for c in tables)
    assert all(count_tokens(c.text) <= 80 for c in tables)
    body = "\n".join(c.text for c in tables)
    for number in range(1, 31):
        assert body.count(f"Row {number:02d} | {400 + number} g") == 1
    assert {box.page for c in tables for box in c.bboxes} == {1, 2}
    assert chunk_set.options.strategy == chunk_set.strategy_id == "labeled-structure-v1"


def test_oversized_list_and_figure_are_atomic_and_description_is_retrieval_only():
    document = shape_llamaparse(result_with([
        {"type": "heading", "value": "Study", "level": 1},
        {"type": "list", "ordered": True, "items": [
            {"type": "text", "value": f"Complete item {number} with several words."} for number in range(20)
        ]},
        {"type": "image", "caption": "Figure 1: Printed caption."},
    ]))
    figure = replace(document.elements[-1], description="Machine-only chart interpretation.")
    document = replace(document, elements=document.elements[:-1] + (figure,))
    chunks = build_chunk_set(document, ChunkingOptions(max_tokens=30)).chunks
    listings = [c for c in chunks if "list" in c.element_kinds]
    assert len(listings) == 1
    assert "Complete item 0" in listings[0].content and "Complete item 19" in listings[0].content
    figures = [c for c in chunks if "image" in c.element_kinds]
    assert len(figures) == 1
    assert "Printed caption" in figures[0].content and "Printed caption" in figures[0].text
    assert "Machine-only chart interpretation." in figures[0].text
    assert "Machine-only" not in "\n".join(c.content for c in chunks)


def test_long_prose_respects_the_budget_including_its_context_prefix():
    prose = " ".join(f"Observation {number} is preserved." for number in range(40))
    document = shape_llamaparse(result_with([
        {"type": "heading", "level": 1, "value": "Study"},
        {"type": "text", "value": prose},
    ]))
    chunks = build_chunk_set(document, ChunkingOptions(max_tokens=40)).chunks
    assert len(chunks) > 1
    assert all(count_tokens(c.text) <= 40 and c.token_count == count_tokens(c.text) for c in chunks)
    display = " ".join(c.content for c in chunks)
    for number in range(40):
        assert f"Observation {number} is preserved." in display


def test_exclusions_remain_a_chunking_choice_and_repeated_body_text_is_kept():
    raw = result_with([
        {"type": "heading", "level": 1, "value": "References"},
        {"type": "text", "value": "Omitted bibliography."},
        {"type": "heading", "level": 1, "value": "Findings"},
        {"type": "text", "value": "Repeated finding"},
    ])
    for number in (2, 3):
        raw["items"]["pages"].append({
            "page_number": number, "page_width": 612, "page_height": 792,
            "items": [{"type": "text", "value": "Repeated finding"}],
        })
    document = shape_llamaparse(raw)
    assert "Omitted bibliography." in [e.text for e in document.elements]
    chunk_set = build_chunk_set(document, ChunkingOptions(exclude_sections=("References",)))
    text = "\n".join(c.text for c in chunk_set.chunks)
    assert "Omitted bibliography." not in text
    assert text.count("Repeated finding") == 3
