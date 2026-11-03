"""
Production containers reach the internet only if they need to (IR-825).

`private` is an internal Compose network, so it has no route out. Only services
that call a vendor, send mail or get certificates also join `egress`. CI's Docker
Compose job checks the real networks.

No database and no Django settings -- it reads files.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

EXPECTED = {
    "db": ["private"],
    "redis": ["private"],
    "migrate": ["private"],
    "docling": ["private"],
    "frontend": ["private"],
    "celery-beat": ["private"],
    "backend": ["private", "egress"],
    "ai-gateway": ["private", "egress"],
    "celery-default": ["private", "egress"],
    "celery-extraction": ["private", "egress"],
    "celery-embedding": ["private", "egress"],
    "celery-shadow": ["private", "egress"],
    "caddy": ["private", "egress"],
}


def _networks_by_service():
    services = PROD.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    found = {}
    for name, body in re.findall(r"^  ([a-z][a-z0-9-]*):\n((?:(?:    .*|\s*)\n)*)", services, re.MULTILINE):
        block = re.search(r"^    networks:\n((?:      - .*\n)+)", body, re.MULTILINE)
        found[name] = re.findall(r"- (\S+)", block.group(1)) if block else []
    return found


def test_each_service_joins_only_the_networks_it_needs():
    assert _networks_by_service() == EXPECTED


def test_the_private_network_has_no_route_out():
    assert re.search(r"^networks:\n  private:\n    internal: true\n", PROD, re.MULTILINE)
