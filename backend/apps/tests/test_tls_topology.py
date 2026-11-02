"""
Only Caddy is reachable from outside in production (IR-847, ADR-056).

nginx passes on a client's X-Forwarded-Proto and Django trusts it, so publishing
nginx would let anyone claim HTTPS. CI's Docker Compose job runs the real Caddy.

No database and no Django settings -- it reads files.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
CADDYFILE = (REPO_ROOT / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8")


def _service(name):
    match = re.search(rf"^  {name}:\n((?:(?:    .*|\s*)\n)*)", PROD, re.MULTILINE)
    assert match, f"no {name} service in docker-compose.prod.yml"
    return match.group(1)


def _active(block):
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_only_caddy_publishes_a_port():
    services = re.findall(r"^  ([a-z][a-z0-9-]*):\n", PROD.split("\nvolumes:")[0], re.MULTILINE)
    publishing = [name for name in services if re.search(r"^    ports:", _active(_service(name)), re.MULTILINE)]
    assert publishing == ["caddy"]


def test_caddy_publishes_web_ports_only():
    assert re.findall(r'- "(\d+:\d+)"', _active(_service("caddy"))) == ["80:80", "443:443"]


def test_caddyfile_allows_only_tls_12_and_13():
    assert re.search(r"^\s*protocols tls1\.2 tls1\.3$", CADDYFILE, re.MULTILINE)


def test_caddy_does_not_trust_forwarded_headers_from_clients():
    assert "trusted_proxies" not in CADDYFILE.replace("no trusted_proxies set", "")
