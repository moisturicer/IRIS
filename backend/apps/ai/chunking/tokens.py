"""Token counting — the real ``voyage-context-4`` tokenizer (IR-287).

**The unit is a token and "700" means 700 tokens.** It did not always. Until
IR-287 this module counted whitespace-delimited *words* and called them
tokens, so ``AI_CHUNK_MAX_TOKENS=512`` produced chunks of roughly 700 real
BPE tokens -- about 44% more than the number read as (IR-243). That gap was
invisible to every caller and was about to get worse: once formulas are OCR'd
to LaTeX (ADR-025), a 512-*word* chunk of prose and a 512-*word* chunk of
LaTeX hold wildly different amounts of real content, and word counting cannot
see the difference.

This module now counts with the tokenizer the embedding model itself uses,
and the ceiling was raised to 700 in the same change so that **chunk
boundaries on ordinary prose did not move**. IR-287 changed the unit, not the
size: switching the counter while leaving the ceiling at 512 would have
shrunk every chunk by roughly 30%, which is choosing a new chunk size by
implication -- exactly what IR-243 refused to do without retrieval evidence.
Tuning the number against IR-133's recall@10 evidence is still open, and when
someone does it the number will mean what it says.

Pinning
-------
``voyage-context-4`` is a Qwen2 BPE tokenizer with a 151,665-token vocabulary.
The vocabulary is **vendored**, not downloaded: ``tokenizer/voyage-context-4.json``
is a byte-for-byte copy of ``tokenizer.json`` from the model repository at
revision ``8ca9460``, and :data:`TOKENIZER_SHA256` pins its content. A test
asserts that hash, so replacing the file is a deliberate act with a visible
diff rather than a silent re-chunking of the corpus.

``tokenizers`` (Hugging Face's runtime) is pinned in ``requirements/base.txt``.
The domain still carries **no vendor SDK**: ``tokenizers`` is a general BPE
engine and the JSON is published data, not ``voyageai``. What the old
docstring defended -- determinism across processes and versions -- is
preserved by pinning both halves, and is stronger than before: a whitespace
count agreed with nothing, while this count agrees with what Voyage bills and
what the context window measures.

The one purity cost is honest: the first call reads a file from disk. It is
read once per process, from a path next to this module, and never over a
network.
"""

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tokenizers import Tokenizer

#: The vendored vocabulary. Lives beside this module so that "the tokenizer
#: the chunker uses" is answerable by looking, not by tracing a setting.
TOKENIZER_PATH = Path(__file__).parent / "tokenizer" / "voyage-context-4.json"

#: Content pin for :data:`TOKENIZER_PATH` -- HuggingFace ``voyageai/voyage-context-4``
#: at revision ``8ca946072a18e398cd61f2ad0243b56d0350b1db``.
TOKENIZER_SHA256 = "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"

#: Name of the model whose tokenizer this is, for anything that reports it.
TOKENIZER_ID = "voyage-context-4"


@lru_cache(maxsize=1)
def get_tokenizer() -> "Tokenizer":
    """The loaded tokenizer, once per process.

    Imported lazily so that importing the chunking domain -- which several
    pure tests and ``manage.py`` do -- does not pay a 7 MB vocabulary load.
    """
    from tokenizers import Tokenizer

    return Tokenizer.from_file(str(TOKENIZER_PATH))


@lru_cache(maxsize=2048)
def count_tokens(text: str) -> int:
    """Count ``text`` in ``voyage-context-4`` tokens.

    Special tokens are excluded: this counts the text's own cost, which is
    what a chunk ceiling and a batch budget are both about.

    Memoized for one specific repetition and no other: the cascade asks
    ``_fits`` about a string and then the emitting stage counts that same
    string again. It does **not** absorb the packing loops, which count a
    *growing* candidate and so miss on every iteration by construction --
    that cost is real and ``text_splitting.split_into_token_groups``
    measures it.

    The cache is sound because this is a pure function of ``text``. It is
    keyed on the text alone, so it would go stale if a process swapped
    tokenizers mid-run; nothing does, and the tests that vary the counter
    replace this function rather than the vocabulary under it.
    """
    if not text.strip():
        return 0
    return len(get_tokenizer().encode(text, add_special_tokens=False).ids)
