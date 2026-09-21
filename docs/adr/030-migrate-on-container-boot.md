# ADR-030: Compose containers migrate on boot, unconditionally

## Status

Accepted — 2026-09-21. Decision made by the project lead (per CLAUDE.md's "What AI does not decide"), recorded here from that decision.

## Context

`IR-318`: `POST /api/v1/records/57/submit/` 500'd against the dev Docker stack with `relation "reviews_recordassignment" does not exist`. `showmigrations` inside the `backend` container showed three unapplied migrations that had been sitting in the repo unrun. `docker compose exec backend python manage.py migrate` fixed it immediately.

Neither Compose file ran `migrate` anywhere. `backend/entrypoint.sh` existed in the repository, and its content — `collectstatic` then `exec "$@"` — read as though it were the container's entrypoint, but **it was never wired in**: `backend/Dockerfile` had no `ENTRYPOINT` directive, so the file was dead code and `collectstatic` had only ever run at image build time (`backend/Dockerfile`'s own `RUN manage.py collectstatic --noinput` step). A container's actual boot path was just `CMD` — `runserver` in dev, `gunicorn` in prod — with nothing between "container starts" and "container serves" that touched the schema at all.

The consequence: a container boots and starts serving requests or consuming Celery tasks regardless of whether its database's schema matches the code it's running. The failure surfaces on whichever endpoint happens to touch the first un-migrated table, in front of whoever happens to hit it — not at boot, where it would be caught immediately. `docker-compose.prod.yml` has the identical gap; `IR-157` (deploy to the interim VPS) will hit this the first time a post-boot migration exists if it isn't decided by then.

`docs/archive/architecture_review_and_aws_roadmap.md` had already flagged this as an undecided question, recommending `migrate` run as a one-off CI/CD task rather than be baked into container startup — a recommendation that was never acted on either way.

## Decision

**`backend/entrypoint.sh` runs `python manage.py migrate --noinput` unconditionally, before `exec "$@"`, and `backend/Dockerfile` gains `ENTRYPOINT ["/app/entrypoint.sh"]` so that script actually runs.** This applies uniformly to every container built from the backend image — `backend` (Django) and all four Celery services (`celery-default`, `celery-extraction`, `celery-embedding`, `celery-beat`) — in both `docker-compose.yml` (dev) and `docker-compose.prod.yml` (prod). No dev/prod split: a Celery worker touches the same tables Django does, so the same failure mode applies to it, and there is no argument for trusting prod's schema state more than dev's.

The pre-existing `collectstatic` call in `entrypoint.sh` is dropped, not carried forward. It was already redundant with the Dockerfile's build-time `collectstatic` step (which bakes `STATIC_ROOT` into the image with throwaway build-time credentials, deliberately, per that step's own comment), and running it again at every boot of all five backend-image services — including four Celery services that never serve a static asset — would have been the one new side effect of wiring the script in for the first time. Migrate is the only thing added.

`celery-beat` gains a `depends_on: db: condition: service_healthy` in both Compose files. It previously depended only on `redis`, which was enough when it ran no code that touched Postgres; now that it migrates on boot, it needs the same ordering guarantee every other backend-image service already had.

## Alternatives Considered

**A one-off migrate step run explicitly as part of deploy, never baked into the image's boot** (the archived AWS-roadmap recommendation). Rejected for now: it requires deploy tooling that doesn't exist yet (`IR-157` — deploying to the interim VPS — hasn't happened), and until that tooling exists, "explicit deploy step" has no home to live in and degrades to "someone remembers to run it by hand," which is the exact failure this ticket is about. Worth revisiting once `IR-157` gives the project a real deploy pipeline to hang a migrate step on.

**A boot-time refusal (`showmigrations` check that exits non-zero without auto-migrating, leaving the actual `migrate` to a human).** Rejected: it fails loudly, which is strictly better than the status quo, but doesn't self-heal — a first-time `docker compose up` on a fresh checkout would need a manual migrate before anything comes up at all, adding a step to the same setup flow `docs/engineering/DEVELOPMENT.md` §6 is supposed to make turnkey.

**Different treatment for dev vs. prod.** Rejected: the failure mode (a container serving traffic or consuming tasks against a schema it doesn't match) is identical in both environments, and prod is the one where this class of bug is more expensive, not less. Splitting behavior would mean the dev path exercises different startup code than prod ever runs, which is its own risk.

## Decision Rationale

Auto-migrate-on-boot is the simplest fix that actually closes the gap for every container that touches the database, not only the one that happens to serve HTTP. It costs one Dockerfile line, one script line, and it makes `entrypoint.sh` — previously inert — do the one thing its name already implied it did.

The concurrency question — five backend-image services starting close together, several potentially racing `migrate` against the same database — is real but bounded: every migration in this codebase runs inside Django's default atomic-per-migration transaction (`grep -rl "atomic = False"` across `apps/` returns nothing). A losing container's transaction fails cleanly with a "relation already exists"-class error, `set -e` in `entrypoint.sh` stops that container, and `restart: unless-stopped` retries it — by which point the winner has committed, so the retry is a no-op. The visible cost is a crash-and-restart on whichever container loses the race on a cold start with pending migrations, not corruption or a stuck state. This durability comes from the codebase's current migrations, not from anything this ADR adds — see **Revisit when**.

## Consequences

**Positive.** A container can no longer boot and silently serve against a stale schema, in dev or in prod. `docker compose up` on a fresh checkout with pending migrations self-heals without a manual `migrate` step. `entrypoint.sh` stops being dead code.

**Negative.** Every container boot now costs a `migrate` no-op round-trip (checking `django_migrations`) even when nothing changed — cheap, but non-zero, five times per `docker compose up`. A cold start with pending migrations can show one or more Celery containers crash-and-restart once before settling, which is more startup log noise than a silent boot.

**Risk.** This safety property depends on every migration staying atomic. A future migration that sets `atomic = False` (for example, `CREATE INDEX CONCURRENTLY` on a large table) breaks the "loser fails cleanly" guarantee this ADR's rationale rests on — see **Revisit when**.

## Revisit when

A migration needs `atomic = False` (e.g., a `CREATE INDEX CONCURRENTLY` on a large table) — concurrent `migrate` invocations across five containers are no longer safe by default at that point, and either a Postgres advisory lock around the migrate call or a dedicated one-shot migrate service should be introduced before that migration ships · `IR-157` gives the project a real deploy pipeline, which reopens whether prod should move to an explicit deploy-time migrate step instead of boot-time · multiple replicas of `backend` itself are introduced (this ADR was decided against one replica per service; N replicas of `backend` racing `migrate` is the same argument at higher concurrency, not a new one, but worth re-confirming).

## MVP Impact

None. This is a deployment-reliability fix, not a feature.

## SaaS Impact

Directly relevant: instance-per-tenant (ADR-005) means this exact gap would exist per tenant instance. Closing it here closes it for every future tenant deployment, not only the shared dev/interim-VPS stack.

## Security Impact

None new. No new permission surface; `migrate` already runs with the same DB credentials the container already holds.

## Deployment Impact

`backend/Dockerfile`: `entrypoint.sh` is now `chmod +x`'d and wired as `ENTRYPOINT`. `backend/entrypoint.sh`: runs `migrate --noinput` before `exec "$@"`; no longer runs `collectstatic`. `docker-compose.yml` and `docker-compose.prod.yml`: `celery-beat` gains a `db: condition: service_healthy` dependency. `docs/engineering/DEVELOPMENT.md` §6 documents the Docker Compose migration path.

## Research Impact

None.

## Related Requirements

None tracked under an `FR-`/`NFR-` id — this is an operational-reliability fix, not a functional or non-functional requirement from the frozen SRS.

## Related Tasks

`IR-318` (this ticket) · `IR-156` (sibling — Docker stack build/serve; did not catch this) · `IR-157` (deploy to interim VPS — blocked on this class of bug being closed, and the trigger for revisiting the "explicit deploy step" alternative above).
