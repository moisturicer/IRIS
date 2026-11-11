#!/usr/bin/env bash
# IR-1018: update the IRIS server to the latest main with one command.
#
#   bash ~/IRIS/scripts/deploy.sh
#
# Run it on the server, as the user who owns the clone. Five steps, each
# reported on its own line; the first that fails stops the run and names
# itself. deploy/README.md says what each step does and what to do when one
# fails.
#
# Settings, all optional:
#   IRIS_DEPLOY_TIMEOUT      seconds step 4 may take in all (default 600)
#   IRIS_DEPLOY_POLL         seconds between checks (default 5)
#   IRIS_DEPLOY_MIN_FREE_GB  free disk a rebuild needs (default 5)

set -euo pipefail

COMPOSE=(docker compose -f docker-compose.prod.yml)
TIMEOUT="${IRIS_DEPLOY_TIMEOUT:-600}"
POLL="${IRIS_DEPLOY_POLL:-5}"
MIN_FREE_GB="${IRIS_DEPLOY_MIN_FREE_GB:-5}"
# Ready on this many checks in a row, so a container that crash-loops isn't
# taken as up because it was caught between two crashes.
STEADY_CHECKS=3
STEP="setup"
DEADLINE=0
# The commit running before this deploy, set once the pull has moved the
# clone, and the commit it moved to.
PREVIOUS=""
NEW=""

say() { echo "IRIS deploy: $*"; }
short() { git rev-parse --short=8 "$1"; }

begin() {
    STEP="step $1/5 ($2)"
}

# Stops the run, naming the step that failed, and says how to go back when
# the clone has moved to a commit that wasn't running before.
fail() {
    echo "IRIS deploy: FAILED at $STEP: $*" >&2
    if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$NEW" ]; then
        local p
        p="$(short "$PREVIOUS")"
        cat >&2 <<EOF
IRIS deploy: to go back to $p, the version that ran before:
    git checkout --detach $p && ${COMPOSE[*]} up -d --build
  That doesn't undo database migrations. Run "git checkout main" before the next deploy.
EOF
    fi
    exit 1
}

show_logs() {
    local service
    for service in "$@"; do
        echo "----- last lines of $service -----" >&2
        "${COMPOSE[@]}" logs --tail 30 "$service" >&2 || true
    done
}

migrate_failed() {
    show_logs migrate
    fail "migrate $1: the database update failed (its log is above)"
}

# One line per container: service|state|health|exit code. A service with
# replicas has one line per replica; health is empty without a healthcheck.
containers() {
    "${COMPOSE[@]}" ps -a --format '{{.Service}}|{{.State}}|{{.Health}}|{{.ExitCode}}' ||
        fail "docker compose ps failed (the error is above). Is Docker running?"
}

# Why a service isn't ready yet, or nothing when it is. migrate is the one
# service that must have run and exited 0; every other one must be running,
# and healthy when it has a healthcheck.
not_ready_reason() {
    local service="$1" lines="$2" state health code
    [ -n "$lines" ] || { echo "no container"; return; }
    while IFS='|' read -r _ state health code; do
        if [ "$service" = migrate ]; then
            [ "$state" = exited ] && [ "$code" = 0 ] && continue
            if [ "$state" = exited ]; then echo "exited $code"; else echo "$state"; fi
            return
        fi
        if [ "$state" != running ]; then
            echo "$state"
            return
        fi
        if [ -n "$health" ] && [ "$health" != healthy ]; then
            echo "$health"
            return
        fi
    done <<< "$lines"
}

# Waits until every service has been ready for STEADY_CHECKS checks in a row,
# or fails at DEADLINE with the logs of the ones that weren't. A migrate that
# exited non-zero fails at once: waiting won't fix it.
wait_until_ready() {
    local services all service lines reason waiting steady=0
    services="$("${COMPOSE[@]}" config --services)" ||
        fail "docker compose config failed (the error is above). Is Docker running?"
    while true; do
        # A failure inside containers() exits only this subshell, so check it.
        all="$(containers)" || exit 1
        waiting=()
        # Compose service names never contain spaces.
        for service in $services; do
            lines="$(awk -F'|' -v s="$service" '$1 == s' <<< "$all")"
            reason="$(not_ready_reason "$service" "$lines")"
            [ -z "$reason" ] && continue
            if [ "$service" = migrate ] && [[ "$reason" == exited* ]]; then
                migrate_failed "$reason"
            fi
            waiting+=("$service ($reason)")
        done
        if [ "${#waiting[@]}" -eq 0 ]; then
            steady=$((steady + 1))
            [ "$steady" -ge "$STEADY_CHECKS" ] && return
        else
            steady=0
            if [ "$SECONDS" -ge "$DEADLINE" ]; then
                show_logs "${waiting[@]%% *}"
                fail "not ready after ${TIMEOUT}s: ${waiting[*]}"
            fi
        fi
        sleep "$POLL"
    done
}

# Retries until DEADLINE, because Caddy and nginx can take a few seconds to
# answer after a restart, and Caddy longer on a new server's first certificate.
site_answers() {
    until curl -fsS -o /dev/null --max-time 20 "$1"; do
        [ "$SECONDS" -lt "$DEADLINE" ] || return 1
        sleep "$POLL"
    done
}

# Everything runs inside main(), so bash has read the whole script before
# step 1 pulls a new copy of this very file over it. The new copy runs from
# the next deploy on.
main() {
    local root
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    cd "$root"

    local setting
    for setting in TIMEOUT POLL MIN_FREE_GB; do
        [[ "${!setting}" =~ ^(0|[1-9][0-9]*)$ ]] ||
            fail "IRIS_DEPLOY_$setting must be a whole number with no leading zero, not '${!setting}'"
    done

    # ---- 1. pull --------------------------------------------------------
    begin 1 pull
    local branch changes old deployed state ahead rebuild
    branch="$(git rev-parse --abbrev-ref HEAD)"
    [ "$branch" = main ] || fail "the clone is on $branch, not main. Run: git checkout main"
    changes="$(git status --porcelain --untracked-files=no)"
    [ -z "$changes" ] || fail "the clone has local changes, which a pull could overwrite:
$changes
Keep them with git stash, or undo them with git checkout -- <file>."
    git fetch --quiet origin main || fail "couldn't fetch main from GitHub (the error is above)"
    ahead="$(git rev-list --count FETCH_HEAD..HEAD)"
    [ "$ahead" = 0 ] || fail "main has $ahead commit(s) GitHub doesn't. Push them, or drop them with: git reset --hard origin/main"

    # The last commit this script deployed, so a run after a failed one
    # rebuilds even though there's nothing new to pull.
    state="$(git rev-parse --git-path iris-deployed)"
    deployed="$(cat "$state" 2>/dev/null || true)"
    old="$(git rev-parse HEAD)"
    git merge --ff-only --quiet FETCH_HEAD || fail "main couldn't fast-forward (the error is above)"
    NEW="$(git rev-parse HEAD)"
    PREVIOUS="${deployed:-$old}"

    if [ "$NEW" = "$deployed" ]; then
        rebuild=false
        say "step 1/5 pull: already up to date at $(short "$NEW"); checking health only"
    elif [ "$NEW" = "$old" ]; then
        rebuild=true
        say "step 1/5 pull: nothing new, but $(short "$NEW") hasn't been deployed by this script; rebuilding"
    else
        rebuild=true
        say "step 1/5 pull: $(short "$old") -> $(short "$NEW"), $(git rev-list --count "$old..$NEW") new commit(s)"
    fi

    # ---- 2. check -------------------------------------------------------
    begin 2 check
    local file domain free_kb
    for file in .env backend/.env ai/.env; do
        [ -f "$file" ] || fail "$file is missing. Create it first (deploy/README.md, Next)."
    done
    "${COMPOSE[@]}" config -q || fail "docker-compose.prod.yml doesn't validate (the error is above)"
    domain="$(sed -n 's/^IRIS_DOMAIN=//p' .env | tail -n 1 | tr -d "\"' ")"
    [ -n "$domain" ] || fail "IRIS_DOMAIN isn't set in .env, so the site can't be checked"
    if $rebuild; then
        free_kb="$(df -Pk . | awk 'NR == 2 { print $4 }')"
        [ "$free_kb" -ge $((MIN_FREE_GB * 1024 * 1024)) ] ||
            fail "only $((free_kb / 1024 / 1024)) GB free, and a rebuild needs $MIN_FREE_GB GB. Free some with: docker builder prune"
    fi
    say "step 2/5 check: settings files present, compose file valid"

    # ---- 3. rebuild -----------------------------------------------------
    begin 3 rebuild
    if $rebuild; then
        say "step 3/5 rebuild: building and restarting; this takes a few minutes"
        if ! "${COMPOSE[@]}" up -d --build; then
            # up fails when migrate does, since the other services wait for it.
            local listing reason
            listing="$(containers)" || exit 1
            reason="$(not_ready_reason migrate "$(awk -F'|' '$1 == "migrate"' <<< "$listing")")"
            [ -n "$reason" ] && migrate_failed "didn't finish ($reason)"
            fail "docker compose up failed (the error is above)"
        fi
    else
        say "step 3/5 rebuild: skipped, nothing new"
    fi

    # ---- 4. health ------------------------------------------------------
    begin 4 health
    DEADLINE=$((SECONDS + TIMEOUT))
    local home="https://$domain/" api="https://$domain/api/v1/colleges/" restarted=false
    wait_until_ready
    if $rebuild; then
        # nginx looks up the backend's address once, when it starts (IR-200).
        "${COMPOSE[@]}" restart frontend || fail "couldn't restart frontend"
        restarted=true
        wait_until_ready
    fi
    if ! site_answers "$home"; then
        show_logs caddy frontend
        fail "$home didn't answer. Check the domain's DNS points at this server, and Caddy's log above for its certificate."
    fi
    if ! $restarted && ! site_answers "$api"; then
        # The page loads but the API doesn't: after a restart with nothing to
        # rebuild, that is usually nginx holding an old backend address (IR-200).
        say "step 4/5 health: the API didn't answer; restarted frontend (IR-200)"
        "${COMPOSE[@]}" restart frontend || fail "couldn't restart frontend"
        wait_until_ready
    fi
    if ! site_answers "$api"; then
        show_logs backend frontend
        fail "$api didn't answer, though the page does. The backend's log is above."
    fi
    say "step 4/5 health: every service is up, and https://$domain answers"

    # ---- 5. report ------------------------------------------------------
    begin 5 report
    echo "$NEW" > "$state"
    say "done, running $(short "$NEW") ($(git log -1 --format=%s "$NEW"))"
}

main "$@"
exit
