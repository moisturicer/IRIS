# IR-1150: per-paper share for the runtime's search

**Proxy tier (ADR-023).** An engineering measurement on openly licensed arXiv
papers, never a finding about CIT-U research.

## Verdict

**On recall, the data cannot separate the share values at the agent's default
limit of 10.** Every value lands within two labels of the others (of 94). A
share mainly decides **how many papers a search shows**. At a limit of 5, a
small share (25% or 33%) **costs recall**: 5 or 6 labels. The case the share
is meant to help (questions needing several papers) **could not be measured**:
no keyword candidate list ever held both labelled papers.

**Recommendation: keep 50%** until a hybrid or multi-paper measurement exists.
It is the only value that cuts single-paper dominance (56% → 31% of searches
at limit 10) with no meaningful recall cost at either limit: one label at
limit 10, one net at limit 5. 33% is the stronger choice for paper diversity
at limit 10, but it costs 5 labels at limit 5. The owner decides; this run
changes no default.

## What ran

`scripts/eval_paper_share.py` (offline, free). For each of the 129 questions in
`docs/evaluation/proxy_starter.json` it ranks candidates **once**, the way
`ResearchTools.search` does (any query term matches, `ts_rank`, the top
`max(limit, 20)`). It then hands those same candidates and their possible
section-mates to `ai.research.selection.select` under each policy. Ranking is
the same in every arm; only selection varies.

- **Corpus:** `iris_ir1054`, trial chunk sets `g_structural`: structural chunking
  with Figure passages at 700 tokens, the strategy IR-1054 kept (ADR-067
  amendment 2026-11-15). 43 papers, 3,141 chunks, every one with a
  `section_key`. The active chunk sets there and in the dev database have no
  `section_key`, so section-mates would never fire on them.
- **Policy:** `tokens_per_passage` 700, `join` on, `section_mates` on,
  `paper_share` ∈ {0 (off), 25, 33, 50, 75, 100}. Limits 10 (the tool's
  default, a budget of 7,000 tokens) and 5 (3,500 tokens).
- **Query:** `resolved_question` when the set gives one, else the question
  text. The agent writes its own queries, so this is a stand-in.
- **Matching:** `apps.ai.evaluation.labels` (Record + quote, the harness's own
  normalization).
- **Spend:** none. No query embedding, no rerank, no model call.

Run file: [`keyword-g_structural.json`](keyword-g_structural.json), with
per-question rows for every arm.

## Results

"Searches >50% one paper" is the share of searches where one paper holds more
than half the returned tokens. "Top paper's token share" is the mean of that
fraction. Tokens are chunker tokens, section-mates included.

### Limit 10 (budget 7,000; any candidate holds 0.606 of the labels)

**Single-paper** (84 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.476 | 4.31 | 56% | 0.56 | 6737 (6985) | 4.18 |
| 25% | 0.464 | 5.74 | 8% | 0.33 | 6837 (6987) | 4.71 |
| 33% | 0.476 | 5.29 | 11% | 0.38 | 6810 (6986) | 4.62 |
| 50% | 0.464 | 4.64 | 31% | 0.47 | 6776 (6980) | 4.32 |
| 75% | 0.464 | 4.31 | 56% | 0.56 | 6737 (6984) | 4.23 |
| 100% | 0.476 | 4.31 | 56% | 0.56 | 6737 (6985) | 4.18 |

**Multi-paper: two labelled papers** (5 questions; no candidate list holds both)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.200 | 4 | 60% | 0.57 | 6540 (7002) | 3.6 |
| 25% | 0.200 | 5.4 | 20% | 0.36 | 6593 (7017) | 3.8 |
| 33% | 0.200 | 5 | 20% | 0.35 | 6554 (7002) | 3.8 |
| 50% | 0.200 | 4.4 | 60% | 0.50 | 6543 (7002) | 3.4 |
| 75% | 0.200 | 4 | 60% | 0.57 | 6540 (7002) | 3.6 |
| 100% | 0.200 | 4 | 60% | 0.57 | 6540 (7002) | 3.6 |

**"Which work…" questions** (`cross-paper` kind, 10 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.400 | 3.9 | 60% | 0.61 | 6620 (7000) | 4.1 |
| 25% | 0.400 | 5.4 | 20% | 0.39 | 6621 (6991) | 4.3 |
| 33% | 0.400 | 4.9 | 20% | 0.41 | 6574 (7000) | 4.4 |
| 50% | 0.400 | 4.3 | 50% | 0.51 | 6636 (7000) | 4.1 |
| 75% | 0.400 | 3.9 | 60% | 0.60 | 6656 (7000) | 4.1 |
| 100% | 0.400 | 3.9 | 60% | 0.61 | 6620 (7000) | 4.1 |

### Limit 5 (budget 3,500; any candidate holds 0.596 of the labels)

**Single-paper** (84 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.393 | 2.55 | 69% | 0.67 | 3247 (3472) | 1.92 |
| 25% | 0.321 | 4.13 | 17% | 0.39 | 3274 (3475) | 2.51 |
| 33% | 0.333 | 3.73 | 19% | 0.42 | 3257 (3481) | 2.29 |
| 50% | 0.381 | 3.07 | 55% | 0.53 | 3255 (3482) | 1.93 |
| 75% | 0.393 | 2.61 | 69% | 0.66 | 3234 (3472) | 2.02 |
| 100% | 0.393 | 2.55 | 69% | 0.67 | 3247 (3472) | 1.92 |

**Multi-paper and "which work…"**: recall is the same in every arm (0.100
and 0.333), and the dominance pattern matches limit 10. Full rows are in the
run file.

### Paired changes against "off" (labels gained / lost)

| Share | Limit 10 | Limit 5 |
|---|---|---|
| 25% | +2 / −3 | 0 / −6 |
| 33% | +2 / −2 | 0 / −5 |
| 50% | 0 / −1 | +1 / −2 |
| 75% | 0 / −1 | 0 / 0 |
| 100% | 0 / 0 | 0 / 0 |

Every change is on a single-paper question.

## What each value gains and costs

- **Off / 100%:** the same in every respect. Highest single-paper recall at
  limit 5. Over half of all searches are mostly one paper, so a "what do
  studies say" search shows the fewest papers.
- **75%:** almost never binds. One paper stays dominant as often as with the
  share off, and it still loses one label at limit 10 (q46). No reason to
  choose it.
- **50% (current default):** halves dominance at limit 10 (56% → 31%) and adds
  about 0.3 papers per search. Costs one label at limit 10 and one net at
  limit 5.
- **33%:** five papers per search at limit 10, with dominance down to 11%, and
  recall equal to off (+2/−2). At limit 5 it allows about one chunk per paper
  before the second pass, and loses 5 single-paper labels (−0.06).
- **25%:** the most diverse, and it loses recall at both limits. It is the
  worst at limit 5 (−6 labels, −0.07).
- **Tokens:** no value changes cost. Every arm fills the budget to within
  about 2% (mean about 6.8k of 7k at limit 10). The share moves the budget
  between papers; it does not save any. Section-mates fill whatever room the
  share frees.

## Limits of this measurement

1. **The multi-paper case is not measured.** No question's keyword candidates
   contain both labelled papers (the per-question ceiling is ≤ 1 of 2). The
   share can only redistribute candidates, so it cannot help here, and it is
   not tested here. Measuring it needs better candidates (hybrid search) or
   more multi-paper labels. The set has 5 two-paper questions and no labelled
   "what do studies say" question.
2. **Keyword candidates only.** The agent's pinned `search` is IR-886's hybrid,
   which fuses keyword, paper-first and flat vector candidates. Vector
   candidates spread across papers differently, so the share may matter more
   or less there. A hybrid arm needs 129 query embeddings (about 3k tokens on
   `voyage-context-4`, well under US$0.01). The `g_structural` chunk vectors
   already exist in `iris_ir1054`. Not run: it needs the owner's approval.
3. **Questions stand in for the agent's queries.** Long questions OR-ed term by
   term rank more loosely than the agent's short queries. The ceiling is
   about 0.60, so roughly 40% of labels are out of reach of any selection.
   ADR-067's caveat applies too: 36 of 94 labels don't match Unstructured's
   text as-is.
4. **Small differences.** One label is about 0.011 of recall. Every difference
   at limit 10 is 2 labels or fewer, inside ADR-033's own noise.

## Reproduce

```bash
cd backend
python ../scripts/eval_paper_share.py --db iris_ir1054 --variant g_structural --out ../docs/evaluation/runs/2026-11-16-ir1150-paper-share/keyword-g_structural.json
```
