#!/usr/bin/env bash
# IR-1018: runs scripts/deploy.sh against a throwaway git repository with a
# fake `docker` and `curl` on PATH, and checks what it decided. No container
# is started: the real stack is proven by the run on iris-demo
# (docs/testing/traceability/IR-1018.md).
#
#   deploy/tests/deploy_checks.sh
#
# Each case gets a fresh clone. The fake docker reads its answers from files
# in $FAKE (see fake_docker below) and writes every call it gets to
# $FAKE/calls, so a case can check what the script ran and what it didn't.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../../scripts/deploy.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
failures=0

export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.invalid
export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.invalid
export GIT_CONFIG_NOSYSTEM=1 HOME="$WORK/home"
mkdir -p "$HOME"
git config --global init.defaultBranch main
git config --global advice.detachedHead false

check() {
    local what="$1"
    shift
    if "$@"; then
        echo "ok   $what"
    else
        echo "FAIL $what"
        failures=$((failures + 1))
    fi
}

said()       { grep -qF -- "$1" "$OUT"; }
ran()        { grep -qF -- "$1" "$FAKE/calls"; }
not_ran()    { ! ran "$1"; }
head_is()    { [ "$(git -C "$CLONE" rev-parse HEAD)" = "$1" ]; }

# ---- the fake docker and curl ------------------------------------------

make_fakes() {
    mkdir -p "$FAKE/bin"
    : > "$FAKE/calls"
    cat > "$FAKE/bin/docker" <<'EOF'
#!/usr/bin/env bash
# Only `docker compose -f FILE <command> ...` is faked.
echo "docker $*" >> "$FAKE/calls"
[ "$1" = compose ] && [ "$2" = -f ] || { echo "fake docker: unexpected: $*" >&2; exit 99; }
shift 3
case "$1" in
    config)
        if [ "${2:-}" = --services ]; then cat "$FAKE/services"; else exit "$(cat "$FAKE/config_rc" 2>/dev/null || echo 0)"; fi ;;
    up)
        touch "$FAKE/up_ran"
        exit "$(cat "$FAKE/up_rc" 2>/dev/null || echo 0)" ;;
    ps)
        # ps_after_up, when present, is what ps shows once `up` has run.
        if [ -e "$FAKE/up_ran" ] && [ -e "$FAKE/ps_after_up" ]; then cat "$FAKE/ps_after_up"; else cat "$FAKE/ps"; fi ;;
    logs)
        echo "last lines of ${*: -1}" ;;
    restart)
        exit 0 ;;
    *)
        echo "fake docker: unexpected compose command: $*" >&2; exit 99 ;;
esac
EOF
    cat > "$FAKE/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl ${*: -1}" >> "$FAKE/calls"
exit "$(cat "$FAKE/curl_rc" 2>/dev/null || echo 0)"
EOF
    chmod +x "$FAKE/bin/docker" "$FAKE/bin/curl"
    printf '%s\n' db migrate backend frontend > "$FAKE/services"
    healthy > "$FAKE/ps"
}

# What `docker compose ps -a` shows for a healthy stack, in the format
# scripts/deploy.sh asks for: service|state|health|exit code.
healthy() {
    printf '%s\n' \
        "db|running|healthy|0" \
        "migrate|exited||0" \
        "backend|running||0" \
        "frontend|running||0"
}

# ---- the repositories ---------------------------------------------------

# origin.git stands in for GitHub; $CLONE is the server's clone; $DEV pushes
# new commits to origin.
new_case() {
    local name="$1"
    echo "--- $name"
    CASE="$WORK/$name"
    FAKE="$CASE/fake"
    CLONE="$CASE/IRIS"
    DEV="$CASE/dev"
    OUT="$CASE/out"
    export FAKE
    make_fakes
    git init -q --bare "$CASE/origin.git"
    git clone -q "$CASE/origin.git" "$DEV" 2>/dev/null
    mkdir -p "$DEV/scripts"
    cp "$SCRIPT" "$DEV/scripts/deploy.sh"
    echo "services: {}" > "$DEV/docker-compose.prod.yml"
    printf '%s\n' .env backend/.env ai/.env > "$DEV/.gitignore"
    git -C "$DEV" add -A
    git -C "$DEV" commit -q -m first
    git -C "$DEV" push -q origin main
    git clone -q "$CASE/origin.git" "$CLONE"
    mkdir -p "$CLONE/backend" "$CLONE/ai"
    echo "IRIS_DOMAIN=iris.example.invalid" > "$CLONE/.env"
    touch "$CLONE/backend/.env" "$CLONE/ai/.env"
}

push_change() {
    echo "$1" >> "$DEV/CHANGES"
    git -C "$DEV" add CHANGES
    git -C "$DEV" commit -q -m "$1"
    git -C "$DEV" push -q origin main
}

# Runs the clone's own copy, as on the server. Short waits keep the run fast.
deploy() {
    PATH="$FAKE/bin:$PATH" IRIS_DEPLOY_TIMEOUT="${TIMEOUT:-2}" IRIS_DEPLOY_POLL=0 \
        IRIS_DEPLOY_MIN_FREE_GB="${MIN_FREE_GB:-0}" \
        bash "$CLONE/scripts/deploy.sh" > "$OUT" 2>&1
}

# ---- cases --------------------------------------------------------------

new_case not-on-main
push_change "second"
git -C "$CLONE" checkout -q -b hotfix
before="$(git -C "$CLONE" rev-parse HEAD)"
deploy; rc=$?
check "refuses a branch other than main"          [ "$rc" -ne 0 ]
check "says why"                                  said "is on hotfix, not main"
check "pulled nothing"                            head_is "$before"
check "ran no docker command"                     [ ! -s "$FAKE/calls" ]

new_case local-changes
push_change "second"
echo "edited on the server" >> "$CLONE/docker-compose.prod.yml"
before="$(git -C "$CLONE" rev-parse HEAD)"
deploy; rc=$?
check "refuses a clone with local changes"        [ "$rc" -ne 0 ]
check "names the changed file"                    said "docker-compose.prod.yml"
check "pulled nothing"                            head_is "$before"
check "ran no docker command"                     [ ! -s "$FAKE/calls" ]

new_case update
push_change "second"
new="$(git -C "$DEV" rev-parse HEAD)"
deploy; rc=$?
check "succeeds"                                  [ "$rc" -eq 0 ]
check "fast-forwards to the new commit"           head_is "$new"
check "rebuilds"                                  ran "up -d --build"
check "restarts frontend after the rebuild"       ran "restart frontend"
check "checks the site over HTTPS"                ran "curl https://iris.example.invalid/"
check "checks the API through the site"           ran "curl https://iris.example.invalid/api/v1/colleges/"
check "reports the deployed commit"               said "done, running ${new:0:8}"

: > "$FAKE/calls"
rm -f "$FAKE/up_ran"
deploy; rc=$?
check "a second run with nothing new succeeds"    [ "$rc" -eq 0 ]
check "says it is already up to date"             said "already up to date"
check "doesn't rebuild"                           not_ran " up "
check "doesn't restart anything"                  not_ran "restart"
check "still checks health"                       ran " ps "
check "still checks the site"                     ran "curl https://iris.example.invalid/"

new_case migrate-fails
push_change "second"
old="$(git -C "$CLONE" rev-parse HEAD)"
echo 1 > "$FAKE/up_rc"
healthy | sed 's/^migrate|exited||0$/migrate|exited||1/' > "$FAKE/ps_after_up"
deploy; rc=$?
check "fails"                                     [ "$rc" -ne 0 ]
check "names the step"                            said "FAILED at step 3/5 (rebuild)"
check "says the database update failed"           said "migrate didn't finish"
check "shows migrate's log"                       said "last lines of migrate"
check "says how to go back to the old commit"     said "git checkout --detach ${old:0:8}"
check "doesn't restart frontend"                  not_ran "restart frontend"
check "doesn't report success"                    not_ran "curl"

: > "$FAKE/calls"
rm -f "$FAKE/up_rc" "$FAKE/ps_after_up" "$FAKE/up_ran"
deploy; rc=$?
check "the next run, with nothing new, rebuilds"  ran "up -d --build"
check "and says why"                              said "hasn't been deployed by this script"
check "and succeeds once migrate does"            [ "$rc" -eq 0 ]

new_case never-healthy
push_change "second"
healthy | sed 's/^backend|running||0$/backend|restarting||1/' > "$FAKE/ps_after_up"
deploy; rc=$?
check "fails"                                     [ "$rc" -ne 0 ]
check "names the step"                            said "FAILED at step 4/5 (health)"
check "names the service and its state"           said "backend (restarting)"
check "shows that service's log"                  said "last lines of backend"

new_case unhealthy-and-missing
push_change "second"
echo ai-gateway >> "$FAKE/services"
healthy | sed 's/^db|running|healthy|0$/db|running|unhealthy|0/' > "$FAKE/ps_after_up"
deploy; rc=$?
check "fails on an unhealthy service"             [ "$rc" -ne 0 ]
check "names it"                                  said "db (unhealthy)"
check "names a service with no container"         said "ai-gateway (no container)"

new_case site-down
push_change "second"
echo 22 > "$FAKE/curl_rc"
deploy; rc=$?
check "fails when the site doesn't answer"        [ "$rc" -ne 0 ]
check "names the step"                            said "FAILED at step 4/5 (health)"
check "names the address"                         said "https://iris.example.invalid/ didn't answer"
check "suggests restarting frontend (IR-200)"     said "restart frontend"
check "shows caddy's and frontend's logs"         said "last lines of caddy"

: > "$FAKE/calls"
rm -f "$FAKE/curl_rc" "$FAKE/up_ran"
deploy; rc=$?
check "the failed run wasn't recorded as deployed" ran "up -d --build"

new_case missing-env
push_change "second"
rm "$CLONE/ai/.env"
deploy; rc=$?
check "refuses a missing ai/.env"                 [ "$rc" -ne 0 ]
check "names the step and the file"               said "FAILED at step 2/5 (check): ai/.env is missing"
check "doesn't rebuild"                           not_ran " up "

new_case invalid-compose
push_change "second"
echo 1 > "$FAKE/config_rc"
deploy; rc=$?
check "refuses a compose file that doesn't validate" [ "$rc" -ne 0 ]
check "names the step"                            said "FAILED at step 2/5 (check)"
check "doesn't rebuild"                           not_ran " up "

new_case low-disk
push_change "second"
MIN_FREE_GB=999999 deploy; rc=$?
check "refuses when the disk is too full"         [ "$rc" -ne 0 ]
check "says how much is free"                     said "GB free, and a rebuild needs 999999 GB"
check "doesn't rebuild"                           not_ran " up "

new_case diverged
push_change "second"
echo "committed on the server" > "$CLONE/LOCAL"
git -C "$CLONE" add LOCAL
git -C "$CLONE" commit -q -m local
deploy; rc=$?
check "refuses when main can't fast-forward"      [ "$rc" -ne 0 ]
check "names the step"                            said "FAILED at step 1/5 (pull)"
check "doesn't rebuild"                           not_ran " up "

new_case bad-setting
TIMEOUT=soon deploy; rc=$?
check "refuses a setting that isn't a number"     [ "$rc" -ne 0 ]
check "names it"                                  said "IRIS_DEPLOY_TIMEOUT must be a whole number"

echo
if [ "$failures" -eq 0 ]; then
    echo "all checks passed"
else
    echo "$failures check(s) failed"
    exit 1
fi
