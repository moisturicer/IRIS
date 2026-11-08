"""The current review text reader's name, for the web and worker processes
(IR-873, ADR-058 §3 as amended 2026-11-08).

The reader parses untrusted PDFs, so it runs only in the sandbox and is never
imported here (`test_review_text_isolation.py`); it is run as a script, so it
can't import this module either. Its name is therefore built twice, here and in
`reader.reader_version`, and `test_review_text_readings.py` fails the day they
differ. **Raise `RULES_VERSION` here and in `reader.py` together.**
"""
from importlib.metadata import version

#: Must equal `reader.RULES_VERSION`.
RULES_VERSION = 2


def reader_version() -> str:
    """The name `reader.read` stamps on a reading, without loading the parser."""
    return f"review-reader-{RULES_VERSION}/pdfplumber-{version('pdfplumber')}"
