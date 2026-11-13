# ADR-056: Manuscript extraction moves to LlamaParse

## Status

**Accepted on merge** — 2026-11-02 (IR-837). The decisions are Jive Tyler Revalde's, from a design session. Merging this PR records acceptance by Lee Jasmin Adolfo, the project lead. Adviser confirmation is not recorded yet (the IR-189 precedent for the Docling-serve amendment). No CIT-U data protection officer's review is recorded (IR-123). **Built (corrected 2026-11-07, IR-968):** the LlamaParse extractor by IR-841, shaping and chunking by IR-840, Figures by IR-845, and Docling's retirement by IR-843. The LlamaExtract suggestions IR-846 built are still in the code although decision 15 is withdrawn; IR-883 removes them. Decisions 3 and 14 are amended by the IR-851 amendment below, and decision 8 by the IR-859 amendment. **Amended 2026-11-04 by Hermoine Zozobrado (IR-879, IR-883):** decision 15 (LlamaExtract auto-fill) is withdrawn; see the last amendment. Decision 1's Docling removal stands, built by IR-843 the same day. **Amended 2026-11-13 by [ADR-067](067-unstructured-replaces-llamaparse.md) (IR-981):** Unstructured replaces LlamaParse once two measured gates pass. Decisions 1, 2, 3, 8 and 9 are superseded at the cutover (IR-988), decision 4 is amended now (the raw result adds IRIS's own reading of the PDF), decision 14's acceptance check is replaced by ADR-067's gates, and decisions 5–7, 10–13 and 16 carry over (11 and 13 adapted, per ADR-067 decision 9). This ADR becomes `Superseded by ADR-067` when IR-988 runs; if either gate fails, it stands.

**Supersedes [ADR-016](016-docling-structured-extraction.md)** (Docling-serve as the extraction path) and **[ADR-025](025-figures-and-formulas-in-extraction.md)** (figures cropped on request, formulas OCR'd, figure contents not described). Both are now `Superseded by ADR-056`. The two ADR-025 amendments (IR-424, IR-437) are carried forward in decision 12 rather than lost.

It is the third-party reader [ADR-054](054-each-person-answers-whether-ai-may-use-their-papers.md) decision 15 anticipates, and it works inside ADR-054's consent and [ADR-052](052-each-paper-states-its-embargo-and-a-person-ends-it.md)'s embargo. It does not change [ADR-015](015-voyage-embedding-and-reranking.md): Voyage still embeds and reranks.

## Context

- **The deployment server has no GPU.** Docling-serve's GPU image is 18.6 GB. On CPU it read a 5-page paper in 98 s and an 18-page paper in 220 s (`docs/evaluation/runs/20261010-docling-cpu-short`, `docs/engineering/DOCLING_RESOURCES.md`). Extrapolated, not measured: a 100-page thesis takes 20–30 minutes, past the 900 s extraction timeout.
- **Docling refuses over 200 pages; upload allows 1,000.** A long thesis is accepted, then fails four times.
- **What the Docling setup drops.** Pictures (only their captions survive), table spans, every provenance entry after the first, and confidence. There is no OCR by default, so scans fail. Page furniture and heading depth are repaired by heuristics spread across six modules.
- **LlamaParse v2**, read from its public documentation on 2026-11-02:
  - typed `items` per page: `heading` (level 1–6), `text`, `list`, `table` (rows, HTML, CSV, merged across pages, quality flags), `image` (caption, box), `code`, `link`, `header`, `footer`
  - boxes in page points, plus word, line and cell boxes
  - printed page numbers and per-page confidence
  - 512 MB and 10,000 pages per file
  - a tier and a dated version pinned on every request
  - uploaded files and the parse cache kept 48 h, then deleted
  - no training on customer data unless an organization opts in

  Sources: `developers.llamaindex.ai/llamaparse/parse/guides/response-format`, `/parse/guides/tiers`, `/general/data_retention`, `/general/enterprise-readiness/data-privacy-security`.
- **LlamaParse's own indexing does not fit.** Index v2 manages chunking (fixed 1,024-token sentence chunks) and the embedding model, offers no Voyage, and keeps vectors in LlamaCloud's store for the length of the agreement. Index v1, which allowed a Postgres sink, is deprecated and offered no Voyage either (`/llamaparse/cloud-index-v2/migration-v1-to-v2`).

## Decision

### The extractor

1. **LlamaParse is IRIS's only Extractor.** Docling is abandoned. It keeps running, unchanged, only until LlamaParse is live (IR-842), and is then removed (IR-843).
2. **Every request pins a tier and a dated version.** The tier is `agentic` with Cost Optimizer, which sends simple pages to the cheaper tier. `latest` is never used outside development. Each Extraction records the Extractor, version and options it ran with.
3. **Everything LlamaParse can return for a paper is requested:**
   - typed items
   - word, line and cell boxes
   - printed page numbers
   - cross-page table merging and table quality flags
   - ~~high-effort confidence (page and document)~~ — withdrawn, see the IR-851 amendment
   - chart values
   - figure images
   - watermark text
4. **The raw LlamaParse result is stored.** One shaping function turns it into IRIS's document whenever it is read (chunking, search text, Publish suggestions). An improved rule never needs a paid re-read.

### What may be sent

5. **The disclosure gate decides every LlamaParse call.** That is consent per ADR-054 and the embargo per ADR-052. The embargo question is answered at upload, before the file is read. An embargoed paper, a paper whose Contact person said No, and a paper with no answer are not sent and not read; the author fills in the details. A release sends it then (ADR-054 decision 15).
6. **Every LlamaParse attempt is admitted and charged** under [ADR-041](041-shared-provider-admission.md), reserving its page count at the tier's price and settling to the credits reported.
7. **Vendor copies are removed.** Requests set `disable_cache`. The uploaded file is deleted once the result is fetched, on success and on failure. Figure images are downloaded at once (decision 9).

### What IRIS builds from it

8. **LlamaParse's labels are IRIS's labels.** Element kinds follow LlamaParse's item types, except that a caption returned as a heading becomes text (IR-859). Anything else becomes a paragraph that keeps its source label. Heading depth is LlamaParse's `level` (amended by IR-859: section numbering sets it). Running headers and footers are LlamaParse's `header` and `footer`. Depth from numbering is kept (IR-859); the other Docling-era repairs, repeated-furniture detection and stranded page numbers, are deleted. Rejoining hyphenated words stays only if the acceptance check (decision 14) finds broken words. Skipping whole sections such as the table of contents or references stays a chunking choice, not a shaping rule.
9. **A Figure is the image LlamaParse cropped, stored by IRIS.** The image is downloaded right after the read and stored with the Manuscript. It is served only through Django's permission layer, resolving its Record through the same visibility predicate as every other read. Rendering crops on request with `pypdfium2` (ADR-025) is dropped.
10. **Figures are described for retrieval only.** IRIS writes each Figure's description with its own `describe_figure` Inference task (ADR-036), through ADR-041 admission. The description and any chart values are embedded so retrieval and Ask IRIS know what a Figure shows. **They are never displayed and never quoted as a Passage.** A citation that lands on a Figure shows the Figure and the author's printed caption. A Figure is therefore no longer dropped for lacking a caption.
11. **Formulas are found by their LaTeX delimiters inside LlamaParse's text**, since LlamaParse has no formula item, and stay a declared kind. A formula is displayed but left out of the embedded text, so it never changes a vector.
12. **Carried forward from ADR-025's amendments:**
    - the answer path forbids images the system did not hand the model (IR-424 §1, §3)
    - formulas are delimited in chunk `content`, never in `text` (IR-424 §2)
    - an AI Overview is gated per Record before anything is assembled (IR-437 §2)
    - "search by equation" is not a capability
13. **Chunks are built by IRIS and embedded by Voyage.** Chunks start at LlamaParse's headings and never cut through a table, list or Figure. A merged table longer than the chunk limit splits by rows, repeating its header row. Chunks go to `voyage-context-4` grouped by paper, as ADR-015 already requires. Retrieval, reranking and visibility filtering stay in Django and Postgres. LlamaParse's indexing product is not used.

### Proving it

14. **No real Manuscript is extracted in production until an acceptance check passes** on the 40-paper proxy corpus (six papers, per the IR-851 amendment) against today's Docling output:
    - formulas still arrive as LaTeX
    - `eval_retrieval` recall@10 does not drop
    - heading nesting is checked against the thesis numbering
    - cost per paper is recorded and accepted by the project owner

    Run files go in `docs/evaluation/runs/`.
15. **Publish suggestions use LlamaExtract.** Title, authors, abstract, keywords and year each come with the page, the matching text and a confidence, so every suggestion can be checked against the paper. This replaces the "retain local extraction" clause of the Publish-autofill ADR drafted for IR-830 (numbered 053 in its working copy, which collides with [053](053-threat-model.md) on `main`) once that ADR lands.
16. **Low-confidence pages are flagged, not dropped,** until the acceptance check shows what cut-off is sensible. The watermark text is recorded for staff and does not change the upload flow.

## Alternatives Considered

**Docling on CPU.** Keeps everything on campus at no cost. Rejected: long theses exceed the timeout on the hardware IRIS will get, and the structure it returns is weaker than LlamaParse's.

**Docling on a rented GPU.** Docling's speed and structure, billed by the second. Rejected: it still sends manuscripts off campus, to a host IRIS would have to run and secure itself, and it keeps the heuristics.

**Unstructured.** Compared in full in [the vendor comparison](proposals/056-extraction-vendor-comparison.md), every claim cited to the vendors' documentation. Unstructured is stronger on:
- price with everything on ($1.50 against about $2.25 per 100 pages)
- built-in figure descriptions
- per-element agreement with OCR
- certifications (adds ISO 27001)
- Asia-Pacific dedicated regions
- choosing the model provider per node

Rejected in favour of LlamaParse's:
- word and line boxes
- printed page numbers
- table grid with quality flags
- 10,000-page limit with settable timeouts
- required dated version pins (Unstructured silently replaces deprecated models)
- published retention and no-training terms for the shared service

Its built-in Voyage embedder offers the `voyage-3` family, not `voyage-context-4`, so it would not replace IRIS's own embedding. Which features a self-serve account includes is also unclear in its documentation.

**LiteParse locally for unreleased papers.** Free and local. Rejected: a second Extractor to maintain, with weaker structure. The consent and embargo gate already keeps unreleased papers unread.

**LlamaParse's indexing (Index v2).** Least code. Rejected: no Voyage, fixed chunks, and vectors held by the vendor for the length of the agreement. It would also split visibility filtering away from Django's single predicate.

**Showing figure descriptions to readers, marked as AI-generated.** Rejected: the description's only job is helping retrieval find the Figure. Showing it invites a reader to treat a model's guess as the author's content, which ADR-025 warned against.

## Decision Rationale

The hardware rules out running a layout model on campus at thesis length. Once text must leave for a third party, the question is which reader returns the structure IRIS's citations depend on, under terms IRIS can check:

- LlamaParse returns typed elements with heading levels, boxes in the same unit IRIS stores, and line-level boxes.
- Its tier and version are pinned per request.
- Its retention terms are published.

Keeping chunking, embedding and retrieval in IRIS preserves Voyage, the eval harness and the one visibility predicate.

## Consequences

- **Positive.**
  - Long theses and scans become readable.
  - Citations can highlight the quoted lines and use the thesis's own page numbers.
  - Figures become findable.
  - The 18.6 GB image and the GPU dependency leave the deployment.
  - Six modules of heuristics shrink to one shaping function.
- **Negative.**
  - Every eligible paper is a paid call: about $1.25 per 100 pages on `agentic` before high-effort confidence, granular boxes and LlamaExtract add theirs.
  - IRIS now depends on a vendor's uptime and terms.
  - Extraction output changes for every paper, so the corpus re-chunks and re-embeds once (IR-842).
- **Neutral.** The embargo and consent gate now protects an extra outside call. It already existed for embedding and generation.

## MVP Impact

The submission workflow does not depend on it: an unreadable or ungated paper is filled in by hand. Ask IRIS and Publish suggestions depend on it for new papers.

## SaaS Impact

Extraction cost becomes per tenant and per page instead of per server. Each tenant needs its own LlamaParse account or usage tags, and its own ADR-041 campaign.

## Security Impact

- **Manuscripts leave the deployment** for LlamaParse, and Figure images for the `describe_figure` vendor. ADR-025's "no image ever leaves the deployment" no longer holds and is withdrawn by this ADR. Both calls are behind the consent and embargo gate (decision 5) and ADR-041 admission.
- **LlamaParse states** it holds zero-retention and no-training agreements with the model providers its managed service uses (OpenAI, Anthropic, Google). Those providers are subprocessors of IRIS's data.
- Stored Figure images are served only through the permission layer, never as public media.

## Deployment Impact

Removes the Docling service, its GPU detection in `scripts/setup_env.py`, and its resource limits (IR-843). Adds outbound HTTPS to the chosen LlamaParse region and new required secrets, which fail closed when absent. Webhooks are not used, because IRIS exposes no public inbound URL; jobs are polled.

## Research Impact

Extraction quality is now a vendor's, measured by IRIS's own acceptance check. Run files record the pinned version, so results stay reproducible. Proxy-corpus numbers are never findings about CIT-U research (ADR-023).

## Open conditions

These block production enablement, not construction:

1. **Retention in writing.** The v2 `disable_cache` replaces v1's `do_not_cache` and `invalidate_cache` (`/parse/guides/migration-v1-to-v2`), and the privacy page still uses the v1 name. Confirm in writing that `disable_cache` stops the 48-hour cache, and how long job results are kept.
2. **Region.** North America or the EU.
3. **Prices.** Granular boxes and LlamaExtract are priced separately; confirm both before the cutover estimate.
4. **Formulas.** Confirm LlamaParse writes LaTeX (decision 14). Met for born-digital papers by IR-851's run; scanned papers are untested.

## Amendment — 2026-11-03 (IR-851): no high-effort confidence, and a six-paper acceptance check

Decided by Jive Tyler Revalde while running IR-851, to keep the check inside LlamaParse's free tier (10,000 credits a month).

**Decision 3 no longer requests high-effort confidence.** It is a second review pass that costs 5 credits a page on top of `agentic`'s 10. Whatever confidence LlamaParse returns without it is still stored and flagged per decision 16.

**Decision 7 stands.** `disable_cache` stays set: turning the cache on would save credits only on a re-read within 48 hours, and would leave a vendor copy of every Manuscript for that time.

**Decision 14 runs on six papers, one per category of the proxy corpus, not forty.** The same six are extracted by Docling into a separate database, so recall is compared paper for paper.

**What it costs.**
- A page no longer gets LlamaParse's own grade of its output, so a weak read is harder to spot.
- 14 labelled questions instead of 52: one question moves recall@10 by about 7 points, so the check shows the direction, not a measured difference.
- The 40-paper Docling baseline is not the comparison.

## Amendment — 2026-11-03 (IR-859): section numbering sets heading depth

Decided by Jive Tyler Revalde after IR-851's run showed 27 of 113 numbered headings at the wrong level in LlamaParse's output. Examples: "1 INTRODUCTION" deeper than "2 METHOD", "1.2 …" shallower than "1 …", and 11 table or figure captions returned as headings.

**Decision 8, as amended.** LlamaParse's labels are still IRIS's labels, and running headers, footers and stranded page numbers still come from LlamaParse. The depth-from-numbering repair is kept and moves into the one shaping function. A numbered heading sits at the depth its decimal, roman or lettered number claims, below the level LlamaParse gives most of the paper's top-level sections. An unnumbered heading is placed against those sections: as high or higher makes it their peer, lower puts it under the open section. A table or figure caption returned as a heading becomes text, which is part of the same decision. One rule was added by the implementer, not decided by the owner, after re-chunking showed paper titles dropping out of context paths: the paper's title is kept at level 1, above its sections.

**What it costs.** A shaping rule reads the text of a heading again, which decision 8 meant to stop. A section number that a paper gets wrong is now trusted over LlamaParse's level. A heading that is really a short line opening "Table 1" or "Fig. 3" becomes text.

## Amendment — 2026-11-04 (IR-879, IR-883): no AI auto-fill

Decided by Hermoine Zozobrado in the review-workspace design session. Transcribed by an agent. **The decisions in this ADR are Jive Tyler Revalde's, and this amendment reverses two of them without his sign-off recorded.** IR-883 asks him to confirm.

**Decision 15 is withdrawn: Publish suggestions don't use LlamaExtract.** IRIS doesn't fill in a submission's fields with AI. Publish keeps the no-AI suggestions read from the Manuscript's stored structure (IR-406, IR-833, `apps/records/metadata_suggestions.py`), for every LlamaParse paper: title and abstract by the existing rules, and labelled front matter where the structure has it. Nothing a paper suggests is sent to a vendor to be read again.

**Decision 1 stands: Docling is retired.** IR-843 (PR #527, merged 2026-11-04) removed the Docling service, adapter, mapping and tests, so LlamaParse is the only Extractor. Keeping Docling as a fallback was decided in the same session and then withdrawn on finding that it had already been removed. If IRIS ever stops using a third-party Extractor, Docling is restored from PR #527's history and tested again. It isn't maintained in the meantime.

**Why.** Auto-filling with AI added a paid vendor call and a pending state to every submission, for fields an author can type.

**What it costs.**

- Authors get fewer pre-filled fields on LlamaParse papers (no authors, keywords or year from LlamaExtract).
- IR-846's built LlamaExtract path is removed (IR-883).
- There is no ready Extractor fallback: going back to Docling means restoring and re-testing it.

## Related Requirements

FR-M3-01, FR-M4: stable labels only, per the frozen-SRS rule.

## Related Tasks

- IR-837: this ADR
- IR-838: extraction module, provenance, contract suite
- IR-839: extraction job and failure classes
- IR-840: one shaping function
- IR-841: LlamaParse Extractor
- IR-842: corpus cutover
- IR-843: Docling retirement (done, PR #527)
- IR-883: remove the LlamaExtract Publish suggestions
- IR-851: acceptance check, and the amendment above
- IR-859: heading depth from numbering, and the amendment above
- Related: IR-189, IR-292, IR-293, IR-816, IR-123
