# IR-842 — cutover command validated on five proxy papers

**Run:** 2026-11-03 at the IR-842 branch. A copy of IR-851's Docling database (`iris_ir851_docling`, migrated forward) and its media volume, in a Linux container from the backend image. `EXTRACTION_BACKEND=llamaparse`, version `2026-09-28`, tier `agentic`, admission enforced, `AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT=0`. Proxy tier only (ADR-023).

To save LlamaParse credits, five of IR-851's six papers were re-read. "Diverse Metallicities" (23 pages) stayed on Docling, so the corpus is mixed on purpose. Nothing else was re-read; the full corpus is not re-extracted.

## Result

| Check | Result |
|---|---|
| Dry run prices and sends nothing | **Pass**: 6 papers, 78 pages, up to 2,184 credits (28 a page: 10 + 18 add-on), about US$2.73 |
| Gate | **Pass**: each paper cleared by `--clear-for-ai`; bypass off |
| Real run needs a stated ceiling | **Pass** (test); run with `--credit-ceiling 1600` against an upper bound of 1,540 |
| Reads queued, read and stored | **Pass**: 5 of 5 `done`, `ready`, extractor `llamaparse` |
| Credits | **1,256 for 55 pages, the same per paper as IR-851**: 551, 56, 448, 65, 136 |
| ChunkSet swap | **Pass**: each re-read record has one active set (LlamaParse) and its Docling set inactive |
| Only changed chunks embedded | **Pass**: no Docling chunk text survived, so all 248 new chunks were embedded and none carried over. Carry-over itself is covered by the existing repository tests |
| `backfill_embeddings --dry-run` afterwards | Nothing left to embed |
| `check_vector_index` | **Pass**: 1.000 on both indexes ([output](check_vector_index.txt)) |
| `eval_retrieval` (14 questions) | recall@10 0.643 without reranking, 0.857 with ([run](../20261103-150134-proxy_ir851_six.json)). IR-851: LlamaParse 0.571 / 0.857 after IR-859, Docling 0.643 / 0.929. One question is 0.071, so no measured difference |
| Re-running the command | **Idempotent**: the dry run afterwards skips the 5 as "already read by LlamaParse" and plans only the 23-page paper ([output](dry-run-after.txt)) |
| Admitted spend | US$1.58 for extraction and Voyage together ([campaign](provider_campaign.txt)) |
| Rollback | **Pass** on record 9: the Docling set is active again with its 25 chunks restored |

## What it does not show

- **Figure descriptions were not exercised.** The database copy holds no stored Figures, and `LLM_DESCRIBE_FIGURE_MODEL` is unset. The dry run says so rather than guessing a cost.
- **Rolling back cannot be undone for free.** After a rollback, re-chunking the LlamaParse read is a no-op (the ingestion job's idempotency key is already used), so going forward again means another paid read.
- **Rollback is per record, not per run.** It reactivates the newest older ChunkSet of every record named (or all records), so it also reverts an unrelated later re-chunk. Name the records.
- **Docling is not removed**, and `EXTRACTION_BACKEND` is not switched in any committed config. That switch, the full-corpus run and the owner's spend approval are still open.
- The 14-question set cannot separate the Extractors (IR-851 reached the same conclusion).
