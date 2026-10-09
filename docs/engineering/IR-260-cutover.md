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
   upgraded. It lists intake records lacking an Adviser and records whose
   Adviser is an owner. Resolve each by an explicit human assignment; the
   migration does not guess.
3. Apply migrations with `python manage.py migrate`. `reviews.0014` withdraws
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

The focused container runs for submission ownership, intake retirement, demo
workflow states and the IR-233 metadata-only revision passed on 2026-10-10
against the isolated `test_iris_db`. The host Python runner could not create
its test database (`permission denied to create database`); container tests use
the project Postgres service. The full-suite result belongs in the PR/CI log.
