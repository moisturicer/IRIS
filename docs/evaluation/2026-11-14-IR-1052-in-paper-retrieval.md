# In-paper retrieval baseline (IR-1052)

> **Proxy tier (ADR-023).** These numbers come from the 40-paper arXiv proxy corpus and are an engineering gate. They are **never** a finding about CIT-U research.

## Why this was measured

Two 2026 studies (Zhou et al., arXiv 2602.16974; ConTEB, arXiv 2505.24782) found that contextualized chunk embeddings can *hurt* retrieval inside a single document while still helping across a corpus. The suspected cause is that sibling chunks from one paper start to look alike. Neither study tested Voyage.

IRIS embeds with `voyage-context-4`, and Paper Chat retrieves inside one Record, which is exactly that case. Until now no question measured it.

## What was run

- **Question set.** [`proxy_record_scoped.json`](proxy_record_scoped.json): 37 questions over 11 proxy papers, labelled Record + page + quote.
  - Each question carries a `scope_record`, and `eval_retrieval` retrieves only inside that Record.
  - `--dry-run` resolves 37 of 37 labels.
- **Corpus comparison.** [`proxy_starter.json`](proxy_starter.json), with 73 scored questions, run on the same commit, database and user.
- **Commit.** `a423a40c` (clean). The database was a private, migrated copy of the dev database, retrieved as `ierc@cit.edu`.
- **Configurations.** Reranking on and off, crossed with keyword fusion on and off. Fusion on means `--technique fusion=on --technique keyword_retrieval=on`, because fusion needs both settings.

Run files, each carrying its own denominator:

| File | Set | Fusion |
|---|---|---|
| [`runs/20261113-185305-proxy-record-scoped.json`](runs/20261113-185305-proxy-record-scoped.json) | in-paper, 37 | off |
| [`runs/20261113-185509-proxy-record-scoped.json`](runs/20261113-185509-proxy-record-scoped.json) | in-paper, 37 | on |
| [`runs/20261113-190002-proxy-starter.json`](runs/20261113-190002-proxy-starter.json) | corpus, 73 | off |
| [`runs/20261113-190509-proxy-starter.json`](runs/20261113-190509-proxy-starter.json) | corpus, 73 | on |

## Results

recall@10, with final-set recall in brackets:

| Configuration | In-paper (n=37) | Corpus (n=73) | In-paper minus corpus |
|---|---|---|---|
| no reranking, fusion off | 0.892 (0.757) | 0.568 (0.479) | **+0.324** |
| reranking, fusion off | 0.973 (0.973) | 0.733 (0.664) | **+0.240** |
| no reranking, fusion on | 0.892 (0.838) | 0.500 (0.486) | +0.392 |
| reranking, fusion on | 0.973 (0.973) | 0.733 (0.692) | +0.240 |

**Verdict: in-paper recall is not lower than corpus recall. It is higher by 0.24 with reranking and by 0.32 without.** The effect the studies warn about does not show up at this resolution.

- **Without reranking, 4 of 37 in-paper questions miss.** They are s08, s16, s17 and s28, all short, method-detail passages.
- **Reranking recovers all four but loses s04.** s04 is a figure-description passage in an appendix.
- **Fusion changes no in-paper recall@10.** It only raises the no-reranking final set from 0.757 to 0.838.

## How far to trust this

1. **The two sets are not paired.** They contain different questions over mostly different papers, so the gap compares two populations, not one question asked two ways.
   - Narrowing to one paper also removes every other paper's distractors. A higher in-paper number is therefore expected even if sibling chunks do blur together.
   - The test that would expose blurring is a miss *inside* the scope: the 4 misses without reranking and the 1 with it. That is 1 to 4 questions out of 37, too few to separate a real effect from noise. Each question is worth 0.027.
2. **The labels are an AI draft.** Claude wrote the questions and copied the quotes from active chunk text. No named person has reviewed them yet.
   - The quotes come from prose chunks, so the set leans toward passages that are easier to retrieve.
   - A person needs to review and sign the set before these numbers are cited anywhere, including as the baseline.
3. **This measures Django's retrieval stack, not live Paper Chat.** Since IR-957, readers are answered by the AI runtime, which scopes inside `ai/research/tools.py` `hybrid_search` (`c.record_id = $2`).
   - Both paths read the same `voyage-context-4` chunk vectors, so the embedding effect under test is shared.
   - The ranking around those vectors differs: always-on keyword+vector fusion and a different reranking path. A runtime-side measurement would be the faithful one.
4. **The corpus number has drifted.** `proxy_starter` reranked recall@10 is 0.733 here, against 0.885 on 2026-09-30. The likely cause is chunking or label changes since then. This report did not look into it.
5. **Running required one database fix.** The proxy papers in the dev database carried no `ai_consent` answer, so the disclosure gate refused all of them.
   - On the private copy only, `ai_consent` was set to `True` for the loader's released papers. This is the same answer `corpus_clearance.clear_for_ai` gives test data.
   - The shared dev database was not changed.

## The baseline to beat

For the section-aligned windows ticket (IR-1056), the in-paper slice of this commit is the baseline:

- **recall@10:** 0.892 without reranking, 0.973 with.
- **Final-set recall:** 0.757 without reranking, 0.973 with.

Reranking leaves only one miss, so the comparison has the most room without reranking.
