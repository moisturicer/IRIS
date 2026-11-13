# Accepted PDF sources — IR-831

Delivery contract: [IR-831](https://citiris.atlassian.net/browse/IR-831), under the approved [Publish specification, IR-830](https://citiris.atlassian.net/browse/IR-830). This extends Django's current ingestion path. It adds no scanner, vendor transmission, AI-owned ingestion writer or deployment authorization.

## Validation and deployment profile

Authorize before inspecting content. Manuscript creation/replacement, slot uploads, requested documents and PDFs filed through general office attachments use `pdf_upload_problem`. General attachments keep their existing non-PDF format policy. PDF filename, declared PDF/generic/missing MIME, original bytes and the 50 MiB bound must agree. Application storage names are generated; `Record.manuscript_filename` retains the display name separately.

The web process streams at most 50 MiB into a private temporary directory and hashes those original bytes. An isolated Python subprocess parses objects with pypdf. It rejects unreadable/zero-page and encrypted PDFs, JavaScript, launch/form submission actions, embedded files, XFA and rich media. Ordinary links and automatic internal page navigation remain valid. Traversal visits indirect references once per action context, includes unreferenced/xref-stream objects, and bounds depth and object/edge visits. Content streams are not expanded for text extraction here.

The subprocess has a hard Linux address-space limit. Its parent kills and waits for it at the wall deadline. Standard output/error go to the null device; only fixed exit codes cross back. Timeout, memory exhaustion, traversal refusal, unsupported enforcement and child crashes cannot accept a file. Temporary bytes are removed on exit. This is PDF-content validation, not a malware verdict.

Explicit candidate profile (also in `backend/.env.example`):

| Setting | Value |
| --- | ---: |
| `PDF_VALIDATION_WALL_SECONDS` | 10 |
| `PDF_VALIDATION_MEMORY_MIB` | 256 |
| `PDF_VALIDATION_MAX_PAGES` | 1000 |
| `PDF_VALIDATION_MAX_OBJECTS` | 200000 |
| `PDF_VALIDATION_MAX_DEPTH` | 100 |

All limits must be positive and finite; integer limits must be integers. Partial/invalid configuration fails startup. With all five absent, startup reports `documents.W001` and PDF intake refuses processing. Non-Linux systems report `documents.W002` and also refuse processing. The example is a verified local candidate, not approval of production capacity or enablement. Tests supply a separate explicit synthetic profile.

Apply the additive migrations before starting this release's web/worker processes. Drain or stop old unfenced extraction/chunk workers before admitting revisioned uploads; mixed old-worker/new-writer operation is unsupported. Restart workers on the same release. Existing legacy queue messages handled by the new worker cannot process a revisioned source without its pin. No rollout was performed for this ticket.

## Review text: a sandbox child that returns data (IR-871)

Each Version's review text (ADR-058 §1 as amended) is read by `apps/records/review_text/reader.py`, in a subprocess shaped like the one above: an isolated interpreter, an environment of only `PATH` and `LANG`, a private temporary directory as its working directory, standard output and error to the null device, and a hard address-space, page and wall limit of its own (`REVIEW_TEXT_WALL_SECONDS`, `_MEMORY_MIB`, `_MAX_PAGES`). It runs in a Celery worker, never in the web process.

**Unlike the upload check, its output crosses back,** so the rule above, "only fixed exit codes cross back", doesn't hold for it. It writes the text as JSON in its temporary directory. The parent reads that only after a clean exit, caps it at 32 MiB, checks its shape and stores it. The parent also checks that the bytes it handed over hash to the Version's recorded SHA-256. This was decided in IR-871's review (Hermoine Zozobrado, 2026-11-05).

The risk is a parser taken over by a crafted PDF copying something it can read into the text reviewers see. The child closes that path itself before it parses anything (`reader.confine`):

1. It opens its input and output first.
2. It imports every module a read loads.
3. It caps `RLIMIT_NOFILE` at its lowest free descriptor.

From then on every open, socket or pipe fails with `EMFILE`. That covers the worker's environment under `/proc` and every other paper's file. `test_review_text_sandbox.py` proves both on Linux.

**What is left:** the child still runs as the worker's OS user, so a flaw that reached an already open descriptor, or a kernel interface that needs none, isn't covered. Running it as a separate unprivileged user would close that, and is a deployment change not made here. A CMap file pdfminer would load from disk, which a few non-Latin fonts need, now fails closed as *no text*.

## PDF evidence: the second child that returns data (IR-1053)

Each Manuscript's PDF evidence (ADR-067 decision 4) is read by `apps/documents/pdf_evidence/reader.py` in a child built the same way as the review text reader: isolated interpreter, `PATH` and `LANG` only, a private temporary directory, output to the null device, and confined by the same three steps before it parses. Its own limits are `PDF_EVIDENCE_WALL_SECONDS` and `PDF_EVIDENCE_MEMORY_MIB`; its page cap is `PDF_VALIDATION_MAX_PAGES`, and it is handed no file above the 50 MB upload cap. It runs in the extraction worker, after the vendor read. The parent reads the JSON only after a clean exit, caps it at 64 MiB and checks its exact shape. Any refusal stores an empty document naming the reason, and extraction still completes. With both `PDF_EVIDENCE_*` unset, `manage.py check` warns (`documents.W003`) and no evidence is read; with only one set, or a value that is not finite and positive, Django refuses to start. `apps/documents/pdf_evidence/tests/test_sandbox.py` proves the confinement on Linux. What is left is the same as for the review text reader.

## Persistent identity and handoff

The existing Record writer commits `abstract_file`, a fresh opaque `manuscript_revision` UUID, `manuscript_sha256` and the display name in one database transaction. The digest attests the original upload, separately from `PdfExtraction.content_hash`, which hashes normalized extraction output. Clients cannot set the digest or revision. An unchanged same-Record upload retains its file/revision and queues nothing. A refused replacement changes nothing.

`PdfExtraction` keeps the source revision and immutable storage name plus an attempt UUID. Replacement clears old text, structure, normalized hash, extractor, error, completion time and claim. Extraction messages carry `(record_id, revision)` and are published after commit. Claims/results lock Record then PdfExtraction. Success, failure and retry recheck both source and attempt under that lock; a superseded, removed or deleted source writes nothing. Old unpinned messages cannot process a revisioned source. Duplicate completed deliveries reuse their result.

Chunk messages also carry the revision. The chunk task locks the same Record/extraction through activation and scheduling, so replacement cannot race the swap. Persisted `ChunkSet.source_revision` identifies the source consumed; embedding handoffs pin that revision and chunk-set ID and refuse inactive/replaced sets. Existing outbound disclosure guards remain in force. Supplementary uploads remain outside the research corpus by `DocumentKind`, independent of upload route.

While an owner prepares an unsubmitted revised Manuscript, its current extraction is pending with `phase=awaiting_submission`; it is not sent to the Extractor and the submitted paper's active chunks remain in place. Submission switches extraction/indexing to the new source. Version rows preserve source identity for restoration. Accepted source files are never deleted as part of replacement.

## Reader contract and recovery

Owner-only `GET /records/<id>/metadata-suggestions/` retains `state`, legacy `suggestions` and `source`; it adds `manuscript_revision`, `phase` and `retryable`. `queued`, `reading`, `retrying` and `awaiting_submission` are pending. `ready` may contain no suggestions. Final `failed` is retryable by an authorized explicit action, never by ordinary task redelivery.

IR-833 adds `fields`: per title, abstract, authors, keywords and publication year, a `value`, its `basis`, `page`/`region` only when the stored structure records them, `auto_apply` (a title or abstract within its limit, nothing else) and `exceeds_limit`. Authors, keywords and year come only from labelled front matter; ambiguous ones are absent. Publish fills only empty or placeholder fields, records each field's decision in owner-only `Record.metadata_sources`, and saves Details with `expected_details_revision`, which the record update refuses with `409 stale_edit` when a newer save exists. Foreground polling backs off to 15 s and stops after two minutes with *Check again*; it replaces the earlier 90-second limit. See [IR-833](../testing/traceability/IR-833.md).

`POST /records/<id>/retry-extraction/` accepts `manuscript_revision`, is owner-only, locks/rechecks the source, refuses stale revisions with 409, and requeues only a terminal failure. It refuses an unsubmitted revision. Upload extraction status omits parser errors, storage paths, fingerprints and task IDs. Refusals return safe field errors.

Historical attachments retain null revisions/blank original-byte digests until deliberately processed by a canonical intake/backfill. This does not claim historical duplicate coverage or retrospectively validate stored bytes. Phase migration maps existing status rows to truthful phases without reading or changing source files.

## Transfer to the later AI-owned ingestion program

Move the accepted-source contract, not a second writer: carry the opaque revision, original-byte digest, immutable source pointer and validation policy/profile into the target ingestion job. Every result and activation must compare that revision under the target writer's own fence. Django continues to own attachment authorization, version/submission and disclosure decisions until the approved migration transfers ownership. Retire the current writer at cutover rather than letting Django and the AI runtime update the same extraction dataset. IR-738 and malware work IR-666 remain separate, non-blocking workstreams.

## Verification

`apps/documents/tests/test_bounded_pdf.py` exercises real child processes with deliberately small page, traversal, memory and wall limits, encryption including empty-password, parsed active content and ordinary links/navigation. `test_accepted_source.py` exercises authenticated upload/status, consistent acceptance across four routes, preserved replacements, idempotent bytes, owner-only retry and removal. Its PostgreSQL workers use independent connections to complete/fail/retry A after B and inspect current output plus downstream source binding.

The implementation PR records the representative-paper profile, realistic-copy migration evidence, focused/full-suite results and known limitations. The candidate profile must be rechecked on the deployment's legitimate corpus before enabling intake there.
