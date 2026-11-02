# ADR-056: Caddy terminates TLS in production

## Status

**Accepted** — 2026-11-02 by Ashlee Sean, who chose this option for [IR-847](https://citiris.atlassian.net/browse/IR-847). Drafted by an AI agent.

Amends [ADR-010](010-deployment-topology.md): production gains a `caddy` service.

## Context

ADR-010 requires HTTPS and names no tool. `docker-compose.prod.yml` published nginx on plain port 80 on every interface. nginx passes on a client's `X-Forwarded-Proto: https` and Django trusts it (IR-662), so anyone reaching port 80 directly could claim HTTPS.

## Decision

- A `caddy` container publishes ports 80 and 443 in production, and is the only way in from outside.
- nginx is no longer published, so a client can't go around Caddy to forge the scheme.
- Caddy gets and renews certificates itself for `IRIS_DOMAIN`, using ACME. They persist in the `caddy_data` volume.
- Only TLS 1.2 and 1.3 are enabled, with Caddy's default ciphers. Plain HTTP redirects to HTTPS.
- Caddy discards any client-sent `X-Forwarded-For` and `X-Forwarded-Proto`. With nginx behind it, `TRUSTED_PROXY_COUNT` is 2.
- HTTP/3 is off, because UDP 443 isn't published.

Traffic between containers stays unencrypted, on Compose's private network.

## Consequences

**Gains:**

- The configuration lives in the repository, moves with the stack to CIT-U hardware, and CI tests it.
- No certificate renewal job to maintain.

**Costs:**

- One more service to run and keep updated.
- Automatic certificates need a public domain, with ports 80 and 443 reachable. A private CIT-U network would need a different certificate source.
- `production.py` sends HSTS for a year with `includeSubDomains` and `preload`. Over real HTTPS, browsers remember that and it covers subdomains, so a person must confirm those values for the chosen domain before the first deployment.

**Rejected:**

- **TLS in the existing nginx:** certbot and its renewal would need adding, and we'd maintain the protocol settings ourselves.
- **A proxy outside this repository:** it depends on hosting that isn't decided, and can't be tested here.
- **Cloudflare Tunnel:** Cloudflare would decrypt unpublished research and IP disclosures.
