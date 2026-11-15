# ADR-070: A reader's own folders follow the account — owner-only, holding saves, never a discovery signal

## Status

**Accepted** — 2026-11-16 by Lee Jasmin Adolfo (verbally; relayed and recorded by Hermoine Zozobrado on IR-572). Built in IR-572 ([PR #827](https://github.com/moisturicer/IRIS/pull/827)). Proposed the same day. [ADR-044](044-account-backed-research-library.md) §Consequences left the design of folders to IR-572 ("a reader's own folders are additive, so they need their own membership table"). Three product choices were made for IR-572 by Hermoine Zozobrado on 2026-11-16: names are unique per account and creating an existing name returns that folder (§3), an account holds at most 10 folders with names of at most 60 characters (§3), and folders made in a browser before this change are hidden, not shown read-only, until IR-579 imports them (§7). The rest follows from ADR-044.

## Context

Since IR-566 a reader's saves and Reading status belong to their account (ADR-044), but their own folders stayed in `localStorage` under `iris_record_collections`. That kept both problems ADR-044 was written to fix: folders made on a lab PC are not there at home, and the next person to sign in on that PC sees them. ADR-044 §Security Impact records the leak as remaining "for Folders until IR-572".

IR-553's acceptance criteria for IR-572 are: folders are owner-only, and membership is unique per folder and Record; removing a Record from a folder never unsaves it and never counts as "Not interested"; creating, renaming and deleting are idempotent, and deleting a folder never deletes saves; My Library's folder views read from the server and roll failures back visibly.

## Decision

1. **Folders live in `apps/library`.** `LibraryFolder(owner, name, created_at, updated_at)`, and `FolderMembership(folder, saved_record, added_at)`, unique on `(folder, saved_record)`. The owner cascades, so removing an account removes its folders and everything filed in them. A deleted Record cascades through its saves, so it leaves every folder.

2. **A folder holds saves, not Records.** A membership points at the reader's `SavedRecord`, so:
   - **filing an unsaved Record saves it first**, with no Reading status, in the same request — as the browser menu already did;
   - **unsaving takes the Record out of every folder**, by cascade;
   - **taking a Record out of a folder, or deleting the folder, never touches the save** or its Reading status, and never writes a `DiscoveryDismissal` ("Not interested", IR-576).

   Because a save is unique per owner and Record, `(folder, saved_record)` is unique per folder and Record, as IR-553 asks.

3. **Names and bounds.** A name is trimmed, required, and at most **60 characters** (the same bound as a saved feed). It is **unique per account ignoring case**, which the database enforces (`unique_library_folder_name`, on `Lower(name)` and owner), as it does for saved feeds. An account holds at most **10 folders** (`MAX_FOLDERS`, one constant); the eleventh is refused with `400 folder_limit`, and the limit is listed with the folders so the interface never hard-codes it. Two readers may use the same name.

4. **The API.** The owner always comes from authentication; no body or URL names one.
   - `GET /api/v1/library/folders/` lists the reader's folders, oldest first, each with `record_ids` (newest filing first), and `limit`.
   - `POST /api/v1/library/folders/` with `{name}` creates a folder (`201`). **Creating a name the reader already has, ignoring case, returns that folder with `200`**, so a retry or a second click never makes a second one. That is what makes creation idempotent.
   - `PATCH /api/v1/library/folders/<id>/` with `{name}` renames it. Renaming to its own name, in any case, is a `200`; to another of the reader's folders' names, a `400`.
   - `DELETE /api/v1/library/folders/<id>/` deletes it and its filings. It is a `204` whether or not the folder exists or is the caller's: it removes only the caller's own rows, and discloses nothing.
   - `PUT /api/v1/library/folders/<id>/records/<record_id>/` files a Record (`201`, or `200` if already filed) and answers `{folder, save}`.
   - `DELETE /api/v1/library/folders/<id>/records/<record_id>/` takes it out (`204` always, as above).

   Another reader's folder answers a rename or a filing with a `404` byte-for-byte identical to a missing one. **Filing rechecks `Record.objects.visible_to(user)`**: a Record the reader cannot read is the same `404` as a missing one, and nothing is saved or filed. A filed Record that later becomes unreadable stays in `record_ids` by its id alone — the id the reader supplied — and the saves list shows it as `{record_id, available: false}` (ADR-044 §4). Removing it needs no visibility check, as unsaving does not.

5. **Folders are never a discovery signal.** No app outside `apps/library` and the account-data registries (§6) may name the folder models; a guard test scans every app. No folder write invalidates For you. A save that filing creates is a save, and shapes For you as any save does (IR-575); the filing itself does not. Folders are not in Django admin and write no `AuditEvent`.

6. **The reader's data rights cover folders.** Account deletion deletes them (`deletion/registry.py`). The personal-data export has a `folders` section: each folder's name and the papers filed in it, with a paper's title only while the reader may read it.

7. **The interface reads folders from the server.** Folders join the one account-scoped library store (ADR-044 §6): loaded with the saves in one read, so a reader is never shown their saves with their folders quietly missing; cleared on every session change; and every answer that lands after an account switch is dropped. Renaming, deleting, filing and taking out are optimistic and roll back visibly with a `role="alert"` message. Creating waits for the server, which names the folder. Once the account holds the most folders it may, "New folder" is not offered and the Save menu says why.

   **Folders made in a browser before IR-572 are not shown, and `iris_record_collections` is left byte-for-byte for IR-579's import.** This is ADR-044 §7 applied to folders: reading them would hand one person's browser folders to whoever signs in next.

## Alternatives Considered

- **A client-chosen folder id** (`PUT /folders/<uuid>/`), with duplicate names allowed. A retry reuses the id, so it is idempotent too, and two folders could share a name. Rejected: a double click before the first answer carries two ids and makes two folders, it adds a pattern no other library endpoint uses, and a reader with two "Methods" folders cannot tell them apart.
- **Membership pointing at the Record**, beside the save. Then "unsave takes it out of every folder" and "a folder holds saved papers" become application code in two places, and a membership can outlive its save.
- **No folder limit, or saved feeds' 10.** No limit leaves nothing to stop a script making thousands of rows. 10 was chosen over a larger bound: it matches saved feeds, and the constant can move later.
- **Show old browser folders read-only, labelled "in this browser only", until IR-579.** Nothing would disappear from view, but the next person on a shared PC would still see them, which is the leak IR-572 exists to end.
- **One JSON document of folders per account.** The uniqueness rule, visibility filtering and per-filing idempotency would all become code over a blob, and two devices would overwrite each other (ADR-044 §Alternatives).

## Decision Rationale

- Pointing a membership at the save turns three acceptance criteria into database behaviour: unique per folder and Record, unsaving empties every folder, and removing from a folder cannot unsave.
- Case-insensitive unique names make idempotent creation the same rule a reader already sees on saved feeds, with no new key for the client to hold.
- The owner filter and the `visible_to` check are ADR-044's, so folders add no new access path to reason about.

## Consequences

- **A reader who made folders in a browser does not see them until IR-579 ships.** Their saves and statuses are already in the account (IR-566); only the grouping waits. IR-579 has to merge browser folders by name, since the account allows one folder per name, and the browser allowed duplicates.
- **IR-579 must respect the limit.** An import that would exceed 10 folders has to say so and let the reader choose.
- **The access matrix now fires the library's cells.** They were declared from IR-566 on but no test ran them (`test_access_matrix.py` had no `library` case). IR-572 adds that case; every declared library cell passed when it was first fired.
- **The migration only adds two tables.** It was run forward, back and forward on a database seeded by `seed_demo` with saves in it (docs/testing/traceability/IR-572.md).

## MVP Impact

Small and additive: two tables, three routes, and folders moved into the existing store. Discover's Save menu and My Library keep their controls; only where folders live changes.

## SaaS Impact

None. IRIS is CIT-U only (PRODUCT.md).

## Security Impact

- New endpoints: an owner filter on every query, a `404` identical to a missing folder for anyone else's, and `visible_to` on every Record filed.
- A filed Record that becomes unreadable discloses nothing beyond the id the reader supplied.
- The shared-PC leak ends for folders. It remains only for reading history until IR-756 (cleared on sign-out since IR-566) and for Calls & Conferences saves.

## Deployment Impact

One migration (`library/0005`). No new service, setting or secret.

## Research Impact

None on the thesis workflow or retrieval. Folders are not a recommendation signal (§5).

## Related Requirements

- IR-553 User Stories 2–4 and 7.
- PRODUCT.md §Capabilities (the browser-only wording this changes).

## Related Tasks

- IR-572 (this slice). IR-566 (saves, ADR-044), IR-575 (saves in For you), IR-576 (Not interested), IR-579 (importing old browser saves and folders).
