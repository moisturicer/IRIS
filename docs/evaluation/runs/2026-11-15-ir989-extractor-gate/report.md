# IR-989 — Extractor quality gate: Unstructured against LlamaParse on six proxy papers

**Run:** 2026-11-15, code at `ee90ff75` (`main`, after IR-1054). **Proxy tier (ADR-023):** six openly licensed arXiv papers ([corpus](../20261103-ir851-llamaparse-six/corpus.json)); no number here is a finding about CIT-U research.

## Verdict: passed by the owner's decision; the rule as measured failed

ADR-067 decision 2's rule, applied by `manage.py extractor_gate verdict` ([verdict.json](verdict.json)):

| Rule | LlamaParse | Unstructured | Result |
|---|---|---|---|
| recall@10 with reranking not lower by more than 0.02 | 0.786 | 0.643 | **Fail** (−0.143, two questions) |
| Wrongly nested numbered headings at most LlamaParse's + 5 | 0 | 0 | Pass |
| No paper with LaTeX under LlamaParse has none under Unstructured | 6 of 6 papers | 6 of 6 papers | Pass |

**As measured, the rule fails on recall.** The other two checks pass. The measured verdict in [verdict.json](verdict.json) is left as computed.

**Decision: the gate passes.** Decided by Jive Tyler Revalde, IR-980's owner, on 2026-11-15. The reason given: the sample is too small for the gap to count.
- **The margin is smaller than one question.** The set has 14 questions, so one question moves recall by 0.071. The rule's 0.02 margin can therefore only be met by losing no questions at all.
- **Both lost questions are the hyphen artifact below.** With that one quote trimmed past the hyphen, the arms tie at 0.786.

**Effect.** Unstructured is eligible, IR-988 is unblocked, and ADR-067 records the numbers and the decision (amendment of 2026-11-15, IR-989).

**The LaTeX check passes because of a separate step.** Unstructured's own Formula text is OCR. Its LaTeX comes from IR-1102's Sonnet transcriptions, which were stored for these papers. Without them, every paper would fail this check.

**Both lost questions are a label artifact, not a retrieval loss.** The two questions Unstructured loses, q42 and q77, share one label quote ("explicit Tsitouras 5(4) method for non-stiff systems…"). Unstructured keeps the PDF's line-end hyphen, so its chunk reads "the ex- plicit Tsitouras 5(4) method…". LlamaParse rejoins it, so its chunk reads "explicit". A label hits only when its quote is contained in the passage text (`apps/ai/evaluation/labels.py`), so this quote can never match Unstructured's text, however well the paragraph ranks.

A diagnostic copy of the question set trims that quote past the hyphen ([proxy_ir851_six_hyphen_diagnostic.json](proxy_ir851_six_hyphen_diagnostic.json)) and changes nothing else. On it:

| recall@10 with reranking | LlamaParse | Unstructured |
|---|---|---|
| Gate set | 0.786 | 0.643 |
| Diagnostic set (q42/q77 quote trimmed) | 0.786 | **0.786** |
| Final-set recall, diagnostic | 0.714 | **0.786** |

On the diagnostic set the arms tie. They differ in which question each misses: q76 for LlamaParse, q29 for Unstructured. The diagnostic does not change the measured verdict; it is the evidence behind the owner's decision. It shows where the gap comes from: IR-1054 already recorded 13 main-set labels blocked by the same kept hyphens ("shaping fix, separate"). No Jira issue tracks that fix yet. Running the gate again after such a fix would be a new gate run, not a correction of this one.

## How it was run

The ticket asks for both reads in one database with trial chunk sets, not two database copies. Each paper holds one stored read (`PdfExtraction` is one-to-one with its Record), so the arms took turns on one database copy:

- **Database.** `iris_ir989` is a copy of `iris_ir1054`, trimmed to the six papers.
  - The copy already held each paper's Unstructured `hi_res` read from IR-1054 (2026-11-15), with PDF evidence, Figures (described) and formula crops (transcribed by Claude Sonnet 5.5).
  - **No paper was re-read.** No Unstructured, LlamaParse or OpenRouter call was made for this gate.
- **LlamaParse reads.** The stored raw results of IR-851's reads (`iris_ir851_llama`) were exported and installed in place of the Unstructured ones.
- **Re-shaping.** `extractor_gate install` re-shapes every read from its stored raw result with today's code: LlamaParse with IR-859's repair, Unstructured with IR-1053/IR-1057's PDF evidence.
- **No crossed media.** A LlamaParse read is installed with no source revision, so Unstructured's Figures and transcriptions never apply to it.
- **Chunking.** Both arms used the one production strategy and target size (ADR-067's IR-1054 amendment): `structural-markdown-v1`, target 700 tokens (the default), ceiling 2,000, `figure_passages=true`, `index_formulas=true`, tokenizer `voyage-context-4`. Every run file records extractor, strategy, options and tokenizer under `provenance.chunking`.
- **Retrieval.** Each arm ran retrieval as `admin@cit.edu`, with the development disclosure bypass (IR-317) on.

```
extractor_gate export  --question-set proxy_ir851_six.json --out <shelf>/unstructured
extractor_gate install <shelf>/llamaparse
eval_retrieval --questions proxy_ir851_six.json --user admin@cit.edu \
  --variant "gate_llamaparse=llamaparse:structural-markdown-v1:figure_passages=true,index_formulas=true"
extractor_gate install <shelf>/unstructured
extractor_gate measure --question-set proxy_ir851_six.json --out measures-unstructured.json
eval_retrieval ... --variant "gate_unstructured=unstructured:structural-markdown-v1:figure_passages=true,index_formulas=true"
extractor_gate install <shelf>/llamaparse      # again, so both arms' sets share the HNSW index
extractor_gate measure ... --out measures-llamaparse.json
eval_retrieval ... --variant gate_llamaparse=...   # 0 embedded: every set reused
extractor_gate verdict --llamaparse measures-llamaparse.json 20261115-141348-proxy_ir851_six.json \
  --unstructured measures-unstructured.json 20261115-141223-proxy_ir851_six.json --out verdict.json
```

The copy is left with the Unstructured reads installed.

**Order.** The LlamaParse arm ran twice. The first run ([141043](20261115-141043-proxy_ir851_six.json)) came before the Unstructured sets existed. The second ([141348](20261115-141348-proxy_ir851_six.json)) ran with both arms' vectors in the shared HNSW index, as `eval_retrieval` advises. Both runs scored the same. The gate reads the second.

## Retrieval

[LlamaParse run](20261115-141348-proxy_ir851_six.json) · [Unstructured run](20261115-141223-proxy_ir851_six.json) · 14 questions, one question = 0.071

| | LlamaParse | Unstructured |
|---|---|---|
| recall@10, no reranking | 0.571 | 0.500 |
| recall@10, with reranking | **0.786** | **0.643** |
| final-set recall, no reranking | 0.571 | 0.500 |
| final-set recall, with reranking | 0.714 | 0.643 |
| Chunks in the trial set | 293 | 334 |

Per question, with reranking:
- **Missed by both:** q61 and q75.
- **Missed by LlamaParse only:** q76.
- **Missed by Unstructured only:** q29, plus q42 and q77, which are the hyphen artifact above.

These numbers sit lower than IR-851's 0.929 for two reasons. The chunking is different (one strategy, Figure passages and indexed formulas now). The LlamaParse reads are re-shaped by today's code. Neither arm is compared with IR-851's numbers, only with each other.

## Structure

[measures-llamaparse.json](measures-llamaparse.json) · [measures-unstructured.json](measures-unstructured.json) · each measure over its own denominator

| Measure | LlamaParse | Unstructured |
|---|---|---|
| Numbered headings, wrongly nested | 0 of 113 | 0 of 112 |
| Captions or headers returned as headings | 1 | 1 |
| Display formulas located | 102 | 90 |
| …arriving as LaTeX | 102 (all) | 86 (Sonnet transcriptions; 4 in Expected Hypervolume untranscribed) |
| Inline `$…$` math in text | 1,427 spans | 1 span |
| Elements with a box | 94–99% per paper | 100% |
| Text elements whose box narrowed to its lines | n/a | 785 of 868 (90.4%); 83 fell back to the element box |
| Pages with a printed page number | 55 of 78 | 65 of 78 |
| Figures stored / described | 0 / 0 | 29 / 29 |

**The heading counts are partly circular.** Both shapings set a numbered heading's depth from its numbering: IR-859 for LlamaParse, and the numbering signal in IR-1057's cascade for Unstructured. `headings.py` then reads the same numbering, so a zero confirms the rules ran more than it measures nesting.

**Which signal decided each Unstructured heading** (152 headings):

| Signal | Headings |
|---|---|
| bookmark | 80 |
| numbering | 37 |
| font | 27 |
| title | 6 |
| open_section | 2 |

LlamaParse's shaping records no deciding signal (`unrecorded`).

**Inline math is lost under Unstructured.** LlamaParse writes in-line symbols as `$x_i$`; Unstructured returns them as plain characters. The gate's LaTeX rule counts display formulas per paper, so it passes. Inline math still differs between the arms, and the rule does not see it.

**Printed page numbers.** Neither arm recovers any for MeshKV or State-Space FIR, two five-page papers that carry none.

**LlamaParse has no stored Figures.** IR-851's reads predate Figure storage, and LlamaParse's images are not kept. Its arm therefore has no Figure passages. No question in this set asks about a Figure; IR-1054's Figure set measures that separately.

## Identifiers, pages, cost and latency

- **LlamaParse:**
  - **Pinned:** v2, tier `agentic`, version `2026-09-28`, as stored in each read's `extractor_version` and `extractor_options`.
  - **Request:** `disable_cache`, `granular_bboxes` word/line/cell, `extract_printed_page_number`, Cost Optimizer and chart parsing on.
- **Unstructured:**
  - **Recorded by the client:** `extractor_version` `general/v0:hi_res`; options `strategy=hi_res`, `coordinates=true`, `include_page_breaks=true`, `pdf_infer_table_structure=true`, `extract_image_block_types=["Image","Table"]`; call mode `synchronous`, 2 attempts allowed, 1 made per paper, timeout 170–350 s by length.
  - **No model or version identifier is returned** (ADR-067 §Amendment, item 4).

| Paper | Pages billed | LlamaParse credits (US$) | Unstructured US$ at $0.015/page | LlamaParse latency (s) |
|---|---|---|---|---|
| Accelerating massive ensembles of ODEs | 17 | 448 ($0.56) | $0.26 | 831 |
| Diverse Metallicities in Protoclusters | 23 | 475 ($0.59) | $0.35 | 110 |
| Expected Hypervolume Maximization | 20 | 551 ($0.69) | $0.30 | 37 |
| MeshKV | 5 | 136 ($0.17) | $0.08 | 38 |
| Noise-adjusted turnover | 8 | 65 ($0.08) | $0.12 | 1,621 |
| State-Space-Based FIR Filtering | 5 | 56 ($0.07) | $0.08 | 272 |
| **Total** | **78** | **1,731 ($2.16)** | **$1.17** | |

- **Unstructured's price is an estimate.** It is the published rate (IR-983). Whether the Platform account bills at that rate is still unconfirmed.
- **Unstructured's other costs are not in the table.** Its formula transcriptions add about $0.15 (86 × ~$0.0017, ADR-067's IR-1102 amendment). Figure descriptions were not costed.
- **LlamaParse latency includes waiting.** It runs from the extraction's creation to completion, including queueing and IR-851's admission refusals (defect 1 there), so it is an upper bound.
- **Unstructured latency was not recorded.** Trial reads do not time the call; IR-984 saw 43 s for one paper on retry.
- **This gate's own spend was Voyage only:** 620 new chunks embedded (about 250k tokens), plus reranking for six runs. That is a few cents, not metered per run.

## Departures from the ticket

- **No paper was re-read, and the dev database was not used.**
  - The ticket asks for Unstructured reads "on the dev database". `iris_db` holds only Docling reads. LlamaParse's six reads exist only in `iris_ir851_llama`.
  - So the gate ran on a copy that already held IR-1054's Unstructured reads (`iris_ir1054`), and LlamaParse's stored raw results were brought into it.
  - Both arms are re-shaped from stored raw results, which ADR-067 decision 4 provides for.
- **The reads take turns rather than sitting "beside" each other.** `PdfExtraction` is one-to-one with its Record, so `extractor_gate install` swaps reads in and out. Trial chunk sets, which the ticket asks for, keep both arms' chunks side by side.

## Not done

- **Rejoining Unstructured's line-end hyphens.** No Jira issue exists for it, and none is created here.
- **Unstructured latency** and a billed Unstructured cost (see above).
