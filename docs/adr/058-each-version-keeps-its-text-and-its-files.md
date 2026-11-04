# ADR-058: Each Version keeps its text and its files

## Status

**Accepted** — 2026-11-04. Decided by Hermoine Zozobrado in a design session reviewing the review-workspace prototype against the code, and transcribed by an agent. §2 is built by IR-872, and §2's amendment below records the decisions made while building it. §1 and §3 are not built.

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
- **Earlier Versions on existing data can't be compared.** Only Versions submitted after this change have text.
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

IR-868 (records this decision). Implementation needs its own issues.
