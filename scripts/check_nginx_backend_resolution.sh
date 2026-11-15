#!/bin/sh
# Proves IR-200 against the real nginx and the real config: nginx looks the
# backend up through Docker's DNS on each request, so a recreated backend at a
# new address is reached with no nginx restart, and when two containers answer
# to `backend` both get requests. The backend is a stand-in that answers with
# its own container name. Run from the repository root; needs Docker.
# `[ test ] && echo ok || fail` reads as if-else here: echo doesn't fail.
# shellcheck disable=SC2015
set -u
export MSYS_NO_PATHCONV=1

root=$(pwd -W 2>/dev/null || pwd)
image=nginxinc/nginx-unprivileged:1.25-alpine
stand_in=python:3.11-alpine
net=iris-resolution-check
html=
failed=0

fail() {
    echo "FAIL: $1"
    failed=1
}

cleanup() {
    docker rm -f iris-resolution-nginx iris-backend-a iris-backend-b iris-backend-c >/dev/null 2>&1
    docker network rm "$net" >/dev/null 2>&1
    [ -n "$html" ] && rm -rf "$html"
}
trap cleanup EXIT
cleanup
# mktemp makes it private, and the container's nginx is another user.
html=$(mktemp -d); chmod 755 "$html"
echo '<!doctype html><title>IRIS</title>' > "$html/index.html"
html_mount=$(cd "$html" && { pwd -W 2>/dev/null || pwd; })

docker network create "$net" >/dev/null

# backend <name>: a stand-in Django on port 8000 that names itself.
backend() {
    docker run -d --name "$1" --network "$net" --network-alias backend "$stand_in" python -c '
import http.server, socket
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = socket.gethostname().encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("0.0.0.0", 8000), H).serve_forever()
' >/dev/null
    # Until it answers on 8000.
    for _ in $(seq 1 20); do
        docker exec "$1" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/")' >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

# Who answered /api/ through nginx (the stand-in's hostname is its container id).
ask() {
    docker exec iris-resolution-nginx curl -s -m 10 -w ' %{http_code}' http://127.0.0.1:8080/api/v1/colleges/
}

id_of() {
    docker inspect -f '{{.Config.Hostname}}' "$1"
}

backend iris-backend-a || fail "stand-in backend a did not start"
docker run -d --name iris-resolution-nginx --network "$net" \
    -v "$root/frontend/docker-entrypoint.d/40-iris-django-admin.sh:/docker-entrypoint.d/40-iris-django-admin.sh:ro" \
    -v "$root/frontend/docker-entrypoint.d/41-iris-runtime-reader.sh:/docker-entrypoint.d/41-iris-runtime-reader.sh:ro" \
    -v "$root/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$root/frontend/security-headers.conf:/etc/nginx/iris/security-headers.conf:ro" \
    -v "$root/frontend/runtime-edge.conf:/etc/nginx/iris/runtime-edge.conf:ro" \
    -v "$html_mount:/usr/share/nginx/html:ro" \
    -e AI_GATEWAY_SERVICE_SECRET=check-only "$image" >/dev/null
ready=
for _ in $(seq 1 20); do
    docker exec iris-resolution-nginx curl -s -o /dev/null http://127.0.0.1:8080/ && { ready=1; break; }
    sleep 1
done
[ -n "$ready" ] || { docker logs iris-resolution-nginx; fail "nginx did not answer within 20s"; exit 1; }

a=$(id_of iris-backend-a)
got=$(ask)
[ "$got" = "$a 200" ] && echo "ok: /api/ reaches the backend ($got)" || fail "/api/ before the recreate: expected '$a 200', got '$got'"

echo "== the backend is recreated at a new address; nginx is not restarted"
addr_a=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$net\").IPAddress}}" iris-backend-a)
# Start the replacement before removing the old one, so it can't reuse the address.
backend iris-backend-b || fail "stand-in backend b did not start"
docker rm -f iris-backend-a >/dev/null
addr_b=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$net\").IPAddress}}" iris-backend-b)
[ "$addr_a" != "$addr_b" ] || fail "the replacement reused the old address ($addr_a), so this proves nothing"
echo "old address $addr_a, new address $addr_b"
b=$(id_of iris-backend-b)
# nginx reuses an answer for up to 10s (valid=10s), then asks again.
reached=
for _ in $(seq 1 20); do
    got=$(ask)
    [ "$got" = "$b 200" ] && { reached=1; break; }
    sleep 1
done
[ -n "$reached" ] && echo "ok: the recreated backend is reached without restarting nginx ($got)" \
    || fail "after the recreate: expected '$b 200', got '$got'"

echo "== two containers answer to backend; both get requests"
backend iris-backend-c || fail "stand-in backend c did not start"
c=$(id_of iris-backend-c)
sleep 11
seen_b=0 seen_c=0
for _ in $(seq 1 20); do
    got=$(ask)
    case "$got" in
        "$b 200") seen_b=$((seen_b + 1)) ;;
        "$c 200") seen_c=$((seen_c + 1)) ;;
        *) fail "a request with two backends got '$got'" ;;
    esac
done
echo "20 requests: $seen_b to b, $seen_c to c"
[ "$seen_b" -gt 0 ] && [ "$seen_c" -gt 0 ] && echo "ok: nginx takes turns between the two" \
    || fail "nginx sent every request to one backend"

echo "== no backend at all: nginx still answers the app, and /api/ is a 502"
docker rm -f iris-backend-b iris-backend-c >/dev/null
sleep 11
status=$(docker exec iris-resolution-nginx curl -s -o /dev/null -m 10 -w '%{http_code}' http://127.0.0.1:8080/api/v1/colleges/)
[ "$status" = 502 ] && echo "ok: /api/ with no backend is a 502" || fail "with no backend, expected a 502, got '$status'"

status=$(docker exec iris-resolution-nginx curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/login)
[ "$status" = 200 ] && echo "ok: the app still loads" || fail "the app page answered $status with no backend"

if [ "$failed" = 0 ]; then
    echo "All IR-200 checks passed."
else
    docker logs iris-resolution-nginx 2>&1 | tail -20
fi
exit "$failed"
