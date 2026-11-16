# IR-1147: short structural sections merged with a sibling

**Proxy tier (ADR-023).** These are openly licensed arXiv papers in `iris_ir1054` (43 papers with Unstructured reads). They are never a finding about CIT-U research.

**Question.** Does letting a short structural passage merge with a neighbouring section under the same parent heading recover the context that the `fixed-window` baseline won on in IR-1054, without losing what headings give?

**Decision rule, fixed before the run.** Adopt the option as the default only if main-set reranked final-set recall rises by at least 0.01, **and** neither the one-paper slice nor the Figure set falls by more than 0.01.

## Setup

- **Baseline:** `g_hybrid`, which is `unstructured:structural-markdown-v1:figure_passages=true,index_formulas=true` (IR-1054's choice).
- **Arms:** `h_sib150`, `h_sib300`, `h_sib450` and `h_sib600`: the same spec plus `sibling_merge_floor=N`. Several floors were tried at the owner's request, so the best floor's gain is optimistic.
- **Sets:** `proxy_starter` (main, 89 scored), `proxy_record_scoped` (one-paper slice, 37) and `figure_reranker_ir1125` (Figure set, 29).
- **Measure:** final-set recall with Voyage reranking (`AI_RERANKER_READS=fallback`), as `admin@cit.edu`. The run files also hold the no-reranking runs.
- **Exact search.** The runs used exact search: `PGOPTIONS="-c enable_indexscan=off"`, for this session only. Trial sets share one HNSW index, and this copy holds about 20 of them with near-identical vectors. With `ef_search` at most 1,000, the first pass returned fewer than 10 passages for some questions in `g_hybrid` and the lower floors (main set 0.449, Figure set 0.690). Those files are in `hnsw-starved/` and are not used. Under exact search `g_hybrid` reproduces IR-1054's numbers (0.551 / 0.649 / 0.931).
- **Spend:** Voyage only. Building the four trial sets embedded 151 new passages (about 78k tokens). The two passes each embedded every question and reranked every candidate set. Model keys were blanked for the runs, so no LLM or OpenRouter call was possible.

`python compare.py` (run in this directory) prints the tables below.

## Results (final-set recall, reranked)

| Floor | Main set | One-paper slice | Figure set |
|---|---|---|---|
| off (`g_hybrid`) | 0.551 | 0.649 | 0.931 |
| 150 | 0.539 | 0.649 | 0.931 |
| 300 | 0.556 | 0.649 | 0.931 |
| 450 | 0.567 | 0.649 | 0.931 |
| 600 | 0.567 | 0.649 | 0.931 |

Paired against `g_hybrid` on the main set (two-sided exact sign test):

| Floor | Won | Lost | p |
|---|---|---|---|
| 150 | none | q03 | 1.000 |
| 300 | q25, q34 | q03 | 1.000 |
| 450 | q25, q34, q100 | q03 | 0.625 |
| 600 | q25, q34, q100 | q03 | 0.625 |

Neither the slice nor the Figure set changes for any floor.

## Outcome

Floor 450 meets the rule. Floor 600 gives the same result, so the smaller floor was chosen. The gain is not statistically significant. Of the baseline's seven wins in IR-1054, three are recovered (q25, q34, q100), and q08, q38, q101 and q102 are not. `AI_CHUNK_SIBLING_MERGE_FLOOR` now defaults to 450 (ADR-067's IR-1147 amendment). Existing chunk sets change only after a re-chunk.

The trial sets `h_sib150` to `h_sib600` remain in `iris_ir1054`. `cleanup_trial_chunk_sets` removes them.
