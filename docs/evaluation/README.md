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

## What a question needs, and what should happen (IR-463)

Three optional fields say whether a question needs the corpus at all and what
the right outcome is. They are **two fields, not one**, because an empty
`expected` list cannot carry two meanings: a general-knowledge question also has
no expected passage, and it must be *answered*, not refused.

| Field | Values | Meaning |
|---|---|---|
| `evidence_required` | `none` / `corpus` / `corpus_multi` | Does answering need the corpus at all? |
| `expected_outcome` | `answer` / `clarify` / `decline-no-evidence` / `decline-restricted` | What the reader should get |
| `institutional` | `true` / `false` | A claim about CIT-U or the repository. Reported separately: a miss here is the dangerous direction (ADR-027 §4) |

- `evidence_required` and `expected_outcome` are declared **together or not at
  all**. A set that declares neither loads exactly as before.
- **An empty `expected: []` is deliberate only when the question declares those
  two fields.** Without them it is an *unlabelled* question: refused by default,
  and skipped (and named) by `--drop-incomplete`. A deliberately empty question
  is never skipped.
- A contradiction is refused: `evidence_required: none` or
  `decline-no-evidence` with expected passages, or `corpus` + `answer` with none.
- A question with no expected passage has nothing to recall, so the retrieval
  harness does not run it and it does not enter either recall average; the run
  reports how many it left out (`without_passages`). Scoring a refusal is
  IR-454's measure, and the model-facing command is IR-464's. **This harness
  still calls no model.**
- `--dry-run` validates every field (an invalid value is refused at load), calls
  no vendor and costs nothing.

### `kind`

Every question in `proxy_starter.json` carries a `kind`, and the loader now
reads it so a report can be grouped by it:

| `kind` | What it probes |
|---|---|
| `mechanism` | A paraphrased question about how something works (the default) |
| `exact-term` | A specific term or number |
| `near-duplicate` | Telling two near-identical papers apart |
| `cross-paper` | An answer spread over several papers |
| `general-knowledge` | Answerable without the corpus (`none` / `answer`) |
| `off-corpus-research` | Research the corpus does not hold (`corpus` / `decline-no-evidence`) |
| `ambiguous` | Too vague to answer (`none` / `clarify`) |
| `follow-up-after-direct` | A follow-up to an answer that used no retrieval |
| `follow-up-after-grounded` | A follow-up to a cited answer; reuses its parent's passage |

### `resolved_question` (IR-464)

The two follow-up kinds mean nothing on their own: "and how does that paper
define it?" has no subject until the preceding turn fills it in. `resolved_question`
carries **what a resolver would have rewritten the question into** — optional, a
non-empty string, and validated at load.

It exists because the evidence detector runs on the raw text **and** on the
Resolved text and combines the two by OR (ADR-035 §5): a rewrite must never be
able to weaken an evidence requirement. Both directions show up in the proxy
set, which is the point of labelling them:

| Question | Raw lane | Resolved lane |
|---|---|---|
| `q61` "what exactly did they say about that?" | misses — no repository vocabulary at all | catches it, on "authors" |
| `q62` "and how does that paper define it?" | catches it, on "paper" | misses — the rewrite names the title instead |

Neither lane alone is right, and the OR of them is. **The two `ambiguous`
questions deliberately carry no Resolved form**: a question too vague to answer
is too vague to resolve, which is why its `expected_outcome` is `clarify`.

A set that supplies no `resolved_question` at all still measures the raw lane;
the Resolved lane simply reports that no question carries one.

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

One of ADR-033 §5's switches, against the same baseline:

```bash
# What is switchable, and which of the six are built:
python manage.py eval_retrieval --list-techniques

# Baseline first, then the candidate. Same commit, same set, same --user.
python manage.py eval_retrieval --questions ../docs/evaluation/proxy_starter.json     --user iris-student@cit.edu
python manage.py eval_retrieval --questions ../docs/evaluation/proxy_starter.json     --user iris-student@cit.edu     --technique keyword_retrieval=on --technique fusion=on
```

Every run records all six switches at the values it used, so two results files
are comparable. Asking for a switch whose setting does not exist yet is refused
rather than recorded as measured. Hybrid retrieval is two settings for one
technique, which is why the pair above moves together and why the command warns
that two switches moved — see ADR-023's IR-394 divergence note.

`--user` is required and is part of what is measured: retrieval filters by
`Record.objects.visible_to(user)`, so a run reports what *that* user can
retrieve. An anonymous user can read nothing and would score zero on a working
stack. `manage.py seed_demo` creates `<role>@cit.edu` logins.

Every run writes `docs/evaluation/runs/<timestamp>-<set>.json` holding its
configuration, both measures, per-question outcomes and provenance (git commit,
embedding space, the embedder and reranker actually used, and the question
set's SHA-256 as well as its path — a set is re-labelled while it is human work
in progress, so the path alone would reproduce the wrong run). That file is how
a figure in the thesis gets traced back to the run that produced it.

The command usually runs in the backend container, which has no git, so pass
the commit from the host or the results file records `unknown`:

```bash
docker compose exec -e IRIS_GIT_COMMIT="$(git describe --always --dirty)" backend     python manage.py eval_retrieval --questions ... --user iris-student@cit.edu
```

`--dirty` marks a run made from a modified tree, so it cannot pass for the
commit it started from. Run from the host with no variable set, the command asks
git itself.

## The technique switches

ADR-033 §5 puts six techniques behind six settings, each defaulting to today's
behaviour, and a default moves only on a run of this harness. The harness
therefore owns the configuration surface, and **every run records all six** at
the values it used — a results file that omits a switch cannot be compared with
a later one that moved it.

```bash
# What the switches are, and which of them exist in this deployment yet:
python manage.py eval_retrieval --list-techniques

# Move one for a run (once its ticket has landed it):
python manage.py eval_retrieval --questions ... --user iris-student@cit.edu     --technique fusion=on
```

| Technique | Setting | Lands with |
|---|---|---|
| `fusion` | `AI_RETRIEVAL_FUSION_ENABLED` | IR-395 |
| `keyword_retrieval` | `AI_KEYWORD_RETRIEVAL_ENABLED` | IR-395 |
| `relevance_cut_off` | `AI_RELEVANCE_MIN_SCORE` | IR-396 |
| `per_paper_cap` | `AI_MAX_PASSAGES_PER_RECORD` | IR-397 |
| `neighbour_joining` | `AI_JOIN_ADJACENT_PASSAGES` | IR-397 |
| `token_budget` | `AI_PASSAGE_TOKEN_BUDGET` | IR-397 |

**None of those settings exists yet.** A technique counts as built when its
setting is really present in `django.conf.settings`, never because the registry
in `apps/ai/evaluation/techniques.py` names it — so asking for one meanwhile is
**refused**, with the ticket that lands it. That refusal is the point of the
registry: a run measuring the baseline, under a results file claiming to have
measured fusion, is worse than no run at all. When a ticket names its setting
differently, one line in that file changes.

Moving two switches in one run is allowed and warned about loudly, because
"one change at a time" is a rule about runs that code cannot enforce — fusion
without keyword retrieval is one technique in two settings. That reading of
ADR-023 is written down as a divergence note in
[ADR-023](../adr/023-retrieval-quality-evaluation.md) and **awaits a human
decision**; the discipline holds by convention meanwhile.

A moved switch is spelled the same way in the results file as on the command
line (`fusion=on`, not `fusion=True`), so a configuration can be copied
straight out of a run file back into a command.

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

## Measuring the evidence detector (IR-464)

A **separate instrument and a separate command**, and the distinction is load
bearing (ADR-035 §10): this one supplies every accuracy number about the
evidence decision, and IR-466's production shadowing supplies operational
figures only and carries no ground truth, because nobody labelled real reader
questions. Reading an accuracy number off the shadow pilot is a category error.

```bash
cd backend
python manage.py eval_evidence --questions ../docs/evaluation/proxy_starter.json
```

It **costs nothing**: no model call, no vendor call, no database read, and no
`--user`, because nothing here is filtered by visibility. It creates no
`Conversation`, no `Turn` and no shadow row, and in IR-464 it calls no model at
all — the results file carries a `model` key that is explicitly `null` so it can
be compared with IR-465's, which will have one.

What it reports, per lane (`raw`, `resolved`, `combined`):

- **Over-fires and misses per reason code.** An over-fire is a rule firing on a
  question annotated `evidence_required: none`; it costs one retrieval.
- **`silent on required` per rule, which is not a detector miss.**
  `sourcing_demand` not firing on a question about a paper is the rule working.
  Only the combined lane can miss, and that column says which rule would have
  caught it.
- **Coverage** — how many questions in the set carry an annotation at all, and
  how many carry a Resolved form.
- **Institutional questions separately**, because a miss there is the dangerous
  direction (ADR-027 §4, dormant rather than satisfied per ADR-035 §9).
- **Categories with fewer than `--min-examples` labelled questions as
  INCONCLUSIVE.** With two questions in a category, one question is fifty
  points, and the figure is not a measurement.

Provenance in every results file: the git commit, the question-set path and
SHA-256, `AI_EVIDENCE_DECISION`, and a **digest of the complete active rule
set** — all five rules including the generic English terms, so changing one word
changes the digest. Written to `runs/<stamp>-evidence-<set>.json`.

**Nothing consumes a verdict.** The detector is not wired into the answer path:
production routing is out of ADR-035's scope (§11), and ADR-035 is Proposed, not
accepted.

### What the current proxy set can and cannot say

Run 2026-10-06 over `proxy_starter.json`: **10 of 62 questions carry an evidence
annotation.** Raw 9/10, Resolved 3/4, combined 10/10 — and **every category is
inconclusive**, because each holds two questions. The combined figure is a
demonstration that the OR rule works on ten questions, not a measurement of the
detector. Labelling more questions in each category is what turns it into one.

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
