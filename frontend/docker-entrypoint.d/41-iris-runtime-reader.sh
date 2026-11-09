#!/bin/sh
# Server-only credential; never substituted into a JavaScript bundle (IR-730).
# Every Ask IRIS question goes through the runtime edge since IR-957. Without
# the secret nginx still serves the site, but the gateway refuses every run,
# so readers see Ask IRIS as unavailable.
set -eu
umask 077
secret=${AI_GATEWAY_SERVICE_SECRET:-}
if [ -z "$secret" ]; then
    echo 'iris: AI_GATEWAY_SERVICE_SECRET is unset; Ask IRIS will answer unavailable' >&2
fi
case "$secret" in
    *[!A-Za-z0-9_=-]*) echo 'iris: AI_GATEWAY_SERVICE_SECRET must use URL-safe characters' >&2; exit 1 ;;
esac
printf 'proxy_set_header X-IRIS-Service-Secret "%s";\n' "$secret" > /tmp/iris-runtime-reader.conf
