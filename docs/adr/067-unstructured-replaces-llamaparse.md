# ADR-067: Unstructured replaces LlamaParse as the only Extractor

## Status

**Accepted on merge** — 2026-11-13 (IR-981). The decisions are Jive Tyler Revalde's, from the IR-980 design session on 2026-11-13. Merging this PR records acceptance by the reviewer who approves it; the PR names them. No adviser confirmation and no CIT-U data protection officer's review is recorded (IR-123).

**Amended 2026-11-14 (IR-984):** the Extractor is Unstructured's Platform API with `strategy=hi_res`, not Transform, and the spike gate's reading-order rule is judged on real two-column pages. The spike gate passed on that basis; see the amendment at the end.

**Not built.** LlamaParse stays the running Extractor until both gates in decision 2 pass and IR-988 runs. Until then this ADR decides what IRIS is moving to and how the move is judged; it changes no behaviour.

**Supersedes [ADR-056](056-manuscript-extraction-moves-to-llamaparse.md) decisions 1, 2, 3, 8 and 9** (the vendor, its pinning, what is requested, its labels and its Figure crops) once the cutover runs. **Amends ADR-056 decision 4** (what the stored raw result is). **Replaces ADR-056 decision 14** (LlamaParse's acceptance check against Docling) with this ADR's two gates (decision 2). Decision 15 was already withdrawn. ADR-056 decisions 5–7, 10, 12 and 16 carry over unchanged, decisions 11 and 13 carry over adapted to Unstructured (decision 9), and so do its IR-851, IR-859 and IR-879/IR-883 amendments where they still apply (decision 12). ADR-056 stays `Accepted` until IR-988, then becomes `Superseded by ADR-067`.

**Amends [ADR-013](013-chunk-level-rag-pipeline.md)'s 2026-09-21 amendment**: the 700-token ceiling becomes a tested target size plus a safety ceiling (decision 14).

It does not change [ADR-015](015-voyage-embedding-and-reranking.md) (Voyage embeds and reranks), [ADR-041](041-shared-provider-admission.md) (admission), [ADR-052](052-each-paper-states-its-embargo-and-a-person-ends-it.md) (embargo) or [ADR-054](054-each-person-answers-whether-ai-may-use-their-papers.md) (consent).

## Context

[ADR-056](056-manuscript-extraction-moves-to-llamaparse.md) chose LlamaParse over Unstructured in [the vendor comparison](proposals/056-extraction-vendor-comparison.md). Unstructured lost on six points: word and line boxes, printed page numbers, the table grid, the page limit, dated version pins, and published retention terms for the shared service.

Running LlamaParse since then showed that two of those points matter less than the comparison assumed:

- **IRIS can recover most of what Unstructured lacks from the PDF itself.** A born-digital thesis carries word boxes, PDF page labels, bookmarks, fonts and often a table-of-contents page. `pypdf` and `pdfplumber` are already in `requirements/base.txt` (IR-665, IR-871), and IRIS already reads Review text with `pdfplumber` on campus (ADR-058 §1 as amended).
- **LlamaParse's heading levels needed a repair anyway.** IR-851 found 27 of 113 numbered headings at the wrong level, which is why IR-859 made section numbering set the depth. IRIS already decides heading depth itself, so a vendor's level is one signal, not the answer.

And Unstructured stays ahead where the comparison said it was: price with everything on (about $1.50 against $2.25 per 100 pages), per-element OCR agreement, ISO 27001 and Asia-Pacific regions.

**What Unstructured's Transform API does not give**, from its documentation (`docs.unstructured.io`, read for the comparison):

- no dated version pin on `/api/v2`, only a `profile`; deprecated models are replaced silently
- boxes per element, not per word or line
- no printed page number field
- heading depth only through `category_depth`/`parent_id`, whose reliability is unmeasured

The chunker also has more strategies than it needs: `structural-markdown-v1` (the default), `labeled-structure-v1` (chosen for LlamaParse papers by IR-840) and `fixed-window` (IR-110's baseline). No measurement has ever compared them, and the 700-token ceiling is still the untested number ADR-013's 2026-09-21 amendment left open.

## Decision

### The vendor

1. **Unstructured (Transform API) becomes IRIS's only Extractor.** LlamaParse is removed at the cutover (IR-988), code and secrets both. There is never a second selectable Extractor: until the cutover, a plain branch on the stored `extractor` name reads existing LlamaParse Extractions, and IR-988 deletes the branch. IR-982's vendor registry is not built.
2. **Two gates decide whether the cutover happens. No sign-off is needed; the measured rule decides.**
   - **Spike gate (IR-984):** no-go if coordinates are missing for more than 10% of text elements on the proxy papers, or if reading order fails the `two_columns` layout fixture (`apps/ai/extraction/tests/fixtures/layouts.py`).
   - **Quality gate (IR-989)**, against the stored LlamaParse reads of the six proxy papers (ADR-056's IR-851 amendment):
     - recall@10 with reranking not lower by more than 0.02
     - wrongly nested numbered headings at most LlamaParse's count plus 5
     - no paper loses all its LaTeX formulas

   **If either gate fails, LlamaParse stays**, this ADR is amended to record the numbers, and the spec (IR-980) returns to its owner.
3. **Pinning is what the API returns.** Each Extraction records every model, profile and version identifier Unstructured's response carries, plus the request options. **Transform `/api/v2` offers no dated pin**, so a re-read months later may come from a different model with no warning. Stored raw results (decision 4) are what keep earlier reads reproducible; a re-read is a new Extraction, never a correction of an old one.

### What is stored

4. **Amends ADR-056 decision 4.** The stored raw result is Unstructured's output **plus IRIS's own reading of the PDF**, taken once at extraction time and stored beside it. That reading is the **PDF evidence**: word boxes, bookmarks, page labels, fonts and table-of-contents entries. Shaping stays one pure function over stored data, so a better rule re-runs without a paid re-read and without opening the PDF again.

### What IRIS recovers locally

5. **Exact citation highlights.** A quoted Passage is found among the `pdfplumber` word boxes inside its Unstructured element's box. On a failed match, or a scanned PDF with no text layer, the highlight falls back to the element box. The fallback rate is reported by IR-989.
6. **Printed page numbers**, first source that answers wins: PDF page labels (`pypdf`), then the text of Unstructured `PageNumber` and `Footer` elements, then filling gaps from the sequence around them.
7. **Section depth cascade**, first signal that answers wins, with the deciding signal recorded on each heading:
   1. PDF bookmarks
   2. the table-of-contents page
   3. section numbering (the IR-859 rule, carried from ADR-056)
   4. font size and bold (`pdfplumber`, Unstructured's `emphasized_text_contents`)
   5. known thesis headings: "Chapter N", "Introduction", "Acknowledgments", "References" and "Appendix" are top level; any other unnumbered heading nests under the open section

   `category_depth` and `parent_id` join the cascade only if the spike finds them reliable. The paper's title stays at level 1 above its sections (the IR-859 implementer's rule).

### Element mapping

8. **Every Unstructured element type and PDF-relevant metadata field has one stated use:**

   | Unstructured | IRIS use |
   | --- | --- |
   | `Title` | heading, depth from the cascade (decision 7); demoted to text when `detection_class_prob` is low |
   | `NarrativeText`, `UncategorizedText` | text, keeping its source label |
   | `ListItem` | list item; consecutive items form one list, never split mid-item |
   | `Table` + `text_as_html` | table; rows read from the HTML; halves split across pages merged if the spike shows splitting; split by rows with the header repeated |
   | `Image` + `image_base64` | Figure, stored by IRIS (IR-987; decision 10) |
   | `FigureCaption` | text, bound to its Image (ADR-025's caption binding, carried by ADR-056) |
   | `Formula` | formula, display only and left out of embedded text; plain text if it is not LaTeX |
   | `CodeSnippet` | code, kept whole |
   | `Header`, `Footer` | page furniture, not chunked; `Footer` feeds the printed page number |
   | `PageNumber` | printed page number, not chunked |
   | `PageBreak` | confirms the page boundary `page_number` gives |
   | `Address`, `EmailAddress` | **dropped from chunks and embedded text** as personal data; kept in the stored raw result |
   | `CompositeElement` | refused: IRIS does not use Unstructured's chunking |

   | Metadata | IRIS use |
   | --- | --- |
   | `coordinates`, `coordinates.system` | element boxes, converted to page points |
   | `page_number` | the PDF page |
   | `emphasized_text_contents`, `emphasized_text_tags` | a section-depth signal (decision 7) |
   | `detection_class_prob` | demotes a low-confidence `Title` |
   | `languages` | stored per chunk; used only after a measurement shows it helps |
   | element ID | recorded on the chunk as provenance |
   | `links`, `filename`, `last_modified` | provenance |

   An element type or field not in these tables is stored in the raw result and ignored by shaping until an ADR amendment gives it a use.

### Carried over from ADR-056

9. **Carried over from ADR-056.**
   - **Unchanged:** the disclosure gate decides every call (decision 5); every attempt is admitted and charged under ADR-041 (decision 6), at Unstructured's price (IR-983); vendor copies are removed, with the uploaded file deleted on success and failure (decision 7); Figures are described for retrieval only and never shown (decision 10); ADR-025's carried-forward rules (decision 12); low-confidence pages are flagged, not dropped (decision 16).
   - **Adapted:** formulas stay display only and out of the embedded text (decision 11), but are found as Unstructured `Formula` elements rather than by LaTeX delimiters in LlamaParse's text. IRIS still builds chunks and Voyage embeds them, and Unstructured's chunking and embedders are not used (decision 13), but chunks start at the headings the cascade places (decision 7) and their length follows decision 14, not one chunk limit.
10. **Figures.** A Figure is the image Unstructured returns as `image_base64`, stored by IRIS with the Manuscript and served only through Django's permission layer, as ADR-056 decision 9 required of LlamaParse's crops.

### Chunking

11. **One production strategy.** `structural-markdown-v1` and `labeled-structure-v1` are compared on Unstructured output, using **trial chunk sets** in `eval_retrieval` and a one-paper (Paper Chat) test set (IR-1050, IR-1051, IR-1052, IR-1054). The winner stays and the loser is deleted. The result is recorded here as an amendment when it exists.
12. **`fixed-window` survives only as the evaluation baseline.** It is never the production strategy.
13. **Every chunking change ships off or behind measurement** (ADR-033 §5). Run files record the extractor, strategy, options and tokenizer.
14. **Amends ADR-013's 2026-09-21 amendment: one ceiling becomes two numbers.**
    - The **target size** is the chunk length the packer aims for. It starts at 700 tokens and is chosen by a sweep over 300, 400, 550, 700 and 1,000 on the winning strategy (IR-1054).
    - The **safety ceiling** is 2,000 tokens: no chunk may exceed it, and the chunker's property tests check that whatever the target. Changing the number needs an amendment here.

    The unit stays real `voyage-context-4` tokens (IR-287).

### Known losses

15. **Accepted and recorded:**
    - A scanned PDF has no text layer, so its highlights stay at element-level boxes.
    - A page with no number anywhere (no page label, no `PageNumber`, no footer, no sequence to fill from) has no printed page number.
    - No dated version pin (decision 3).

## Alternatives Considered

**Keep LlamaParse.** No migration, word boxes and dated pins from the vendor. Rejected if the gates pass: it costs more with everything on, and its heading levels needed IRIS's own repair regardless. It remains the outcome if either gate fails.

**Unstructured beside LlamaParse, selectable per deployment.** The first version of IR-980. Rejected: two Extractors to maintain, test and price, and a registry seam that nothing in production would vary across.

**Use Unstructured's hierarchy (`category_depth`, `parent_id`) for heading depth.** Least code. Rejected as the primary signal: its reliability on theses is unmeasured, and IR-851 showed that trusting a vendor's levels gets about a quarter of numbered headings wrong. It joins the cascade if the spike earns it a place.

**Let Unstructured chunk (`CompositeElement`) or embed.** Rejected for the reasons ADR-056 decision 13 gave LlamaParse's indexing: no `voyage-context-4`, chunk sets outside IRIS's hashing and swaps, and admission and visibility split away from Django.

**Keep every chunking strategy registered.** Rejected: three strategies, none measured against the others, means the one serving readers was chosen by default, not by evidence.

**Keep one 700-token ceiling.** Rejected: one number was doing two jobs. As a target it was never tested, and as a hard limit it split tables and lists that a larger safety ceiling would keep whole.

## Decision Rationale

Once IRIS decides heading depth and page numbers itself, a vendor's job shrinks to reading order, element types, boxes, tables, formulas and images. Unstructured does that for less, and what it does not return, IRIS can read from the PDF with libraries it already ships. The gates make the switch a measured outcome rather than a preference: if Unstructured reads worse, LlamaParse stays.

Keeping the PDF evidence beside the vendor's output preserves ADR-056's best property: shaping is pure, so every improvement re-runs for free.

## Consequences

- **Positive.**
  - Lower extraction cost with everything on.
  - One Extractor and one chunking strategy, each chosen by measurement.
  - Heading depth and page numbers come from the paper's own signals, with the deciding signal recorded, so a wrong depth can be traced.
  - Personal addresses and emails stop reaching chunks and vectors.
- **Negative.**
  - No dated pin: a re-read can change silently.
  - The PDF evidence step is new code IRIS owns (IR-1053), and the cascade is more rules than LlamaParse's single level.
  - Scanned PDFs lose line-level highlights.
  - Every paper re-extracts, re-chunks and re-embeds once at the cutover (IR-988).
- **Neutral.** The disclosure gate, admission and vendor-copy deletion protect a different vendor's call the same way.

## MVP Impact

None on the submission workflow. Ask IRIS, Paper Chat and Publish suggestions read whatever the active Extraction is; the cutover changes their input, not their behaviour.

## SaaS Impact

Extraction stays per tenant and per page. Unstructured's Asia-Pacific regions and dedicated instances give a tenant more choice of where pages are read.

## Security Impact

- **Manuscripts leave the deployment for Unstructured instead of LlamaParse**, behind the same consent and embargo gate and ADR-041 admission.
- Unstructured's VLM partitioner sends pages to a model provider (Anthropic by default, through Unstructured's own key, per [the vendor comparison](proposals/056-extraction-vendor-comparison.md) §5). Which provider, and whose key, is an open condition (below).
- `Address` and `EmailAddress` elements are kept out of chunks and embedded text, so they never reach Voyage, a prompt or a citation. They stay in the stored raw result, which is never served to readers.
- Figure images are served only through the permission layer.

## Deployment Impact

Adds outbound HTTPS to Unstructured and new required secrets, which fail closed when absent. At the cutover, removes LlamaParse's secrets and outbound access. The PDF evidence step runs in the extraction worker and needs no new service.

## Research Impact

Extraction and chunking become measured choices: two gate reports, a strategy comparison and a size sweep, each committed under `docs/evaluation/runs/` with the extractor, strategy, options and tokenizer recorded. With no dated pin, the stored raw result is the reproducibility record. Proxy-corpus numbers are never findings about CIT-U research (ADR-023).

## Open conditions

These are terms and price checks, like ADR-056's, not quality gates: the gates decide whether Unstructured reads well enough, and these decide whether IRIS may send it real Manuscripts. They block production enablement, not construction:

1. **Retention in writing.** How long Transform keeps uploaded files and results, and whether the shared service trains on them.
2. **Model provider.** Which provider reads pages and whether IRIS passes its own `provider_api_key`.
3. **Account features.** Whether a self-serve Transform account returns `image_base64`, `text_as_html` and coordinates (the comparison's section 0).
4. **Price.** Unstructured's per-page price, for IR-983.

## Amendment — 2026-11-14 (IR-984): the Platform API's `hi_res` strategy, and the spike gate on real pages

Decided by Jive Tyler Revalde on 2026-11-14, from the IR-984 spike report
(`docs/evaluation/runs/2026-11-13-unstructured-spike/report.md`). Proxy-tier
numbers (ADR-023): never a finding about CIT-U research.

**1. The Extractor is Unstructured's Platform API with `strategy=hi_res`, not
Transform.** This amends decision 1.

- **Request:** the partition endpoint (`api.unstructuredapp.io/general/v0/general`)
  with `strategy=hi_res`, `coordinates=true`, `pdf_infer_table_structure=true`,
  `include_page_breaks=true` and `extract_image_block_types=["Image","Table"]`.
- **Credentials:** the Platform API has its own account and key, separate from
  Transform's. Transform keys are refused there.
- **Why not Transform:** on 40 real two-column pages, Transform made 14
  column-order errors. `hi_res` made one, a figure caption placed before body
  text, as did LlamaParse.

**2. `hi_res`, not `auto`.** The two returned identical output on all four
papers and cost the same, so `auto` sent every page to `hi_res`. Pinning
`hi_res` keeps that guaranteed.

- **What `auto` risks:** it may send a page to `vlm`, which returns no
  coordinates, or to `fast`, which made 4 column-order errors and returns no
  `Formula` elements or table HTML.
- **What pinning `hi_res` costs:** no page is ever read by a VLM, even a page a
  VLM would read better. Scanned pages are the likely case, and decision 15
  already accepts element-level boxes for them.

**3. The spike gate's reading-order rule is judged on real two-column pages.**
This amends decision 2.

- **Why:** the `two_columns` fixture also fails LlamaParse and Docling, because
  its three-line columns read as rows. So it cannot separate vendors.
- **The measure:** column back-jumps on two-column proxy pages, where a
  right-column block is followed by a left-column block on the same page. It is
  scored against `pdfplumber`'s character positions; the scorer is in the
  report's `real_order/`.
- **What would have failed it:** more back-jumps than LlamaParse on the same
  pages.

| Extractor | Back-jumps (40 pages) | Text elements without coordinates |
|---|---|---|
| LlamaParse (running) | 1 (a caption) | — |
| Docling (previous) | 0 | — |
| Platform `hi_res` | 1 (a caption) | 0 of 772 |
| Platform `auto` | 1, identical to `hi_res` | 0 of 772 |
| Platform `fast` | 4 | 0 |
| Platform `vlm` | 0 (10 pages) | all |
| Transform `balanced` | 14 | 0 of 939 |

**4. What `hi_res` returns, against decision 8's mapping:**

- **`Formula` is a real element type, but its text is OCR, not LaTeX**
  (e.g. `N-1 |A) = >> 2(n)|n). n=0`). Decision 11 still holds: formulas stay
  display-only and out of the embedded text. But displayed formulas will be
  poorer than LlamaParse's, and the quality gate's formula rule (IR-989) is at
  risk. If it fails, that gate decides, as decision 2 says.
- **`parent_id` is returned** and joins decision 7's cascade as one signal,
  ranked below the PDF's own signals until IR-989 measures it.
- **Not returned:** `category_depth`, `emphasized_text_*` and
  `detection_class_prob`. So:
  - font and emphasis come from `pdfplumber` alone (decision 7, signal 4);
  - a low-confidence `Title` cannot be demoted by the vendor's probability.
- **`image_base64` is returned for `Image` and `Table` elements** (4 of 4
  images on paper 38), so decision 10 can be built.
- **`languages` and `links` are returned**, used as decision 8 already says.
- **No model or version identifier is returned.** Decision 3 is unchanged:
  record the request options, and rely on the stored raw result.

**5. Client behaviour (IR-985).**

- **No unbounded synchronous call.** One synchronous `hi_res` call ran past
  900 s without answering; the same paper took 43 s on retry. So the client
  uses a bounded timeout with a retry, or an on-demand job, and records which.
- **Re-record the fixtures.** The fixture recordings committed by IR-984 are
  Transform's. The client and shaping (IR-986) need a Platform `hi_res`
  recording of the four fixtures.

**6. Open conditions, restated for the Platform API:**

1. **Retention:** unchanged, now asked of the Platform service.
2. **Model provider:** does not arise for `hi_res`, which sends no page to a
   model (no `enrichment_origins` in its output). It returns if `vlm` or
   `auto` is ever adopted.
3. **Account features:** answered. A self-serve Platform account returns
   coordinates, `text_as_html` and `image_base64`.
4. **Price:** Unstructured publishes $0.015 per page for every strategy, after
   10,000 free pages (`unstructured.io/pricing`, read 2026-11-14). It is still
   to be confirmed that the separate Platform account bills at that rate
   (IR-983).

## Related Requirements

FR-M3-01, FR-M4: stable labels only, per the frozen-SRS rule.

## Related Tasks

- IR-980: the spec
- IR-981: this ADR
- IR-984: spike (spike gate)
- IR-989: quality gate
- IR-988: cutover and LlamaParse removal
- IR-985: Unstructured client
- IR-986: shaping
- IR-987: Figures
- IR-983: Unstructured's price in admission
- IR-1053: PDF evidence
- IR-1050: chunker consolidation part A (production strategy, target size and safety ceiling)
- IR-1051: trial chunk sets
- IR-1052: one-paper test set
- IR-1054: strategy comparison and size sweep
- IR-1055, IR-1056: section-mate expansion and section-aligned embedding windows
- IR-982: vendor registry, closed as won't do
