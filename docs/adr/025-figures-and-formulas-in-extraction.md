# ADR-025: Figures are cropped from the source PDF, formulas are OCR'd, and figure contents are not described

## Status

**Accepted** — 2026-09-17.

**Amends [ADR-016](016-docling-structured-extraction.md)** on what the extractor captures. Does not supersede it: structured extraction through Docling-serve, on-premise, with no fallback extractor, is unchanged.

**Records a correction to a premise repeated across three modules.** See Context.

## Context

Ask IRIS can name a figure and cannot show one. It can cite "Figure 3" from a caption and has no way to put the picture in front of a reader. Mathematical notation fares worse: a formula arrives as whatever the PDF's text layer held, which for equations is mangled glyphs or nothing, and an element with no text is dropped silently.

Two Docling options govern this, and neither is set:

| Option | Default | IRIS today |
|---|---|---|
| `do_formula_enrichment` — "perform formula OCR, return LaTeX code" | off | not set |
| `do_picture_description` / `do_picture_classification` | off | not set |
| `include_images` | **on** | explicitly set **off** |

### The premise that turned out to be false

Three modules justify their behaviour by reference to a **citation overlay**:

- `extraction/docling_client.py` turns images off because "the citation overlay draws regions over the real PDF, so a rendered picture would be megabytes of derived asset nothing reads".
- `extraction/docling_mapping.py` gives a caption its own rectangle so "the highlight lands on the caption text, not on the whole image".
- `chunking/regions.py` deduplicates rectangles so "the citation overlay would stack identical boxes on top of each other".

**That overlay has never been built.** Audited 2026-09-17: the only PDF viewer in the tree renders a downloaded blob inside a bare `<iframe>` — the browser's native PDF plugin, which cannot be drawn on and cannot be scrolled to a page programmatically. Neither `pdfjs-dist` nor `react-pdf` is declared in the frontend.

**Consequently every chunk in IRIS stores bounding boxes that no code reads.** The regions work in IR-113, the coordinate-origin normalization in IR-107, and the caption-parenting fix in IR-245 all produced data with no consumer.

This does not make those decisions wrong. It means a future reader would find three confident justifications pointing at a component that does not exist, and could not tell whether that was understood or overlooked. This ADR is that record.

## Decision

### Figures are shown by cropping the source PDF on request

A **Figure** — a picture identified by the page and rectangle it occupies (see `CONTEXT.md`) — is rendered from the stored PDF when an answer needs it, through Django's permission layer, and is never stored as a derived asset.

This keeps ADR-016's reasoning intact: the PDF remains the single source of truth and no duplicate image store exists. What changes is that the extractor must **emit a Figure element carrying the picture's own rectangle**, which it currently discards — today a picture contributes no element of its own and only its caption survives.

**Render adapter: `pypdfium2`.** Apache-2.0/BSD-3. **PyMuPDF is disqualified on licensing**, not on taste: it is AGPL-or-commercial, and IRIS has a commercial track with per-tenant deployments where users upload PDFs — the exact case AGPL's copyleft is triggered by. ADR-016 dropped PyMuPDF for unrelated reasons; this reason is permanent.

**Crops are cached in Redis**, keyed by record, page, rectangle and the extraction content hash. Not persisted to storage: that reintroduces the derived-asset duplication ADR-016 rejected, with an invalidation problem attached. The content hash makes a stale crop impossible.

### A Figure carries no text and rides on its caption's chunk

A Figure element has no text, so it cannot be a retrievable unit of its own — there would be nothing to embed and it could never be found. It **merges into the chunk holding its caption**, contributing its rectangle and its kind and nothing else.

Retrieval then finds that chunk by the caption's words, and the answer can render the Figure because the chunk already carries the rectangle. No new retrieval concept is introduced.

**An uncaptioned Figure is dropped.** With no caption adjacent, its rectangle would attach to whatever prose happened to precede it, and an answer could show a chart beside a claim it has nothing to do with. Dropping is the closed failure mode and matches how the normalizer already discards elements it cannot place.

**This makes Figure support caption-quality-dependent.** A submission whose figures are not properly captioned gets no figures. Recorded rather than hidden.

### Formulas are OCR'd to LaTeX and declared as a kind

`do_formula_enrichment` is turned on, and `FORMULA` becomes a declared element kind rather than an unmapped label passing through by accident of the unknown-label rule.

Declaring it is the point: the pass-through "works" today only in the sense that the string survives, and nothing downstream can act on it. A declared kind is what lets the chunker refuse to split mid-expression and keep a formula attached to the paragraph that introduces it — a formula alone is uninterpretable and retrieves as noise.

**Expectation recorded so a spec cannot promise otherwise: embedding models are weak at mathematical notation.** Formulas will be found through their surrounding prose, not by the notation. "Search by equation" is not a capability this buys.

### Figure contents are not described

`do_picture_description` stays off, and turning it on is deferred to its own ADR.

The blocking objection is not cost or speed. It is that **a generated description is invented text that is indistinguishable from source text**. If IRIS stored one as a chunk and cited it as a Passage, a reader would see a quotation and reasonably believe the paper said it, when what they are reading is a small vision model's guess about a chart. In a system whose purpose is grounded citation into IP disclosures, that is an integrity failure, not a quality shortfall.

If picture description is ever adopted, a described Figure must be visibly marked as machine-generated and should not be citable as a Passage.

`do_picture_classification` — a local classifier producing a type label such as "bar chart" — is a separate, weaker case with none of that objection, and is tracked as a future upgrade rather than decided here.

## Alternatives Considered

**Build the PDF.js citation overlay first, and show figures through it.** This is the component the codebase already assumes. Rejected for this effort on two grounds. It is a substantial frontend build — worker setup, virtualised page rendering, coordinate mapping, accessibility — that would consume the whole effort. And an overlay cannot place a figure **inline in a chat answer**, which is the actual requirement; it only works for a reader already inside a document viewer. The overlay remains worth building, as its own effort. **This ADR does not decide against it.**

**Turn `include_images` on and store extracted images.** Rejected, and ADR-016's reasoning is why: megabytes of derived assets duplicating the source of truth, requiring invalidation whenever a document is replaced.

**Make a Figure its own retrievable unit.** Rejected: with no text there is nothing to embed, so it could never be retrieved. It would be a row that exists and is unreachable.

**Attach an uncaptioned Figure to the nearest preceding block.** Rejected: silently associates a picture with unrelated prose, which is worse than omitting it.

**PyMuPDF as the render adapter.** Rejected on licensing, as above.

## Decision Rationale

Cropping is chosen because it is the cheapest path from "bounding boxes nobody reads" to "a reader sees the figure", and because it works inside a chat answer, where an overlay cannot.

Declining picture description is the decision most likely to be revisited, so the reasoning is deliberately recorded in full: the objection is about **a reader's ability to tell what the paper said from what a model guessed**, and it does not weaken as vision models improve.

## Consequences

- The stored bounding boxes gain their first consumer.
- A new backend dependency: `pypdfium2`. No render library or Pillow is declared today.
- Extraction output changes, so the content hash changes, so every document re-chunks and re-embeds. **This is free right now** — there is no corpus and no vector exists — and expensive once IR-278 delivers real papers and they are indexed. The extraction changes should land before that, not after.
- Figure support depends on caption quality in the source document.
- The answer-side half of this work **depends on IR-284**: a Figure reference has nowhere to live until a citation is an object rather than a bare Record id.
- The three overlay justifications in `docling_client.py`, `docling_mapping.py` and `regions.py` should be corrected to say the overlay is unbuilt and to point here.
- Formula-dense chunks hold more real tokens than prose chunks of the same word count. Nothing overflows — the per-chunk context window is 32,000 tokens and a pathological 512-word LaTeX chunk is far under it — so no guard is added. The chunk-size distortion is real but confined to mathematical sections, and recalibrating the counter stays deferred per IR-243.

## MVP Impact

Additive. Ask IRIS gains figures and readable formulas; nothing existing changes behaviour.

## SaaS Impact

Crop rendering is CPU work inside the Django process, cached per instance. Under [ADR-005](005-instance-per-tenant.md) that cost is per-tenant and scales with answer volume, not corpus size.

## Security Impact

**No image ever leaves the deployment.** Cropping happens in-process from a file Django already controls, and picture description — the only option that would transmit a figure to a model — is declined. The on-premise property [ADR-016](016-docling-structured-extraction.md) calls load-bearing is preserved exactly.

The crop endpoint resolves its Record through the same visibility predicate as every other read, so a Figure from a Record the asker cannot open is a 404 identical to a missing record. A crop endpoint that took a file path rather than a Record id would bypass the permission layer, which the security rule in `CLAUDE.md` forbids outright.

## Deployment Impact

One new Python dependency. Formula enrichment lengthens Docling conversions; the 900s synchronous ceiling from IR-249 should be re-checked against a real formula-heavy document before bulk ingestion.

## Research Impact

Figures and formulas are a substantial part of what a thesis actually communicates, and a RAG system that silently drops both is answering from a partial document. Recording *why* figure description is declined — grounding integrity, not capability — is itself a defensible research position about retrieval over confidential institutional records.

## Related Requirements

FR-M3-01, FR-M4 — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-107, IR-113, IR-245 (produced the region data this finally consumes), IR-243 (token counter, still deferred), IR-284 (citation objects — blocks the answer-side half), IR-278 (corpus — sets the deadline for landing extraction changes cheaply).
