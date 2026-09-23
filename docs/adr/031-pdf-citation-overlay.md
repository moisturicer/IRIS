# ADR-031: Citation regions reach the wire; the manuscript is servable again

## Status

Accepted — 2026-09-23.

**Answers the question [ADR-025](025-figures-and-formulas-in-extraction.md) left open**, without superseding it: ADR-025 found that "the citation overlay has never been built" and that three modules justified their behaviour by reference to it, and explicitly declined to build it, leaving it "worth building, as its own effort." This is that effort's first half — the data reaching the client. The reader (IR-335, not yet started) is the second half.

## Context

Three things converged to make a citation unusable, discovered while implementing a PDF reader for the paper view:

**The manuscript link has been dead since 2026-09-09.** `RecordSerializer` serializes `abstract_file` as Django's stored `FileField.url` — a `/media/abstracts/<name>.pdf` path. IR-152 removed both the nginx `/media/` location block and Django's `DEBUG` `static()` route, for a real reason: `RecordUpload.file` derives its filename from the upload, so serving `/media/` unauthenticated made every thesis readable at a guessable URL. But `abstract_file` was not audited in that pass, and it was never routed through an authorized view the way uploads and record files were. The result: every "View Paper" button, and every citation link that appended `?page=N`, has pointed at a URL nothing has served in any environment since IR-152 — confirmed by reading `frontend/nginx.conf` and `config/urls.py` directly, not inferred. `RecordDetailSerializer.get_files` had the identical defect: `f.file.url` for the same reason, while `RecordUploadDownloadView`/`RecordFileDownloadView` already existed as the authorized path and nothing pointed at them.

**The rectangles a citation would highlight exist and go nowhere.** `apps/ai/chunking/document.py::BoundingBox` and `ChunkSet.page_sizes` are populated end to end by the Docling adapter (IR-107, IR-113) and persisted on every `DocumentChunk.bboxes`. But `apps/ai/retrieval/ports.py::RetrievedChunk` — the value every retrieval path returns — carries only `source_page`, never the rectangles. `Citation` (`apps/ai/answers/citations.py`) is built from `RetrievedChunk` and inherits the same gap. So a fully-extracted, fully-chunked corpus with real bounding boxes on every element still produces a wire response that can only say *which page*, never *where on it*.

**Generation streams as one line, not as it is written.** IR-325 gave `LLMProvider` a `stream()` method, and IR-326/IR-329 built the SSE endpoint and the frontend renderer around it. But IR-321's resilience decorators (`RetryingLLMProvider`, `CircuitBreakingLLMProvider`, `FallbackLLMProvider`) were written before `stream()` existed and implement only `generate()`, so every configured provider inherits the port's buffering default: open the whole generation call, wait for it to finish, yield the entire answer as a single delta. `ChatStreamView`'s own docstring records this as a known limitation. The event-by-event narration a reader sees — "searching," "found," "thinking" — is real, but the words of the answer itself still arrive in one burst, against the real configured model.

**The AI Overview paid for every page view.** `PaperAiOverview` calls `/ai/ask/` from a `useEffect` on mount, with no cache anywhere — every visit to a record's page is a full retrieval-and-generation cycle against a corpus-wide question, for an answer that is a pure function of the record's own extracted text and cannot have changed since the last view.

None of these four is the citation overlay ADR-025 declined to build. All four are preconditions a reader (this session's, or IR-335's) needs regardless of whether the eventual UI draws boxes with an overlay or crops a figure — a citation has to open a servable PDF, at a real page, and it helps to know where on that page, generated affordably, delivered as it is written.

## Decision

**Make citation data complete on the wire, fix the servable-file gap, make streaming genuinely stream, and cache the one answer that is a pure function of a record.** No frontend reader is built by this ADR — IR-335 is.

1. **`apps/ai/regions.py`** (new, pure, no Django) converts a chunk's stored `bboxes` — PDF points, top-left origin — into fractions of the page (0–1), normalized against `ChunkSet.page_sizes`. A rectangle is **withheld, not sent as a guess**, in four cases: it is flagged `degenerate` (zero-area, `apps/ai/repositories.py::serialize_regions`'s own flag); its page has no recorded size to normalize against; it is malformed; or it is inverted/zero-area even unflagged. A coordinate a few points past the trim edge is clamped, not dropped — that is measurement noise on a real passage, not a wrong one. A chunk that survives with zero regions still sends its `page`; a reader still opens at the right page and simply draws nothing on it. This mirrors the closed-failure-mode style ADR-025 §Decision already chose for Figures: nothing invented, an honest absence over a plausible-looking wrong answer.

2. **`RetrievedChunk` and `Citation` both gain `regions`.** `apps/ai/retrieval/two_stage.py` and `degraded.py` populate them from `chunk.bboxes` / `chunk_set.page_sizes`; `reranking.py`'s reorder now rebuilds each entry with `dataclasses.replace(candidate, score=score)` instead of naming every field by hand, which is what keeps this the last time a field added to `RetrievedChunk` needs a matching edit in three places to survive a decorator. `apps/ai/presentation.py` puts normalized `regions` on every passage and citation reaching `/ai/ask/`, `/ai/ask/stream/` and `/ai/search/`. `apps/ai/conversations.py::_resolve_citation` re-resolves regions from the live chunk on every replay — the same re-resolution ADR-019 already applies to the quote text, for the same reason: a stored citation is a pointer, and a re-chunk can tombstone the chunk it pointed at.

3. **`RecordViewSet.manuscript`** (`GET /records/<id>/manuscript/`) serves the paper inline (`Content-Type: application/pdf`, `Accept-Ranges: bytes`, no attachment disposition), resolved through `Record.objects.visible_to(user)` exactly as every other record action is (IR-153) — a reader without access gets the same 404 as a missing record, never a 403 that would confirm it exists. It reuses `download_service.resolve_record_download_file`, the same file-picking logic the existing download-request flow already has. `RecordDetailSerializer.abstract_file` now reports this endpoint's URL (or `null`, via a new cheap `has_record_download_file` existence check that does not open a file handle) instead of the dead `/media/` path; `get_files` points at the pre-existing authorized `RecordFileDownloadView` instead of `f.file.url`, closing the identical defect there.

4. **`RetryingLLMProvider`, `CircuitBreakingLLMProvider` and `FallbackLLMProvider` gain `stream()`.** The rule every one of the three follows: **retry and failover happen only before the first delta is yielded.** `_open_stream()` starts the wrapped stream and pulls exactly one delta before returning control to whichever guard (retry loop, breaker, provider list) wraps it — so a failure at connection time (a bad key, an exhausted quota, a dropped socket before any token arrives) is retried or switched on exactly as `generate()`'s failures already are, and a failure *after* a delta has reached the reader propagates immediately, because retrying or switching there would either repeat text already on their screen or start a second answer underneath it. The circuit breaker records success or failure around *opening* the stream, not around fully consuming it — a provider that produced a first token is not the down provider the breaker exists to stop calling. `GroundedAnswerService` additionally now catches `CircuitOpen` alongside `LLMUnavailable` on both `answer()` and `answer_stream()`, so a tripped breaker degrades to the unavailable state (ADR-008) instead of surfacing as an unhandled 500.

5. **`RecordOverview`** (new model, one row per record) caches the AI Overview, keyed for invalidation on the active `ChunkSet.content_hash` and a `prompt_version` constant. `apps/ai/overview.py::overview_for` returns the cached row when both still match, and otherwise generates through `composition_root().answer_service(record=record)` — **scoped to the record**, not the corpus-wide question `PaperAiOverview` used to ask — and stores the result. An `unavailable` answer is never cached: it is a condition that passes, and caching it would leave the paper's summary blank long after the vendor came back. `GET /api/v1/ai/records/<id>/overview/` is the endpoint, resolved through `visible_to(user)` like every other record read; one row serves every reader because every passage in it comes from the record the reader already opened, so there is no narrower view a second reader could need.

## Alternatives Considered

**Build the PDF.js citation overlay now, in the same effort.** Rejected for exactly the reason ADR-025 gave: it is a substantial, separable frontend build (worker setup, virtualized page rendering, coordinate-to-pixel mapping at arbitrary zoom, keyboard and screen-reader accessibility for the highlighted region), and building it blind — before the wire even carries regions — would mean guessing the shape it consumes rather than being handed one. This ADR is what lets that build start from a real, tested contract instead of a stub. Tracked as IR-335.

**Leave `bboxes` in PDF points and normalize client-side.** Rejected. The client would need `ChunkSet.page_sizes` as a second fetch per citation to make sense of a rectangle, duplicating a computation IRIS can do once, server-side, in a unit (fractions of the page) that is correct at any zoom without the client knowing the PDF's native point dimensions at all. Keeping the conversion in `apps/ai/regions.py`, pure and independently tested, is also what makes "which rectangles never got sent, and why" a property the backend test suite can assert without a browser.

**Fix only the manuscript link, and leave regions and streaming for a later ticket.** Rejected. All three were found while building the same reader, are each individually small, and each is independently a real defect blocking a reader today — the manuscript link has been silently dead for two weeks, and the streaming gap has sat behind a docstring since IR-326. Splitting them into separate tickets would mean re-deriving the same context three times for defects a single PR fixes cleanly.

**Cache the AI Overview in Redis rather than a model.** Rejected. The cache needs to answer "is this still valid" against a fact that changes rarely and matters permanently (which chunk set this was generated from), which is exactly what a row with a foreign key and a hash column is for; a TTL-based cache would either expire a still-valid summary and pay to regenerate it, or outlive a re-chunk and serve a stale one. A database row is also inspectable in the admin and survives a Redis flush, which a purely operational cache should not need to.

## Decision Rationale

Every one of the four fixes removes a gap between what the backend already computes and what a caller can observe: the rectangles were already extracted, the file was already stored, the streaming port already existed, and the overview's answer was already deterministic given the corpus. None of the four decisions introduces new inference, a new vendor call shape, or a new visibility rule — `visible_to(user)` gates the manuscript endpoint and the overview endpoint exactly as it already gates retrieval (ADR-014's one-predicate rule, restated in CLAUDE.md §Rules "Security"), and the streaming fix changes only *when* text already being generated reaches the reader, not what is generated or from what sources.

## Consequences

**Positive.** A citation can now be followed to a servable PDF at the right page, with the data to eventually highlight the exact passage. Generation against the real configured model streams token by token rather than arriving as one delayed burst. The paper view's AI Overview costs one vendor call per record's lifetime between re-chunks, not one per page view.

**Negative / accepted.** `regions` on the wire is dead weight until IR-335 draws it — this ADR ships a contract with no consumer yet, deliberately, per the "answers reach the wire" framing above. `RecordOverview` adds a table and a migration for a cache whose invalidation is coarse: any re-chunk regenerates the whole overview even if the change was cosmetic (e.g., new front-matter exclusion) rather than substantive. Streaming's retry-only-before-first-delta rule means a failure that happens to land right after the first token is treated identically to one that happens after the whole answer — no partial retry — which is the same trade-off IR-328's partial-Turn persistence already accepts for a client disconnect.

## MVP Impact

None. Extends existing Ask IRIS and paper-view surfaces; no new user-facing screen ships from this ADR alone.

## SaaS Impact

The overview cache is a real cost reduction per tenant: a record viewed repeatedly no longer re-runs retrieval and generation on every view.

## Security Impact

**The manuscript endpoint is a new file-serving surface — resolved through `visible_to(user)`, the same predicate every other record read uses, with a 404 (not 403) on refusal, per CLAUDE.md §Rules "Security": never expose a file path that bypasses Django's permission layer.** No new CORS, no new public port, no change to authentication. Regions reaching the wire disclose no new information a citation did not already carry — the quoted text itself is a stronger disclosure than a rectangle's coordinates.

## Deployment Impact

One new migration (`ai/0014`, `RecordOverview`, replacing the unused `DocumentSummary` placeholder). No new service, no new container, no new environment variable.

## Research Impact

Directly relevant — RAG is thesis-critical as of 2026-09-04 (CLAUDE.md §Repository, ADR-013 §Research Impact amended). Genuine token-by-token streaming and a servable manuscript are both part of Ask IRIS's core interaction; regions on the wire are the foundation IR-335's citation reader is evaluated against.

## Related Requirements

FR-M3-01, FR-M3-02 — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-334 (this ADR) · IR-335 (the PDF.js reader and overlay this ADR's regions feed, not yet started) · IR-152 (the `/media/` removal this corrects the missed edge of) · IR-107, IR-113 (the extraction and chunking work whose rectangles this finally exposes) · IR-321 (the resilience decorators this extends with `stream()`) · IR-325, IR-326, IR-329 (the streaming path this closes the last gap in) · ADR-025 (the citation-overlay question this answers the data half of).
