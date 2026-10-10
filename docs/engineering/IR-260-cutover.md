# IR-260 adviser-first cutover

ADR-032 §13 governs this cutover. Every new Proposal, Thesis/Research and Project
enters at its named Adviser. The submit endpoint refuses an absent Adviser or
one who owns the record. The entry service creates the active Adviser
assignment, entry seat, routing event and v1 snapshot together. A later
revision uses `POST /api/v1/records/<id>/new-version/`; `/submit/` accepts only
a draft.

## Before applying the migration

1. Stop backend and worker writes, and make a PostgreSQL backup outside the
   application container. From an operator shell with the deployment's own
   connection settings, use `pg_dump --format=custom --file=iris-before-ir260.dump iris_db`.
   Keep the dump outside the checkout and record its checksum and location in
   the release log. For a seeded development database, retain a separate copy
   before refreshing it.
2. Run `python manage.py list_unassigned_intake` against the database being
   upgraded. It lists active intake work (including a declined intake request)
   lacking an Adviser and records whose Adviser is an owner. Resolve each by
   an explicit human assignment; the migration blocks and lists their IDs
   rather than guessing.
3. Apply migrations with `python manage.py migrate`. `reviews.0014` first
   compares every in-flight record's active and required completed assignments
   and open decline request with the frozen §6 mapping. It reports every
   inconsistent record ID before changing data. Then it converts all six
   legacy in-flight statuses to `in_review` and withdraws
   an active intake assignment with reason `ADR-032: intake retired`, opens an
   Adviser assignment and entry seat, and stores `in_review`. Historical
   `rdco_intake` and `intake` rows remain readable as `Intake (retired)`.
4. Run `list_unassigned_intake` again. Investigate every remaining row before
   reopening writes. Check a migrated record through its API detail and My
   Reviews, then exercise the Proposal, direct Adviser decision and specialist
   route paths on a seeded copy.

`reviews.0014` has no safe reverse migration. Restore the pre-migration dump
with `pg_restore` into a **separate, empty database** and switch the deployment
back only after verifying it. Do not run `migrate reviews 0013` on live data;
that would claim to restore withdrawn assignments and record statuses without
actually reconstructing the prior workflow.

## Local verification

The fixed-stage workflow matrix and characterization suites were the IR-257
backfill oracle and are retired at this cutover, as the test migration plan
requires. The shadow dual-write, intake rejection, and old `/reviews/resubmit/`
policy cases also describe paths that are now unreachable. Adviser-first API
tests in `test_routing`, `test_office_review`, `test_decisions`,
`test_new_version`, `test_cutover_journeys`, and `test_transition_transactions`
cover their surviving routing, authority, clearance-aware versus restart-all,
versioning, and atomicity rules. The old submit and resubmit URLs return 410.

The focused container runs for submission ownership, intake retirement, demo
workflow states and the IR-233 metadata-only revision passed on 2026-10-10
against the isolated `test_iris_db`. The host Python runner could not create
its test database (`permission denied to create database`); container tests use
the project Postgres service. Record the five migrated-data API journeys,
per-status/seat/version before-and-after counts, and final full-suite output
in the PR before treating this cutover as ready for review.

### Development database preflight (2026-10-10)

Read-only snapshot before contract migration:

| Stored status | Records |
|---|---:|
| `draft` | 3 |
| `adviser_review` | 2 |
| `rdco_intake` | 1 |
| `parallel_review` | 4 |
| `rdco_review` | 1 |
| `in_review` | 2 |
| `approved` | 1 |
| `completed` | 1 |
| `published` | 11 |
| `rejected` | 2 |

Reviewer seats: **8**. Record versions: **25**. The read-only consistency gate
reported only Record **33**, which has active intake work but no eligible
Adviser. These are development counts, not pilot release evidence.

### Migration on a copy of the development database (2026-10-10)

1. **Backup.** `pg_dump --format=custom` of the development database was taken
   before any change: `iris-before-ir260-20261010.dump`, kept outside the
   checkout, sha256 `d7103d2b7fc89a45a1c83f1dfdba5cefe1c31c957b91e62f39b054e39e720cbe`.
2. **The human assignment the gate asked for.** Record 33 (`[DEMO] Awaiting
   RDCO intake`, owner student@cit.edu) was given **adviser@cit.edu** as its
   Adviser, decided by the project lead. adviser@cit.edu does not own it.
3. **The copy.** The dump was restored into a separate database,
   `iris_ir260_copy`, and the same assignment applied there. The development
   database itself was **not** migrated.
4. **Preflight.** `list_unassigned_intake` against the copy: *0 intake
   record(s) need an Adviser decision.*
5. **Migrate.** `manage.py migrate` against the copy applied
   `documents.0012`, `reviews.0014` and `reviews.0015`, all OK.

| | Before | After |
|---|---:|---:|
| `adviser_review` | 2 | 0 |
| `rdco_intake` | 1 | 0 |
| `parallel_review` | 4 | 0 |
| `rdco_review` | 1 | 0 |
| `in_review` | 2 | **10** |
| `draft` · `approved` · `completed` · `published` · `rejected` | 3 · 1 · 1 · 11 · 2 | unchanged |
| Reviewer seats | 8 (3 assigned, 3 in review, 2 done) | **9** (4 assigned, 3 in review, 2 done) |
| Record versions | 25 | 25 |
| Active assignments | adviser 3, intake 1, itso 1, ierc 4, ktto 3, rdco 1 | adviser **4**, intake **0**, itso 1, ierc 4, ktto 3, rdco 1 |

Every in-flight legacy status became `in_review`. The one intake assignment
was withdrawn and replaced by an Adviser assignment with an `entry` seat,
which accounts for the ninth seat. No version needed backfilling: IR-416's
`records/0015` had already given every submitted record one.
