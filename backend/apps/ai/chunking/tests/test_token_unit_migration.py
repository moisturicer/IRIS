"""IR-287: the counting unit changed and the chunk size did not.

The acceptance criterion this file exists for is the awkward one to state and
the only one worth proving: replacing ``len(text.split())`` with the real
``voyage-context-4`` tokenizer, and raising the ceiling from 512 to 700 in
the same change, must leave **chunk boundaries on ordinary prose where they
were**. Switching the counter alone would have shrunk every chunk by roughly
30%, which is choosing a new chunk size by implication -- exactly what IR-243
refused to do without retrieval evidence.

"Before" is reconstructed by injecting the old word counter into the modules
that count, and the old context-path budget and merge-floor cap along with
it. Patching module globals is normally a smell; here it is the test's whole
subject, because the claim is precisely that *only the unit* changed.

What the evidence actually shows, including where it falls short
---------------------------------------------------------------
A words-to-tokens ratio is a property of the material, not a constant.
Measured with this tokenizer it spans a wide range: **1.13** on the clean
flowing prose of ``fixtures/prose_document.py``, **~1.7** on this repo's own
engineering markdown, and **~1.37** on the real 47-page Docling-extracted
submission IR-243 measured. 700 is 512 x that last figure, because a
Docling-extracted thesis is what the chunker actually eats.

The consequence is that **this fixture cannot demonstrate the shipped 700
directly**, and the tests below do not pretend otherwise. On material of this
density the ceilings that reproduce the old boundaries exactly run from 518
to 673 tokens; 700 sits just above that band. So the tests prove two separate
things and name which is which:

* the **mechanism** -- at the equivalent ceiling for a document's own density
  the boundaries are identical, cut for cut, with the ceiling binding
  (:func:`test_boundaries_are_identical_at_the_equivalent_ceiling`);
* the **daylight** -- how far the shipped 700 sits from that band on prose
  this clean, and in which direction
  (:func:`test_the_shipped_ceiling_sits_just_above_this_fixtures_band`).

Demonstrating 700 itself needs a real Docling-extracted submission, and there
is no corpus until IR-278 lands. What can be said without one is that the
change cannot have *shrunk* anything, which is the failure IR-243 forbade,
and :func:`test_the_shipped_ceiling_never_shrinks_a_chunk` asserts that.
Tuning the number against IR-133's recall@10 evidence remains open.
"""

import pytest

from apps.ai.chunking import packing, tokens
from apps.ai.chunking import context_path as context_path_module
from apps.ai.chunking.strategies import fixed_window, structural
from apps.ai.chunking.strategies.structural import STRATEGY_ID, StructuralCascadeChunker
from apps.ai.chunking.tests.fixtures.prose_document import prose_document
from apps.ai.chunking.values import ChunkingOptions

#: The shipped defaults, and the ones they replaced.
OLD_MAX_TOKENS, NEW_MAX_TOKENS = 512, 700
OLD_CONTEXT_PATH, NEW_CONTEXT_PATH = 48, 64
OLD_FLOOR_CAP, NEW_FLOOR_CAP = 64, 88

#: The ceiling that reproduces ``OLD_MAX_TOKENS`` words exactly on the
#: fixture, and the top of the band that still does. Measured, not derived:
#: 512 x the fixture's own 1.13 words-to-tokens ratio.
EQUIVALENT_CEILING, BAND_TOP = 578, 673

#: Every module that counts. Each imports ``count_tokens`` by name, so the
#: old unit has to be injected into each of them rather than into one place.
#: ``text_splitting`` is absent on purpose: it counts only through
#: ``packing.assembled_fits``, which is the point of that helper existing.
_COUNTING_MODULES = (packing, context_path_module, structural, fixed_window)


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


def _words(chunks):
    return [len(c.content.split()) for c in chunks]


# --------------------------------------------------------------------------
# The mechanism: only the unit changed
# --------------------------------------------------------------------------


def test_the_ceiling_binds_on_this_fixture(monkeypatch):
    """Guard the guard.

    Every other test here compares boundaries, and a comparison of boundaries
    that the ceiling never decided proves nothing about the ceiling. The
    fixture's Discussion section is deliberately longer than either ceiling,
    so it must come back split. If someone shortens the fixture, this fails
    first and says why, rather than leaving the rest passing vacuously.
    """
    document = prose_document()

    before = _before(document, monkeypatch)
    sections = sum(1 for e in document.elements if e.kind == "heading")

    assert len(before) > sections, "no section was split: the ceiling never bound"
    assert max(_words(before)) > OLD_MAX_TOKENS * 0.8


def test_boundaries_are_identical_at_the_equivalent_ceiling(monkeypatch):
    """512 words and 578 tokens chunk this document identically, cut for cut.

    This is the acceptance criterion's mechanism: with the ceiling binding on
    a real section, moving from words to tokens moves nothing, provided the
    number moves with the unit. 578 is 512 x this fixture's own measured
    density, not a tuned constant -- see the module docstring for why the
    shipped 700 is a different number and what it is calibrated on.
    """
    document = prose_document()

    before = _before(document, monkeypatch)
    after = _after(document, monkeypatch, max_tokens=EQUIVALENT_CEILING)

    assert [c.content for c in before] == [c.content for c in after]
    # ``text`` is what gets embedded and carries the context path; asserting
    # it separately is not redundant, because the context-path budget moved
    # from 48 words to 64 tokens in the same change.
    assert [c.text for c in before] == [c.text for c in after]
    assert [c.context_path for c in before] == [c.context_path for c in after]


def test_the_equivalence_survives_the_whole_band(monkeypatch):
    """The equivalence is a band, not a knife edge.

    If it held at exactly one ceiling it would be a coincidence of this
    document rather than a property of the change. It holds from 518 to 673
    here; the top of that band is asserted because it is the number that says
    how much room the shipped ceiling had.
    """
    document = prose_document()

    before = [c.content for c in _before(document, monkeypatch)]

    assert [c.content for c in _after(document, monkeypatch, max_tokens=BAND_TOP)] == before


# --------------------------------------------------------------------------
# The shipped ceiling: what it does, stated rather than implied
# --------------------------------------------------------------------------


def test_the_shipped_ceiling_sits_just_above_this_fixtures_band(monkeypatch):
    """700 does *not* reproduce the old boundaries on prose this clean.

    Recorded rather than hidden. 700 is calibrated on the ~1.37 density of a
    real Docling-extracted submission (IR-243); this fixture is flowing prose
    at 1.13, so the shipped ceiling is more generous here than the words it
    replaced. The direction matters and the next test pins it. If a future
    change ever makes this assertion fail, the fixture and the shipped
    ceiling have come into agreement and the module docstring is stale.
    """
    document = prose_document()

    before = [c.content for c in _before(document, monkeypatch)]
    shipped = [c.content for c in _after(document, monkeypatch)]

    assert shipped != before
    assert NEW_MAX_TOKENS > BAND_TOP


def test_the_shipped_ceiling_never_shrinks_a_chunk(monkeypatch):
    """The failure IR-243 forbade, and the one thing provable without a corpus.

    "Switching the counter and leaving the ceiling at 512 would shrink every
    chunk by roughly 30% -- which is choosing a new chunk size by
    implication." Whatever else the shipped ceiling does on material of one
    density or another, it must never come out *below* the size the word
    counter produced, because that is the silent re-chunking the ticket
    exists to avoid.
    """
    document = prose_document()

    before = _before(document, monkeypatch)
    shipped = _after(document, monkeypatch)

    assert len(shipped) <= len(before)
    assert max(_words(shipped)) >= max(_words(before))


def test_the_unit_change_alone_would_have_shrunk_every_chunk(monkeypatch):
    """The negative control: this is what IR-287 deliberately did not do.

    Counting real tokens while leaving the ceiling at 512 cuts the largest
    chunk down. If this ever stops being true, the unit and the ceiling have
    drifted back into agreement by accident, and the tests above are passing
    for a reason that has nothing to do with the change they describe.
    """
    document = prose_document()

    before = _before(document, monkeypatch)
    naive = _after(document, monkeypatch, max_tokens=OLD_MAX_TOKENS)

    assert [c.content for c in naive] != [c.content for c in before]
    assert max(_words(naive)) < max(_words(before))


# --------------------------------------------------------------------------
# The tokenizer itself
# --------------------------------------------------------------------------


def test_the_vendored_vocabulary_matches_its_pin():
    """The corpus is re-chunked by any change to this file, so pin it.

    A silent swap -- a helpful upgrade script, a bad merge, a checkout that
    rewrote the line endings -- would move every boundary in the corpus with
    no diff anyone would read as meaning that.
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


def test_token_counts_are_not_additive_across_a_join():
    """Why packing counts the assembled window instead of summing pieces.

    This is not a hypothetical: it is the case that broke the ceiling
    guarantee when the unit changed, kept here so the reason `assembled_fits`
    exists cannot be refactored away by someone who assumes addition works.
    """
    parts = ["aaab", "bbfk"]
    joined = tokens.count_tokens(" ".join(parts))

    assert joined > sum(tokens.count_tokens(p) for p in parts)


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
