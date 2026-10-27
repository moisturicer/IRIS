# ADR-043: A reader's saved Records and reading status belong to their account

## Status

**Proposed** — 2026-10-15 (IR-566, under IR-553). **Awaiting approval by a named person.**

IR-566 lists four things to settle before it is ready for an agent. This ADR settles one of them, how saves are stored and owned, once it is accepted. The other three are product decisions, set out as open questions in §Open questions with their benefits and drawbacks; this ADR does not make them. IR-566 is built only after acceptance and those answers.

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

1. **A new Django app, `apps/library`, owns the reader's private library.** It is not `apps/records`, which owns institutional workflow, and not `apps/storage`, which holds uploaded files and is slated for removal. Later slices (folders, positions, notes) add to the same app.

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

## Open questions

These are product decisions for the team. They are listed here because IR-566 names them, and each changes what IR-566 builds.

### Q1 — Likes (the Star button)

| Option | Benefits | Drawbacks |
|---|---|---|
| **A. Account-backed and private**: a boolean on `SavedRecord`, or its own table | Follows the reader like saves do; no shared-PC leak | Two near-identical gestures (Star and Save) both stored, so readers must learn the difference; more API and UI surface to test |
| **B. Retired**: Star is removed and Save covers it | One gesture; less to build and explain; IR-553 already says no public popularity count is added, so a Like has no other use | Readers lose a quick "I liked this" with no folder attached; existing stars need IR-579's import or are dropped |
| **C. Stays browser-only and labelled** | Nothing to build now | Keeps the shared-PC leak for Likes, which the IR-553 spec says to end |

### Q2 — Reading history

| Option | Benefits | Drawbacks |
|---|---|---|
| **A. Stays browser-only, labelled, and cleared on sign-out** | No new server data about what people read, the most sensitive part of a library; clearing on sign-out ends the shared-PC leak | Does not follow the reader across devices |
| **B. Account-backed** | Follows the reader | Stores a reading log on the server. IR-557 must then promise never to use private reading as a discovery signal, and its retention needs its own decision |

### Q3 — Calls & Conferences saves

The IR-566 ticket proposes keeping them out of scope. They stay in `lib/opportunityLibrary.ts`, still labelled browser-only, unless the team adds them explicitly.

### Q4 — Who accepts this ADR

The ticket asks for a named person. That is not an agent's call (CLAUDE.md §What AI does not decide).

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
- **IR-572 (folders) builds on this app and model.** A reader's own folders are additive, so they need their own membership table. That is IR-572's design, not this ADR's.

## MVP Impact

Small and additive: one app, one table, three endpoints and a store. Discover and My Library keep their current controls; only where the data lives changes.

## SaaS Impact

None. IRIS is CIT-U only (PRODUCT.md).

## Security Impact

- New endpoints: an object-level owner filter on every query, and `visible_to` on every Record they touch.
- A saved Record that is now hidden discloses nothing beyond the id the reader supplied.
- The shared-PC leak of saves ends for new saves; Q2 decides history.

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
