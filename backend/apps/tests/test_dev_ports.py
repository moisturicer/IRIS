"""
The development stack is reachable only from the developer's own machine (IR-669, IR-828).

No database and no Django settings -- it reads files.
"""

import re
from pathlib import Path

COMPOSE = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text(encoding="utf-8")


def test_every_published_port_binds_to_localhost():
    active = "\n".join(line for line in COMPOSE.splitlines() if not line.strip().startswith("#"))
    published = [
        entry
        for block in re.findall(r"^    ports:\n((?:      - .*\n)+)", active, re.MULTILINE)
        for entry in re.findall(r'- "?([^"\n]+)"?', block)
    ]
    assert len(published) == 4, published
    assert [entry for entry in published if not entry.startswith("127.0.0.1:")] == []
