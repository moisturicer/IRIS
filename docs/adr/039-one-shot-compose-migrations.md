# ADR-039: Compose runs migrations once before application services

## Status

**Proposed** — 2026-10-11 (IR-528), awaiting human approval. If accepted, this
decision supersedes [ADR-037](037-migrate-on-container-boot.md).

## Context

ADR-037 put `migrate` in the shared backend image entrypoint. That means the
Django server and each Celery process independently run the same migration
chain at startup. In the development database, `reviews.0014` correctly
refused to proceed because a legacy `[DEMO]` intake record had no eligible
Adviser. The same safe refusal then caused every backend and worker container
to exit and restart repeatedly, obscuring the single data issue behind several
identical crash loops.

## Decision

Both development and production Compose files define one `migrate` service.
It waits for PostgreSQL health, runs `python manage.py migrate --noinput` once,
and does not restart. The backend and every Celery service depend on its
successful completion. The shared backend entrypoint only launches its passed
command.

Seeded workflow records are reset through a separate explicit management
command. It previews `[DEMO]` records by default, requires `--execute` to delete
them, and refuses execution when `DEBUG` is off. Ordinary records, accounts,
catalogue lookup data, and stored uploaded files are outside its scope.

## Alternatives considered

- Keep per-container migration and add retry delays: this still runs the
  migration chain independently in every service and leaves the same failure
  multiplied across containers.
- Run migrations manually: this is easy to forget and makes a normal Compose
  startup depend on an undocumented human step.
- Delete demo data automatically during startup: rejected because startup must
  not erase developer data without an explicit operator action.

## Consequences

- A migration failure appears once in the `migrate` service, and dependent
  application and worker containers do not start against a stale schema.
- Compose users must rerun or recreate the migration service after fixing a
  failed migration or its blocking data.
- `docker compose up` now relies on Compose's
  `service_completed_successfully` dependency condition.

## Revisit when

A deployment pipeline provides a managed release-time migration step, or the
application is deployed through an orchestrator with a native migration job.

## Related tasks

IR-528.
