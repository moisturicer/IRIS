# IR-851 — LlamaParse acceptance check on six proxy papers

**Run:** 2026-11-03, code at `84dfd0cb` (`main` plus IR-851's confidence change). LlamaParse v2, tier `agentic`, version `2026-09-28`, North America, Cost Optimizer on, `disable_cache` on, high-effort confidence off ([ADR-056 amendment of 2026-11-03](../../../adr/056-manuscript-extraction-moves-to-llamaparse.md)).

**Proxy tier (ADR-023).** Six openly licensed arXiv papers, one per category of `docs/corpus` ([corpus.json](corpus.json)). No number here is a finding about CIT-U research.

## Verdict

| Check | Result |
|---|---|
| Contract suite (IR-838) against LlamaParse output | **Pass, on recordings only** — run on IR-841's synthetic recordings, which were made with high-effort confidence on. Not run on output from the new request |
| Extracted through the admitted, gated path | **Pass** — `AI_PROVIDER_ADMISSION=enforce` ([spend](provider_campaign-llamaparse.txt)); each paper cleared by `load_corpus --clear-for-ai` (IR-815). IR-317's bypass was off |
| Formulas arrive as LaTeX | **Pass** — all 102 formula elements, plus inline math in `$…$` |
| Heading nesting matches the numbering | **Fail** — 27 of 113 numbered headings at the wrong level, and 11 captions or running headers returned as headings |
| No broken hyphenated words | **Pass** — none found (Docling: 4) |
| recall@10 does not drop below Docling | **Fail without reranking, by one question** (0.571 against 0.643); equal with reranking (0.929). At 14 questions, one question is within noise |
| `check_vector_index` | **Pass** — 1.000 on both indexes, both databases ([LlamaParse](check_vector_index-llamaparse.txt), [Docling](check_vector_index-docling.txt)) |
| Low-confidence and failed pages recorded | **Recorded** — 3 low-confidence pages, 0 failed pages |
| Cost per paper recorded | **Recorded** — 22.2 credits a page, about $0.36 a paper here |
| Credits per page by tier recorded | **Not recorded** — LlamaParse reports one total per job |

## How it was run

Two fresh databases on the dev stack, the same six PDFs in each: `iris_ir851_llama` (LlamaParse) and `iris_ir851_docling` (Docling-serve, CPU, today's settings). Commands and workers ran in containers from the backend image, with the IR-851 worktree mounted, so PDF intake (IR-830) applied. Each database had its own Redis databases and its own media volume.

```
load_corpus <six> --origin imported_reference --clear-for-ai   # extract, chunk, embed
backfill_abstracts                                              # record vectors embed title + abstract
backfill_embeddings
check_vector_index
eval_retrieval --questions docs/evaluation/proxy_ir851_six.json --user student@cit.edu
```

The question set is `proxy_starter.json` cut to the 15 questions whose passages are all in these six papers, less q15. q15's quote is on page 2 in LlamaParse and in the starter label, but on page 1 in a fresh Docling read, so it cannot be scored for both. 14 questions remain.

The containers had no git checkout, so the run files read `git_commit: "unknown"`. [extractions-llamaparse.txt](extractions-llamaparse.txt) ties them to this code: every stored request omits `confidence_score_effort`. The analysis scripts are committed beside this report ([analyse.py](analyse.py), [headings.py](headings.py)).

## Retrieval

[LlamaParse run](../20261103-074520-proxy_ir851_six.json) · [Docling run](../20261103-074556-proxy_ir851_six.json)

| | LlamaParse | Docling |
|---|---|---|
| recall@10, no reranking | 0.571 | 0.643 |
| recall@10, with reranking | **0.929** | **0.929** |
| final-set recall, no reranking | 0.571 | 0.571 |
| final-set recall, with reranking | **0.929** | 0.857 |

One question is 0.071. The two differ by exactly one question in each direction: q77 (a follow-up, "which two of those did they build?") is found only by Docling without reranking, and q105 and q29 reach the final set only from LlamaParse. With 14 questions that is no measured difference either way.

## Structure

[analysis-llamaparse.json](analysis-llamaparse.json) · [analysis-docling.json](analysis-docling.json)

**Formulas.** LlamaParse returned 102 formula elements. 95 carry LaTeX markup (`\frac`, `\int`, `\rangle`, `_{…}`), and the other 7 are expressions that need none (`2^q`, `q`, `P(0) = |a|^2`). It also returned 1,425 inline `$…$` spans. Docling returned 90 display formulas and essentially no inline math (one span). IR-841's recording saw an inline formula come back plain. On these papers it did not: open condition 4 is met for born-digital papers.

**Headings.** A heading's level should follow its number: "2" above "2.1" above "2.1.1", and in MeshKV "IV." above "B.". Each heading's level is compared with the level most headings of its depth have in the same paper ([headings.json](headings.json)):

| Paper | Numbered (LP / D) | LlamaParse off-level | LlamaParse nesting deepens? | False headings | Docling off-level |
|---|---|---|---|---|---|
| Accelerating massive ensembles of ODEs | 30 / 30 | 10 | No | 0 | 0 |
| Diverse Metallicities in Protoclusters | 19 / 22 | 5 | No | 0 | 0 |
| Expected Hypervolume Maximization | 25 / 25 | 5 | No | 2 | 0 |
| MeshKV (roman and lettered) | 18 / 17 | 2 | Yes | 6 | 0, but flat |
| Noise-adjusted turnover | 5 / 5 | 2 | Yes | 3 | 0 |
| State-Space-Based FIR Filtering | 16 / 16 | 3 | Yes | 0 | 0 |
| **Total** | **113 / 115** | **27** | | **11** | **0** |

Typical errors:
- "1 INTRODUCTION" one level deeper than "2 METHOD".
- "1.2 Existing GPU-accelerated ODE libraries" shallower than "1 INTRODUCTION".
- "7. ACKNOWLEDGMENTS" and MeshKV's "X. CONCLUSION" above their sibling sections.

The false headings are table captions ("TABLE I: Flit classes in MESHKV.", "Table 1: Expected turnover…"), a figure caption, and the running header "A PREPRINT". Docling's zero comes from the depth-from-numbering repair that ADR-056 decision 8 deletes, not from Docling itself. In MeshKV it gives the roman sections and their lettered subsections the same level. A wrong level puts a chunk under the wrong section in its context path.

**Hyphenation.** Candidates are a lowercase word, a hyphen, a space and a lowercase word in chunk text. LlamaParse: two, both "low- and", a real suspended hyphen. Docling: six, the same two plus four broken words in MeshKV ("ac- cumulator", "co- ord", "in- flight", "run- ning"). LlamaParse rejoins line-end hyphens itself, so IR-840's hyphen rejoining is not needed for these papers.

**Confidence.** With high-effort confidence off, LlamaParse still returned a confidence for every page. Three pages fall under 0.5, all in the appendix of "Diverse Metallicities" (min 0.366): pages 18 and 19 are a large table, and page 21 is a page of spectra figures. Their text is present. No page failed.

## Cost

| Paper | Pages | Credits | Per page | Pages Cost Optimizer billed cheaper |
|---|---|---|---|---|
| MeshKV | 5 | 136 | 27.2 | 2 |
| Expected Hypervolume Maximization | 20 | 551 | 27.6 | 7 |
| Accelerating massive ensembles of ODEs | 17 | 448 | 26.4 | 6 |
| Diverse Metallicities in Protoclusters | 23 | 475 | 20.7 | 5 |
| State-Space-Based FIR Filtering | 5 | 56 | 11.2 | 2 |
| Noise-adjusted turnover | 8 | 65 | 8.1 | 5 |
| **Total** | **78** | **1,731** | **22.2** | **27** |

1,731 credits is $2.16 at $1.25 per 1,000. The whole campaign, including Voyage, settled at $2.21. LlamaParse reports one credit total per job, not a split by tier or feature, so the credits per page by tier cannot be recorded.

**The price is not the 10–13 credits a page predicted.** `agentic` (10) plus layout images (3) is 13, and Cost Optimizer should lower that. The extra tracks charts and tables: MeshKV's five pages carry 5 charts and 6 tables. The likely source is `specialized_chart_parsing: "agentic"`, which LlamaParse's pricing page does not list. Unconfirmed.

At 22 credits a page, the 752-page proxy corpus would cost about 16,700 credits ($21), and a 100-page thesis about $2.80.

## Defects found

1. **Admission reserves 508 minutes for every LlamaParse read.** `LlamaParseExtractor.timeout_seconds` is sized for the largest accepted PDF (1,000 pages), and admission leases that long, whatever the paper's length. Under a 540-minute campaign, only one read fits at a time. The second worker's read was refused (`campaign_exhausted`) three times and failed. It succeeded when retried alone.
2. **Admission under-reserves money.** The reserve is 13 credits a page, and the bill was up to 27.6. Settlement corrects the campaign total, so the ceiling held, but a campaign can be overrun by up to 2× in flight. `AI_ADMISSION_EXTRACTION_ADDON_CREDITS_PER_PAGE` needs the chart-parsing cost.
3. **Heading levels need the numbering repair, or a new rule.** Captions returned as headings also need dropping. See Structure.

None of these has a Jira issue yet.

## Not covered

- The contract suite on output from the new request. Re-recording IR-841's four synthetic PDFs would cost about 100 credits.
- 6 papers and 14 questions, not ADR-056 decision 14's 40 papers. Recall shows a direction, not a measured difference.
- The figure crops IR-845 needs. LlamaParse returned 11 layout crops for MeshKV alone, and the adapter dropped 4 of them because they matched no image item. Not assessed further.
- Scanned PDFs: every paper here is born-digital.
