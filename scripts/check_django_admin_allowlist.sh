#!/bin/sh
# Proves IR-668 and IR-782 against the real nginx, the real config and the real
# entrypoint script. Nothing listens behind nginx, so a request nginx proxies
# ends in 502, one it refuses ends in 403, and an app page answers 200 with the
# stand-in index.html. Run from the repository root; needs Docker.
set -u
export MSYS_NO_PATHCONV=1

root=$(pwd -W 2>/dev/null || pwd)
image=nginxinc/nginx-unprivileged:1.25-alpine
name=iris-django-admin-check
html=$(mktemp -d)
# mktemp makes it private, and the container's nginx is another user.
chmod 755 "$html"
echo '<!doctype html><title>IRIS</title>' > "$html/index.html"
printf false > "$html/runtime-reader-enabled"
chmod 644 "$html/runtime-reader-enabled"
html_mount=$(cd "$html" && { pwd -W 2>/dev/null || pwd; })
failed=0

fail() {
    echo "FAIL: $1"
    failed=1
}

# run_nginx [docker run options]; $mode and $command say how it runs.
run_nginx() {
    # shellcheck disable=SC2086
    docker run --add-host backend:127.0.0.1 --add-host ai-gateway:127.0.0.1 $mode "$@" \
        -v "$root/frontend/docker-entrypoint.d/40-iris-django-admin.sh:/docker-entrypoint.d/40-iris-django-admin.sh:ro" \
        -v "$root/frontend/docker-entrypoint.d/41-iris-runtime-reader.sh:/docker-entrypoint.d/41-iris-runtime-reader.sh:ro" \
        -v "$html_mount/runtime-reader-enabled:/etc/nginx/iris/runtime-reader-enabled:ro" \
        -v "$root/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
        -v "$root/frontend/security-headers.conf:/etc/nginx/iris/security-headers.conf:ro" \
        -v "$html_mount:/usr/share/nginx/html:ro" \
        "$image" $command
}

# start [docker run options]: the settings must pass `nginx -t` and then answer.
start() {
    docker rm -f "$name" >/dev/null 2>&1
    mode=--rm command="nginx -t"
    started=$(run_nginx "$@" 2>&1) || return 1
    mode="-d --name $name" command=
    run_nginx "$@" >/dev/null || return 1
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        docker exec "$name" curl -s -o /dev/null http://127.0.0.1:8080/ && return 0
        sleep 1
    done
    return 1
}

# expect <what> <status> <path> [X-Forwarded-For]
expect() {
    if [ -n "${4:-}" ]; then
        got=$(docker exec "$name" curl -s -o /dev/null -w '%{http_code}' -H "X-Forwarded-For: $4" "http://127.0.0.1:8080$3")
    else
        got=$(docker exec "$name" curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080$3")
    fi
    if [ "$got" = "$2" ]; then
        echo "ok: $1 ($got)"
    else
        fail "$1: expected $2, got $got"
    fi
}

echo "== nothing configured"
start || fail "nginx did not start with no allowlist"
expect "the default is deny" 403 /django-admin/
expect "the default denies deeper paths" 403 /django-admin/login/
expect "the refusal's own address is not reachable" 404 /django-admin-refused
expect "a forwarded address buys nothing" 403 /django-admin/ 127.0.0.1
headers=$(docker exec "$name" curl -s -D - -o /dev/null http://127.0.0.1:8080/django-admin/)
case "$(printf '%s' "$headers" | tr 'A-Z' 'a-z')" in
    *'x-content-type-options: nosniff'*) echo "ok: the 403 carries the security headers" ;;
    *) fail "the 403 lacks the security headers: $headers" ;;
esac
expect "the sign-in page stays open" 200 /login
# IRIS's own pages are the app, not Django (IR-782): opening or refreshing one
# gets index.html. A 502 would mean nginx proxied it to the backend.
for path in /admin/ /admin/users /admin/role-requests /admin/audit /rdco/ /rdco/users /rdco/role-requests; do
    body=$(docker exec "$name" curl -s -w '\n%{http_code}' "http://127.0.0.1:8080$path")
    status=$(printf '%s' "$body" | tail -n 1)
    if [ "$status" = 200 ] && printf '%s' "$body" | grep -q '<title>IRIS</title>'; then
        echo "ok: $path loads the app"
    else
        fail "$path: expected the app's index.html (200), got '$status'"
    fi
done

echo "== the direct peer is listed, no proxy in front"
start -e DJANGO_ADMIN_ALLOWED_NETWORKS=127.0.0.1/32 -e TRUSTED_PROXY_COUNT=1 || fail "nginx did not start"
expect "the listed peer gets through" 502 /django-admin/

echo "== the direct peer is not listed, a forged header names a listed address"
start -e DJANGO_ADMIN_ALLOWED_NETWORKS=203.0.113.0/24 -e TRUSTED_PROXY_COUNT=1 || fail "nginx did not start"
expect "an unlisted peer is refused" 403 /django-admin/
expect "a forged address is not read with one proxy" 403 /django-admin/ 203.0.113.9

echo "== a TLS proxy in front of nginx"
start -e 'DJANGO_ADMIN_ALLOWED_NETWORKS=203.0.113.0/24, 2001:db8::/32' -e TRUSTED_PROXY_COUNT=2 || fail "nginx did not start"
expect "the listed client gets through" 502 /django-admin/ 203.0.113.9
expect "a listed IPv6 client gets through" 502 /django-admin/ 2001:db8::1
expect "an unlisted client is refused" 403 /django-admin/ 198.51.100.1
expect "a forged entry left of the proxy's is not read" 403 /django-admin/ "203.0.113.9, 198.51.100.1"
expect "a forged entry cannot hide a listed client" 502 /django-admin/ "198.51.100.1, 203.0.113.9"
expect "no header falls back to the peer, which is unlisted" 403 /django-admin/

echo "== refused settings stop the container"
for bad in "DJANGO_ADMIN_ALLOWED_NETWORKS=not-a-network TRUSTED_PROXY_COUNT=1" \
           "DJANGO_ADMIN_ALLOWED_NETWORKS=0.0.0.0/0 TRUSTED_PROXY_COUNT=1" \
           "DJANGO_ADMIN_ALLOWED_NETWORKS=203.0.113.9" \
           "DJANGO_ADMIN_ALLOWED_NETWORKS=203.0.113.9 TRUSTED_PROXY_COUNT=0"; do
    args=
    for pair in $bad; do
        args="$args -e $pair"
    done
    # shellcheck disable=SC2086
    if start $args; then
        fail "started with: $bad"
    elif printf '%s' "$started" | grep -q '^iris: '; then
        echo "ok: refused $bad"
    else
        fail "stopped, but not by the allowlist script: $bad: $started"
    fi
done

docker rm -f "$name" >/dev/null 2>&1
rm -rf "$html"
if [ "$failed" = 0 ]; then
    echo "All IR-668 checks passed."
fi
exit "$failed"
