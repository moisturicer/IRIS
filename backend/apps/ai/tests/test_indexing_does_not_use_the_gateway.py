"""ADR-024's deployment promise, asserted rather than trusted (IR-281).

The gateway call this replaces posted to `/api/v1/ai/internal/embed/`, a
route the gateway never registered, at an endpoint whose response carries no
vector field — three independent breakages that went unnoticed for months
precisely because nothing on this path had ever produced a vector.

Keeping it out is therefore a test, not a comment: a Celery worker must not
need a second container alive to index, and the way that regresses is one
`import httpx` and one settings read in a task nobody looks at again.

No database and no Django settings — it reads files.
"""

import pathlib

APPS_AI = pathlib.Path(__file__).resolve().parents[1]


def test_no_module_under_apps_ai_reads_the_gateway_url():
    offenders = [
        path.relative_to(APPS_AI).as_posix()
        for path in APPS_AI.rglob("*.py")
        if path.name != pathlib.Path(__file__).name
        and "AI_GATEWAY_URL" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"the indexing path reads the gateway URL in {offenders}"
