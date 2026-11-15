"""The sibling-section merge floor as a setting, a trial option and stored data (IR-1147)."""

import pytest

from apps.ai.chunking import ChunkingOptions
from apps.ai.ingestion.pipeline import default_chunking_options
from apps.ai.repositories import _deserialize_options, _serialize_options
from apps.ai.trials import VariantError, parse_variant


def test_the_setting_defaults_to_the_measured_floor(settings):
    assert settings.AI_CHUNK_SIBLING_MERGE_FLOOR == 450
    assert default_chunking_options().sibling_merge_floor == 450


def test_ingestion_reads_the_setting(settings):
    settings.AI_CHUNK_SIBLING_MERGE_FLOOR = 300
    assert default_chunking_options().sibling_merge_floor == 300


def test_a_trial_variant_sets_the_floor():
    variant = parse_variant("sib300=::sibling_merge_floor=300")
    assert variant.spec == "::sibling_merge_floor=300"
    assert variant.chunking_options(ChunkingOptions()).sibling_merge_floor == 300


def test_a_bad_floor_is_refused():
    with pytest.raises(VariantError):
        parse_variant("x=::sibling_merge_floor=lots")


def test_a_small_target_under_the_default_floor_still_builds(settings):
    settings.AI_CHUNK_MAX_TOKENS = 30
    assert default_chunking_options().effective_sibling_merge_floor == 30


def test_the_floor_round_trips_through_storage():
    options = ChunkingOptions(sibling_merge_floor=250)
    assert _deserialize_options(_serialize_options(options)) == options


def test_a_set_stored_before_the_floor_reads_as_off():
    stored = _serialize_options(ChunkingOptions())
    del stored["sibling_merge_floor"]
    assert _deserialize_options(stored).sibling_merge_floor == 0
