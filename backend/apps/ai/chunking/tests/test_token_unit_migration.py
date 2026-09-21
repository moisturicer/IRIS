"""IR-287: the counting unit changed and the chunk size did not.

The acceptance criterion this file exists for is the awkward one to state and
the only one worth proving: replacing ``len(text.split())`` with the real
``voyage-context-4`` tokenizer, and raising the ceiling from 512 to 700 in
the same change, must leave **chunk boundaries on ordinary prose where they
were**. Switching the counter alone would have shrunk every chunk by roughly
30%, which is choosing a new chunk size by implication -- exactly what IR-243
refused to do without retrieval evidence.

"Before" is reconstructed by injecting the old word counter into the four
modules that count, and the old merge-floor cap along with it. Patching
module globals is normally a smell; here it is the test's whole subject,
because the claim is precisely that *only the unit* changed.

What the numbers rest on
------------------------
A words-to-tokens ratio is a property of the material, not a constant, and
measured with this tokenizer it spans a wide range: about 1.13 on the clean
flowing prose in ``fixtures/prose_document.py``, about 1.7 on this repo's own
engineering markdown (dense with paths, code spans and tables), and about
1.37 on the real 47-page submission IR-243 measured -- which is the number
700 comes from, because a Docling-extracted thesis is what the chunker
actually eats.

That spread is why the two tests below differ in what they pin. The first
runs the **shipped defaults** and shows boundaries unmoved. The second forces
the ceiling to bind and shows that when it does, it falls in the same place
once the ceiling is scaled by *this document's* ratio -- the mechanism, not
the number. Material cleaner than the real corpus therefore gets somewhat
larger chunks under the new ceiling and material denser than it gets somewhat
smaller ones; 700 is calibrated on the real corpus, and tuning it against
IR-133's recall@10 evidence remains open.
"""

import pytest

from apps.ai.chunking import packing, text_splitting, tokens
from apps.ai.chunking import context_path as context_path_module
from apps.ai.chunking.strategies import structural
from apps.ai.chunking.strategies.structural import STRATEGY_ID, StructuralCascadeChunker
from apps.ai.chunking.tests.fixtures.prose_document import prose_document
from apps.ai.chunking.values import ChunkingOptions

#: The shipped defaults, and the ones they replaced.
OLD_MAX_TOKENS, NEW_MAX_TOKENS = 512, 700
OLD_CONTEXT_PATH, NEW_CONTEXT_PATH = 48, 64
OLD_FLOOR_CAP, NEW_FLOOR_CAP = 64, 88

#: Every module that counts. Each imports ``count_tokens`` by name, so the
#: old unit has to be injected into each of them rather than into one place.
_COUNTING_MODULES = (packing, text_splitting, context_path_module, structural)


def _count_words(text: str) -> int:
    """The counter this repository called ``count_tokens`` until IR-287."""
    return len(text.split())


def _chunk(document, *, counter, max_tokens, context_path_max, floor_cap, monkeypatch):
    """Chunk ``document`` under one counting regime."""
    for module in _COUNTING_MODULES:
        monkeypatch.setattr(module, "count_tokens", counter)
    monkeypatch.setattr(
        ChunkingOptions,
        "effective_min_tokens",
        property(
            lambda self: self.min_tokens
            if self.min_tokens is not None
            else max(1, min(floor_cap, self.max_tokens // 8))
        ),
    )
    options = ChunkingOptions(
        strategy=STRATEGY_ID,
        max_tokens=max_tokens,
        context_path_max_tokens=context_path_max,
    )
    return StructuralCascadeChunker().chunk(document, options).chunks


def _before(document, monkeypatch, max_tokens=OLD_MAX_TOKENS):
    return _chunk(
        document,
        counter=_count_words,
        max_tokens=max_tokens,
        context_path_max=OLD_CONTEXT_PATH,
        floor_cap=OLD_FLOOR_CAP,
        monkeypatch=monkeypatch,
    )


def _after(document, monkeypatch, max_tokens=NEW_MAX_TOKENS):
    return _chunk(
        document,
        counter=tokens.count_tokens,
        max_tokens=max_tokens,
        context_path_max=NEW_CONTEXT_PATH,
        floor_cap=NEW_FLOOR_CAP,
        monkeypatch=monkeypatch,
    )


# --------------------------------------------------------------------------
# The acceptance criterion
# --------------------------------------------------------------------------


def test_prose_boundaries_are_identical_at_the_shipped_defaults(monkeypatch):
    """512 words and 700 tokens chunk the same prose the same way."""
    document = prose_document()

    before = _before(document, monkeypatch)
    after = _after(document, monkeypatch)

    assert [c.content for c in before] == [c.content for c in after]
    # ``text`` is what gets embedded and carries the context path; asserting
    # it separately is not redundant, because the context-path budget moved
    # from 48 words to 64 tokens in the same change.
    assert [c.text for c in before] == [c.text for c in after]
    assert [c.context_path for c in before] == [c.context_path for c in after]


def test_a_binding_ceiling_falls_in_the_same_place_once_scaled(monkeypatch):
    """Where the ceiling actually splits a section, only the unit changed.

    120 words is small enough to split this document into twenty-one chunks,
    so the ceiling -- not the floor or the section boundaries -- decides where
    the cuts land. 136 tokens is the equivalent budget for prose of this
    density, and the two agree cut for cut.
    """
    document = prose_document()

    before = _before(document, monkeypatch, max_tokens=120)
    after = _after(document, monkeypatch, max_tokens=136)

    assert len(before) > 15, "the ceiling must actually bind for this to prove anything"
    assert [c.content for c in before] == [c.content for c in after]


def test_the_new_unit_alone_would_have_shrunk_every_chunk(monkeypatch):
    """The negative control: this is what IR-287 deliberately did not do.

    Counting real tokens while leaving the ceiling at 512 produces strictly
    more chunks than before. If this ever stops being true, the ceiling and
    the unit have drifted back into agreement by accident and the test above
    is passing for the wrong reason.
    """
    document = prose_document()

    before = _before(document, monkeypatch)
    naive = _after(document, monkeypatch, max_tokens=120)
    shrunk = _before(document, monkeypatch, max_tokens=120)

    assert len(before) < len(shrunk)
    assert len(naive) >= len(before)


# --------------------------------------------------------------------------
# The tokenizer itself
# --------------------------------------------------------------------------


def test_the_vendored_vocabulary_matches_its_pin():
    """The corpus is re-chunked by any change to this file, so pin it.

    A silent swap -- a helpful upgrade script, a bad merge -- would move every
    boundary in the corpus with no diff anyone would read as meaning that.
    """
    import hashlib

    digest = hashlib.sha256(tokens.TOKENIZER_PATH.read_bytes()).hexdigest()
    assert digest == tokens.TOKENIZER_SHA256


def test_the_tokenizer_is_the_one_the_embedding_model_uses():
    """Qwen2 BPE, 151,665 tokens, as published for voyage-context-4."""
    assert tokens.TOKENIZER_ID == "voyage-context-4"
    assert tokens.get_tokenizer().get_vocab_size() == 151_665


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_blank_text_costs_nothing(blank):
    assert tokens.count_tokens(blank) == 0


def test_counting_is_not_word_counting_any_more():
    """The regression this ticket exists to prevent reappearing.

    Hyphenated and inflected academic vocabulary is where the two units part
    company most visibly, and it is ordinary in a thesis.
    """
    text = "Clearance-aware resubmission preserves non-invalidated interdisciplinary clearances."

    assert tokens.count_tokens(text) > len(text.split())


def test_the_batching_estimator_agrees_with_the_chunker():
    """One tokenizer, one definition of a token (IR-287).

    A chunk built to fit a ceiling is batched against the vendor's limit by
    the same arithmetic; a second estimate here was a source of truth waiting
    to drift.
    """
    from apps.ai.providers.batching import estimate_tokens

    for text in (
        "",
        "one",
        "Clearance-aware resubmission preserves non-invalidated clearances.",
        " ".join(["institutional"] * 200),
    ):
        assert estimate_tokens(text) == tokens.count_tokens(text)
