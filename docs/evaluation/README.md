# Retrieval evaluation — how to label a question set and run the harness

The harness answers one question: **did a retrieval change help?** It answers it
as a number you can put in the thesis and reproduce later.

Authority for everything here is [ADR-023](../adr/023-retrieval-quality-evaluation.md)
(as amended 2026-09-28) and [ADR-033](../adr/033-hybrid-retrieval-and-passage-selection.md).
Tickets: IR-133 "G · Retrieval eval harness (recall@10)" and IR-394 "D · The
eval harness measures what the model received, with labels that survive
re-chunking".

## What it measures

Two numbers per run, never one:

| Measure | Over what | What it catches |
|---|---|---|
| **recall@10** | The ten passages retrieval returned | Whether the right passage was found at all |
| **final-set recall** | The passages actually handed to the model | Whether it survived the disclosure gate, the source cap, and (once they exist) the relevance cut-off and token budget |

Both are the fraction of *labelled* passages that were found, averaged over
questions. A micro figure — labels found over labels total — is printed beside
each, because the two diverging tells you the misses are concentrated in a few
questions.

Recall, not precision: retrieval's job is to not miss the right passage, and
reranking's job is to sort out the noise afterwards. A miss is fatal; a junk
passage at rank 7 is cheap.

## The label format

Each expected result is **a record, a page and a short quote**:

```json
{
  "id": "q07",
  "question": "how does the sampling loop decide which examples to label?",
  "expected": [
    {
      "record": "Online Adaptive Kernel Mixing for Gaussian Process Decision Making",
      "page": 4,
      "quote": "selects the instance whose posterior variance is largest"
    }
  ]
}
```

- `record` is the **title** (what `load_corpus` names a record after) or a
  numeric id. Use the title: ids differ between databases, titles travel.
- `quote` is **verbatim** text from the passage, 4–30 words. A passage counts as
  a hit when it contains the quote, after both sides are lowercased and their
  whitespace collapsed.
- `page` is recorded and checked, but **never scored** — a chunk can span a page
  boundary. A page that disagrees is reported so you can correct the label.

**Why not a chunk id.** Re-chunking replaces every chunk id in a record
(`apps/ai/repositories.py` swaps the whole `ChunkSet`), so chunk-id labels would
be destroyed by the very comparison the harness exists to make — "did raising
`AI_CHUNK_MAX_TOKENS` help?". A quote is found in whichever chunk ends up
holding it. There is a test for exactly this:
`apps/ai/evaluation/tests/test_labels.py::test_a_label_survives_rechunking_at_any_ceiling`.

## How to label — the procedure

Extend [`proxy_starter.json`](proxy_starter.json). It already holds labelled
questions (each tagged with a `kind`: `mechanism`, `exact-term`, `near-duplicate`
or `cross-paper`); add new ones after the last id. A question whose paper has no
vectors yet cannot be measured, so check `backfill_embeddings --dry-run` first.

For each question:

1. Open the paper. Find a passage that makes a **specific** claim.
2. Write the question **a researcher would ask to find that claim** — in their
   words, not the paper's.
3. Copy 4–30 words verbatim out of the passage, and note the page.
4. Run the dry run. It costs nothing and calls no vendor:

```bash
cd backend
python manage.py eval_retrieval --questions ../docs/evaluation/proxy_starter.json \
    --dry-run --drop-incomplete
```

It tells you, per label, whether the record resolves and whether the quote
actually appears in a chunk of it. A quote that Docling extracted differently,
or one that straddles a chunk boundary, is caught here rather than scoring zero
in a paid run. `manage.py inspect_chunks <record_id>` shows you the chunk text
to copy from.

### Two traps that invalidate the numbers

- **Never write the question after seeing what retrieval returned.** That is
  writing the exam from the answer key, and it pushes recall toward 1.0 for no
  reason. Write questions from the PDF only.
- **Do not reuse the paper's own phrasing in the question.** Lexical overlap
  measures keyword matching, not semantic retrieval. Paraphrase on purpose:
  "how do they pick which examples to label", not "how does uncertainty
  sampling work".

Aim for 20–25 questions to start. ADR-023's target is fifty, and that target is
for the **real CIT-U corpus** (IR-278), not this one.

## Running it

```bash
cd backend
# Both configurations, which is the comparison IR-133 asks for:
python manage.py eval_retrieval --questions ../docs/evaluation/proxy_starter.json \
    --user staff@cit.edu

# One configuration, a different k, no results file:
python manage.py eval_retrieval --questions ... --user staff@cit.edu \
    --reranking on -k 20 --no-write
```

`--user` is required and is part of what is measured: retrieval filters by
`Record.objects.visible_to(user)`, so a run reports what *that* user can
retrieve. An anonymous user can read nothing and would score zero on a working
stack. `manage.py seed_demo` creates `<role>@cit.edu` logins.

Every run writes `docs/evaluation/runs/<timestamp>-<set>.json` holding its
configuration, both measures, per-question outcomes and provenance (git commit,
embedding space, the embedder and reranker actually used). That file is how a
figure in the thesis gets traced back to the run that produced it.

### Rules that come from the ADR, not from taste

- **Manual only, never CI.** A run embeds every question and reranks every
  candidate set. On a push trigger, the evaluation budget becomes a function of
  commit frequency.
- **One change at a time against a fixed baseline.** No combination matrix: with
  six switches that is a large grid of paid runs whose interactions a 20-paper
  corpus cannot resolve, and the output would be an unattributable "the stack
  got better".
- **Proxy numbers decide switches, never findings.** A number from
  `docs/corpus/` is an engineering gate. It is not evidence about CIT-U research
  and does not become so by having been acted on.
- **Read the delta against the question count.** With 20 questions, one question
  is 0.05 of the score. The comparison table prints that threshold; a delta
  below it moved nothing.

## Pointing the harness at the real eval set

Nothing in the code knows about `proxy_starter.json`. When the real
fifty-question set exists:

1. Put it at `docs/evaluation/citu_fifty.json`, same format, with
   `"tier": "corpus"` and `"corpus"` naming the real corpus.
2. Pass `--questions ../docs/evaluation/citu_fifty.json`. That is the whole
   change.
3. Results from it are **tier 2 — thesis evidence** (ADR-023). Keep them in
   `runs/` alongside the proxy runs; the `tier` field in each results file is
   what distinguishes them, so never copy a proxy number into a tier-2 table.

## What blocks a real number today

- **The corpus has no Voyage vectors.** Every vector observed so far came from
  the deterministic fake. Indexing is `manage.py backfill_embeddings` (measured
  on the dev database: 26 records, 1,236 chunks, ~381,073 tokens).
- **The disclosure gate refuses every record** until `Record` carries an embargo
  field (IR-250), so the final set is empty and final-set recall is 0. Use
  `AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT` / `manage.py
  index_with_disclosure_bypass` (IR-317, development only) meanwhile. The
  command warns when it sees this.
- **Passage selection does not exist yet** (IR-397), so final-set recall today
  differs from recall@10 only by the gate and the source cap. The number is
  reported anyway: the seam it measures is `apps/ai/answers/selection.py`, and
  IR-396/IR-397 land inside it.
