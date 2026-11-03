"""
The AI services are not handed Django's database login (IR-826, ADR-014 precondition 4).

Nothing under `ai/` reads `DATABASE_URL`; the DSN only carried the application
credential into a process that can reach the internet. AI-owned runs use their
own `RUNS_DATABASE_URL` login from `ai/.env`, which ADR-014's 2026-11-03
amendment proposes allowing.

No database and no Django settings -- it reads files.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

AI_SERVICES = [
    ("docker-compose.yml", "ai-gateway"),
    ("docker-compose.prod.yml", "ai-gateway"),
    ("docker-compose.yml", "ai-runs-worker"),
]


def _service_block(compose_file, service):
    text = (REPO_ROOT / compose_file).read_text(encoding="utf-8")
    match = re.search(rf"^  {service}:\n((?:(?:    .*|\s*)\n)*)", text, re.MULTILINE)
    assert match, f"no {service} service in {compose_file}"
    return match.group(1)


@pytest.mark.parametrize(("compose_file", "service"), AI_SERVICES)
def test_ai_service_gets_no_django_database_login(compose_file, service):
    active = "\n".join(
        line for line in _service_block(compose_file, service).splitlines() if not line.strip().startswith("#")
    )
    assert re.search(r"\bDATABASE_URL\b", active) is None
    assert re.search(r"\bDB_(USER|PASSWORD|NAME)\b", active) is None


@pytest.mark.parametrize("compose_file", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_gateway_comment_names_this_ticket_not_the_missing_one(compose_file):
    block = _service_block(compose_file, "ai-gateway")
    assert "IR-826" in block
    assert re.search(r"\bIR-58\b", block) is None
