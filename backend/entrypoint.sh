#!/bin/sh
set -e

# IR-318 / ADR-023: every backend-image container -- Django and each Celery
# process alike, since a worker touches the same tables -- migrates before
# it starts serving requests or consuming tasks. `set -e` means a failed
# migrate stops the container instead of it serving against a stale schema.
# Migrations in this codebase are all atomic (transactional DDL), so if two
# containers race this on the same boot, the loser's transaction fails
# cleanly and `restart: unless-stopped` retries it as a no-op once the
# winner has committed.
python manage.py migrate --noinput
exec "$@"
