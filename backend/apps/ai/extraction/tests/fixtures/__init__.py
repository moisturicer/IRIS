"""Synthetic PDFs for the Extractor contract suite (IR-838).

Written for the purpose from ``layouts.py``; no third-party paper is in the
repo. Regenerate with ``python -m apps.ai.extraction.tests.fixtures.build``.
"""

from pathlib import Path

from .layouts import FIXTURES, Fixture, blank_pdf, expected_document, render

DIRECTORY = Path(__file__).parent


def pdf_bytes(fixture: Fixture) -> bytes:
    return (DIRECTORY / fixture.filename).read_bytes()


__all__ = ["FIXTURES", "Fixture", "blank_pdf", "expected_document", "pdf_bytes", "render"]
