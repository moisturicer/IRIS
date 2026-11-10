#!/usr/bin/env bash
# IR-1014: runs deploy/bootstrap_server.sh for real, twice, and checks what it
# left behind. Meant for a throwaway Ubuntu 24.04 machine (CI's runner): it
# creates /swapfile, edits /etc/fstab and clones into the user's home.
#
#   sudo deploy/tests/bootstrap_checks.sh
#
# Docker is already installed on CI's runner, so the fresh-install path is
# proven by the manual run on a new EC2 instance (docs/testing/traceability/IR-1014.md).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../bootstrap_server.sh"
USER_NAME="${SUDO_USER:?run this with sudo, as the user the bootstrap is for}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CLONE="$HOME_DIR/IRIS"
LOGS="$(mktemp -d)"
failures=0

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

swap_on()        { swapon --show=NAME --noheadings | grep -qx /swapfile; }
fstab_once()     { [ "$(grep -c '^/swapfile none swap sw 0 0$' /etc/fstab)" = 1 ]; }
in_docker_group() { id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx docker; }
cloned()         { [ -d "$CLONE/.git" ] && [ "$(stat -c %U "$CLONE")" = "$USER_NAME" ]; }
on_main()        { [ "$(git -C "$CLONE" rev-parse --abbrev-ref HEAD)" = main ]; }
no_env_files()   { [ ! -e "$CLONE/.env" ] && [ ! -e "$CLONE/backend/.env" ] && [ ! -e "$CLONE/ai/.env" ]; }
iris_not_running() { [ -z "$(docker ps -q --filter label=com.docker.compose.project=iris)" ]; }
said()           { grep -q "$2" "$LOGS/$1"; }
nothing_changed() { ! grep -E ': (installed|created|added|cloned)( |$)' "$LOGS/run2.log"; }

# Refuses before changing anything.
# The log is root's to write; only the script runs as the user.
# shellcheck disable=SC2024
sudo -u "$USER_NAME" "$SCRIPT" > "$LOGS/notroot.log" 2>&1
check "refuses to run without root" [ $? -ne 0 ]
check "says to use sudo" said notroot.log "run it with sudo"

# A DuckDNS file anyone can read is refused, and nothing is changed first.
install -d -m 700 /etc/iris
printf 'DUCKDNS_DOMAIN=example\nDUCKDNS_TOKEN=not-a-real-token\n' > /etc/iris/duckdns
chmod 644 /etc/iris/duckdns
"$SCRIPT" > "$LOGS/openfile.log" 2>&1
check "refuses a DuckDNS file others can read" [ $? -ne 0 ]
check "says why" said openfile.log "readable by root only"
check "changed nothing before refusing" [ ! -e /swapfile ]
rm -f /etc/iris/duckdns

# First run: does everything.
"$SCRIPT" > "$LOGS/run1.log" 2>&1
check "first run succeeds" [ $? -eq 0 ]
check "swap is on" swap_on
check "swap is kept across reboots, listed once" fstab_once
check "the user is in the docker group" in_docker_group
check "main is cloned into the user's home, owned by them" cloned
check "the clone is on main" on_main
check "DuckDNS is skipped without its file" said run1.log "duckdns: skipped"
check "no .env file is written" no_env_files
check "IRIS is not started" iris_not_running
fstab_before="$(sha256sum /etc/fstab)"

# Second run: changes nothing and says so.
"$SCRIPT" > "$LOGS/run2.log" 2>&1
check "second run succeeds" [ $? -eq 0 ]
check "second run reports nothing new" nothing_changed
for step in docker docker-group swap clone; do
    check "second run says $step is already done" said run2.log "$step: already done"
done
check "fstab is unchanged" [ "$fstab_before" = "$(sha256sum /etc/fstab)" ]
check "still one swap line" fstab_once

if [ "$failures" -ne 0 ]; then
    echo "$failures check(s) failed. Bootstrap output:"
    for log in "$LOGS"/*.log; do echo "--- $(basename "$log")"; cat "$log"; done
    exit 1
fi
echo "all checks passed"
