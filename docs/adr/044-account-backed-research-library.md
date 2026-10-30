# ADR-044: A reader's saved Records and reading status belong to their account

## Status

**Accepted** — 2026-10-30 by Lee Jasmin Adolfo (IR-566, under IR-553). Proposed 2026-10-15.

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

IR-553's later slices all assume an account-owned library: folders (IR-572), resume reading (IR-573), saved research shaping For you (IR-575), importing old browser saves (IR-579) and notes (IR-580). IR-566 is the first slice, and it needs a persistence decision before any of them.

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

7. **New saves stop writing to `localStorage`. Existing browser keys are left untouched**, because IR-579 imports them with the reader's explicit choice. Reading them here would quietly hand one person's browser data to whoever signs in next, which is the bug this ADR exists to fix.

## Product decisions

Decided 2026-10-30. Each changes what IR-566 builds.

### Q1 — Likes (the Star button): **retired**

The Star button is removed and Save covers it. Existing stars in `iris_starred_records` are left untouched; IR-579 offers them for import as saves.

| Option | Benefits | Drawbacks |
|---|---|---|
| A. Account-backed and private | Follows the reader; no shared-PC leak | Two near-identical gestures to store, explain and test |
| **B. Retired (chosen)** | One gesture; less to build and explain; IR-553 adds no public popularity count, so a Like has no other use | Readers lose a quick mark with no folder; stars survive only through IR-579 |
| C. Browser-only and labelled | Nothing to build | Keeps the shared-PC leak IR-553 says to end |

### Q2 — Reading history: **browser-only, cleared on sign-out**

History stays in `iris_reading_history`, labelled browser-only, and IR-566 clears it on sign-out and on an account switch, which ends its shared-PC leak. Moving between devices is served by account-backed Reading status here and by IR-573's per-Record position, not by a history log.

| Option | Benefits | Drawbacks |
|---|---|---|
| **A. Browser-only, cleared on sign-out (chosen)** | No server-side log of what people read, the most sensitive part of a library, so no new retention, access or deletion duty under the Data Privacy Act; reversible — server history can be added later | Papers opened but never saved do not follow the reader |
| B. Account-backed | Follows the reader | A server-side reading log needing a retention rule, a deletion control and IR-557's promise never to use it as a discovery signal; hard to undo once collected |

### Q3 — Calls & Conferences saves: **out of scope**

They stay in `lib/opportunityLibrary.ts`, labelled browser-only, and keep their shared-PC leak until a follow-up ticket moves them. A Calls save reveals far less about a reader than a paper library does, and including them would add a second model and API to this slice.

### Q4 — Who accepts this ADR: **Lee Jasmin Adolfo**, 2026-10-30.

## Alternatives Considered

- **Keep `localStorage`, but key it by user id.** This stops the next person on a shared PC from seeing your saves. It still does not follow the reader to another device, which is User Story 1, and anything kept in a browser is still readable by anyone with access to that browser profile.
- **A separate `ReadingStatus` table beside `SavedRecord`.** This would allow a status on an unsaved Record. Today's interface has no such state, since a status *is* a folder you save into. It also needs a cross-table rule to keep one status per Record, where a nullable column gets that for free.
- **Store saves on `Record` as a many-to-many.** This puts private reader data on the institutional model that `apps/records` owns. Every Record query would then carry a join that has nothing to do with the workflow.
- **Store the library as one JSON document per user.** Idempotent per-Record writes, the uniqueness rule and visibility filtering all become application code over a blob. Concurrent edits from two devices also overwrite each other.

## Decision Rationale

- One row per owner and Record makes the ticket's two invariants database constraints: saved once, at most one status.
- Taking the owner only from authentication, and rechecking visibility on every read, keeps the library inside CLAUDE.md's two security rules: an object-level check on every endpoint, and one visibility predicate everywhere.
- Leaving the browser keys untouched keeps the migration a reader's explicit act (IR-579) rather than a silent transfer of one browser's data to whoever is signed in.

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
