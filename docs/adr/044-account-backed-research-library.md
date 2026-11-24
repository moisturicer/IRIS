# ADR-044: A reader's saved Records and reading status belong to their account

## Status

**Accepted** — 2026-10-30 by Lee Jasmin Adolfo (IR-566, under IR-553). Proposed 2026-10-15. Q3 (Calls & Conferences saves) is replaced by [ADR-050](050-calls-for-papers-and-rdco-confirmation.md), Accepted 2026-11-01 and not built yet: saved Calls follow the account and appear in My Library.

IR-566 listed four things to settle before it is ready for an agent: how saves are stored and owned (§Decision), and three product decisions — Likes, reading history and Calls & Conferences saves. The team answered all three on 2026-10-30; they are recorded in §Product decisions with the options that were weighed.

## Context

A reader's library lives in the browser today, not the account. `frontend/src/lib/recordLibrary.ts` keeps three `localStorage` keys:

| Key | Holds | Surfaces |
|---|---|---|
| `iris_record_collections` | Folders of Record ids: the three reading-status folders (Want to read, Reading, Completed; at most one per Record) and the reader's own folders | Discover's Save menu (`PaperSaveDropdown`), My Library |
| `iris_starred_records` | Starred Record ids. The IR-553 spec calls these Likes | Discover's star button, My Library |
| `iris_reading_history` | The last 50 visits, with titles copied in | My Library's history |

Calls & Conferences keeps its own saves the same way (`lib/opportunityLibrary.ts`).

This has two consequences IR-553 names:

- **It does not follow the reader.** A paper saved on a lab PC is not there at home.
- **It leaks between people.** `localStorage` belongs to the browser's origin, not to whoever is signed in. On a shared PC, the next student to sign in sees the previous student's saved papers and history. Every surface says "stored in this browser only" (PRODUCT.md §Capabilities, IR-410), which is honest about the first problem but does nothing about the second.

IR-553's later slices all assume an account-owned library: folders (IR-572), resume reading (IR-573), saved research shaping For you (IR-575), importing old browser saves (IR-579) and notes (IR-580). IR-566 is the first slice, and it needs a persistence decision before any of them. *(Changed by the amendment of 2026-11-16 (IR-579) below: deleted, not imported.)*

## Decision

1. **A new Django app, `apps/library`, owns the reader's private library.** It is not `apps/records`, which owns institutional workflow, and not `apps/documents`, which owns uploaded files. Later slices (folders, positions, notes) add to the same app.

2. **One table to start: `SavedRecord`.**

   | Field | Notes |
   |---|---|
   | `owner` | FK to the user, `on_delete=CASCADE`: removing an account removes its library |
   | `record` | FK to `Record`, `on_delete=CASCADE` (see §Consequences) |
   | `reading_status` | Nullable: Want to read, Reading or Completed. A governed vocabulary, so it joins `apps/tests/test_enum_vocabulary.py`'s guard |
   | `saved_at`, `updated_at` | Timestamps |

   It is unique on `(owner, record)`, so a Record is saved at most once per reader. A single nullable column means a Record has at most one reading status, which the database enforces with no extra check. Setting a status saves the Record, as moving it into a status folder does today, and unsaving clears the status with it.

3. **The owner always comes from authentication.** No request body or URL carries an owner. Every queryset starts from `SavedRecord.objects.filter(owner=request.user)`, so another reader's saves are never addressable. A save that is not yours reads exactly like one that does not exist.

4. **Every read and write rechecks the Record against the single visibility predicate**, `Record.objects.visible_to(user)` (CLAUDE.md §Security).
   - **Saving a Record you cannot read is refused** with a 404, identical to a missing Record, so the endpoint cannot be used to probe for hidden ones.
   - **A saved Record you can no longer read is listed only as unavailable.** The response carries its id, which you supplied yourself, and `available: false`. No title, author or status of the hidden Record is returned.

5. **The API is idempotent:**
   - `PUT /api/v1/library/saves/<record_id>/` with an optional `reading_status` creates or updates the save.
   - `DELETE` removes it; deleting what is not there is still a 204.
   - `GET /api/v1/library/saves/` lists the reader's saves, resolved through `visible_to`.

   Repeating any request leaves the same state, which is what lets the interface retry and roll back without double counting.

6. **The interface keeps one account-scoped cache.** Discover, the Record page and My Library all read and write one store keyed by the signed-in user's id.
   - Updates are optimistic, and a failure rolls back visibly with a message, never silently.
   - Logout or an account switch clears the store.
   - Every request carries the id of the account that made it, so a response that lands after the switch is dropped rather than shown to the next person.

7. **New saves stop writing to `localStorage`. Existing browser keys are left untouched**, because IR-579 imports them with the reader's explicit choice. Reading them here would quietly hand one person's browser data to whoever signs in next, which is the bug this ADR exists to fix. *(Changed by the amendment of 2026-11-16 (IR-579) below: deleted, not imported.)*

## Product decisions

Decided 2026-10-30. Each changes what IR-566 builds.

### Q1 — Likes (the Star button): **retired**

The Star button is removed and Save covers it. Existing stars in `iris_starred_records` are left untouched; IR-579 offers them for import as saves. *(Changed by the amendment of 2026-11-16 (IR-579) below: deleted, not imported.)*

| Option | Benefits | Drawbacks |
|---|---|---|
| A. Account-backed and private | Follows the reader; no shared-PC leak | Two near-identical gestures to store, explain and test |
| **B. Retired (chosen)** | One gesture; less to build and explain; IR-553 adds no public popularity count, so a Like has no other use | Readers lose a quick mark with no folder; stars survive only through IR-579 *(changed 2026-11-16, IR-579: deleted, not imported)* |
| C. Browser-only and labelled | Nothing to build | Keeps the shared-PC leak IR-553 says to end |

### Q2 — Reading history: **browser-only, cleared on sign-out** (reversed by §Amendment — 2026-11-01)

History stays in `iris_reading_history`, labelled browser-only, and IR-566 clears it on sign-out and on an account switch, which ends its shared-PC leak. Moving between devices is served by account-backed Reading status here and by IR-573's per-Record position, not by a history log.

| Option | Benefits | Drawbacks |
|---|---|---|
| **A. Browser-only, cleared on sign-out (chosen)** | No server-side log of what people read, the most sensitive part of a library, so no new retention, access or deletion duty under the Data Privacy Act; reversible — server history can be added later | Papers opened but never saved do not follow the reader |
| B. Account-backed | Follows the reader | A server-side reading log needing a retention rule, a deletion control and IR-557's promise never to use it as a discovery signal; hard to undo once collected |

### Q3 — Calls & Conferences saves: **out of scope**

They stay in `lib/opportunityLibrary.ts`, labelled browser-only, and keep their shared-PC leak until a follow-up ticket moves them. A Calls save reveals far less about a reader than a paper library does, and including them would add a second model and API to this slice.

### Q4 — Who accepts this ADR: **Lee Jasmin Adolfo**, 2026-10-30.

## Amendment — 2026-11-01 (IR-756): reading history follows the account

**Accepted** 2026-11-01 by Lee Jasmin Adolfo.

**What this supersedes.** Q2 above chose browser-only history, cleared on sign-out. **That choice is reversed.** A paper a reader opens on a lab PC without saving it should be findable at home. Reading status and IR-573's position do not cover that case, because readers rarely save what they open. The privacy cost Q2 named is accepted under the rules below. Q2's sign-out clearing still ships in IR-566 and closes the shared-PC leak until IR-756 lands.

1. **History lives in `apps/library`**, one row per owner and Record. A revisit updates `viewed_at`. Only the 50 most recent are kept per owner. Owner and Record cascade.
2. **Only the reader can see it.** The owner always comes from authentication. There is no staff endpoint, no Django admin registration and no `AuditEvent`.
3. **A visit is recorded only by an explicit, idempotent `PUT /api/v1/library/history/<record_id>/`** sent by the paper view. It is never a side effect of `GET /records/<id>/`, so reviewers, the AI Overview and prefetches record nothing. A Record the reader cannot see is refused with a 404, as in §4.
4. **Reads go through `visible_to`.** A visit to a Record the reader can no longer read shows only as unavailable. No title is copied into the browser.
5. **Clear history deletes the rows**, not just hides them.
6. **History is never a discovery signal.** No For you, ranking or count reads it, as IR-557 promised. A guard test fails if a recommender reads the model.
7. **The reader can pause history.** `LibraryPreferences.keep_history` defaults to on and is created lazily. It is toggled in the History view beside a notice that history is stored on the account and only the reader sees it. Pausing stops new entries and keeps existing ones. The server enforces it: the `PUT` returns 204 and records nothing. *(The toggle is removed by the amendment of 2026-11-24 b (IR-1331) below; the server setting stays.)*
8. **Existing browser history is never uploaded automatically.** IR-579 offers it for import with saves and stars, for the same reason as §7. *(Changed by the amendment below: it is dropped, not offered.)*

## Amendment — 2026-11-16 (IR-756): old browser history is dropped, and the account-data rules

**Status of this amendment: Accepted** — 2026-11-16, when IR-756's PR (#828) merged after Ashlee's review, as relayed by Hermoine Zozobrado. Decided by Hermoine Zozobrado, 2026-11-16, while building IR-756.

1. **Point 8 above now matches IR-579's card: browser history is never imported.** The paper view stops writing `iris_reading_history`, and nothing reads it. The wipe on every sign-in, sign-out and session end stays (Q2), so the shared-PC leak stays closed and whatever an older build left goes at the next one. Importing it would hand one browser's list to whoever signs in, the bug this ADR exists to fix, and a history of 50 recent papers refills on its own within days.
2. **Deleting an account deletes its reading history and its `LibraryPreferences`.** The personal-data download lists them: a `reading_history` section, with each paper's id and when it was last opened, and its title only while the person may still read it; and a `library_preferences` section with `keep_history`. History is the reader's own data, so it goes back to them and goes with them, as notes and highlights do.
3. **The History view is reached from the Saved papers Folder picker.** Point 7 puts the pause switch there, and IR-776 had removed History from My Library while it was browser-only. The picker is the one control every reader has, author or not, so History is an option in it again.

## Amendment — 2026-11-16 (IR-579): old browser saves, folders and stars are deleted, not imported

**Status of this amendment: Accepted** — 2026-11-16 by Lee Jasmin Adolfo, as relayed by Hermoine Zozobrado, after IR-579's PR (#839) merged with Ashlee's review. Decided by Hermoine Zozobrado, 2026-11-16, while building IR-579. It replaces IR-579's import, which Hermoine Zozobrado had accepted earlier the same day on the card.

**Why.** §7, Q1 and ADR-070 §7 left `iris_record_collections` (the pre-IR-566 status folders and the reader's own folders) and `iris_starred_records` (stars) untouched so that IR-579 could offer them for import. **IRIS has had no readers**: the browser library was never released, so the only browsers holding these keys are the team's development and test machines. An import (a preview resolved through current permissions, selection, a per-account import identity, retries) would protect data nobody needs, and every day the keys stay is a day the next person on that browser could be handed them.

1. **Both keys are deleted, never read, uploaded or imported.** The auth store deletes them on every sign-in, sign-out and session end, together with `iris_reading_history` (the amendment above), through one function, `clearOldBrowserLibrary()` in `frontend/src/lib/recordLibrary.ts`.
2. **Nothing reads or writes them any more**, and no import endpoint, model or preview is built. The browser-only save and folder code was already deleted by IR-566 and IR-572; this removes the last "left for IR-579" comments and the tests that held the keys byte-for-byte.
3. **This supersedes** §7's "IR-579 imports them", Q1's "IR-579 offers them for import as saves" and its table's "stars survive only through IR-579", the Context's "importing old browser saves (IR-579)", the Decision Rationale line about leaving the keys untouched, and ADR-070 §7's and Consequences' references to IR-579's import and its folder limit.

**Alternative considered: build the import as IR-579's card described.** It would keep any pre-account work by the reader's own choice, at the cost of a preview, an import endpoint and its retry identity, and tests for data that exists only on test machines. Rejected for that reason. Were IRIS ever released with a browser library, this choice would need revisiting.

## Amendment — 2026-11-16 (IR-573): where the reader left off follows the account

**Status of this amendment: Accepted** — 2026-11-16, when IR-573's PR (#841) merged after Ashlee's review, as relayed by Hermoine Zozobrado. Decided by Hermoine Zozobrado, 2026-11-16, while building IR-573.

IR-553 asks for a per-Record reading position, keyed by owner, Record and Manuscript identity, and for its retention to be recorded before it is built. These are its rules.

1. **One position per reader and Record, on the bytes it was read on.** `apps/library` keeps `ReadingPosition`: the page and how far down it the top of the reader's view was (a fraction, 0 to 1, which survives a change of zoom or layout), with the Manuscript revision and SHA-256 the server was serving that reader, as a highlight does (ADR-065). Reading on moves the one row. The client only says which revision it was shown; the server refuses a write unless that is still what the reader is served.
2. **A replaced Manuscript never inherits another file's place.** A position is given back only while its identity is still served. It is deleted once no one is served those bytes, which is when the Record's own file and its latest Version's both differ from it: at once when a Record or Version is saved, and on the reader's next open for a path that writes an identity without saving (a maintenance command's `.update()`).
3. **Only the 200 most recently read Records keep a position, per reader.** Decided by the owner on 2026-11-16 over no limit (the e-book reader's way, which keeps a place on a paper read once years ago) and deleting a place left unread for 12 months (which needs a scheduled job). Saving trims the rest, the way history keeps its 50.
4. **Deleting an account deletes its positions,** and the personal-data download lists them in a `reading_positions` section: each paper's page, fraction and when, with its title only while the person may still read it.
5. **Only the current paper keeps a place, and it is put back silently.** An earlier Version opened from the picker is a deliberate comparison, so it opens at its start and saves nothing. A citation, a highlight opened from Notes or `?page=` always wins over resuming, including a citation still being re-read after a reload: the old place is not asked for until it has landed. The paper reopens where the reader left off with no notice, as e-book readers do; the toolbar's page number is the only sign (owner, 2026-11-16).
6. **Saving is bounded and never in the way.** The paper view saves 1.5 s after the reader stops, at most 10 s apart while they keep going, and at once when the tab is hidden or they leave the paper. Nothing is saved until the reader moves or a citation, highlight or `?page=` lands them somewhere, so a failed read never overwrites a place with page 1; following a citation counts as reading there. A save the server refuses because the paper was replaced (409) or is no longer readable (404) stops saving for that visit. A save started in one session is never sent in the next, and a failed one leaves the reader as it was.
7. **Never a discovery signal.** As for history (point 6 of the 2026-11-01 amendment): not in Django admin, no `AuditEvent`, no staff endpoint, and a guard test keeps every other app, `core` and the AI runtime from naming it. Draft and review reading keeps a place like any other, and nothing else can see it.

## Amendment — 2026-11-24 (IR-1324): History opens from Recently opened, not from the folders

**Status of this amendment: Accepted** — 2026-11-24, when IR-1324's PR (#1009) merged after Ashlee Sean's review, as relayed by Hermoine Zozobrado. Decided by Hermoine Zozobrado on 2026-11-24, while building IR-1324: History was to be removed from Saved Papers, and this keeps point 7's controls reachable.

1. **This replaces point 3 of the IR-756 amendment.** IR-1324 replaces Saved Papers' Folder picker with folder tiles, and History is not a folder.
   - **An author** opens the History view from **Manage history** under the Overview's *Recently opened*, which already shows the top of that list. Its back link returns to the Overview.
   - **A reader with no Overview** opens it from **Manage reading history**, beside *Saves and folders follow your account* on Saved Papers.
2. **Nothing else changes.** Point 5 (Clear history deletes the rows) and point 7 (the reader can pause history, with the notice) still apply. *(Changed by the amendment of 2026-11-24 b (IR-1331) below: History is a pop-up, cleared by choice, with no pause.)* Their controls stay in the History view, and every reader, author or not, can still reach it.

## Amendment — 2026-11-24 b (IR-1331): History is a pop-up, cleared by choice, with no pause

**Status of this amendment: Proposed.** Decided by Hermoine Zozobrado on 2026-11-24 (option C of three weighed in chat), while building IR-1331. It becomes Accepted when IR-1331's PR merges after review.

**Why.** History opened inside the *Saved Papers* tab, so the tab highlight jumped there from the Overview and History looked misplaced.

1. **History is a pop-up.** *Manage history* under the Overview's *Recently opened*, and *Manage reading history* on Saved Papers for a reader with no Overview, open it over the page, and the tab does not change. This replaces the 2026-11-24 amendment's History view.
2. **Compact rows.** Each paper the reader opened is one row: a tick box, its title, wrapping rather than cut (DESIGN.md's Full Text Rule), as a link that opens the paper and closes the pop-up, and the day it was opened. A paper the reader can no longer read is a row with no title and no link, so it can still be cleared (§4 still holds: nothing about it is disclosed).
3. **Clearing is by choice, and asked twice.** The reader ticks papers, or *Select all*, then *Clear history*, which asks once more and names how many. Only the ticked rows are deleted, through `POST /library/history/remove/` with `{"record_ids": [...]}`: owner-scoped, one transaction, the same 204 whatever the ids name, and a 400 for anything but 1 to 50 integer ids, so a mistake never reads as "clear everything". Point 5 of the IR-756 amendment (the rows are deleted, not hidden) still applies. `DELETE /library/history/` stays on the server, unused by the screens.
4. **There is no pause control.** This reverses the *toggle* in point 7 of the IR-756 amendment. The server keeps `LibraryPreferences.keep_history` and still refuses to record while it is off, so nothing already stored changes meaning. A reader who paused before IR-1331 sees *History is paused* in the pop-up with **Turn history back on**, so nobody is left paused with no way out.

| Option | Benefits | Drawbacks |
|---|---|---|
| A. History in place on the Overview tab | Smallest change; the highlight stays put | No address; the Overview shows two different things; readers keep a different path |
| B. A History tab | An address that survives a reload; one path for every reader | A sixth tab for authors, so the bar scrolls sooner on a phone |
| **C. A pop-up (chosen)** | Never leaves the page the reader was on; one pop-up for authors and readers | A long list is shown in a dialog; no address of its own |

**What this gives up.** A reader can no longer stop history being kept; they can only clear what was kept, paper by paper or all at once. That is a privacy control removed, which the reviewer should weigh.

## Alternatives Considered

- **Keep `localStorage`, but key it by user id.** This stops the next person on a shared PC from seeing your saves. It still does not follow the reader to another device, which is User Story 1, and anything kept in a browser is still readable by anyone with access to that browser profile.
- **A separate `ReadingStatus` table beside `SavedRecord`.** This would allow a status on an unsaved Record. Today's interface has no such state, since a status *is* a folder you save into. It also needs a cross-table rule to keep one status per Record, where a nullable column gets that for free.
- **Store saves on `Record` as a many-to-many.** This puts private reader data on the institutional model that `apps/records` owns. Every Record query would then carry a join that has nothing to do with the workflow.
- **Store the library as one JSON document per user.** Idempotent per-Record writes, the uniqueness rule and visibility filtering all become application code over a blob. Concurrent edits from two devices also overwrite each other.

## Decision Rationale

- One row per owner and Record makes the ticket's two invariants database constraints: saved once, at most one status.
- Taking the owner only from authentication, and rechecking visibility on every read, keeps the library inside CLAUDE.md's two security rules: an object-level check on every endpoint, and one visibility predicate everywhere.
- Leaving the browser keys untouched keeps the migration a reader's explicit act (IR-579) rather than a silent transfer of one browser's data to whoever is signed in. *(Changed by the amendment of 2026-11-16 (IR-579) below: deleted, not imported.)*

## Consequences

- **Record deletion cascades.** A deleted Record disappears from every library, while a Record that is withdrawn or restricted stays listed as unavailable. To the reader, a deleted Record looks the same as one that never existed, which matches how the rest of the API treats a missing Record.
- **The "stored in this browser only" wording goes** wherever saves become account-backed: `PaperSaveDropdown`, `SavedView`, IR-410's Saved note and PRODUCT.md §Capabilities. The design-system document records the change in the same PR, as IR-566 requires.
- **The migration only adds a table.** It is still run against a copy of a realistic database before merge (CLAUDE.md §Migrations).
- **A reader's own Folders stay in the browser until IR-572.** Between IR-566 and IR-572 the Save menu holds account-backed saves and Reading status beside browser-only Folders, labelled as such, so Folders keep the shared-PC leak for that interval. IR-572 should follow IR-566 directly.
- **The Star button goes** (Q1), and reading history is cleared on sign-out (Q2).
- **IR-572 (folders) builds on this app and model.** A reader's own folders are additive, so they need their own membership table. That is IR-572's design, not this ADR's.

## MVP Impact

Small and additive: one app, one table, three endpoints and a store. Discover and My Library keep their current controls; only where the data lives changes.

## SaaS Impact

None. IRIS is CIT-U only (PRODUCT.md).

## Security Impact

- New endpoints: an object-level owner filter on every query, and `visible_to` on every Record they touch.
- A saved Record that is now hidden discloses nothing beyond the id the reader supplied.
- The shared-PC leak ends for new saves and for reading history (cleared on sign-out). It remains for Folders until IR-572 and for Calls & Conferences saves until their follow-up.

## Deployment Impact

One migration. No new service, setting or secret.

## Research Impact

None on the thesis workflow or retrieval. IR-575 later reads saves as a recommendation signal, and only through `visible_to`.

## Related Requirements

- IR-553 User Stories 1–4 and 7.
- PRODUCT.md §Capabilities and Constraints (the browser-only wording this changes).

## Related Tasks

- IR-566 (this slice); IR-572, IR-573, IR-575, IR-579 and IR-580 build on it.
- IR-410 (My Library); IR-117 (the server-side library card nobody wrote).
