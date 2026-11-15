"""Section-aligned embedding windows, wired into indexing and trials (IR-1056)."""

import pytest

from apps.ai.chunking.document import DocumentElement
from apps.ai.indexing import active_chunks, embed_active_chunk_set
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.providers import batching
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.tests.test_trial_chunk_sets import indexed_paper
from apps.ai.trials import VariantError, build_trial, chunking_provenance, parse_variant, plan_trial


def _paragraph(tag: str, words: int) -> str:
    return " ".join(f"{tag}{i}" for i in range(words)) + "."


def _long_paper_elements():
    # Section A is one chunk; section B is long enough to become two.
    return (
        DocumentElement(kind="heading", text="1 Background", level=1, page=1),
        DocumentElement(kind="paragraph", text=_paragraph("alpha", 120), page=1),
        DocumentElement(kind="heading", text="2 Results", level=1, page=2),
        DocumentElement(kind="paragraph", text=_paragraph("beta", 200), page=2),
        DocumentElement(kind="paragraph", text=_paragraph("gamma", 200), page=2),
    )


class Recording(DeterministicEmbeddingProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.documents: list[list[str]] = []
        self.chunks_sent = 0

    def embed_document_chunks(self, documents):
        documents = [list(d) for d in documents]
        self.documents += documents
        self.chunks_sent += sum(len(d) for d in documents)
        return super().embed_document_chunks(documents)


@pytest.fixture
def recording(embedder):
    return Recording(dimensions=embedder.dimensions)


@pytest.fixture
def paper(embedder, monkeypatch):
    record = indexed_paper("A long monograph", embedder, elements=_long_paper_elements())
    chunks = list(active_chunks(record.pk).order_by("sequence"))
    tops = [tuple(c.section_key or ())[-1] for c in chunks]
    assert tops[0] == "1 Background" and tops[1:] == ["2 Results"] * (len(tops) - 1) != [], tops
    costs = [batching.estimate_tokens(c.text) for c in chunks]
    # Fits the first two chunks only: the count cut splits section 2.
    monkeypatch.setattr(batching, "EMBED_WINDOW_TOKENS", costs[0] + costs[1])
    texts = [c.text for c in chunks]
    by_count = batching.window_for_embedding(texts)
    by_section = batching.window_for_embedding(
        texts, section_keys=[c.section_key for c in chunks])
    assert by_count[0] == texts[:2] and by_section[0] == texts[:1]
    return record, texts, by_count, by_section


@pytest.mark.db_required
@pytest.mark.django_db
class TestIndexing:
    def test_off_by_default_cuts_by_count(self, paper, recording, settings):
        assert settings.AI_SECTION_ALIGNED_WINDOWS is False
        record, _, by_count, _ = paper
        embed_active_chunk_set(record.pk, provider=recording, force=True)
        assert recording.documents == by_count

    def test_on_cuts_at_the_section_break(self, paper, recording, settings):
        settings.AI_SECTION_ALIGNED_WINDOWS = True
        record, _, _, by_section = paper
        outcome = embed_active_chunk_set(record.pk, provider=recording, force=True)
        assert recording.documents == by_section
        assert outcome.windows == len(by_section)


@pytest.mark.db_required
@pytest.mark.django_db
class TestTrialVariant:
    def test_windows_is_a_known_option(self):
        assert parse_variant("sw=::windows=section").windows == "section"
        with pytest.raises(VariantError, match="windows is one of"):
            parse_variant("sw=::windows=sideways")

    def test_unset_windows_follows_production(self, settings):
        assert parse_variant("x=::").windows == "count"
        settings.AI_SECTION_ALIGNED_WINDOWS = True
        assert parse_variant("x=::").windows == "section"

    def test_a_section_variant_re_embeds_a_long_paper_instead_of_reusing_count_vectors(
        self, paper, space, recording
    ):
        _, texts, _, by_section = paper
        plan = plan_trial(parse_variant("sw=::windows=section"), space_id=space.pk)
        assert plan.new_chunks == len(texts)
        outcome = build_trial(plan, provider=recording)
        assert outcome.carried == 0 and outcome.embedded == len(texts)
        assert recording.documents == by_section

    def test_a_count_variant_still_reuses_the_active_vectors(self, paper, space, recording):
        plan = plan_trial(parse_variant("cw=::windows=count"), space_id=space.pk)
        assert plan.new_chunks == 0
        build_trial(plan, provider=recording)
        assert recording.chunks_sent == 0

    def test_a_count_variant_never_reuses_a_section_variants_vectors(self, paper, space, recording):
        _, texts, _, _ = paper
        build_trial(plan_trial(parse_variant("sw=::windows=section"), space_id=space.pk),
                    provider=recording)
        # Leave only the section variant's vectors for this text.
        ChunkEmbedding.objects.filter(chunk__chunk_set__is_active=True).delete()
        plan = plan_trial(parse_variant("cw=::windows=count"), space_id=space.pk)
        assert plan.new_chunks == len(texts)

    def test_a_short_paper_reuses_vectors_whatever_the_windowing(self, space, embedder, recording):
        indexed_paper("A short note", embedder)
        plan = plan_trial(parse_variant("sw=::windows=section"), space_id=space.pk)
        assert plan.new_chunks == 0
        build_trial(plan, provider=recording)
        assert recording.chunks_sent == 0

    def test_a_rebuild_after_the_setting_flips_rewrites_the_set(
        self, paper, space, recording, settings
    ):
        build_trial(plan_trial(parse_variant("x=::"), space_id=space.pk), provider=recording)
        settings.AI_SECTION_ALIGNED_WINDOWS = True
        outcome = build_trial(plan_trial(parse_variant("x=::"), space_id=space.pk),
                              provider=recording)
        assert outcome.written == 1
        assert chunking_provenance(parse_variant("x=::"))["chunk_sets"][0]["options"]["windows"] == "section"

    def test_provenance_records_the_windowing(self, paper, space, recording):
        variant = parse_variant("sw=::windows=section")
        build_trial(plan_trial(variant, space_id=space.pk), provider=recording)
        assert chunking_provenance(variant)["chunk_sets"][0]["options"]["windows"] == "section"
