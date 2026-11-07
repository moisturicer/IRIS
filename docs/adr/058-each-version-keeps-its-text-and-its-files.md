# ADR-058: Each Version keeps its text and its files

## Status

**Accepted** — 2026-11-04. Decided by Hermoine Zozobrado in a design session reviewing the review-workspace prototype against the code, and transcribed by an agent. §2 is built by IR-872, and §2's amendment below records the decisions made while building it. §1 is amended 2026-11-05 (IR-871): a Version's text for review is read on campus without AI, apart from the LlamaParse Extraction. §1 as amended is built by IR-871, and the build notes under it record the decisions made while building it. §3 is not built.

**Amends:**

- [ADR-013](013-chunk-level-rag-pipeline.md): the manuscript extraction belongs to a Version, not to the Record. Chunking and retrieval still read only the latest submitted Version's extraction.
- [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §5: a Version also names the documents that were current when it was submitted.

**Supersedes** [`../review_workspace_roadmap.md`](../review_workspace_roadmap.md) Phase 2 and its open decision #4 (text retention).

**Used by** ADR-032 §7's review-thread amendment of 2026-11-04: anchors, Outdated threads, the suggested-wording check and the Changes tab all need text that doesn't change once its Version exists.

## Context

ADR-032 §5 made a Version a snapshot of what was under review. Observed in the code on 2026-11-04, it records only part of that:

- **The manuscript's text is overwritten.** `PdfExtraction.record` is a `OneToOneField` (`apps/documents/models.py:146`). A new Version's extraction replaces the previous one, and `restore_submitted_manuscript` deletes every extraction but the submitted one (`apps/records/versions.py:157-160`). No two Versions can be compared, and a passage a reviewer commented on can't be found again after the next Version.
- **The other documents aren't tied to a Version.** `RecordVersion` names the manuscript file and nothing else (`apps/records/models.py:427-470`). Each required document (`RecordUpload`) has its own per-slot counter (`apps/documents/models.py:45-68`), so "Consent form v2" says nothing about which paper Version it went with. Office files (`RecordFile`) aren't versioned at all.

So "what exactly did the reviewers see at v2?" has no answer today. That is the question a disputed decision raises, and the history ADR-003 measures.

**IRIS never edits the manuscript** (ADR-032 §7, amendment of 2026-11-04). A revision is a new PDF the author makes elsewhere, so everything below reads the uploaded files. Nothing writes to them.

## Decision

### 1. Version text

- **The extraction belongs to the Version it was made from.** `PdfExtraction` gains a link to the `RecordVersion` it was extracted for, and a Version that changes the manuscript gets a new extraction row. The Record-level one-to-one goes.
- **A metadata-only Version shares the text of the Version before it** and extracts nothing again (ADR-032 §5, "What changed means").
- **AI reads only the latest submitted Version.** The extraction that chunking, Ask IRIS, Paper Chat and the AI Overview read is the latest submitted Version's, as ADR-032 §5's IR-273 amendment already requires. Earlier Versions' text is never chunked, embedded or retrieved.
- **No new extraction calls.** A Version's manuscript is already extracted when that Version is submitted (`submit_new_version`). This decision keeps the result instead of overwriting it, so it costs storage and no extra LlamaParse credits (ADR-056).
- **Kept for the Record's whole life**, published, unlisted or rejected alike. A soft-deleted Record keeps it under the same rule as its other review history. IRIS never deletes review history (IR-256).
- **Withdrawing a revision deletes no Version's text.** `restore_submitted_manuscript` may still delete an *unsubmitted* upload's extraction, which belongs to no Version, and nothing else.
- **Versions from before this change aren't reconstructed.** Their text was overwritten, so they read *"vN's text was not kept"*, and comparing with them is unavailable. Nothing is guessed.
- **Scanned or failed extractions say so.** A Version with no usable text shows *"No text for vN, so it can't be compared"*, never an empty comparison.

**Amendment, 2026-11-05 (IR-871; decided by Hermoine Zozobrado, Accepted). Review text is read on campus, without AI.**

§1 assumed a Version's text was its LlamaParse Extraction. Since IR-882 (ADR-052 as amended 2026-11-04), every paper starts embargoed and LlamaParse waits until the Adviser or RDCO releases it, so a paper under review has no Extraction at all. IR-882's build notes in ADR-052 left this open for this ADR. It is settled here:

1. **Review text is not the Extraction.** Each Version that changes the manuscript gets its own **review text**: its sections (heading and page) and passages (text, page and regions in ADR-031's shape). It is read from that Version's own manuscript PDF with pdfplumber and plain rules. This replaces §1's "the extraction belongs to the Version it was made from". Everything else §1 says about a Version's text applies to the review text: a metadata-only Version shares the previous one's, it is kept for the Record's life, withdrawing a revision deletes no Version's, and a scanned or unreadable PDF reads *"No text for vN"*.
2. **It is read at submission, whatever the embargo or AI consent says.** Nothing leaves the server and no model is called, so neither ADR-052's gate nor ADR-054's consent concerns it. The extraction gate already applies only to Extractors that leave campus. It runs in the same bounded worker sandbox as upload checks (IR-830), never in a web worker.
3. **The Extraction and the AI path don't change.** `PdfExtraction` stays one per Record. LlamaParse reads the latest submitted Version once it is released, and only that is chunked, embedded and retrieved (ADR-013, ADR-056). Review text is never chunked, embedded or retrieved, and it is served only under `may_read_review` (§4). Review never reads the Extraction, and the AI never reads review text.
4. **Versions from before this change are read from their own files.** This supersedes §1's "Versions from before this change aren't reconstructed" and the Consequence "Earlier Versions on existing data can't be compared". Each existing Version still has its manuscript file (ADR-032 §5), and no file a Version names can be deleted (§2's amendment, point 3). A one-time command reads them as if they had been read at submission. That re-reads the file the reviewers saw, so nothing is guessed. The reason for "not reconstructed" was a paid, off-campus Extractor, and it no longer applies. A Version whose file is missing still reads *"vN's text was not kept"*.
5. **The reader is recorded.** Each review text names the reader's version. Text already stored is never re-read in place, so a Thread's anchor keeps resolving against the text it was checked against. Re-reading with a newer reader is a deliberate command.

**Evidence.** A throwaway prototype (`prototype/pdf-version-comparison`, `backend/apps/reviews/prototype_pdf_comparison/`, 2026-11-05) wrote two Versions of a seeded paper with seven known edits: a changed figure, an added section, a removed paragraph, swapped sections, a renamed section, a corrected table value and an added sentence. It produced them twice, once drawn by a script and once built in Microsoft Word and exported by Word, and it ran the repo's two-column and multi-page table fixtures as well. All 59 checks passed:
- running heads and page numbers removed
- every word and sentence whole
- every sentence's page matching Word's own pagination
- every section's change found, sections pushed onto a later page still unchanged
- Threads found again, or Outdated where their words changed

It was **not** run on a real CIT-U thesis, and it didn't test figures, equations, footnotes, citations, tables without borders, headings that aren't bold or PDFs from other programs. IR-871 runs it on two Versions of a real thesis before merging.

**Alternatives considered:**

- **Upload `.docx` instead of PDF, and make a PDF at the final Decision.** A Word file gives cleaner text and real headings. Rejected:
  - Before conversion there are no pages, so ADR-031's regions, page citations, ADR-048's watermark and §3's "found on p. N" all break.
  - It needs a document converter service.
  - Signed and scanned forms have no Word file.
  - Existing PDFs would need a second path anyway.
  - The prototype found a PDF's text enough on a thesis-shaped paper.
- **Let LlamaParse read Versions under review.** Rejected: it sends an embargoed paper off campus, which ADR-052 forbids until release.
- **Compare in the browser from the PDF viewer's text layer.** It needs no server reading. Rejected: Outdated threads and the suggested-wording check (§3) must run when a Version is submitted, not only when someone opens it.

**Build notes, 2026-11-05 (IR-871; decided by Hermoine Zozobrado while building it, Accepted).** Seven points the amendment left open:

1. **A passage is one sentence**, or one row of a ruled table, with its page, its paragraph number and one region per line. This is the shape the prototype checked, and §3 and ADR-032 §7's anchors work sentence by sentence. *Rejected:* a paragraph with every word's box (about 1 MB per thesis, and §3 rebuilds sentences on every comparison), and a paragraph with line boxes only (a sentence starting mid-line would be highlighted from the line's start). A later change to the sentence rules is a new reader, under point 5 above.
2. **Stored as section rows with their sentences as JSON.** `ReviewText` holds one manuscript file's reading: its state, reason, reader, page count and warnings. `ReviewTextSection` holds one row per section: heading, page, `key` and `text_hash`, with the passages as JSON. No card under IR-870 queries a passage in SQL, while a Viewed mark (IR-877) needs a section the database checks. Each `key` is the heading without numbering (`#2` and on for a repeat, `front-matter` before the first heading). Each `text_hash` hashes the normalised passages, so a later reading can match an unchanged section exactly.
3. **A Version points at its text** (`RecordVersion.review_text`, `RESTRICT`). A metadata-only Version points at the previous Version's, so nothing walks back through Versions and nothing is copied. A Version with no manuscript has none.
4. **Headings are found by numbering and capitals as well as bold**, because headings that aren't bold were never tested. Table-of-contents lines (dot leaders, a trailing page number) and captions are never headings, and a numbered line, a change of case, or a change of font or size starts a new heading rather than continuing one. Running heads and footers are found by repetition across the page's whole width, before columns are split. Both rules were changed after the first real paper (IR-871's traceability file).
5. **A layout the rules don't know never gives a misleading text** (amended 2026-11-06, after the first real paper; decided by Hermoine Zozobrado, Accepted). The university's fields use many formats, and no reader can promise all of them, so the reader fails safe instead:
   - When its sections take a shape no real paper's headings take, the paper is stored as **one `document` section**, and every sentence keeps its page and regions. The warning `sections_unreliable` names the shape: no headings, about as many headings as sentences, one heading repeated, or headings over mostly nothing. Comparing sentences and finding a Thread's quote don't depend on headings, so an unknown layout gets a coarser view, never a wrong one.
   - A heading wraps onto at most three lines.
   - A change of font size starts a new paragraph, so a footnote, caption or block quote is never glued into a body sentence.
   - When more than a fifth of the words have no character behind them (U+FFFD, or pdfminer's `(cid:N)`), nothing is stored and the Version reads *"No text for vN"*. A smaller share is kept and counted (`unmapped_characters`).
   - The other warnings remain: a section over 15 pages, and pages with no text. IR-873 reads them all to say how far a comparison can be trusted.

   Real papers from each college are being collected to grow the rules (IR-871's traceability file); each failure they show becomes a rule and a test, under a new `RULES_VERSION` once any text is stored.
6. **The sandbox has its own limits**, `REVIEW_TEXT_WALL_SECONDS`, `_MEMORY_MIB` and `_MAX_PAGES`, because a layout read does more work than the upload check. Like IR-830's, they are required: with any unset, nothing is read and the text waits as *not read yet*, for `read_review_texts` to retry. `GET /records/<id>/versions/<n>/text/` serves a text under `may_read_review` and is audited as the Version's manuscript is. `versions_payload` carries each Version's text state.
7. **The reader's text is the one sandbox output that crosses back**, against IR-830's "only fixed exit codes cross back" (`docs/engineering/PDF_INTAKE.md`). It has to: the text is the result. To narrow the risk that a parser taken over by a crafted PDF copies something into it, the child opens its input and output first and then caps its own open-file limit, so it can open nothing else: not the worker's environment, not another paper. The parent checks that the bytes it read are the Version's recorded SHA-256 before storing anything. The child still runs as the worker's OS user; a separate unprivileged user would close the rest and is a deployment change left for later.

### 2. A Version names its documents

- **When a Version is written, it records which file was current in each of the Record's upload slots**: one row per slot, pointing at the existing `RecordUpload`. Nothing is copied. `write_version` (`apps/records/versions.py:194`), the one writer of Versions, writes these rows in the same transaction.
- **A document uploaded between Versions joins the current Version.** A document request (ADR-022) doesn't make a new Version, so the signed consent form IERC asked for during v3 is recorded as *added during v3*, with its upload time. The next Version names it as current, if it still is.
- **No file a Version names can be deleted** through the API, which matches ADR-032 §5's rule for the manuscript. A draft's files are free to delete until it is first submitted.
- **Office files (`RecordFile`) stay outside the Version.** They are the office's own review record (ADR-032 §10, IR-474 amendment), not the author's submission, and they keep their existing removal rule.
- **Versions from before this change get a best-guess list** from upload times. Each is labelled *"files reconstructed"*, so it is never mistaken for a record.

**Amendment, 2026-11-04 (IR-872; decided by Hermoine Zozobrado while building it, Accepted).** Five points §2 left open:

1. **An empty slot gets no row.** A Version lists only the documents it had. "Not uploaded at vN" is read from the Record type's slots.
2. **"Added during vN" is read from upload times, not stored.** An upload after vN was submitted, and before vN+1 if there is one, was added during vN. One writer (`write_version`) means no upload path can forget to record it. The times stay true because of point 3.
3. **Nobody deletes what the review relied on, staff included.** Through the API, a file is refused deletion when a Version names it, **or when it answered a document request** (`DocumentRequestItem.upload`), because the requesting party accepted or rejected it. This goes beyond §2's "a Version names", and it holds even for the office override the slot rule allows. The database enforces the first part too: `RecordVersionDocument.upload` is `RESTRICT`, so a bug can't delete a named file, while a Record's own delete still cascades. Only a superuser in Django admin can remove such a file, after unlinking it on purpose.
4. **Every other removal asks first.** Paper View confirms before deleting a document version or an office file, and it offers no Remove at all on a file the server says is kept (`delete_refused`), showing the server's reason instead.
5. **The reconstructed label is one flag per Version** (`RecordVersion.documents_reconstructed`), true for every Version written before IR-872, because within one old Version every row is equally a guess.

### 3. Comparison

- **A pure comparison** (`apps/reviews/comparison.py`) aligns two Versions' texts by section heading, then compares the passages in each section sentence by sentence. Each section reads unchanged, changed, added, removed or moved, and each passage added, removed or changed, with its page and regions in *both* Versions (ADR-031's region format).
- **Normalised before matching:** hyphenation at line breaks, ligatures, whitespace, running heads and page numbers. The source text is kept, and normalisation is only for matching.
- **What can't be aligned is reported** rather than forced into a match.
- **Documents are compared too:** *"Consent form replaced since v2"*, *"Approval sheet unchanged"*.
- **The default comparison** is the Version this reviewer last finished a review on → latest. Without one, it is previous → latest. Any pair can be chosen.
- **The suggested-wording check** (ADR-032 §7, 2026-11-04) asks the comparison whether an accepted suggestion's text appears in the next Version, and it shows *found on p. N* or *not found*. It's a hint and decides nothing.

### 4. Who reads it

Earlier Versions' text, their documents and every comparison are review material under `may_read_review` (ADR-032 §10, IR-479). They never reach Discover, Ask IRIS, public Comments or a non-participant. Serving one is audited as ADR-032 §5 already audits an earlier Version's manuscript.

## Alternatives Considered

**Keep the text only while the Record is under review.** It uses less storage. Rejected: after the Decision, old threads would lose their passage and nobody could check what was reviewed, which is when a dispute is raised.

**Re-extract an earlier Version on demand.** It needs no new storage. Rejected: it spends extraction credits on every look, and a changed extractor would give a different text than the one reviewers commented on.

**Copy each document into Version-owned storage.** It makes every Version self-contained. Rejected for the reason ADR-032 §5 rejected it for the manuscript: it doubles storage for nothing a pointer lacks.

**Version only the manuscript.** It needs nothing new. Rejected: "what did the reviewers see?" stays unanswerable, and Changes can't say that a requested document arrived.

## Decision Rationale

A Version is meant to be the snapshot a review was made against. A snapshot that loses its text at the next Version, and leaves out half the submission, can't support anchored comments, a comparison or a disputed decision. Text and pointers are cheap. The review history is what the thesis studies.

## Consequences

**Positive:**

- Reviewers see what changed since their last review without re-reading the paper.
- Comments stay anchored across Versions, and the response letter can point at the new passage.
- "What did the reviewers see at v2?" has an answer.

**Negative:**

- Storage grows by one extraction for each manuscript-changing Version.
- A migration: the extraction's link moves from Record to Version, and the new link table needs a reconstruction pass over existing Versions.
- ~~**Earlier Versions on existing data can't be compared.** Only Versions submitted after this change have text.~~ Superseded by §1's 2026-11-05 amendment, point 4: earlier Versions are read from their own files, and only a Version whose file is missing can't be compared.
- **Two texts per paper** (§1's 2026-11-05 amendment): review text for every Version, read on campus, and the LlamaParse Extraction for the latest released one. They can disagree about the same page, because they come from two readers.
- Comparison of two typesettings of the same text produces noise. Normalisation reduces it and doesn't remove it.

## MVP Impact

Required by ADR-032 §7's review threads (2026-11-04), which are being built now.

## SaaS Impact

None beyond storage, which grows per institution with its review volume.

## Security Impact

More review material is kept, all under `may_read_review`. The AI path reads exactly what it read before. The authorization matrix (`apps/tests/access/`) gains the comparison and the per-Version document endpoints.

## Deployment Impact

One schema migration and one data migration (reconstructing document lists). Test both against a copy of a realistic database.

## Research Impact

The Changes tab shortens re-review under **both** resubmission policies. ADR-004's comparison must run with it present in both arms. ADR-032 §7's 2026-11-04 amendment records that it is live before any evaluation run.

## Related Requirements

None by `FR-` label.

## Related Tasks

IR-868 (records this decision). IR-872 builds §2. IR-871 builds §1 as amended 2026-11-05 (review text, read on campus). IR-873 builds §3.
