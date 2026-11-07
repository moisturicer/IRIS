"""Review text never reaches the AI (IR-871, ADR-058 §1 as amended, point 3).

It is never chunked, embedded or retrieved, the AI never reads it, and review
never reads the Extraction. Static checks over the source, so a later change
that wires one into the other fails here, by name.
"""
from pathlib import Path

from django.conf import settings

BACKEND = Path(settings.BASE_DIR)
REPO = BACKEND.parent
TABLES = ("records_reviewtext", "records_reviewtextsection")
NAMES = ("ReviewText", "review_text", "reviewtext", *TABLES)


def _sources(root):
    return [
        p for p in root.rglob("*")
        if p.suffix in (".py", ".sql") and p.is_file()
        and "test" not in p.name and "tests" not in p.parts and "__pycache__" not in p.parts
    ]


def _offenders(roots, names):
    found = []
    for root in roots:
        for path in _sources(root):
            text = path.read_text(encoding="utf-8", errors="ignore")
            found += [f"{path.relative_to(REPO)}: {n}" for n in names if n in text]
    return found


def test_no_ai_module_or_ai_runtime_mentions_review_text():
    # Django's AI app, the AI runtime and gateway, and the roles they read under.
    assert _offenders([BACKEND / "apps" / "ai", REPO / "ai"], NAMES) == []


def test_the_review_text_package_never_reads_the_extraction_or_asks_the_gate():
    package = BACKEND / "apps" / "records" / "review_text"
    assert _offenders([package], (
        # Code names, not words, so a docstring may still say what it isn't.
        "PdfExtraction", "ChunkSet", "awaits_disclosure", "extraction.gate", "apps.ai",
        "llamaparse_client", "EmbeddingProvider", "embed_", "import httpx", "import openai",
    )) == []


def test_the_reader_is_run_only_by_the_sandbox():
    # Nothing in production imports the reader into a web or worker process.
    users = [
        str(p.relative_to(BACKEND)) for p in _sources(BACKEND / "apps")
        if "review_text.reader" in p.read_text(encoding="utf-8", errors="ignore")
        or "from . import reader" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert set(users) <= {str(Path("apps/records/review_text/testing.py"))}
