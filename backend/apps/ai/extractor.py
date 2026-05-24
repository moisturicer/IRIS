"""
apps/ai/extractor.py
--------------------
PDF text extraction and cleaning utilities using PyMuPDF (fitz).

Usage (called by Celery tasks or directly):
    from apps.ai.extractor import extract_text_from_pdf

    text = extract_text_from_pdf("/path/to/file.pdf")
"""

import re
import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: str) -> str:
    """
    Open a PDF file, extract raw text from every page, then clean and return it.

    Args:
        file_path: Absolute path to the PDF file on disk.

    Returns:
        A single cleaned string containing all readable text in the document.

    Raises:
        FileNotFoundError: If the path does not point to an existing file.
        fitz.FileDataError: If the file is not a valid or readable PDF.
    """
    raw_pages = _extract_raw_pages(file_path)
    cleaned   = _clean_text(raw_pages)
    return cleaned


# ---------------------------------------------------------------------------
# Step 1 — Raw extraction
# ---------------------------------------------------------------------------

def _extract_raw_pages(file_path: str) -> list[str]:
    """
    Open the PDF with PyMuPDF and return a list of raw text strings,
    one entry per page.
    """
    pages: list[str] = []

    with fitz.open(file_path) as pdf:
        for page in pdf:
            # "text" layout mode preserves reading order across columns
            text = page.get_text("text")
            pages.append(text)

    return pages


# ---------------------------------------------------------------------------
# Step 2 — Cleaning pipeline
# ---------------------------------------------------------------------------

def _clean_text(pages: list[str]) -> str:
    """
    Apply the full cleaning pipeline to a list of per-page strings and
    return one unified, cleaned string.

    Pipeline:
        1. Remove likely headers / footers from each page
        2. Join pages with a blank line separator
        3. Strip special / non-printable characters
        4. Normalise whitespace
    """
    cleaned_pages = [_remove_headers_footers(page) for page in pages]
    combined      = "\n\n".join(cleaned_pages)
    combined      = _remove_special_characters(combined)
    combined      = _normalise_whitespace(combined)
    return combined


def _remove_headers_footers(page_text: str) -> str:
    """
    Remove likely header and footer lines from a single page's text.

    Heuristics used:
    - First 1–2 lines of a page are often a running header.
    - Last 1–2 lines of a page are often a running footer (e.g. page numbers).
    - Lines that consist solely of a number (page numbers) are removed.
    - Lines that match common academic header/footer patterns are removed.
    """
    lines = page_text.splitlines()

    if not lines:
        return page_text

    # Drop leading and trailing lines that look like headers/footers
    HEADER_LINES_TO_STRIP = 2
    FOOTER_LINES_TO_STRIP = 2

    if len(lines) > HEADER_LINES_TO_STRIP + FOOTER_LINES_TO_STRIP:
        lines = lines[HEADER_LINES_TO_STRIP:-FOOTER_LINES_TO_STRIP]

    # Remove standalone page-number lines and lines that are only dashes/dots
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _is_header_footer_line(stripped):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


# Patterns that strongly suggest a header or footer line
_HEADER_FOOTER_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d+$"),                           # bare page number
    re.compile(r"^page\s+\d+\s*(of\s+\d+)?$", re.IGNORECASE),  # "Page 1 of 10"
    re.compile(r"^[-–—=_.]{3,}$"),                  # separator lines
    re.compile(r"^\s*$"),                            # blank / whitespace-only
    re.compile(r"^(cebu institute|cit-u|iris)", re.IGNORECASE),  # institution watermarks
]


def _is_header_footer_line(line: str) -> bool:
    """Return True if the line matches any known header/footer pattern."""
    return any(pattern.match(line) for pattern in _HEADER_FOOTER_PATTERNS)


def _remove_special_characters(text: str) -> str:
    """
    Remove non-printable control characters and uncommon Unicode symbols
    while keeping standard punctuation and accented letters.

    Keeps:
        - Printable ASCII (0x20–0x7E)
        - Extended Latin letters (accents, ñ, etc.)
        - Common whitespace (space, newline, tab)
    """
    # Remove null bytes and other control characters (except \n and \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Remove non-breaking spaces and other exotic whitespace → regular space
    text = re.sub(r"[\xa0\u2000-\u200f\u2028\u2029\u202f\u205f\u3000]", " ", text)

    # Remove soft hyphens used for line-break hints
    text = text.replace("\u00ad", "")

    # Remove Unicode replacement character
    text = text.replace("\ufffd", "")

    return text


def _normalise_whitespace(text: str) -> str:
    """
    Collapse runs of blank lines to a single blank line,
    and trim leading/trailing whitespace from every line.
    """
    # Strip trailing spaces from each line
    lines = [line.rstrip() for line in text.splitlines()]

    # Collapse 3+ consecutive blank lines into 2
    result: list[str] = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)

    return "\n".join(result).strip()
