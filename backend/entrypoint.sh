#!/bin/sh
set -e

# Compose runs schema changes once in its `migrate` service before the
# application and worker services start. Keep this shared entrypoint focused
# on launching the requested process.
exec "$@"
