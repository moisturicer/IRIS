# ADR-064: A reader's private notes on a Record — owner-only, kept when access is revoked, and never silently overwritten

## Status

**Proposed** — 2026-11-12 (IR-580, under IR-553), awaiting acceptance by Lee Jasmin Adolfo. The note retention rule (§Decision 6) is the "decision before ready-for-agent" on IR-580; it was written into the IR-580 spec by Jive Tyler I. Revalde. This ADR records it and the choices that follow from it. Nothing in it is authorised until it is accepted.

> **Amended 2026-11-24 ([IR-1326](https://citiris.atlassian.net/browse/IR-1326); decided by Hermoine Zozobrado; Proposed until its PR merges after review).** Notes are kept only on a **published** paper, and never in Review. See *Amendment — 2026-11-24*.

## Context

IR-553 gives a reader a private library in their account ([ADR-044](044-account-backed-research-library.md)). Its User Stories 10–11 and 20 add **private notes** typed beside a paper in the reading workspace. A note is the reader's own writing, so three things matter more than they do for a save or a reading status:

- **Trust in what was typed.** A reader who sees "Saved" must be right, and two devices must never silently overwrite each other.
- **Privacy.** A note can say what the reader really thinks of a paper, a supervisor or a lab. Staff, the Record's owners and other readers must not be able to read it, and nothing that draws on reader data (recommendations, discussion, review, vendor prompts) may use it.
- **Access that changes under it.** A Record can be withdrawn, restricted or embargoed after a reader wrote about it. The spec asks what happens to the note.

## Decision

1. **A note lives in `apps/library`, one per reader and Record.** `ReadingNote(owner, record, body, revision, created_at, updated_at)`, unique on `(owner, record)`. Owner and Record cascade, as for `SavedRecord` (ADR-044 §2): removing an account removes its notes, and a deleted Record removes its notes. Writing a note does not save the Record.

2. **The owner always comes from authentication.** Every queryset starts from `ReadingNote.objects.filter(owner=request.user)`. There is no staff endpoint, no Django admin registration and no `AuditEvent`. A note that is not yours reads exactly like one that does not exist.

3. **Every call rechecks the Record against `Record.objects.visible_to(user)`**, the single visibility predicate (CLAUDE.md §Security), including `DELETE`. A Record the reader cannot read answers a `404` identical to a missing Record, so the endpoint cannot be used to probe for hidden ones.

4. **The API:**
   - `GET /api/v1/library/notes/<record_id>/` returns `{body, revision, updated_at}`. A Record the reader can read but has not written on returns `{body: "", revision: 0, updated_at: null}` and creates nothing, so `404` only ever means "not readable".
   - `PUT /api/v1/library/notes/<record_id>/` takes `{body, base_revision}`. If `base_revision` equals the stored revision (`0` when there is no note), it stores the body, increases `revision` by one and returns the note. Otherwise it returns **`409`** with `{code: "revision_conflict", body, revision}` — the server's current text — and **writes nothing**.
   - `DELETE` removes the note; deleting what is not there is a `204`.
   - `body` is at most **20,000 characters**; more is a `400` and writes nothing. An empty body is stored (the row and its revision stay), so conflict detection survives a cleared editor.

5. **A conflict keeps both texts.** The interface keeps the reader's draft, shows it beside the server's text, pauses autosave and lets the reader edit one text and save it against the new revision. There is no automatic merge and no last-writer-wins.

6. **Retention.** A reader's note text is **kept when their access to the Record is revoked**, and a note carries no source quotation. IR-580 stores only what the reader typed. A quotation of the paper is not part of this ADR: when IR-583 (highlights) adds one, it is withheld whenever the Record is unreadable, while the reader's own text stays. Consequences of keeping the text:
   - while access is revoked the reader cannot read, change or delete the note either (§3), and it returns unchanged if access is restored;
   - nothing lists notes, so a revoked Record's note is not shown as "unavailable"; IR-580 adds no list;
   - **text the reader pasted from the paper stays in the note.** IRIS cannot tell a quotation from the reader's own words, and does not try.

7. **Notes are never a signal and never an input.** No app outside `apps/library` and the account-data registries (deletion and export, §8) may name the note model: a guard test scans every app, so a new surface that reaches for notes fails the day it is written. That covers `apps/ai`, the discovery recipe (ADR-062 §5), `apps/reviews`, `apps/notifications` and public discussion. Ask IRIS and Paper Chat do not read notes. Letting a note become AI context is a separate, explicit, per-note choice in a later IR-553 slice and needs its own decision.

8. **The reader's data rights cover notes.** Account deletion deletes them (`deletion/registry.py`). The personal-data export includes each note's text and revision (`personal_data/registry.py`), with the Record's title only while the reader may read it.

9. **The draft is never stored in the browser.** Autosave sends the text to the server and the editor holds the draft in memory. `localStorage` is not used (ADR-044 §7 and its shared-PC finding). The status line reads **Saving**, **Saved** or **Could not save**, with a Retry after a failure. A failure keeps the draft and never shows Saved. Closing the browser tab or reloading with an unsaved draft asks first (`beforeunload`).

## Amendment — 2026-11-24: published papers only, and none in Review

**Status: Proposed.** It is accepted when IR-1326's pull request merges after review. Decided by Hermoine Zozobrado on 2026-11-24, in chat. Transcribed by an agent. It narrows §3 (the Record gate).

**The problem.** In Review, selecting text offered both *Comment*, which is shared and part of the review ([ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §7), and *Highlight*, which is private and goes nowhere. The two look alike on the PDF, so a reviewer could think they had flagged a passage for the authors when they hadn't. Highlight's optional note also went to Notes, which Review doesn't open.

**The decision.**
1. **Only a published paper takes notes.** The server's gate is `annotatable(user)`: `Record.objects.visible_to(user)` narrowed to `pipeline_status = published`. A draft or a paper in review answers the same `404` as a missing Record, to its owner too. This is the rule Ask IRIS already follows ([ADR-052](052-each-paper-states-its-embargo-and-a-person-ends-it.md) as amended for IR-1252).
2. **Nothing is deleted.** A note on a paper that is not published, or one sent back to review after it was, is kept and withheld, as §6 keeps one whose access is revoked, and it returns when the paper is published.
3. **Review shows none.** The selection menu offers no *Save highlight* there and no private highlight is drawn, so selecting text in Review is for a review comment alone. Notes is not offered there, as before.

**Cost.** An author or Adviser can no longer keep private notes or highlights on their own draft or a paper in review; review comments are the tool for that stage.

## Alternatives Considered

- **Several notes per Record.** More flexible, but IR-580 asks for "a focused editor, not a grid of cards", and every extra note is another row to reconcile on two devices.
- **Last write wins, with a timestamp.** Simple, and the ticket forbids it: the reader would lose text without knowing.
- **Merge both texts automatically.** Two edits to one paragraph have no correct merge, and a wrong one is silent.
- **Delete a note when access is revoked.** Matches "no access, no data", and destroys the reader's own writing because an office restricted a paper.
- **Let the reader reach their note regardless of access.** Kinder, but it breaks the one-visibility-predicate rule and can be used to confirm that a hidden Record exists.
- **Keep a local draft in `localStorage`** to survive a crash. It would show the next person on a shared PC what the last one wrote.

## Decision Rationale

- One row per owner and Record, with `revision` compared on every write, makes "no invisible overwrite" a rule of the write rather than of the page.
- The same owner filter and `visible_to` check as ADR-044 means a note adds no new access path to reason about.
- Keeping the text, and withholding only a quotation, protects the reader's work without giving the paper's content to someone who may no longer read it.

## Consequences

- **Navigating inside IRIS with an unsaved draft is not guarded.** The browser's own leave warning does not fire for in-app navigation, and the router in use offers no blocker the page tests can run under. Leaving the paper sends one last best-effort save; if that fails the draft is lost without a warning. Closing the panel, switching to Ask IRIS and changing section all keep the draft, because the page holds it. A navigation blocker is a follow-up.
- A reader cannot delete a note on a Record they can no longer read. It stays until access returns or the Record or account is deleted.
- Pasted excerpts survive revocation (§6). Anyone who needs those removed must delete the account.
- The reading layout needs a second occupant of its panel slot (Ask IRIS is the only one today), built in the same change.
- `ReadingNote` joins the account-deletion and personal-data registries, whose tests fail until it is declared.

## MVP Impact

Small and additive: one table, one URL, one panel.

## SaaS Impact

None. IRIS is CIT-U only (PRODUCT.md).

## Security Impact

- New endpoint: an owner filter and `visible_to` on every call; no staff path.
- A hidden Record's note discloses nothing: the same `404` as a missing Record.
- Notes sit outside every shared surface: discussion, review, recommendations, notifications and vendor prompts (§7).

## Deployment Impact

One migration. No new service, setting or secret.

## Research Impact

None on the workflow or retrieval. Notes are not an evaluation signal.

## Related Requirements

- IR-553 User Stories 10–11 and 20.

## Related Tasks

- IR-580 (this slice); IR-583 (highlights, which may add a quotation); ADR-044, ADR-062 §5.
