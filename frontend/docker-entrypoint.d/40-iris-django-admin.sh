#!/bin/sh
# Writes the /django-admin/ allowlist nginx.conf includes (IR-668).
#
# DJANGO_ADMIN_ALLOWED_NETWORKS  addresses or CIDRs, separated by spaces or commas.
#                                Unset or empty allows nobody.
# TRUSTED_PROXY_COUNT            the backend's value (IR-656): proxies in front of
#                                Django, nginx included. Required with an allowlist.
#
# nginx is the last of those proxies, so it hears from count-1 proxies and the
# client is the entry they appended first: position count-1 from the right of
# the header it received. Anything further left was sent by the client. A header
# too short to hold that entry falls back to the peer, as client_address.py does.
#
# A bad value stops the container: a mistyped allowlist must not look like a
# working one.
set -eu

out=/tmp/iris-django-admin.conf
networks=$(printf '%s' "${DJANGO_ADMIN_ALLOWED_NETWORKS:-}" | tr ',' ' ')

refuse() {
    echo "iris: $1" >&2
    exit 1
}

entries=
for network in $networks; do
    case "$network" in
        *[!0-9A-Fa-f:./]*) refuse "DJANGO_ADMIN_ALLOWED_NETWORKS: '$network' is not an address or CIDR" ;;
        */0) refuse "DJANGO_ADMIN_ALLOWED_NETWORKS: '$network' allows every address" ;;
    esac
    entries="$entries    $network 1;
"
done

client_map='map "" $django_admin_client { default $remote_addr; }'
if [ -n "$entries" ]; then
    count=${TRUSTED_PROXY_COUNT:-}
    case "$count" in
        '' | *[!0-9]*) refuse "TRUSTED_PROXY_COUNT must be a number when DJANGO_ADMIN_ALLOWED_NETWORKS is set" ;;
    esac
    [ "$count" -ge 1 ] || refuse "TRUSTED_PROXY_COUNT must be at least 1: production always runs behind nginx"
    if [ "$count" -ge 2 ]; then
        client_map="map \$http_x_forwarded_for \$django_admin_client {
    default \$remote_addr;
    \"~(?:^|,)\\s*([^,\\s]+)\\s*(?:,[^,]*){$((count - 2))}\$\" \$1;
}"
    fi
fi

{
    printf '%s\n' "$client_map"
    printf 'geo $django_admin_client $django_admin_allowed {\n    default 0;\n%s}\n' "$entries"
} > "$out"
