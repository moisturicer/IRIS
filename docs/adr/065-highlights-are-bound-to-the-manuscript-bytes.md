# ADR-065: A reader's highlights are bound to the Manuscript bytes they were made on — stale after a replacement, withheld without access

## Status

**Proposed** — 2026-11-12 (IR-583, under IR-553), awaiting acceptance by Lee Jasmin Adolfo. It completes the retention rule [ADR-064](064-private-reading-notes.md) §6 left open ("when IR-583 adds a quotation, it is withheld whenever the Record is unreadable, while the reader's own text stays"). Nothing in it is authorised until it is accepted.

## Context

IR-553 User Stories 12–13 ask for highlights that keep their meaning: a passage the reader saved from a paper must never end up pointing at different text because the paper was replaced, and must not hand the paper's words to someone who may no longer read it.

A highlight is different from a note in two ways. Its text is **the paper's**, not the reader's, so who may see it is decided by the Record's visibility, not by who wrote it. And its place, a page and rectangles as fractions of that page ([ADR-031](031-pdf-citation-overlay.md)), is meaningful only for the exact bytes it was measured on.

The system already has an identity for those bytes. Every accepted Manuscript upload gets a fresh `manuscript_revision` (UUID) and the SHA-256 of its bytes (`documents.sources.manuscript_changes`), copied onto the `RecordVersion` it is submitted as. Which of them a reader is *served* is `records.versions.served_manuscript` (ADR-032 §5, IR-273): the latest submitted Version's for everyone but an owner whose own revision is not yet submitted.

## Decision

1. **A highlight is its own row in `apps/library`**, `ReadingHighlight(owner, record, manuscript_revision, manuscript_sha256, page, quote, prefix, suffix, regions, created_at)`. It holds source text only. The reader's own words stay in `ReadingNote.body`, which a highlight never touches, and saving one neither creates nor edits a note. Owner and Record cascade, as for notes (ADR-064 §1).

2. **It is bound to the bytes it was made on, and the server decides which bytes those were.** The identity stored is the one the server was serving that reader when they saved (`served_manuscript_identity`). The client never supplies it. It supplies only the revision it was *shown*: the manuscript response now carries `X-Manuscript-Revision`, the reader keeps it, and `POST` sends it back as `manuscript_revision`. If that is no longer what the server serves this reader, the answer is **`409 manuscript_changed`** and nothing is stored. A Record with no recorded identity answers `409 manuscript_unavailable`. So a paper replaced between opening and pressing Save can never take a highlight made on the old one.

3. **A highlight is `current` only while the reader is served exactly that identity** (revision *and* SHA-256). Otherwise it is **`stale`**. Nothing rewrites a stored highlight's identity, page or regions, so it is never attached to new bytes: a stale one is shown as the passage it was, labelled in words as from an earlier version, and is never drawn on the paper now shown. If a `RecordVersion` still holds its bytes, the list names it (`open_version`); the interface opens it there only when the reader may already open that Version, and otherwise says it can't be opened here. Quote, prefix and suffix are bounded as review threads' are (2,000, 500 and 500 characters; at most 50 regions).

4. **Replacement is what makes one stale; re-chunking is not.** IR-583's text says "replaced or re-chunked". A highlight's regions are measured on the PDF's own pages, not on chunks, and re-chunking does not change those bytes, so it cannot re-attach a highlight to different text. The identity therefore does not include a chunk set. If a later change ever moves the bytes without a new revision, the SHA-256 comparison still catches it. *Cost:* a highlight survives re-chunking and re-extraction, which is what the reader would expect.

5. **Access is rechecked every time a quotation or an anchor is presented**, against the one predicate `Record.objects.visible_to(user)`.
   - `GET /library/highlights/<record_id>/` and `POST` on a Record the reader cannot read are the same `404` as a missing Record.
   - `GET /library/highlights/` lists the reader's highlights across Records. One whose Record they can no longer read is listed as `{id, record_id, available: false}` and nothing else — no quote, context, page, regions or state. The ids are ones the reader supplied (ADR-044 §4). This is the unavailable-source indicator.
   - Highlights are kept while access is revoked and come back unchanged if it returns.
   - `DELETE /library/highlights/<record_id>/<id>/` removes the reader's own and answers `204` for anyone else's, a missing one and one on an unreadable Record alike. Removing your own row discloses nothing, and a reader must be able to drop one they can no longer open. This differs from ADR-064 §3, where a note on an unreadable Record can be neither read, changed nor deleted. A highlight on one is withheld source text the reader may want gone, and answering `204` to everything gives no way to tell a hidden Record from a missing one.

6. **Owner only, and never a signal.** The owner always comes from authentication; every queryset starts from `owner=request.user`. No staff endpoint, no Django admin registration, no `AuditEvent`. A guard test fails if any app outside `apps/library` and the account-data registries names the model, as it does for notes (ADR-064 §7). Highlights are not an input to Ask IRIS, recommendations, discussion, review or notifications.

7. **The reader's data rights cover highlights.** Account deletion deletes them. The personal-data export includes each highlight's page and, while the reader may still read the Record, its quotation and the Record's title.

8. **The selection menu is shared.** Selecting text in the reader (or taking find's current match, the keyboard's way to a passage) opens one menu whose actions are data the page hands the reader (`SelectionAction`). IR-583 supplies *Save highlight*; IR-581's *Ask about selection* adds its own entry to the same list. The menu is offered on the current paper only, never on an earlier Version viewed beside it.

## Alternatives Considered

- **Trust the client's page and revision.** Simple, and a forged or stale one would bind a highlight to bytes the reader never saw. Rejected: the server stamps the identity and only verifies the client's claim.
- **Re-attach a stale highlight by searching its quote in the new text** (as review threads are found again, ADR-058). Useful, and exactly the silent re-attachment IR-583 forbids for a *personal* highlight, whose regions would then be drawn on bytes nobody checked. Rejected; a reader can select the passage again.
- **Delete stale highlights.** Tidy, and destroys what the reader chose to keep. Rejected.
- **Include the chunk set in the identity**, so re-chunking marks highlights stale. Rejected in §4: it would invalidate highlights without any change to the bytes they point at.
- **Store the quote in the note.** One table, and it mixes source text, which must be withheld on revocation, with the reader's own, which is kept. Rejected.
- **Keep highlights in `localStorage`.** Rejected for the shared-PC reason of ADR-044 §7.

## Decision Rationale

- Binding to a UUID the server mints on each accepted upload, and checking it on every write, turns "never silently re-attached" into a rule of the write rather than of the page.
- Withholding the whole entry, not only the quote, when the Record is unreadable means the page number and rectangles of a hidden paper's text are not disclosed either.
- Reusing review threads' bounds and region format keeps one selection code path.

## Consequences

- **A replaced paper strands highlights.** They are readable and removable, not openable on the new paper. A reader of a published paper cannot open an earlier Version, so a stale highlight there can only be read.
- **The unavailable list has no screen yet.** `GET /library/highlights/` reports unreadable sources, but no page in this change lists highlights across papers: Notes shows the current Record's, which a reader who cannot read it cannot open. An account-wide Highlights view, which would show the indicator, is a follow-up.
- The manuscript response gains a header, and a `served_manuscript_identity` helper joins `records.versions`.
- `ReadingHighlight` joins the account-deletion and personal-data registries, whose tests fail until it is declared.

## MVP Impact

Small and additive: one table, three routes, one header, one menu.

## SaaS Impact

None. IRIS is CIT-U only (PRODUCT.md).

## Security Impact

- New endpoints: an owner filter on every query and a `visible_to` check before any quotation or anchor leaves; no staff path.
- A hidden Record's highlight discloses only ids the reader supplied.
- A client cannot choose the identity a highlight is bound to.
- Highlights sit outside every shared surface (§6).

## Deployment Impact

One migration (`library/0004`). No new service, setting or secret.

## Research Impact

None on the workflow or retrieval. Highlights are not an evaluation signal.

## Related Requirements

- IR-553 User Stories 12–13.

## Related Tasks

- IR-583 (this slice); IR-581 (adds *Ask about selection* to the shared menu); ADR-064 §6, ADR-044, ADR-031, ADR-058.
