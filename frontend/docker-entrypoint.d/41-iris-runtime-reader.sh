#!/bin/sh
# Server-only credential; never substituted into a JavaScript bundle (IR-730).
# AI_RUNTIME_READER is the same deployment switch Django reads (IR-863); the
# browser learns it from Django, never from the build.
set -eu
umask 077
secret=${AI_GATEWAY_SERVICE_SECRET:-}
case $(printf '%s' "${AI_RUNTIME_READER:-false}" | tr '[:upper:]' '[:lower:]') in
    true|1|yes|on|y|t) enabled=true ;;
    *) enabled=false ;;
esac
if [ "$enabled" = true ] && [ -z "$secret" ]; then
    echo 'iris: AI_GATEWAY_SERVICE_SECRET is required for the runtime reader' >&2
    exit 1
fi
case "$secret" in
    *[!A-Za-z0-9_=-]*) echo 'iris: AI_GATEWAY_SERVICE_SECRET must use URL-safe characters' >&2; exit 1 ;;
esac
printf 'proxy_set_header X-IRIS-Service-Secret "%s";\n' "$secret" > /tmp/iris-runtime-reader.conf
