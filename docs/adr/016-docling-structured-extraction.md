# ADR-016: Docling-serve restored as the extraction path

## Status

Accepted — 2026-09-03 · **amended 2026-09-04, decision point 4 and §Research Impact**

> **Amendment, 2026-09-04 — the PyMuPDF fallback is dropped.** Decision point 4
> below retained PyMuPDF for Docling-serve unavailability. On the instruction
> of the project lead during IR-107 implementation, it is not built: **Docling
> is the only extractor, and unavailability is a failure that retries.**
>
> The reasoning is this ADR's own. A fallback extractor produces a flat string
> with no element kinds and no `prov`, so every chunk derived through it has no
> regions and no citation can be highlighted — which is the outcome the whole
> decision exists to prevent. A path that silently degrades to it would make
> the loss invisible: the extraction row says `done`, the text is populated,
> and only a reader clicking a citation ever finds out. Failing loudly and
> retrying is the honest behaviour, and the Celery retry plus the container's
> `restart: unless-stopped` cover the case the fallback was for. Not building
> it also removes the last undeclared extraction dependency from the tree.
>
> Recorded rather than reconciled, per the source-of-truth hierarchy in
> `CLAUDE.md`. **Decision point 4 as written below no longer describes the
> code.** Retained verbatim so the change is visible rather than erased.

**Amends [ADR-006](006-minimum-rag-pipeline.md)** on the one point ADR-013 left standing. ADR-013 superseded ADR-006's exclusions of chunking, reranking and multiple providers, but said nothing about extraction, so ADR-006's incidental avoidance of Docling survived a decision that had removed its reason. This ADR closes that.

## Context

> **Note, 2026-09-03.** An earlier draft of this ADR argued from `docs/SRS.md` and `docs/SDD.md`. Those are now **frozen thesis deliverables and are not an authority** — see the source-of-truth hierarchy in `CLAUDE.md`. The decision is unchanged; the reasoning below stands without them, which is the test any ADR should pass.

[ADR-013](013-chunk-level-rag-pipeline.md) made the chunk the retrievable unit. That single decision changes what extraction is *for*. Previously its output was a string headed for a full-text index, and flattening cost nothing. Now its output is the chunker's input, and the chunker splits on document structure — headings, table rows, list items — none of which survive a flattened string.

Revision 2 of [`../chunker_architecture.md`](../chunker_architecture.md) is explicit about the harder consequence. Serializing to markdown discards the per-element page and bounding-box data, and **no later work recovers it**: matching chunk text back against a PDF fails on ligatures, hyphenation across line breaks, and multi-column reading order. Flattening at extraction is the one decision that makes verifiable citations permanently impossible — not merely deferred.

That matters here more than it would elsewhere. IRIS answers questions about **unpublished theses and pre-filing IP disclosures**, reviewed by KTTO and IERC. An AI claim about that material has to be checkable against its source, and a citation a reader cannot verify is a claim asking to be trusted.

**ADR-006 deferred Docling, and its stated reason has lapsed.** The objection was one clause: *"No new services. Avoids the 4 GB Docling container and the FastAPI gateway."* Both halves are gone. [ADR-014](014-ai-gateway-as-a-service.md) adopted the gateway as a sixth service, and the Docling container is **already declared in both Compose files** (`docker-compose.yml:83`, `docker-compose.prod.yml:74`) with `DOCLING_API_URL` already present in `config/settings/base.py:192`. The service ADR-006 was avoiding is provisioned; only the client call was never written. ADR-013 superseded ADR-006's other exclusions but was silent on extraction, so the deferral outlived the reason for it.

**The code says the same thing about itself.** `backend/apps/documents/tasks.py`'s module docstring reads: *"Replace the three-tier extractor chain below with a single Docling-serve API call… POST bytes to Docling-serve… Returns extracted text as Markdown."* `backend/requirements/base.txt` carries matching unactioned TODOs. The chain is scaffolding that was never removed.

**And the scaffolding does not work.** None of its three extractors has its library declared in any requirements file — not `unstructured`, not PyMuPDF, not `pytesseract`. The chain catches `ImportError` per extractor, so on a clean install all three fail and extraction raises. There is no working extractor today, which removes the last practical argument for keeping it.

## Decision

**Docling-serve is the extraction path.** ~~PyMuPDF is retained as the fallback for Docling-serve unavailability.~~ — **no fallback extractor, per the 2026-09-04 amendment.**

1. **A Docling-serve client is implemented**, against the `DOCLING_API_URL` that already exists. *Implemented 2026-09-04 as `POST {DOCLING_API_URL}/v1/convert/file`* — the bare `/convert` that the ticket inherited from the frozen SDD is not an endpoint on current docling-serve.
2. **The structured output is persisted, not only the flattened text.** `PdfExtraction.extracted_text` continues to be populated so full-text search is unaffected; the structure is stored alongside it because it is what the chunker consumes and what carries regions through to citations.
3. **The prototype three-tier chain is deleted**, along with both dead `PDFExtractorService` copies and the undeclared `opendataloader_pdf` import.
4. ~~**PyMuPDF is retained solely for Docling-serve unavailability, and must be declared in requirements** — a fallback that raises `ImportError` is not a fallback.~~ **Superseded by the 2026-09-04 amendment above: no fallback extractor is built.** The extraction row still records which extractor produced the result.

## Alternatives Considered

**Keep PyMuPDF and chunk over plain text.** Rejected. It is cheaper and it was briefly specified this way before the prototype status of the current extractor was established. It costs citation provenance permanently, because coordinates cannot be recovered downstream — and it would mean the design's `bboxes`, `element_kinds` and `source_page` fields ship unpopulated, which is the exact stored-but-unread defect the chunker document opens by diagnosing.

**OpenDataLoader as the structured extractor.** Rejected as the primary. A strategy for it exists in the tree with a *"Placeholder implementation assuming a standard API"* comment and the package is declared in no requirements file, so it has never run. It is a third undeclared dependency, behind a name already used by a different package elsewhere in the same tree.

**Docling as a Python library rather than Docling-serve.** Rejected. Both Compose files already declare the service form, and it keeps a heavy dependency out of the Django image. Extraction throughput scales by adding replicas rather than by growing every worker.

**A hosted extraction API.** Rejected, and worth stating explicitly: Docling-serve is on-premise, so PDF bytes never leave the deployment. That is why this work carries none of the third-party transmission exposure that [ADR-015](015-voyage-embedding-and-reranking.md) has to reason about. (This sentence originally leaned on a KTTO/IERC sign-off recorded for ADR-015. **Corrected 2026-09-04:** that written governance precondition was dropped from ADR-015 on the same day, so there is no sign-off to lean on — and the argument never needed one. On-premise means the bytes do not leave, which is a property of the deployment rather than a permission anyone granted.) Trading Docling for a hosted extractor would move whole unpublished PDFs to a third party that no sign-off names, and would need its own decision.

## Decision Rationale

The decision follows from ADR-013 alone. Once the chunk is the retrievable unit, the chunker needs structure; structure is what a flattening extractor destroys; and the destruction is irreversible. There is no version of chunk-level RAG that runs well on a flat string, and no way to add coordinates back afterwards.

ADR-006's counter-argument was about avoiding a container and a service. ADR-014 took the service, and the container is already declared and configured. Nothing remains of the objection.

The cost is low because the expensive parts are already paid: the container is provisioned in both Compose files, the setting exists, and the work reduces to an HTTP call, a persistence decision, and deleting scaffolding that currently raises on import.

The alternative — chunk over flat text — is cheaper this week and forecloses citation provenance permanently. That is the wrong trade for a system whose AI output is read by an ethics review board.

## Consequences

**Positive.** The chunker gets structured input, so chunking can split on real document structure rather than guessing from a string. Regions survive into chunks, which keeps citation highlighting possible. Scanned theses gain OCR through Docling's own pipeline, removing the need for a separate OCR fallback library. Three pieces of dead code leave the tree.

**Negative.** A running service becomes a hard dependency of ingestion, where previously extraction was in-process. Extraction now fails when a container is down — mitigated by the existing Celery retry (three attempts, sixty seconds apart) and by `restart: unless-stopped` on the service, the fallback having been dropped in the 2026-09-04 amendment. The Docling image is large.

**Risk.** Docling's OCR quality on a poor scan is unknown, and the chunker's region work depends on it producing usable `prov` for recognized text. The mitigation is stated in the chunker document and costs about an hour: run one real scanned submission through Docling and inspect the output before committing to the region work.

## Revisit when

Docling-serve proves unreliable or too heavy for the deployment, its OCR proves inadequate on real scanned submissions, or an extraction requirement appears that the service form cannot satisfy.

## MVP Impact

**MVP Required, P1.** Tracked as IR-107, inside the ADR-013 Week 7 timebox. It blocks IR-89.

That budget was already described as optimistic in ADR-013, and this work sits inside it. If the timebox binds, ADR-013's pre-committed fallback is unchanged: ship abstract-level semantic search, which needs neither this nor chunking.

## SaaS Impact

One more container per tenant instance under [ADR-005](005-instance-per-tenant.md). Extraction throughput scales by replica count rather than per-worker memory.

## Security Impact

**Favourable, and a reason to prefer this over the alternatives.** Docling-serve runs on-premise, so PDF bytes — including unpublished theses and pre-filing IP disclosures — never leave the deployment. This carries none of the third-party transmission exposure that gates ADR-015, and the external-AI-transmission gate in `security/SECURITY.md` §8 does not apply to it.

The structured output is stored, which means more of the document is persisted in the database than before. It inherits the record's visibility and adds no new access path; retrieval over it is governed by the same `visible_to(user)` predicate as everything else.

## Deployment Impact

None beyond what is already declared. The `docling` service exists in both Compose files with `depends_on` wired, and `DOCLING_API_URL` already defaults to `http://docling:5001`.

> **Amended 2026-09-04, IR-107.** This paragraph said *"`requests` must be added to `backend/requirements/base.txt`, where it is already an unactioned TODO."* **It is not.** `httpx` is already declared there and already used for the ai-gateway call in `apps/ai/tasks.py`; a second HTTP stack for one more call adds a dependency, a failure mode and an exception hierarchy in exchange for nothing. The unactioned TODO is removed rather than actioned. What the requirement meant — a declared HTTP client — holds.
>
> One configuration key is new: `DOCLING_TIMEOUT_SECONDS`, defaulting to 600 and set to 900 on the extraction worker in both Compose files, replacing the `EXTRACTION_TIMEOUT` that was declared there and read by nothing.

## Research Impact

Extraction quality does not affect what the controlled comparison in [ADR-004](004-restart-all-comparison-mode.md) measures — that experiment is of the workflow mechanism. ~~RAG remains a supporting capability, not the thesis contribution.~~ **Superseded 2026-09-04, matching the amendment on [ADR-013](013-chunk-level-rag-pipeline.md#research-impact): RAG is thesis-critical, not merely supporting.**

## Related Requirements

`FR-M3-01` (extraction) · `FR-M3-02` (FTS) · `FR-M4-01` (RAG chatbot) · `NFR-R2` — **ids used as stable labels only.** The SRS is frozen and is not the source for what they mean.

## Related Tasks

IR-107 (this decision) · IR-89 (blocked by it) · task spec `R-01` in [`../architecture-tasks/06-rag.md`](../architecture-tasks/06-rag.md), which predates ADR-013 and describes the three-tier chain.
