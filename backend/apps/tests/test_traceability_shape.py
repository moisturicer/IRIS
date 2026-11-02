"""
TRACEABILITY.md stays a matrix, and notes stay in their own files (IR-276, ADR-055).

No database and no Django settings -- it reads files.
"""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[3] / "docs" / "testing"
MATRIX = DOCS / "TRACEABILITY.md"
#: The longest intended line is a paragraph of prose above the table.
MAX_LINE = 1200
#: A row is an id, a short title, a link and a short status.
MAX_ROW = 400


def _matrix_lines():
    return MATRIX.read_text(encoding="utf-8").splitlines()


def _matrix_rows():
    return [line for line in _matrix_lines() if "](traceability/" in line and line.startswith("| ")]


def test_ticket_notes_do_not_return_to_the_matrix():
    headings = [line for line in _matrix_lines() if re.match(r"## IR-\d+", line)]
    assert headings == [], "add docs/testing/traceability/IR-XXX.md instead"


def test_no_line_grows_past_what_git_can_merge():
    long_lines = [line[:60] for line in _matrix_lines() if len(line) > MAX_LINE]
    assert long_lines == []


def test_rows_stay_short():
    long_rows = [row[:60] for row in _matrix_rows() if len(row) > MAX_ROW]
    assert long_rows == []


def test_every_row_links_to_a_file_that_exists():
    rows = _matrix_rows()
    assert rows, "the matrix has no rows, so this test checked nothing"
    missing = [
        target
        for row in rows
        for target in re.findall(r"\]\(traceability/([^)]+)\)", row)
        if not (DOCS / "traceability" / target).is_file()
    ]
    assert missing == []
