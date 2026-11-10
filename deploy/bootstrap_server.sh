#!/usr/bin/env bash
# Get a fresh Ubuntu 24.04 server ready for IRIS (IR-1014).
#
#   sudo deploy/bootstrap_server.sh            # by hand, on any Ubuntu 24.04 server
#   (or paste this whole file into EC2 "User data" at launch)
#
# It installs Docker from Docker's apt repository, adds the login user to the
# `docker` group, creates a swap file that survives reboots, clones IRIS's
# `main` into the user's home, and, when /etc/iris/duckdns exists, keeps the
# DuckDNS name pointed at this server on every boot.
#
# It never starts IRIS and never writes a .env file: secrets and vendor keys
# stay a separate, deliberate step (deploy/README.md). Safe to run again: a
# step that is already done is left alone and reported as "already done".
#
# Settings, all optional, none secret:
#   IRIS_USER       the login user           (default: the sudo caller, else ubuntu)
#   IRIS_DIR        where to clone main      (default: <user's home>/IRIS)
#   IRIS_SWAP_SIZE  the swap file's size     (default: 4G; a number then M or G)
#
# The DuckDNS token is read only from /etc/iris/duckdns, which must be owned by
# root and readable by root only:
#   DUCKDNS_DOMAIN=iris-citu        (the subdomain, without .duckdns.org)
#   DUCKDNS_TOKEN=<your token>

set -euo pipefail

IRIS_REPO=https://github.com/moisturicer/IRIS.git
IRIS_BRANCH=main
SWAPFILE=/swapfile
SWAP_LINE="$SWAPFILE none swap sw 0 0"
DUCKDNS_FILE=/etc/iris/duckdns
DUCKDNS_UPDATER=/usr/local/sbin/iris-duckdns-update
DUCKDNS_UNIT=/etc/systemd/system/iris-duckdns.service
# Docker's release signing key (docs.docker.com/engine/install/ubuntu).
DOCKER_KEY_FINGERPRINT=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
# At first boot unattended-upgrades can hold apt's lock for several minutes.
APT=(apt-get -o DPkg::Lock::Timeout=900 -y -q)

say()  { echo "IRIS bootstrap: $*"; }
fail() { echo "IRIS bootstrap: error: $*" >&2; exit 1; }
# Whole-line match against a string, not a pipe: grep -q can exit before the
# writer finishes, and pipefail then reports the match as a failure.
has_line() { grep -qx -- "$1" <<< "$2"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- Checks before anything changes ------------------------------------------

[ "$(id -u)" -eq 0 ] || fail "run it with sudo (it installs packages and edits /etc/fstab)"

# shellcheck disable=SC1091
. /etc/os-release
[ "${ID:-}" = ubuntu ] || fail "this is for Ubuntu; found ${PRETTY_NAME:-an unknown system}"
[ "${VERSION_ID:-}" = 24.04 ] || say "warning: written for Ubuntu 24.04; this is ${PRETTY_NAME}"

if [ -n "${IRIS_USER:-}" ]; then
    :
elif [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    IRIS_USER="$SUDO_USER"
else
    IRIS_USER=ubuntu
fi
getent passwd "$IRIS_USER" > /dev/null || fail "no user named $IRIS_USER (set IRIS_USER)"
USER_HOME="$(getent passwd "$IRIS_USER" | cut -d: -f6)"
IRIS_DIR="${IRIS_DIR:-$USER_HOME/IRIS}"
IRIS_SWAP_SIZE="${IRIS_SWAP_SIZE:-4G}"
[[ "$IRIS_SWAP_SIZE" =~ ^[1-9][0-9]*[MG]$ ]] || fail "IRIS_SWAP_SIZE must be a number then M or G, for example 4G"

if [ -e "$IRIS_DIR" ] && [ ! -d "$IRIS_DIR/.git" ]; then
    fail "$IRIS_DIR exists and is not a git clone; move it or set IRIS_DIR"
fi

duckdns_value() {
    # Read KEY=value without running the file as a script.
    sed -n "s/^$1=//p" "$DUCKDNS_FILE" | tail -n 1 | tr -d '\r'
}

if [ -e "$DUCKDNS_FILE" ]; then
    [ "$(stat -c '%U %a' "$DUCKDNS_FILE")" = "root 600" ] \
        || fail "$DUCKDNS_FILE must be owned by root and readable by root only: sudo chown root:root $DUCKDNS_FILE && sudo chmod 600 $DUCKDNS_FILE"
    DUCKDNS_DOMAIN="$(duckdns_value DUCKDNS_DOMAIN)"
    [[ "$DUCKDNS_DOMAIN" =~ ^[a-z0-9-]+$ ]] \
        || fail "DUCKDNS_DOMAIN in $DUCKDNS_FILE must be the subdomain only, for example iris-citu"
    [ -n "$(duckdns_value DUCKDNS_TOKEN)" ] || fail "DUCKDNS_TOKEN is missing from $DUCKDNS_FILE"
fi

export DEBIAN_FRONTEND=noninteractive

# --- Docker -------------------------------------------------------------------

if command -v docker > /dev/null && docker compose version > /dev/null 2>&1; then
    if systemctl is-enabled --quiet docker && systemctl is-active --quiet docker; then
        say "docker: already done"
    else
        systemctl enable --now docker
        say "docker: started (it was installed but not running or not started at boot)"
    fi
else
    say "docker: installing from Docker's apt repository"
    "${APT[@]}" update
    "${APT[@]}" install ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    key="$WORK/docker.asc"
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$key"
    found="$(gpg --show-keys --with-colons "$key" | awk -F: '$1 == "fpr" { print $10; exit }')"
    [ "$found" = "$DOCKER_KEY_FINGERPRINT" ] \
        || fail "Docker's signing key has an unexpected fingerprint ($found); not installing"
    install -m 0644 "$key" /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    "${APT[@]}" update
    "${APT[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    say "docker: installed"
fi

# --- The docker group -----------------------------------------------------------

if has_line docker "$(id -nG "$IRIS_USER" | tr ' ' '\n')"; then
    say "docker-group: already done"
else
    usermod -aG docker "$IRIS_USER"
    say "docker-group: added (takes effect at $IRIS_USER's next login)"
fi

# --- Swap -----------------------------------------------------------------------

make_swapfile() {
    rm -f "$SWAPFILE"
    fallocate -l "$IRIS_SWAP_SIZE" "$SWAPFILE" \
        || dd if=/dev/zero of="$SWAPFILE" bs=1M count="$(numfmt --from=iec "$IRIS_SWAP_SIZE" | awk '{ print int($1 / 1048576) }')" status=none
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE" > /dev/null
}
swap_changed=no
if ! has_line "$SWAPFILE" "$(swapon --show=NAME --noheadings)"; then
    # A run stopped between fallocate and mkswap leaves a file swapon refuses:
    # make it again rather than fail on every later run.
    if [ ! -e "$SWAPFILE" ] || ! swapon "$SWAPFILE" 2> /dev/null; then
        make_swapfile
        swapon "$SWAPFILE"
    fi
    swap_changed=yes
fi
# Any /swapfile entry counts, whatever its options, so none is added twice.
if ! awk -v f="$SWAPFILE" '$1 == f { found = 1 } END { exit !found }' /etc/fstab; then
    echo "$SWAP_LINE" >> /etc/fstab
    swap_changed=yes
fi
if [ "$swap_changed" = yes ]; then
    say "swap: created ($IRIS_SWAP_SIZE at $SWAPFILE, kept across reboots)"
else
    say "swap: already done"
fi

# --- The code -------------------------------------------------------------------

if [ -d "$IRIS_DIR/.git" ]; then
    say "clone: already done ($IRIS_DIR; not updated, see deploy/README.md)"
else
    if ! command -v git > /dev/null; then
        "${APT[@]}" update
        "${APT[@]}" install git
    fi
    sudo -u "$IRIS_USER" git clone --quiet --branch "$IRIS_BRANCH" "$IRIS_REPO" "$IRIS_DIR"
    say "clone: cloned ($IRIS_BRANCH of $IRIS_REPO into $IRIS_DIR)"
fi

# --- DuckDNS --------------------------------------------------------------------

if [ ! -e "$DUCKDNS_FILE" ]; then
    say "duckdns: skipped (no $DUCKDNS_FILE; see deploy/README.md to set it up, then run this again)"
else
    updater="$WORK/updater"
    cat > "$updater" <<'UPDATER'
#!/usr/bin/env bash
# Point the DuckDNS name in /etc/iris/duckdns at this server (IR-1014).
# Installed by deploy/bootstrap_server.sh; runs on every boot.
set -euo pipefail
value() { sed -n "s/^$1=//p" /etc/iris/duckdns | tail -n 1 | tr -d '\r'; }
domain="$(value DUCKDNS_DOMAIN)"
token="$(value DUCKDNS_TOKEN)"
# The URL goes through stdin, so the token never appears in the process list.
# An empty ip= makes DuckDNS use the address this request comes from.
answer="$(printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' "$domain" "$token" \
    | curl -fsS --max-time 30 --retry 5 --retry-connrefused --config -)"
if [ "$answer" != OK ]; then
    echo "DuckDNS refused the update for $domain (answered ${answer:-nothing}); check the token in /etc/iris/duckdns" >&2
    exit 1
fi
echo "DuckDNS: $domain.duckdns.org now points at this server"
UPDATER
    unit="$WORK/unit"
    cat > "$unit" <<UNIT
[Unit]
Description=Point the IRIS DuckDNS name at this server (IR-1014)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$DUCKDNS_UPDATER

[Install]
WantedBy=multi-user.target
UNIT
    duckdns_changed=no
    if ! cmp -s "$updater" "$DUCKDNS_UPDATER"; then
        install -m 0700 -o root -g root "$updater" "$DUCKDNS_UPDATER"
        duckdns_changed=yes
    fi
    if ! cmp -s "$unit" "$DUCKDNS_UNIT"; then
        install -m 0644 "$unit" "$DUCKDNS_UNIT"
        systemctl daemon-reload
        duckdns_changed=yes
    fi
    if ! systemctl is-enabled --quiet iris-duckdns.service; then
        systemctl enable --quiet iris-duckdns.service
        duckdns_changed=yes
    fi
    # Update now as well as at every boot. A refused update fails the run, so a
    # wrong token is seen here rather than after the next reboot.
    systemctl start iris-duckdns.service \
        || fail "duckdns: the update failed; see: journalctl -u iris-duckdns.service"
    if [ "$duckdns_changed" = yes ]; then
        say "duckdns: installed ($DUCKDNS_DOMAIN.duckdns.org updated now and on every boot)"
    else
        say "duckdns: already done (address sent again, as at every boot)"
    fi
fi

say "finished. IRIS is not started and no .env file was written; next steps are in $IRIS_DIR/deploy/README.md"
