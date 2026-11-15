# IR-1150: per-paper share for the runtime's search

**Proxy tier (ADR-023).** An engineering measurement on openly licensed arXiv
papers, never a finding about CIT-U research.

## Verdict

**With the candidates the agent actually gets (hybrid search), every share
below 75% loses recall, and no value gains any.** The current 50% loses 4
labels at limit 10 and 7 at limit 5, with nothing found in return. The
multi-paper case the share is meant to help is still **not measurable**: in
only one of five two-paper questions do the candidates hold both papers, and
every arm finds both there.

**Recommendation: turn the share off (`RUNS_PAPER_SHARE=0`) as the default,**
until a set with real multi-paper questions shows a gain. Off and 100% are
identical, and 75% almost never binds (−1 label). If a guard against one paper
filling a search is wanted anyway, 50% is the most it should be: it costs
about 0.05 recall on single-paper questions. The owner decides; this run
changes no default.

The keyword-only replay (free, run first) could not separate the values at
limit 10. That was a weaker test: keyword candidates come from more papers to
begin with (4.3 per search with the share off, against 3.1 for hybrid), so the
share rarely had anything to cut.

## What ran

`scripts/eval_paper_share.py`. For each of the 129 questions in
`docs/evaluation/proxy_starter.json`, it ranks candidates **once**, then hands
those same candidates and their possible section-mates to
`ai.research.selection.select` under each policy. Ranking is identical across
arms; only selection varies.

- **Candidates:**
  - **hybrid** (the main result), as IR-886's `hybrid_search` builds them:
    keyword (`ts_rank`, 20), paper-first vector (top 20 papers, 20 chunks) and
    flat vector (20), fused by rank with the runtime's own `fuse_by_rank`. No
    rerank: the runtime reranks only when `RUNS_RERANK_MODEL` is set.
  - **keyword**, as `search` builds them: the top `max(limit, 20)`.
- **Corpus:** `iris_ir1054`, trial chunk sets `g_structural`: structural chunking
  with Figure passages at 700 tokens, the strategy IR-1054 kept (ADR-067
  amendment 2026-11-15). 43 papers and 3,141 chunks, every one with a
  `section_key` and a stored `voyage-context-4` vector (space 2); paper vectors
  are from `ai_recordspaceembedding`. The active chunk sets there and in the
  dev database have no `section_key`, so section-mates would never fire on
  them.
- **Policy:** `tokens_per_passage` 700, `join` on, `section_mates` on,
  `paper_share` ∈ {0 (off), 25, 33, 50, 75, 100}. Limits 10 (the tool's
  default, a 7,000-token budget) and 5 (3,500 tokens).
- **Query:** `resolved_question` when the set gives one, else the question
  text. The agent writes its own queries, so this is a stand-in.
- **Matching:** `apps.ai.evaluation.labels`: Record + quote, with the harness's
  own normalization.
- **Spend:** 129 Voyage query embeddings, 1,754 tokens billed (well under
  US$0.01), approved by the owner on 2026-11-16. No rerank and no model call.
  The query vectors are cached outside the repository; the keyword arm is free.

Run files: [`hybrid-g_structural.json`](hybrid-g_structural.json) and
[`keyword-g_structural.json`](keyword-g_structural.json). Both have
per-question rows for every arm.

## Results (hybrid candidates)

"Searches >50% one paper" is the share of searches where one paper holds more
than half the returned tokens. "Top paper's token share" is the mean of that
fraction. Tokens are chunker tokens, section-mates included. The *ceiling* is
the share of labels held by any candidate or neighbour: what no selection can
beat.

### Paired changes against "off" (labels gained / lost, of 94)

| Share | Limit 10 | Limit 5 |
|---|---|---|
| 25% | +2 / −14 (p ≈ 0.004) | +1 / −11 (p ≈ 0.006) |
| 33% | +2 / −11 (p ≈ 0.02) | 0 / −10 (p ≈ 0.002) |
| 50% | 0 / −4 (p ≈ 0.13) | 0 / −7 (p ≈ 0.02) |
| 75% | 0 / −1 | 0 / 0 |
| 100% | 0 / 0 | 0 / 0 |

The p-values are two-sided sign tests on the questions that changed. The
losses are on single-paper questions, except two two-paper questions: q26 at
25% and 33% (limit 10) and q28 at 25% (limit 5).

### Limit 10 (budget 7,000; ceiling 0.691)

**Single-paper** (84 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | **0.607** | 3.05 | 74% | 0.70 | 6605 (6980) | 4.88 |
| 25% | 0.476 | 5.11 | 10% | 0.36 | 6810 (6984) | 5.64 |
| 33% | 0.512 | 4.48 | 16% | 0.41 | 6719 (6979) | 5.5 |
| 50% | 0.560 | 3.61 | 60% | 0.58 | 6646 (6986) | 4.99 |
| 75% | 0.595 | 3.06 | 74% | 0.69 | 6597 (6983) | 4.92 |
| 100% | 0.607 | 3.05 | 74% | 0.70 | 6605 (6980) | 4.88 |

**Two labelled papers** (5 questions; both papers reachable in only one)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.400 | 3.2 | 40% | 0.62 | 6848 (6989) | 6.6 |
| 25% | 0.300 | 4.2 | 20% | 0.44 | 6227 (6998) | 5.2 |
| 33% | 0.300 | 3.8 | 40% | 0.49 | 6333 (6989) | 5.6 |
| 50% | 0.400 | 3.4 | 40% | 0.55 | 6386 (6989) | 5.6 |
| 75% | 0.400 | 3.2 | 40% | 0.62 | 6848 (6989) | 6.6 |
| 100% | 0.400 | 3.2 | 40% | 0.62 | 6848 (6989) | 6.6 |

**"Which work…" questions** (`cross-paper` kind, 10 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | 0.533 | 2.9 | 60% | 0.70 | 6621 (6984) | 5.6 |
| 25% | 0.467 | 4.5 | 20% | 0.44 | 6407 (6983) | 5.4 |
| 33% | 0.467 | 4 | 30% | 0.48 | 6151 (6984) | 4.7 |
| 50% | 0.533 | 3.3 | 60% | 0.62 | 6183 (6984) | 4.7 |
| 75% | 0.533 | 2.9 | 60% | 0.69 | 6609 (6984) | 5.6 |
| 100% | 0.533 | 2.9 | 60% | 0.70 | 6621 (6984) | 5.6 |

**Unlabelled** (40 questions: general knowledge, off-corpus, ambiguous)

| Share | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) |
|---|---|---|---|---|
| off | 4.8 | 40% | 0.47 | 6811 (6992) |
| 25% | 5.42 | 12% | 0.32 | 6872 (6990) |
| 33% | 5.05 | 10% | 0.36 | 6820 (6988) |
| 50% | 4.83 | 22% | 0.43 | 6831 (6992) |
| 75% / 100% | 4.8 | 40% | 0.47 | 6811 (6992) |

### Limit 5 (budget 3,500; ceiling 0.681)

**Single-paper** (84 questions)

| Share | Label recall | Papers / search | Searches >50% one paper | Top paper's token share | Tokens / search (p90) | Mates |
|---|---|---|---|---|---|---|
| off | **0.488** | 2.01 | 84% | 0.77 | 3194 (3476) | 2.13 |
| 25% | 0.381 | 3.73 | 23% | 0.44 | 3286 (3476) | 3.06 |
| 33% | 0.369 | 3.24 | 34% | 0.48 | 3217 (3480) | 2.93 |
| 50% | 0.405 | 2.48 | 69% | 0.61 | 3163 (3479) | 2.26 |
| 75% | 0.488 | 2.02 | 84% | 0.76 | 3180 (3478) | 2.24 |
| 100% | 0.488 | 2.01 | 84% | 0.77 | 3194 (3476) | 2.13 |

For two-paper and "which work…" questions, recall is equal to off or lower in
every arm (0.2–0.3 and 0.40–0.47). Full rows are in the run file.

## What each value gains and costs

- **Off / 100%:** the same in every respect, and the best recall at both
  limits. Most searches are mostly one paper: 74% at limit 10, 84% at limit 5.
  With hybrid candidates, the paper that ranks first usually *is* the answer.
- **75%:** binds rarely. It loses one label at limit 10 and none at limit 5,
  and changes dominance by under a point. It costs almost nothing and does
  almost nothing.
- **50% (current default):** cuts dominance from 74% to 60% of searches at
  limit 10 (+0.6 papers per search). Costs 4 labels at limit 10 (−0.05
  single-paper recall) and 7 at limit 5 (−0.08).
- **33%:** about 4.5 papers per search, dominance 16%. Costs 11 labels at
  limit 10 and 10 at limit 5 (−0.10 to −0.12).
- **25%:** the most papers per search, and the largest cost: 14 labels at
  limit 10 (−0.13).
- **Tokens:** no value changes cost. Every arm fills the budget to within a
  few percent; the share moves tokens between papers and saves none. What it
  frees goes to section-mates and lower-ranked papers, and on this set those
  hold the evidence less often than the top paper's further passages.

## Limits of this measurement

1. **The multi-paper case is not measured.** Five two-paper questions; the
   candidates hold both papers in one (q34), and every arm finds both there.
   No question in the set is a labelled "what do studies say" question. The
   loss on single-paper questions is measured; the possible gain on
   multi-paper questions is not. A set with such questions is what could
   justify a share.
2. **Questions stand in for the agent's queries.** The agent can also search
   again, which a replay of one search cannot show: a share spends budget on
   breadth that a second, narrower search might supply more cheaply, or the
   other way round.
3. **No rerank.** A reranked list could put a different paper first; this
   replay ranks as the runtime does when `RUNS_RERANK_MODEL` is unset.
4. **Label text.** ADR-067's caveat applies: 36 of the 94 labels don't match
   Unstructured's text as-is, which caps recall near 0.69 here.

## Reproduce

```bash
cd backend
python ../scripts/eval_paper_share.py --candidates hybrid --vectors <cache.json> --out ../docs/evaluation/runs/2026-11-16-ir1150-paper-share/hybrid-g_structural.json
```

`--vectors` reuses a cache of query vectors and embeds only the missing ones
(a paid Voyage call). Without `--candidates hybrid`, the run is keyword-only
and free.
